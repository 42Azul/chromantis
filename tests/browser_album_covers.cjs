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
    const searchRequests = paths.length;
    await page.locator("#results .folder-card").filter({ has: page.locator(".album-cover") }).click();
    const browse = page.locator("#album-browse");
    await browse.getByRole("heading", { level: 1 }).waitFor();
    assert.ok(!paths.slice(searchRequests).some(path => path.startsWith("/api/v1/album-review")));
    assert.ok(!paths.includes("/api/v1/album-images"));
    await browse.getByRole("button", { name: "Ver fotos del álbum" }).click();
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
    for (const mode of ["light", "dark"]) {
      await page.locator("#appearance").selectOption(mode);
      await browse.getByRole("heading", { level: 1 }).scrollIntoViewIfNeeded();
      await page.screenshot({ path: `/tmp/chromantis-album-browse-${mode}.png` });
    }
    assert.equal(await browse.getByRole("button", { name: "Etiquetar fotos" }).count(), 0);
    const editorWidth = Number(process.env.EDITOR_TEST_WIDTH || 360);
    await page.setViewportSize({ width: editorWidth, height: 800 });
    await page.evaluate(() => { document.documentElement.style.fontSize = "200%"; });
    const checkWidth = () => page.evaluate(() => document.documentElement.scrollWidth <= innerWidth);
    assert.ok(await checkWidth(), "The viewer should fit with doubled text.");
    const heading = browse.getByRole("heading", { level: 1 });
    await heading.focus();
    await page.keyboard.press("Tab");
    assert.equal(await page.locator(":focus").textContent(), "Volver a resultados");
    await page.keyboard.press("Tab");
    assert.equal(await page.locator(":focus").textContent(), "Etiquetar álbum");
    await page.keyboard.press("Enter");
    await page.waitForFunction(() => document.activeElement?.placeholder === "Escribe un nombre o alias");
    await page.keyboard.type("Anita");
    await page.keyboard.press("Enter");
    await page.getByRole("button", { name: "Quitar a Ana del álbum" }).waitFor();
    assert.ok(await checkWidth(), "The editor should fit with doubled text.");
    for (const mode of ["light", "dark"]) {
      await page.locator("#appearance").selectOption(mode);
      await page.getByPlaceholder("Escribe un nombre o alias").focus();
      await page.screenshot({ path: `/tmp/chromantis-keyboard-editor-${editorWidth}-${mode}.png`, fullPage: true });
    }
    const save = page.getByRole("button", { name: "Guardar y volver a resultados" });
    for (let tabs = 0; tabs < 30 && !(await save.evaluate(button => button === document.activeElement)); tabs++) {
      await page.keyboard.press("Tab");
    }
    assert.ok(await save.evaluate(button => button === document.activeElement), "Save should be reachable by Tab.");
    await page.keyboard.press("Enter");
    await page.getByText("Álbumes de 2024", { exact: true }).waitFor();
    await page.waitForFunction(() => document.activeElement?.id === "results-title");
    assert.ok(await checkWidth(), "The year results should fit with doubled text.");
    await page.locator("#query").fill("Ana");
    await page.locator("#search-form button[type=submit]").click();
    await page.locator("#results .folder-card").filter({ hasText: "2024/2024-07-01_playa" }).waitFor();
    assert.ok(!paths.includes("/api/v1/image"), "The browsing and name-only review flow should not open originals.");
  } finally {
    await browser.close();
  }
}

main().catch(error => {
  console.error(error);
  process.exitCode = 1;
});
