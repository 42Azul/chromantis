// Run against tests/android_fixture.py --index-only --split-year over loopback HTTPS.
// Requires Playwright with Chromium installed.
const assert = require("node:assert/strict");
const { chromium } = require("playwright");

async function main() {
  const { FIXTURE_URL, FIXTURE_CODE, CHROMIUM_EXECUTABLE } = process.env;
  assert.match(FIXTURE_URL, /^https:\/\/127\.0\.0\.1:\d+$/);
  assert.ok(FIXTURE_CODE);
  const browser = await chromium.launch({ executablePath: CHROMIUM_EXECUTABLE });
  try {
    const page = await browser.newPage({ ignoreHTTPSErrors: true, viewport: { width: 360, height: 800 } });
    const albumSaves = [];
    const unexpected = [];
    await page.route("**/*", route => {
      const request = route.request();
      const url = new URL(request.url());
      if (url.origin !== FIXTURE_URL || /^\/api\/v1\/(image|thumbnail|album-cover|album-images)$/.test(url.pathname)) {
        unexpected.push(url.pathname);
        return route.abort();
      }
      if (url.pathname === "/api/v1/album-review" && request.method() === "POST") {
        albumSaves.push(request.postDataJSON());
        if (albumSaves.length === 1) return route.fulfill({ status: 503, json: {} });
      }
      return route.continue();
    });
    await page.goto(FIXTURE_URL);
    await page.locator("#family-sign-in summary").click();
    await page.locator("#family-code").fill(FIXTURE_CODE);
    await page.locator("#family-login-form button").click();
    const picker = page.getByPlaceholder("Escribe un nombre o alias");
    await picker.fill("Anita");
    await picker.press("Enter");
    await page.getByRole("button", { name: "Quitar a Ana del álbum" }).waitFor();
    const save = page.getByRole("button", { name: "Guardar y siguiente" });
    await save.click();
    const error = page.locator("#album-save-status");
    await error.getByText("No se pudo guardar el álbum.", { exact: false }).waitFor();
    assert.ok(await save.isEnabled());
    assert.ok(await save.evaluate(button => button === document.activeElement));
    assert.ok(await page.getByRole("button", { name: "Quitar a Ana del álbum" }).isVisible());
    for (const mode of ["light", "dark"]) {
      await page.locator("#appearance").selectOption(mode);
      await error.scrollIntoViewIfNeeded();
      await page.screenshot({ path: `/tmp/chromantis-offline-error-${mode}.png` });
    }
    await save.click();
    await page.getByText("Álbum guardado.", { exact: true }).waitFor();
    assert.equal(albumSaves.length, 2);
    assert.deepEqual(albumSaves[0], albumSaves[1]);
    await page.locator("#archive-nav").click();
    await page.locator("#query").fill("Ana");
    await page.locator("#archive-search").click();
    await page.locator("#results .folder-card").filter({ hasText: albumSaves[1].path }).waitFor();
    await page.locator("#browse-years").click();
    const results = page.locator("#results");
    const folder = path => results.locator(".folder-card").filter({ hasText: path });
    const album = page.locator("#album-browse");
    await folder("2003").click();
    const first = "2003(1)/album_00";
    const second = "2003(2)/album_00";
    await folder(first).click();
    await album.getByText(first, { exact: true }).waitFor();
    await album.getByRole("button", { name: "Volver a resultados" }).click();
    await page.getByRole("button", { name: "Página siguiente" }).click();
    await folder(second).click();
    await album.getByText(second, { exact: true }).waitFor();
    await album.getByRole("button", { name: "Volver a resultados" }).click();
    await folder(second).waitFor();
    assert.equal(await results.locator(".folder-card").count(), 1);
    await page.getByRole("button", { name: "Página anterior" }).click();
    await folder(first).waitFor();
    assert.equal(await results.locator(".folder-card").count(), 30);
    assert.deepEqual(unexpected, []);
  } finally {
    await browser.close();
  }
}

main().catch(error => {
  console.error(error);
  process.exitCode = 1;
});
