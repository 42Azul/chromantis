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
assert.equal(results.cards[0].children.length, 2);
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
assert.equal(views[0].view, "album-review");
assert.equal(views[0].options.path, item.folder_path);
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
  const { returnTo } = views[0].options;
  assert.equal(returnTo.label, "Volver a resultados");
  await returnTo.open();
  assert.equal(views.at(-1).view, "archive");
  assert.equal(query.value, "Anita");
  assert.deepEqual(searches.at(-1), { action: "confirmed", options: { term: "Anita", offset: 24 } });
  assert.equal(resultsTitle.focused, true);
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

verifyReturnToPhotoSearch().then(verifySearchSelection).then(verifyManualPhotoTags).then(() => {
  console.log("Confirmed photo UI regression checks passed.");
}).catch(error => {
  console.error(error);
  process.exitCode = 1;
});
