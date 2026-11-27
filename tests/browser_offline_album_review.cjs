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
    const nextLoads = [];
    const resultRefreshes = [];
    let failResultRefresh = false;
    const unexpected = [];
    let explicitOriginal;
    const originals = [];
    await page.route("**/*", route => {
      const request = route.request();
      const url = new URL(request.url());
      if (url.origin === FIXTURE_URL && url.pathname === "/api/v1/image" && explicitOriginal) {
        originals.push(url.searchParams.get("path"));
        return route.continue();
      }
      if (url.origin !== FIXTURE_URL || /^\/api\/v1\/(image|thumbnail|album-cover|album-images)$/.test(url.pathname)) {
        unexpected.push(url.pathname);
        return route.abort();
      }
      if (url.pathname === "/api/v1/album-review" && request.method() === "POST") {
        albumSaves.push(request.postDataJSON());
        if (albumSaves.length === 1) return route.fulfill({ status: 503, json: {} });
      }
      if (url.pathname === "/api/v1/album-review" && request.method() === "GET" &&
          albumSaves.length === 2 && Number(url.searchParams.get("after")) === albumSaves[1].id) {
        nextLoads.push(url.search);
        if (nextLoads.length === 1) return route.fulfill({ status: 503, json: {} });
      }
      if (url.pathname === "/api/v1/folders" && failResultRefresh) {
        resultRefreshes.push(url.search);
        if (resultRefreshes.length === 1) return route.fulfill({ status: 503, json: {} });
        failResultRefresh = false;
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
    await page.setViewportSize({ width: 360, height: 600 });
    const form = page.locator("#album-review-form");
    await form.getByText("Añadir etiquetas", { exact: true }).click();
    await page.evaluate(() => {
      document.documentElement.style.fontSize = "200%";
      document.querySelector("#album-review-content").scrollIntoView();
    });
    assert.ok(await form.evaluate(element => element.getBoundingClientRect().bottom > innerHeight));
    assert.ok(await save.evaluate(button => {
      const rect = button.getBoundingClientRect();
      return rect.top >= 0 && rect.bottom <= innerHeight;
    }), "The save action should be in view while the form extends below the screen.");
    assert.ok(await page.evaluate(() => document.documentElement.scrollWidth <= innerWidth));
    await page.evaluate(() => { document.documentElement.style.fontSize = ""; });
    await page.setViewportSize({ width: 360, height: 800 });
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
    await page.getByText("Álbum guardado. No se pudo cargar el siguiente.", { exact: true }).waitFor();
    const retry = page.getByRole("button", { name: "Reintentar la carga" });
    assert.ok(await retry.evaluate(button => button === document.activeElement));
    for (const mode of ["light", "dark"]) {
      await page.locator("#appearance").selectOption(mode);
      await retry.scrollIntoViewIfNeeded();
      await page.screenshot({ path: `/tmp/chromantis-queue-retry-${mode}.png` });
    }
    await retry.press("Enter");
    await page.getByText("Álbum guardado.", { exact: true }).waitFor();
    assert.equal(nextLoads.length, 2);
    assert.equal(nextLoads[0], nextLoads[1]);
    assert.equal(albumSaves.length, 2);
    assert.deepEqual(albumSaves[0], albumSaves[1]);
    const headingSelector = "#album-review-content h2";
    await page.waitForFunction(selector => document.activeElement.matches(selector), headingSelector);
    const previousHeading = await page.locator(headingSelector).elementHandle();
    await page.getByRole("button", { name: "Saltar", exact: true }).click();
    await page.waitForFunction(oldHeading => !oldHeading.isConnected &&
      document.activeElement.matches("#album-review-content h2"), previousHeading);
    assert.equal(albumSaves.length, 2, "Skipping must leave the album pending.");
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
    const review = page.locator("#album-review-content");
    const verifySameTitleAlbum = async path => {
      await folder(path).click();
      await album.getByText(path, { exact: true }).waitFor();
      await album.getByRole("button", { name: "Etiquetar álbum" }).click();
      await review.getByRole("heading", { name: "album 00", exact: true }).waitFor();
      await review.getByText(`Carpeta: ${path}`, { exact: true }).waitFor();
    };
    await verifySameTitleAlbum(first);
    await review.getByRole("button", { name: "Quitar a Ana del álbum" }).waitFor();
    await review.getByRole("button", { name: "Volver a resultados", exact: true }).click();
    await page.getByRole("button", { name: "Página siguiente" }).click();
    await verifySameTitleAlbum(second);
    const ana = review.getByRole("button", { name: "Quitar a Ana del álbum" });
    assert.equal(await ana.count(), 0);
    await picker.fill("Anita");
    await picker.press("Enter");
    await ana.waitFor();
    // Update the same album through the real API while its older revision is open in the editor.
    const concurrentEdit = await page.evaluate(async path => {
      const current = await fetch(`/api/v1/album-review?${new URLSearchParams({ path })}`);
      const { item: { id, revision } } = await current.json();
      const updated = await fetch("/api/v1/album-review", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ id, path, revision, manual_add: ["reunion"] }),
      });
      return updated.status;
    }, second);
    assert.equal(concurrentEdit, 200);
    const saveAndReturn = review.getByRole("button", { name: "Guardar y volver a resultados" });
    await saveAndReturn.click();
    const reload = review.getByRole("button", { name: "Descartar mis cambios y recargar" });
    await reload.waitFor();
    assert.ok(await saveAndReturn.isDisabled());
    assert.ok(await ana.isVisible());
    assert.ok(await reload.evaluate(button => button === document.activeElement));
    for (const mode of ["light", "dark"]) {
      await page.locator("#appearance").selectOption(mode);
      await reload.scrollIntoViewIfNeeded();
      await page.screenshot({ path: `/tmp/chromantis-review-conflict-${mode}.png` });
    }
    const writesBeforeReload = albumSaves.length;
    await reload.press("Enter");
    await review.getByText(`Carpeta: ${second}`, { exact: true }).waitFor();
    await review.getByRole("checkbox", { name: "Quitar «reunion»", exact: true }).waitFor();
    assert.equal(await ana.count(), 0);
    assert.equal(albumSaves.length, writesBeforeReload);
    await picker.fill("Anita");
    await picker.press("Enter");
    await ana.waitFor();
    await saveAndReturn.click();
    await folder(second).waitFor();
    assert.equal(await results.locator(".folder-card").count(), 1);
    const finalReview = await page.evaluate(async path => {
      const response = await fetch(`/api/v1/album-review?${new URLSearchParams({ path })}`);
      return (await response.json()).item;
    }, second);
    assert.deepEqual(finalReview.manual_tags, ["reunion"]);
    assert.deepEqual(finalReview.person_ids, albumSaves[1].add_people);
    await page.getByRole("button", { name: "Página anterior" }).click();
    await folder(first).waitFor();
    assert.equal(await results.locator(".folder-card").count(), 30);
    const byYear = page.locator("#year-album-controls");
    await byYear.getByLabel("Nombre del álbum").fill("Álbum-00");
    await byYear.getByLabel("Orden").selectOption("name");
    await byYear.getByRole("button", { name: "Aplicar" }).click();
    await folder(second).waitFor();
    assert.equal(await results.locator(".folder-card").count(), 2);
    for (const mode of ["light", "dark"]) {
      await page.locator("#appearance").selectOption(mode);
      await page.locator("#archive").screenshot({ path: `/tmp/chromantis-year-order-${mode}.png` });
    }
    await folder(second).click();
    await album.getByRole("button", { name: "Volver a resultados", exact: true }).click();
    await folder(second).waitFor();
    await page.waitForFunction(path => document.activeElement?.dataset.albumPath === path, second);
    assert.equal(await byYear.getByLabel("Nombre del álbum").inputValue(), "Álbum-00");
    assert.equal(await byYear.getByLabel("Orden").inputValue(), "name");
    await byYear.getByLabel("Orden").selectOption("timeline");
    const sorted = page.waitForResponse(response => new URL(response.url()).searchParams.get("sort") === "timeline");
    await byYear.getByRole("button", { name: "Aplicar" }).click();
    assert.equal((await (await sorted).json()).sort, "timeline");

    await page.locator("#query").fill("Ana");
    await page.locator("#archive-search").click();
    await folder(first).waitFor();
    await folder(second).waitFor();
    await verifySameTitleAlbum(second);
    await ana.click();
    failResultRefresh = true;
    await saveAndReturn.click();
    const retrySearch = page.getByRole("button", { name: "Reintentar la búsqueda" });
    await retrySearch.waitFor();
    await page.getByText("Álbum guardado. No se pudieron actualizar los resultados.", { exact: true }).waitFor();
    assert.equal(await results.locator(".folder-card").count(), 0, "Stale hits should disappear after a correction.");
    assert.ok(await retrySearch.evaluate(button => button === document.activeElement));
    for (const mode of ["light", "dark"]) {
      await page.locator("#appearance").selectOption(mode);
      await page.screenshot({ path: `/tmp/chromantis-search-refresh-${mode}.png` });
    }
    const writesBeforeSearchRetry = albumSaves.length;
    await retrySearch.press("Enter");
    await folder(first).waitFor();
    assert.equal(await folder(second).count(), 0, "The corrected album should no longer match Ana.");
    assert.equal(await results.locator(".folder-card").count(), 1);
    assert.deepEqual(resultRefreshes, [resultRefreshes[0], resultRefreshes[0]]);
    assert.equal(albumSaves.length, writesBeforeSearchRetry);
    const catalog = page.locator("#album-tag-catalog");
    await catalog.locator("summary").click();
    const tag = catalog.getByRole("button", { name: "reunion · 1", exact: true });
    await tag.waitFor();
    for (const mode of ["light", "dark"]) {
      await page.locator("#appearance").selectOption(mode);
      await tag.scrollIntoViewIfNeeded();
      await page.screenshot({ path: `/tmp/chromantis-album-tags-${mode}.png` });
    }
    await tag.press("Enter");
    await folder(second).waitFor();
    assert.equal(await results.locator(".folder-card").count(), 1);
    await folder(second).click();
    await album.getByRole("button", { name: "Volver a resultados", exact: true }).click();
    await folder(second).waitFor();
    await page.waitForFunction(path => document.activeElement?.dataset.albumPath === path, second);
    for (const mode of ["light", "dark"]) {
      await page.locator("#appearance").selectOption(mode);
      await folder(second).focus();
      await page.screenshot({ path: `/tmp/chromantis-return-result-${mode}.png` });
    }
    const yearFilter = page.getByRole("button", { name: "Quitar filtro de Año: 2003" });
    await page.locator("#query").fill("solo 2003");
    await page.locator("#archive-search").click();
    await yearFilter.waitFor();
    assert.equal(await page.locator("#query").inputValue(), "");
    assert.equal(await results.locator(".folder-card").count(), 1);
    await yearFilter.click();
    await yearFilter.waitFor({ state: "hidden" });
    await page.locator("#query").fill("con Ana");
    await page.locator("#archive-search").click();
    const personFilter = page.getByRole("button", { name: "Quitar filtro de Persona: Ana" });
    await personFilter.waitFor();
    assert.equal(await results.locator(".folder-card").count(), 0);
    for (const mode of ["light", "dark"]) {
      await page.locator("#appearance").selectOption(mode);
      await personFilter.scrollIntoViewIfNeeded();
      await page.screenshot({ path: `/tmp/chromantis-tag-refinements-${mode}.png` });
    }
    await personFilter.click();
    await folder(second).waitFor();
    assert.equal(await results.locator(".folder-card").count(), 1);
    await page.locator("#query").fill("2024");
    await page.locator("#archive-search").click();
    await page.getByText("No se han encontrado álbumes.", { exact: true }).waitFor();
    await page.locator("#query").fill("2003");
    await page.locator("#archive-search").click();
    await folder(second).waitFor();
    assert.equal(await results.locator(".folder-card").count(), 1);
    for (const mode of ["light", "dark"]) {
      await page.locator("#appearance").selectOption(mode);
      await page.screenshot({ path: `/tmp/chromantis-tag-and-year-${mode}.png` });
    }
    await folder(second).click();
    const shortcut = album.getByRole("button", { name: "Buscar álbumes con la etiqueta reunion" });
    await shortcut.waitFor();
    for (const mode of ["light", "dark"]) {
      await page.locator("#appearance").selectOption(mode);
      await page.screenshot({ path: `/tmp/chromantis-album-shortcut-${mode}.png` });
    }
    await shortcut.press("Enter");
    await folder(second).waitFor();
    assert.equal(await results.locator(".folder-card").count(), 1);
    assert.equal(await page.locator("#query").inputValue(), "");
    await page.getByRole("button", { name: "Quitar filtro de Etiqueta: reunion" }).click();
    await page.waitForFunction(() => document.querySelectorAll("#results .folder-card").length > 1);
    const photoPath = `${second}/Photo_01.jpg`;
    assert.equal(await page.evaluate(async path => {
      const current = await fetch(`/api/v1/photo-tags?${new URLSearchParams({ path })}`);
      const { items: [{ identity }] } = await current.json();
      const saved = await fetch("/api/v1/photo-tags", {
        method: "PATCH", headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ photos: [{ path, identity }], manual_add: ["Romería"] }),
      });
      return saved.status;
    }, photoPath), 200);
    await catalog.locator("summary").click();
    await catalog.locator("#tag-catalog-kind").selectOption("photos");
    const labelName = catalog.getByLabel("Nombre de la etiqueta");
    await labelName.fill("inexistente");
    await labelName.press("Enter");
    await catalog.getByText("No hay etiquetas con ese nombre.").waitFor();
    await labelName.fill("ROMÉ");
    await labelName.press("Enter");
    const photoTag = catalog.getByRole("button", { name: "romeria · 1", exact: true });
    await photoTag.waitFor();
    assert.equal(await catalog.getByRole("button", { name: "reunion · 1", exact: true }).count(), 0);
    for (const mode of ["light", "dark"]) {
      await page.locator("#appearance").selectOption(mode);
      await photoTag.scrollIntoViewIfNeeded();
      await page.screenshot({ path: `/tmp/chromantis-photo-tag-catalog-${mode}.png` });
    }
    await photoTag.press("Enter");
    await results.locator(".photo-card").getByRole("heading", { name: "Photo_01.jpg" }).waitFor();
    assert.equal(await results.locator(".photo-card").count(), 1);
    assert.equal(await page.locator("#query").inputValue(), "romeria");
    const parentAlbum = results.getByRole("button", { name: "Ver álbum de Photo_01.jpg", exact: true });
    await parentAlbum.press("Enter");
    await album.getByRole("button", { name: "Volver a resultados" }).press("Enter");
    await page.waitForFunction(path => document.activeElement?.getAttribute("data-source-photo") === path, photoPath);
    assert.equal(await page.locator("#query").inputValue(), "romeria");
    explicitOriginal = photoPath;
    await results.getByRole("button", { name: "Abrir Photo_01.jpg", exact: true }).click();
    const shortcutToPhotos = page.getByRole("button", { name: "Buscar fotos con la etiqueta romeria" });
    await shortcutToPhotos.waitFor();
    await page.getByText("No se pudo abrir el original.", { exact: true }).waitFor();
    for (const mode of ["light", "dark"]) {
      await page.locator("#appearance").evaluate((select, value) => {
        select.value = value;
        select.dispatchEvent(new Event("change"));
      }, mode);
      await page.screenshot({ path: `/tmp/chromantis-photo-shortcut-${mode}.png` });
    }
    await shortcutToPhotos.press("Enter");
    await page.waitForFunction(() => !document.querySelector("#lightbox").open);
    await results.locator(".photo-card").getByRole("heading", { name: "Photo_01.jpg" }).waitFor();
    assert.equal(await results.locator(".photo-card").count(), 1);
    assert.deepEqual(originals, [photoPath]);
    assert.deepEqual(unexpected, []);
  } finally {
    await browser.close();
  }
}

main().catch(error => {
  console.error(error);
  process.exitCode = 1;
});
