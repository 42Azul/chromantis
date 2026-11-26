// Run against open_fixture in tests/android_fixture.py with a fresh invitation.
const assert = require("node:assert/strict");
const { readFileSync } = require("node:fs");
const { chromium } = require("playwright");

async function main() {
  const { FIXTURE_URL, FIXTURE_CODE, CHROMIUM_EXECUTABLE } = process.env;
  assert.match(FIXTURE_URL, /^https:\/\/127\.0\.0\.1:\d+$/);
  assert.ok(FIXTURE_CODE);
  const browser = await chromium.launch({ executablePath: CHROMIUM_EXECUTABLE });
  try {
    const page = await browser.newPage({ ignoreHTTPSErrors: true, viewport: { width: 390, height: 844 } });
    const paths = [];
    let failThumbnail = false;
    await page.route("**/*", route => {
      const url = new URL(route.request().url());
      if (url.origin !== FIXTURE_URL) return route.abort();
      paths.push(url.pathname);
      if (failThumbnail && url.pathname === "/api/v1/thumbnail" &&
          url.searchParams.get("path")?.endsWith("/Photo_04.jpg")) {
        return route.fulfill({ status: 404, json: { error: "Synthetic preview unavailable" } });
      }
      return route.continue();
    });
    await page.goto(FIXTURE_URL);
    await page.locator("#family-sign-in summary").click();
    await page.locator("#family-code").fill(FIXTURE_CODE);
    await page.locator("#family-login-form button").click();
    await page.locator("#archive-nav").click();
    await page.locator("#browse-years").click();
    await page.locator("#results .folder-card").filter({ hasText: "2024" }).click();
    await page.locator("#results .folder-card").filter({ hasText: "playa" }).click();
    await page.locator("#album-browse").getByRole("button", { name: "Ver fotos del álbum" }).click();
    await page.getByRole("button", { name: "Seleccionar fotos", exact: true }).click();
    await page.getByRole("checkbox", { name: /Photo_02.jpg/ }).check();
    await page.getByRole("checkbox", { name: /Photo_04.jpg/ }).check();
    for (const mode of ["light", "dark"]) {
      await page.locator("#appearance").selectOption(mode);
      const originalsBeforeCollage = paths.filter(path => path === "/api/v1/image").length;
      await page.getByRole("button", { name: "Crear collage" }).click();
      const dialog = page.getByRole("dialog", { name: "Crear collage" });
      const preview = dialog.getByRole("img", { name: "Vista previa del collage" });
      await preview.waitFor();
      const pixels = await preview.evaluate(canvas => [
        canvas.width, canvas.height,
        canvas.getContext("2d").getImageData(240, 240, 1, 1).data[0],
        canvas.getContext("2d").getImageData(720, 240, 1, 1).data[0],
      ]);
      assert.deepEqual(pixels.slice(0, 2), [960, 480]);
      assert.ok(pixels[2] >= 38 && pixels[2] <= 54);
      assert.ok(pixels[3] >= 84 && pixels[3] <= 100);
      assert.equal(paths.filter(path => path === "/api/v1/image").length, originalsBeforeCollage);
      await dialog.screenshot({ path: `/tmp/chromantis-web-collage-${mode}.png` });
      if (mode === "dark") {
        const [file] = await Promise.all([
          page.waitForEvent("download"),
          dialog.getByRole("button", { name: "Descargar collage" }).click(),
        ]);
        assert.equal(file.suggestedFilename(), "chromantis-collage.jpg");
        const bytes = readFileSync(await file.path());
        assert.equal(bytes.subarray(0, 3).toString("hex"), "ffd8ff");
      }
      await dialog.getByRole("button", { name: "Cerrar" }).click();
      assert.equal(await page.getByRole("checkbox", { name: /Photo_04.jpg/ }).isChecked(), true);
    }
    failThumbnail = true;
    await page.getByRole("button", { name: "Crear collage" }).click();
    const dialog = page.getByRole("dialog", { name: "Crear collage" });
    await dialog.getByText("No se pudo cargar Photo_04.jpg.").waitFor();
    assert.ok(await dialog.getByRole("button", { name: "Descargar collage" }).isDisabled());
    await page.keyboard.press("Escape");
    await dialog.waitFor({ state: "hidden" });
    assert.ok(await page.getByRole("checkbox", { name: /Photo_04.jpg/ }).isChecked());
  } finally {
    await browser.close();
  }
}

main().catch(error => { console.error(error); process.exitCode = 1; });
