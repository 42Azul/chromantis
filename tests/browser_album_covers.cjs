// Run against tests/android_fixture.py with a fresh synthetic invitation.
// Requires Playwright with Chromium installed. Optional CHROMIUM_EXECUTABLE selects a local binary.
const assert = require("node:assert/strict");
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
  } finally {
    await browser.close();
  }
}

main().catch(error => {
  console.error(error);
  process.exitCode = 1;
});
