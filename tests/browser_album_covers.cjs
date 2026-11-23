// Run against open_fixture in tests/android_fixture.py with beach_photos=9 and a fresh invitation.
// Requires unzip to check the downloaded album.
// Requires Playwright with Chromium installed. Optional CHROMIUM_EXECUTABLE selects a local binary.
const assert = require("node:assert/strict");
const { execFileSync } = require("node:child_process");
const { chromium } = require("playwright");

async function main() {
  const { FIXTURE_URL, FIXTURE_CODE, CHROMIUM_EXECUTABLE } = process.env;
  assert.match(FIXTURE_URL, /^https:\/\/127\.0\.0\.1:\d+$/);
  assert.ok(FIXTURE_CODE);
  const browser = await chromium.launch({ executablePath: CHROMIUM_EXECUTABLE });
  try {
    const page = await browser.newPage({
      ignoreHTTPSErrors: true,
      viewport: { width: 390, height: 844 },
    });
    const paths = [];
    await page.route("**/*", route => {
      const url = new URL(route.request().url());
      if (url.origin !== FIXTURE_URL) return route.abort();
      paths.push(url.pathname);
      return route.continue();
    });
    await page.goto(FIXTURE_URL);
    await page.locator("#family-sign-in summary").click();
    await page.locator("#family-code").fill(FIXTURE_CODE);
    await page.locator("#family-login-form button").click();
    await page.locator("#archive-nav").click();
    await page.locator("#browse-years").click();
    await page.locator("#results .folder-card").filter({ hasText: "2024" }).waitFor();
    assert.ok(!paths.includes("/api/v1/album-cover"));
    await page.locator("#results .folder-card").filter({ hasText: "2024" }).click();
    const cover = page.locator("#results .album-cover");
    await cover.waitFor();
    assert.ok(await cover.evaluate(image => image.complete && image.naturalWidth > 0));
    for (const mode of ["light", "dark"]) {
      await page.locator("#appearance").selectOption(mode);
      await page.screenshot({ path: `/tmp/chromantis-album-cover-${mode}.png` });
    }
    assert.equal(paths.filter(path => path === "/api/v1/album-cover").length, 1);
    assert.ok(!paths.includes("/api/v1/image"));
    await page.locator("#results .folder-card").filter({ has: page.locator(".album-cover") }).click();
    await page.getByRole("button", { name: "Ver fotos del álbum" }).click();
    await page.getByRole("button", { name: "Seleccionar fotos", exact: true }).click();
    await page.getByRole("checkbox", { name: /Photo_02.jpg/ }).check();
    await page.getByRole("checkbox", { name: /Photo_04.jpg/ }).check();
    const exportButton = page.getByRole("button", { name: "Descargar selección" });
    for (const mode of ["light", "dark"]) {
      await page.locator("#appearance").selectOption(mode);
      await exportButton.scrollIntoViewIfNeeded();
      await page.screenshot({ path: `/tmp/chromantis-selection-${mode}.png` });
    }
    const [download, request] = await Promise.all([
      page.waitForEvent("download"),
      page.waitForRequest(request => request.url().endsWith("/api/v1/photo-export")),
      exportButton.click(),
    ]);
    assert.deepEqual(request.postDataJSON().paths.map(path => path.split("/").at(-1)),
      ["Photo_02.jpg", "Photo_04.jpg"]);
    assert.equal(download.suggestedFilename(), "chromantis-photos.zip");
    assert.equal(await download.failure(), null);
    const albumButton = page.getByRole("button", { name: "Descargar álbum" });
    for (const mode of ["light", "dark"]) {
      await page.locator("#appearance").selectOption(mode);
      await albumButton.scrollIntoViewIfNeeded();
      await page.screenshot({ path: `/tmp/chromantis-album-export-${mode}.png` });
    }
    const [album] = await Promise.all([page.waitForEvent("download"), albumButton.click()]);
    const names = execFileSync("unzip", ["-Z1", await album.path()], { encoding: "utf8" }).trim().split("\n");
    assert.deepEqual(names, Array.from({ length: 9 }, (_, i) => {
      const number = String(i + 1).padStart(2, "0");
      return `${number}-Photo_${number}.jpg`;
    }));
  } finally {
    await browser.close();
  }
}

main().catch(error => {
  console.error(error);
  process.exitCode = 1;
});
