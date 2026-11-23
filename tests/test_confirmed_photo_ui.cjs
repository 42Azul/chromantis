const assert = require("node:assert/strict");
const { readFileSync } = require("node:fs");

const source = readFileSync("src/chromantis/api/ui/app.js", "utf8");
function between(start, end) {
  const first = source.indexOf(start);
  const last = source.indexOf(end, first);
  assert.ok(first >= 0 && last > first);
  return source.slice(first, last);
}

const results = { classList: { remove() {}, toggle() {} }, replaceChildren(...cards) { this.cards = cards; },
  querySelectorAll() { return (this.cards || []).flatMap(card => card.children.filter(child => child.tag === "label").map(label => label.children[0])); } };
const tools = { replaceChildren(...buttons) { this.buttons = buttons; } };
const browsing = { replaceChildren(...buttons) { this.buttons = buttons; } };
const opened = [];
const edits = [];
const permissions = { curate: false };
const searches = [];
const views = [];
const query = { value: "" };
const resultsTitle = { focus() { this.focused = true; } };
const render = new Function("results", "browsing", "opened", "searches", "edits", "permissions", "views", "query", "resultsTitle", "tools", `
  ${between("const familyPhotoSearchModes", "const sharedSecret")}
  const indexStatus = { thumbnails: false };
  const photoURLs = new Set();
  const photoRequests = new AbortController();
  const $ = id => ({ results, browsing, query, archive: { hidden: false }, "results-title": resultsTitle,
    "photo-tag": { value: "" }, "photo-results-tools": tools })[id];
  const resetPhotos = () => {};
  const message = () => {};
  const isOwner = () => false;
  let canCurateAlbums;

  const element = (tag, options, ...children) => ({ tag, props: options, children, listeners: {},
    addEventListener(name, listener) { this.listeners[name] = listener; }, append(child) { children.push(child); } });
  const button = (label, click) => ({ label, click, setAttribute() {} });
  const openPhoto = (item, filename, preview, fetchOriginal) => opened.push({ item, preview, fetchOriginal });
  const openPhotoTags = (items, signal, saved) => edits.push({ items, saved });
  const archiveRequest = (action, options) => searches.push({ action, options });
  const showView = (view, options) => views.push({ view, options });
  ${between("function openAlbumFromResults(", "function renderFolders(")}
  ${between("function photoSelectionControls(", "function albumPhotoGallery(")}
  ${between("function renderFamilyPhotoResults(", "function renderBatch(")}
  ${between("function photoCard(", "function closeAlbumReview(")}
  return (...args) => { canCurateAlbums = permissions.curate; return renderFamilyPhotoResults(...args); };
`)(results, browsing, opened, searches, edits, permissions, views, query, resultsTitle, tools);

const item = { path: "2024/fixture/Photo-25.jpg", folder_path: "2024/fixture" };
render({ items: [item], next_offset: null }, "confirmed", "Anita", 24, 24);
assert.equal(results.cards.length, 1);
assert.equal(results.cards[0].children.length, 3);
assert.equal(results.cards[0].children[1].children.at(-1).children[0], item.folder_path);
assert.deepEqual(opened, []);
const [frame] = results.cards[0].children;
assert.equal(frame.label, "Abrir foto");
frame.click();
assert.deepEqual(opened, [{ item, preview: undefined, fetchOriginal: true }]);
assert.equal(browsing.buttons.length, 1);
browsing.buttons[0].click();
assert.deepEqual(searches, [{ action: "confirmed", options: { term: "Anita", offset: 0 } }]);

render({ items: [item], next_offset: 24 }, "confirmed", "Anita", 0, 24);
assert.equal(browsing.buttons.length, 1);
browsing.buttons[0].click();
assert.deepEqual(searches[1], { action: "confirmed", options: { term: "Anita", offset: 24 } });
permissions.curate = true;
render({ items: [item], next_offset: null }, "confirmed", "Anita", 24, 24);
const edit = results.cards[0].children.find(child => child.label === "Etiquetar foto");
const album = results.cards[0].children.find(child => child.label === "Ver álbum");
assert.equal(edit.label, "Etiquetar foto");
edit.click();
assert.deepEqual(edits[0].items, [item]);
assert.equal(opened.length, 1);
edits[0].saved();
assert.deepEqual(searches.at(-1), { action: "confirmed", options: { term: "Anita", offset: 24 } });
assert.equal(album.label, "Ver álbum");
album.click();
assert.equal(views[0].view, "album-browse");
assert.equal(views[0].options.album.path, item.folder_path);
render({ items: [item], next_offset: 24 }, "tagged", "romería", 0, 24);
browsing.buttons[0].click();
assert.deepEqual(searches.at(-1), { action: "tagged", options: { term: "romería", offset: 24 } });
results.cards[0].children.find(child => child.label === "Etiquetar foto").click();
edits.at(-1).saved();
assert.deepEqual(searches.at(-1), { action: "tagged", options: { term: "romería", offset: 0 } });
render({ items: [item], next_offset: 48 }, "confirmed", "Anita", 24, 24, "romería");
browsing.buttons[1].click();
assert.deepEqual(searches.at(-1), { action: "confirmed", options: { term: "Anita", tag: "romería", offset: 48 } });
results.cards[0].children.find(child => child.label === "Etiquetar foto").click();
edits.at(-1).saved();
assert.deepEqual(searches.at(-1), { action: "confirmed", options: { term: "Anita", tag: "romería", offset: 24 } });

async function verifySearchSelection() {
  const photos = [
    { path: "2024/first/IMG_001.jpg", folder_path: "2024/first" },
    { path: "2023/second/IMG_001.jpg", folder_path: "2023/second" },
  ];
  const beforeOpening = opened.length;
  render({ items: photos, next_offset: 48 }, "confirmed", "Anita", 24, 24, "romería");
  assert.equal(tools.hidden, false);
  let [toggle, all, save] = tools.buttons;
  assert.equal(save.hidden, true);
  assert.equal(save.disabled, true);
  toggle.click();
  let checks = results.querySelectorAll();
  checks[0].checked = true;
  checks[0].listeners.change();
  assert.equal(save.textContent, "Etiquetar fotos (1)");
  save.click();
  assert.deepEqual(edits.at(-1).items, [photos[0]]);
  assert.equal(opened.length, beforeOpening, "Selecting must not open originals");
  await edits.at(-1).saved();
  assert.deepEqual(searches.at(-1), { action: "confirmed", options: { term: "Anita", tag: "romería", offset: 24 } });
  assert.equal(save.disabled, true);
  toggle.click();
  all.click();
  assert(checks.every(input => input.checked));
  assert.equal(all.disabled, true);
  assert.equal(save.textContent, "Etiquetar fotos (2)");
  save.click();
  assert.deepEqual(edits.at(-1).items, photos, "One batch can include different albums");
  checks[1].checked = false;
  checks[1].listeners.change();
  assert.equal(save.textContent, "Etiquetar fotos (1)");
  const beforeCancel = edits.length;
  toggle.click();
  assert(checks.every(input => !input.checked));
  save.click();
  assert.equal(edits.length, beforeCancel, "Cancel must not submit a stale selection");

  render({ items: [photos[1]], next_offset: null }, "tagged", "romería", 48, 24);
  [toggle, all, save] = tools.buttons;
  assert.equal(save.disabled, true, "A new page starts with no selection");
  assert.equal(save.hidden, true);
  toggle.click();
  all.click();
  save.click();
  await edits.at(-1).saved();
  assert.deepEqual(searches.at(-1), { action: "tagged", options: { term: "romería", offset: 48 } });
  permissions.curate = false;
  render({ items: photos, next_offset: null }, "confirmed", "Ana", 0, 24);
  assert.equal(tools.hidden, true);
  assert.equal(results.querySelectorAll().length, 0, "Viewers have no selection controls");
  permissions.curate = true;
}

async function verifyReturnToPhotoSearch() {
  await views[0].options.refresh();
  assert.equal(query.value, "Anita");
  assert.deepEqual(searches.at(-1), { action: "confirmed", options: { term: "Anita", offset: 24 } });
}

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
    { path: "another-album/C.jpg", identity: "third", people: [], manual_tags: [{ tag: "keep" }] },
  ];
  const writes = [];
  const messages = {};
  const api = async (path, options) => {
    if (options.method === "PATCH") {
      writes.push(options.data);
      return {};
    }
    if (path === "/album-review/people") return { items: [] };
    assert.deepEqual(new URLSearchParams(path.split("?")[1]).getAll("path"), selected.map(photo => photo.path));
    return { items: selected };
  };
  const open = new Function("$", "element", "api", "messages", `
    const message = (name, text) => { messages[name] = text; };
    const queryParams = pairs => "?" + new URLSearchParams(pairs);
    const reviewPersonPicker = () => element("div", {});
    ${between("async function openPhotoTags(", "function albumPhotoGallery(")}
    return openPhotoTags;
  `)(id => elements[id], element, api, messages);

  await open(selected, new AbortController().signal);
  assert.equal(messages["photo-tags-file"], "fixture/A.jpg, another-album/C.jpg");
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

async function verifyPrivateThumbnailReuse() {
  const Cache = new Function(`${between("class PrivateThumbnailCache", "const thumbnailCache")} return PrivateThumbnailCache;`)();
  const requests = [];
  let complete;
  const fetchPreview = async path => { requests.push(path); return new Blob(["1234"]); };
  const cache = new Cache(fetchPreview, 8, 2);
  const signal = new AbortController().signal;
  const photo = { path: "2024/fixture/A.jpg", identity: "first" };
  const first = await cache.load(photo, signal);
  assert.equal(await cache.load(photo, signal), first);
  assert.equal(requests.length, 1);
  await cache.load({ ...photo, identity: "replacement" }, signal);
  assert.equal(requests.length, 2);
  await cache.load({ path: "other.jpg", identity: "other" }, signal);
  assert.equal(cache.bytes, 8);
  assert.equal(cache.entries.size, 2);
  await cache.load(photo, signal); // The oldest version was evicted.
  assert.equal(requests.length, 4);
  await cache.load({ path: photo.path }, signal);
  await cache.load({ path: photo.path }, signal);
  assert.equal(requests.length, 6); // Old-server metadata never creates an unsafe cache key.
  cache.clear();
  assert.equal(cache.bytes, 0);
  assert.equal(cache.entries.size, 0);
  await cache.load(photo, signal);
  assert.equal(requests.length, 7);
  const aborted = new AbortController();
  aborted.abort();
  await assert.rejects(cache.load(photo, aborted.signal), { name: "AbortError" });
  assert.equal(requests.length, 7);

  const pending = new Cache(() => new Promise(resolve => { complete = resolve; }));
  const oldSession = pending.load(photo, signal);
  pending.clear();
  complete(new Blob(["private preview"]));
  await assert.rejects(oldSession, { name: "AbortError" });
  assert.equal(pending.entries.size, 0);
  const failed = new Cache(async () => { throw Object.assign(new Error("revoked"), { status: 401 }); });
  await assert.rejects(failed.load(photo, signal), { status: 401 });
  assert.equal(failed.entries.size, 0);
  const oversized = new Cache(fetchPreview, 1);
  await oversized.load(photo, signal);
  assert.equal(oversized.bytes, 0);
}

async function verifyLazyAlbumCover() {
  let visible, complete;
  const requests = [];
  const urls = new Set();
  const controller = new AbortController();
  const load = new Function("api", "queryParams", "photoURLs", "IntersectionObserver",
    `${between("function loadAlbumCover(", "function renderFolders(")} return loadAlbumCover;`)(
    (path, options) => {
      requests.push({ path, options });
      return new Promise(resolve => { complete = resolve; });
    },
    data => "?" + new URLSearchParams(data), urls,
    class {
      constructor(callback) { visible = callback; }
      observe() {}
      disconnect() {}
    },
  );
  const card = { prepend() { assert.fail("A stale cover must not reach the card"); } };
  load(card, "2024/Picnic", controller.signal);
  visible([{ isIntersecting: false }]);
  assert.equal(requests.length, 0);
  visible([{ isIntersecting: true }]);
  assert.deepEqual(requests, [{
    path: "/album-cover?path=2024%2FPicnic", options: { raw: true, signal: controller.signal },
  }]);
  controller.abort();
  complete(new Blob(["synthetic"]));
  await Promise.resolve();
  assert.equal(urls.size, 0);
}

verifyReturnToPhotoSearch().then(verifySearchSelection).then(verifyManualPhotoTags).then(verifyPrivateThumbnailReuse).then(verifyLazyAlbumCover).then(() => {
  console.log("Confirmed photo UI regression checks passed.");
}).catch(error => {
  console.error(error);
  process.exitCode = 1;
});
