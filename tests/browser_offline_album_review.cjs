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
      if (url.pathname === "/api/v1/album-review" && request.method() === "GET" &&
          albumSaves.length === 2 && Number(url.searchParams.get("after")) === albumSaves[1].id) {
        nextLoads.push(url.search);
        if (nextLoads.length === 1) return route.fulfill({ status: 503, json: {} });
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
    assert.deepEqual(unexpected, []);
  } finally {
    await browser.close();
  }
}

main().catch(error => {
  console.error(error);
  process.exitCode = 1;
});
