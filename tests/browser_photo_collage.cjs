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
    await page.addInitScript(() => {
      window.shareMode = "unsupported";
      window.collageShares = [];
      navigator.canShare = ({ files }) => window.shareMode !== "unsupported" &&
        files.length === 1 && files[0].type === "image/jpeg";
      navigator.share = async ({ files }) => {
        if (!navigator.userActivation.isActive) throw new DOMException("Inactive", "NotAllowedError");
        if (window.shareMode === "cancel") throw new DOMException("Canceled", "AbortError");
        if (window.shareMode === "error") throw new DOMException("Unavailable", "NotAllowedError");
        window.collageShares.push([...new Uint8Array(await files[0].arrayBuffer())]);
      };
    });
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
      assert.equal(await dialog.getByRole("button", { name: "Compartir collage" }).count(), 0);
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

    failThumbnail = false;
    const taggedPaths = ["2023/2023-10-05_excursion/Photo_01.jpg", "2024/2024-07-01_playa/Photo_04.jpg"];
    const tagged = await page.evaluate(async selection => {
      const query = new URLSearchParams(selection.map(path => ["path", path]));
      const response = await fetch(`/api/v1/photo-tags?${query}`);
      if (!response.ok) return response.status;
      const { items } = await response.json();
      const saved = await fetch("/api/v1/photo-tags", {
        method: "PATCH",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({
          photos: items.map(({ path, identity }) => ({ path, identity })),
          manual_add: ["Romería", "Encuentro"],
        }),
      });
      return saved.status;
    }, taggedPaths);
    assert.equal(tagged, 200);
    await page.locator("#archive-nav").click();
    const catalog = page.locator("#album-tag-catalog");
    await catalog.locator("summary").click();
    await catalog.locator("#tag-catalog-kind").selectOption("photos");
    await catalog.getByRole("button", { name: "romeria · 2", exact: true }).click();
    const tools = page.locator("#photo-results-tools");
    await tools.getByRole("button", { name: "Seleccionar fotos", exact: true }).click();
    for (const path of taggedPaths) {
      await page.getByRole("checkbox", { name: `Seleccionar ${path}`, exact: true }).check();
    }
    await page.evaluate(() => { window.shareMode = "supported"; });
    const before = paths.length;
    for (const mode of ["light", "dark"]) {
      await page.locator("#appearance").selectOption(mode);
      await tools.getByRole("button", { name: "Crear collage" }).click();
      const preview = dialog.getByRole("img", { name: "Vista previa del collage" });
      await preview.waitFor();
      const reds = await preview.evaluate(canvas => [
        canvas.getContext("2d").getImageData(240, 240, 1, 1).data[0],
        canvas.getContext("2d").getImageData(720, 240, 1, 1).data[0],
      ]);
      assert.ok(reds[0] >= 15 && reds[0] <= 31);
      assert.ok(reds[1] >= 84 && reds[1] <= 100);
      const share = dialog.getByRole("button", { name: "Compartir collage" });
      await share.waitFor();
      await dialog.screenshot({ path: `/tmp/chromantis-search-collage-${mode}.png` });
      if (mode === "dark") {
        await page.evaluate(() => { window.shareMode = "cancel"; });
        await share.click();
        assert.equal(await dialog.locator('[role="status"]').textContent(), "");
        await page.evaluate(() => { window.shareMode = "error"; });
        await share.click();
        await dialog.getByText("No se pudo compartir el collage. Puedes descargarlo.").waitFor();
        await page.evaluate(() => { window.shareMode = "supported"; });
        await share.click();
        await page.waitForFunction(() => window.collageShares.length === 1);
        const [file] = await Promise.all([
          page.waitForEvent("download"),
          dialog.getByRole("button", { name: "Descargar collage" }).click(),
        ]);
        const downloaded = readFileSync(await file.path());
        assert.equal(downloaded.subarray(0, 3).toString("hex"), "ffd8ff");
        assert.deepEqual(Buffer.from(await page.evaluate(() => window.collageShares[0])), downloaded);
      }
      await dialog.getByRole("button", { name: "Cerrar" }).click();
      await dialog.waitFor({ state: "hidden" });
    }
    assert.ok(!paths.slice(before).includes("/api/v1/image"));
    for (const path of taggedPaths) {
      assert.ok(await page.getByRole("checkbox", { name: `Seleccionar ${path}`, exact: true }).isChecked());
    }
    await page.getByRole("button", { name: "Guardar búsqueda", exact: true }).click();
    assert.equal(await page.locator("#photo-search-shortcut").textContent(), "Búsqueda guardada");
    await catalog.locator("summary").click();
    await catalog.getByRole("button", { name: "encuentro · 2", exact: true }).click();
    await page.locator("#photo-year").fill("2024");
    await page.locator("#archive-search").click();
    await page.waitForFunction(() => document.getElementById("result-count").textContent === "1");
    assert.ok((await page.locator("#results").textContent()).includes("Photo_04.jpg"));
    await page.getByRole("button", { name: "Guardar búsqueda", exact: true }).click();
    await page.reload();
    await page.locator("#archive-nav").click();
    await catalog.locator("summary").click();
    for (const mode of ["light", "dark"]) {
      await page.locator("#appearance").selectOption(mode);
      await catalog.screenshot({ path: `/tmp/chromantis-saved-search-${mode}.png` });
    }
    await catalog.getByRole("button", { name: "Reabrir búsqueda: romeria", exact: true }).click();
    await page.waitForFunction(() => document.getElementById("result-count").textContent === "2");
    assert.equal(await page.locator("#query").inputValue(), "romeria");
    await catalog.locator("summary").click();
    await catalog.getByRole("button", { name: "Quitar acceso: romeria", exact: true }).click();
    assert.equal(await catalog.getByRole("button", { name: "Reabrir búsqueda: romeria" }).count(), 0);
    await catalog.getByRole("button", { name: "Reabrir búsqueda: encuentro · 2024", exact: true }).click();
    await page.waitForFunction(() => document.getElementById("result-count").textContent === "1");
    assert.equal(await page.locator("#photo-year").inputValue(), "2024");
    for (const mode of ["light", "dark"]) {
      await page.locator("#appearance").selectOption(mode);
      await page.locator("#archive").screenshot({ path: `/tmp/chromantis-photo-year-${mode}.png` });
    }
    await page.getByRole("button", { name: "Ver álbum de Photo_04.jpg", exact: true }).click();
    await page.getByRole("button", { name: "Volver a resultados", exact: true }).click();
    await page.waitForFunction(() => document.getElementById("result-count").textContent === "1");
    assert.equal(await page.locator("#photo-year").inputValue(), "2024");
    await page.locator("#photo-year").clear();
    await page.locator("#archive-search").click();
    await page.waitForFunction(() => document.getElementById("result-count").textContent === "2");
    await page.locator("#scope").selectOption("folders");
    await page.clock.setFixedTime(new Date(2026, 9, 5, 12));
    await page.locator("#timeline summary").click();
    await page.locator("#timeline-anniversary").click();
    await page.locator("#results-title").getByText("Tal día como hoy", { exact: true }).waitFor();
    const anniversaryAlbum = page.locator('#results [data-album-path="2023/2023-10-05_excursion"]');
    assert.match(await anniversaryAlbum.textContent(), /2023-10-05.*fecha de carpeta/);
    assert.equal(await page.locator("#result-count").textContent(), "1");
    for (const mode of ["light", "dark"]) {
      await page.locator("#appearance").selectOption(mode);
      await page.locator("#archive").screenshot({ path: `/tmp/chromantis-web-anniversary-${mode}.png` });
    }
    await anniversaryAlbum.click();
    await page.getByRole("button", { name: "Volver a resultados", exact: true }).click();
    await anniversaryAlbum.waitFor();
    await page.locator("#disconnect").click();
    await page.locator("#sign-in").waitFor();
    assert.equal(await page.evaluate(() => sessionStorage.getItem("chromantis.savedPhotoSearches")), null);
  } finally {
    await browser.close();
  }
}

main().catch(error => { console.error(error); process.exitCode = 1; });
