const assert = require("node:assert/strict");
const { readFileSync } = require("node:fs");

const source = readFileSync("src/chromantis/api/ui/app.js", "utf8");
function between(start, end) {
  const first = source.indexOf(start);
  const last = source.indexOf(end, first);
  assert.ok(first >= 0 && last > first);
  return source.slice(first, last);
}

const results = { classList: { remove() {} }, replaceChildren(...cards) { this.cards = cards; } };
const browsing = { replaceChildren(...buttons) { this.buttons = buttons; } };
const opened = [];
const searches = [];
const render = new Function("results", "browsing", "opened", "searches", `
  const indexStatus = { thumbnails: false };
  const photoURLs = new Set();
  const photoRequests = new AbortController();
  const $ = id => ({ results, browsing })[id];
  const resetPhotos = () => {};
  const message = () => {};
  const isOwner = () => false;
  const element = (tag, options, ...children) => ({ tag, children });
  const button = (label, click) => ({ label, click, setAttribute() {} });
  const openPhoto = (item, filename, preview, fetchOriginal) => opened.push({ item, preview, fetchOriginal });
  const archiveRequest = (action, options) => searches.push({ action, options });
  ${between("function renderConfirmedPhotos(", "function renderBatch(")}
  ${between("function photoCard(", "function closeAlbumReview(")}
  return renderConfirmedPhotos;
`)(results, browsing, opened, searches);

const item = { path: "2024/fixture/Photo-25.jpg" };
render({ items: [item], next_offset: null }, "Anita", 24, 24);
assert.equal(results.cards.length, 1);
assert.deepEqual(opened, []);
const [frame] = results.cards[0].children;
assert.equal(frame.label, "Abrir foto");
frame.click();
assert.deepEqual(opened, [{ item, preview: undefined, fetchOriginal: true }]);
assert.equal(browsing.buttons.length, 1);
browsing.buttons[0].click();
assert.deepEqual(searches, [{ action: "confirmed", options: { person: "Anita", offset: 0 } }]);

render({ items: [item], next_offset: 24 }, "Anita", 0, 24);
assert.equal(browsing.buttons.length, 1);
browsing.buttons[0].click();
assert.deepEqual(searches[1], { action: "confirmed", options: { person: "Anita", offset: 24 } });
console.log("Confirmed photo UI regression checks passed.");
