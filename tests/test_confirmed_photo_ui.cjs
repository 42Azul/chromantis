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
const edits = [];
const permissions = { curate: false };
const searches = [];
const render = new Function("results", "browsing", "opened", "searches", "edits", "permissions", `
  const indexStatus = { thumbnails: false };
  const photoURLs = new Set();
  const photoRequests = new AbortController();
  const $ = id => ({ results, browsing })[id];
  const resetPhotos = () => {};
  const message = () => {};
  const isOwner = () => false;
  let canCurateAlbums;

  const element = (tag, options, ...children) => ({ tag, children, append(child) { children.push(child); } });
  const button = (label, click) => ({ label, click, setAttribute() {} });
  const openPhoto = (item, filename, preview, fetchOriginal) => opened.push({ item, preview, fetchOriginal });
  const openPhotoTags = (items, signal, saved) => edits.push({ items, saved });
  const archiveRequest = (action, options) => searches.push({ action, options });
  ${between("function renderConfirmedPhotos(", "function renderBatch(")}
  ${between("function photoCard(", "function closeAlbumReview(")}
  return (...args) => { canCurateAlbums = permissions.curate; return renderConfirmedPhotos(...args); };
`)(results, browsing, opened, searches, edits, permissions);

const item = { path: "2024/fixture/Photo-25.jpg" };
render({ items: [item], next_offset: null }, "Anita", 24, 24);
assert.equal(results.cards.length, 1);
assert.equal(results.cards[0].children.length, 2);
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
permissions.curate = true;
render({ items: [item], next_offset: null }, "Anita", 24, 24);
const edit = results.cards[0].children.at(-1);
assert.equal(edit.label, "Etiquetar foto");
edit.click();
assert.deepEqual(edits[0].items, [item]);
assert.equal(opened.length, 1);
edits[0].saved();
assert.deepEqual(searches.at(-1), { action: "confirmed", options: { person: "Anita", offset: 24 } });
async function verifyManualPhotoTags() {
  function element(tag, props, ...children) {
    return {
      tag, props, children, value: props.value || "",
      get firstChild() { return this.children[0]; },
      replaceChildren(...items) { this.children = items; },
      addEventListener(name, listener) { this[name] = listener; },
    };
  }

  const dialog = element("dialog", {});
  dialog.showModal = () => { dialog.open = true; };
  dialog.close = () => { dialog.open = false; };
  const elements = {
    "photo-tags": dialog, "photo-tags-content": element("div", {}), "close-photo-tags": element("button", {}),
  };
  const selected = [
    { path: "fixture/A.jpg", identity: "first", people: [], manual_tags: [{ tag: "old" }] },
    { path: "fixture/C.jpg", identity: "third", people: [], manual_tags: [{ tag: "keep" }] },
  ];
  const writes = [];
  const api = async (path, options) => {
    if (options.method === "PATCH") {
      writes.push(options.data);
      return {};
    }
    if (path === "/album-review/people") return { items: [] };
    assert.deepEqual(new URLSearchParams(path.split("?")[1]).getAll("path"), selected.map(photo => photo.path));
    return { items: selected };
  };
  const open = new Function("$", "element", "api", `
    const message = () => {};
    const queryParams = pairs => "?" + new URLSearchParams(pairs);
    const reviewPersonPicker = () => element("div", {});
    ${between("async function openPhotoTags(", "function albumPhotoGallery(")}
    return openPhotoTags;
  `)(id => elements[id], element, api);

  await open(selected, new AbortController().signal);
  const form = elements["photo-tags-content"].firstChild.firstChild;
  const submit = () => form.submit({ preventDefault() {} });
  await submit();
  assert.deepEqual(writes, []);
  assert.equal(dialog.open, true);
  const tags = form.children.find(child => child.tag === "details").children[1];
  const [entry, keep, old] = tags.children.map(label => label.children[0].tag === "input"
    ? label.children[0] : label.children[1]);
  assert.deepEqual([keep.value, old.value], ["keep", "old"]);
  entry.value = " Picnic, familia, ";
  old.checked = true;
  await submit();
  assert.deepEqual(writes, [{
    photos: selected.map(({ path, identity }) => ({ path, identity })),
    add_people: [], remove_people: [], manual_add: ["Picnic", "familia"], manual_remove: ["old"],
  }]);
  assert.equal(dialog.open, false);
}

verifyManualPhotoTags().then(() => {
  console.log("Confirmed photo UI regression checks passed.");
}).catch(error => {
  console.error(error);
  process.exitCode = 1;
});
