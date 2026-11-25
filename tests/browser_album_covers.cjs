// Run against open_fixture in tests/android_fixture.py with beach_photos=9 and a fresh invitation.
// Set BEACH_PHOTOS=33 and use beach_photos=33 to exercise the confirmed large export.
// Requires unzip to check the downloaded album.
// Requires Playwright with Chromium installed. Optional CHROMIUM_EXECUTABLE selects a local binary.
const assert = require("node:assert/strict");
const { execFileSync } = require("node:child_process");
const { chromium } = require("playwright");

async function main() {
  const { FIXTURE_URL, FIXTURE_CODE, CHROMIUM_EXECUTABLE } = process.env;
  assert.match(FIXTURE_URL, /^https:\/\/127\.0\.0\.1:\d+$/);
  assert.ok(FIXTURE_CODE);
  const albumPhotoCount = Number(process.env.BEACH_PHOTOS || 9);
  const browser = await chromium.launch({ executablePath: CHROMIUM_EXECUTABLE });
  try {
    const page = await browser.newPage({
      ignoreHTTPSErrors: true,
      viewport: { width: 390, height: 844 },
    });
    await page.addInitScript(() => {
      window.shareMode = "supported";
      window.sharedFiles = [];
      navigator.canShare = ({ files }) => window.shareMode !== "unsupported" && files.length > 0;
      navigator.share = async ({ files }) => {
        if (window.shareMode === "cancel") throw new DOMException("Cancelled", "AbortError");
        if (window.shareMode === "error") throw new DOMException("Unavailable", "NotAllowedError");
        assertActivation();
        window.sharedFiles.push(await Promise.all(files.map(async file => ({
          name: file.name, type: file.type, bytes: [...new Uint8Array(await file.arrayBuffer())],
        }))));
        function assertActivation() {
          if (!navigator.userActivation.isActive) throw new DOMException("Missing activation", "NotAllowedError");
        }
      };
    });
    const paths = [];
    let rejectLargeOnce = true;
    await page.route("**/*", route => {
      const url = new URL(route.request().url());
      if (url.origin !== FIXTURE_URL) return route.abort();
      paths.push(url.pathname);
      if (url.pathname === "/api/v1/photo-export" && route.request().postDataJSON().large && rejectLargeOnce) {
        rejectLargeOnce = false;
        return route.fulfill({ status: 503, json: {} });
      }
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
    const photo = browse.getByRole("button", { name: "Abrir Photo_01.jpg", exact: true });
    const viewer = page.locator("#lightbox");
    const share = viewer.getByRole("button", { name: "Compartir" });
    const original = viewer.getByRole("link", { name: "Descargar original" });
    const [image] = await Promise.all([
      page.waitForResponse(response => new URL(response.url()).pathname === "/api/v1/image"),
      photo.click(),
    ]);
    await share.waitFor();
    await page.evaluate(() => { document.documentElement.style.fontSize = "200%"; });
    assert.ok(await viewer.evaluate(dialog => dialog.scrollWidth <= dialog.clientWidth),
      "The original viewer controls should fit with doubled text.");
    await page.evaluate(() => { document.documentElement.style.fontSize = ""; });
    assert.equal(await page.evaluate(() => window.sharedFiles.length), 0);
    for (const mode of ["light", "dark"]) {
      await page.locator("#appearance").evaluate((select, value) => {
        select.value = value;
        select.dispatchEvent(new Event("change"));
      }, mode);
      await page.screenshot({ path: `/tmp/chromantis-original-share-${mode}.png` });
    }
    await share.click();
    await page.waitForFunction(() => window.sharedFiles.length === 1);
    assert.deepEqual(await page.evaluate(() => window.sharedFiles[0][0]), {
      name: "Photo_01.jpg", type: "image/jpeg", bytes: [...await image.body()],
    });
    assert.equal(paths.filter(path => path === "/api/v1/image").length, 1);
    await page.evaluate(() => { window.shareMode = "cancel"; });
    await share.click();
    await page.waitForFunction(() => !document.querySelector("#share-original").disabled);
    assert.equal(await viewer.locator("#original-status").textContent(), "");
    await page.evaluate(() => { window.shareMode = "error"; });
    await share.click();
    await viewer.getByText("No se pudo compartir. Puedes descargar el original.").waitFor();
    await viewer.getByRole("button", { name: "Cerrar" }).click();
    await page.waitForFunction(() => document.querySelector("#share-original").onclick === null);
    await page.evaluate(() => { window.shareMode = "unsupported"; });
    await photo.click();
    await original.waitFor();
    assert.equal(await share.count(), 0);
    const [originalDownload] = await Promise.all([page.waitForEvent("download"), original.click()]);
    assert.equal(originalDownload.suggestedFilename(), "Photo_01.jpg");
    assert.equal(await originalDownload.failure(), null);
    await viewer.getByRole("button", { name: "Cerrar" }).click();
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
    const prepare = page.getByRole("button", { name: "Preparar para compartir" });
    const shareSelection = page.getByRole("button", { name: "Compartir selección", exact: true });
    await prepare.click();
    await page.getByText("Este navegador no puede compartir estas fotos. Puedes descargarlas.").waitFor();
    assert.equal(await shareSelection.count(), 0);
    await page.evaluate(() => { window.shareMode = "supported"; });
    await prepare.click();
    await shareSelection.waitFor();
    const fourthPhoto = page.getByRole("checkbox", { name: /Photo_04.jpg/ });
    await fourthPhoto.uncheck();
    await prepare.waitFor();
    assert.equal(await shareSelection.count(), 0);
    await fourthPhoto.check();
    await prepare.click();
    await shareSelection.waitFor();
    assert.equal(await page.evaluate(() => window.sharedFiles.length), 1);
    for (const mode of ["light", "dark"]) {
      await page.locator("#appearance").selectOption(mode);
      await shareSelection.scrollIntoViewIfNeeded();
      await page.screenshot({ path: `/tmp/chromantis-selection-share-${mode}.png` });
    }
    await page.evaluate(() => { window.shareMode = "cancel"; });
    await shareSelection.click();
    await page.waitForFunction(() => [...document.querySelectorAll("button")]
      .some(button => button.textContent === "Compartir selección" && !button.disabled));
    const exportCount = paths.filter(path => path === "/api/v1/photo-export").length;
    await page.evaluate(() => { window.shareMode = "supported"; });
    await shareSelection.click();
    await page.waitForFunction(() => window.sharedFiles.length === 2);
    const shared = await page.evaluate(() => window.sharedFiles[1]);
    const zipped = await download.path();
    assert.deepEqual(shared, ["Photo_02.jpg", "Photo_04.jpg"].map((name, index) => ({
      name, type: "image/jpeg",
      bytes: [...execFileSync("unzip", ["-p", zipped, `0${index + 1}-${name}`])],
    })));
    assert.equal(paths.filter(path => path === "/api/v1/photo-export").length, exportCount);
    let albumButton = page.getByRole("button", { name: "Descargar álbum", exact: true });
    if (albumPhotoCount > 20) {
      await albumButton.click();
      albumButton = page.getByRole("button", { name: "Confirmar descarga grande" });
      await albumButton.waitFor();
    }
    for (const mode of ["light", "dark"]) {
      await page.locator("#appearance").selectOption(mode);
      await albumButton.scrollIntoViewIfNeeded();
      await page.screenshot({ path: `/tmp/chromantis-album-export-${albumPhotoCount}-${mode}.png` });
    }
    if (albumPhotoCount > 20) {
      await albumButton.click();
      await page.getByText("No se pudo preparar el ZIP. Puedes volver a intentarlo.").waitFor();
    }
    const [album] = await Promise.all([page.waitForEvent("download"), albumButton.click()]);
    const names = execFileSync("unzip", ["-Z1", await album.path()], { encoding: "utf8" }).trim().split("\n");
    assert.deepEqual(names, Array.from({ length: albumPhotoCount }, (_, i) => {
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
    assert.equal(paths.filter(path => path === "/api/v1/image").length, 2,
      "Only the two explicit viewer opens should request originals.");
  } finally {
    await browser.close();
  }
}

main().catch(error => {
  console.error(error);
  process.exitCode = 1;
});
