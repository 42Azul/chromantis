const assert = require("node:assert/strict");
const { readFileSync } = require("node:fs");

function element(tag, attributes = {}, ...children) {
  return {
    tag, attributes, children, disabled: false, value: attributes.value || "", textContent: "",
    get firstChild() { return this.children[0]; },
    replaceChildren(...items) { this.children = items; },
    addEventListener(name, action) { this[name] = action; },
    removeAttribute(name) { delete this[name]; },
    querySelector(selector) {
      return this.children.filter(child => typeof child === "object")
        .map(child => child.attributes.class === selector.slice(1) ? child : child.querySelector(selector))
        .find(Boolean);
    },
  };
}
const button = (text, click) => Object.assign(element("button"), { textContent: text, click });
const descendants = node => [node, ...node.children.filter(child => typeof child === "object").flatMap(descendants)];
const source = readFileSync("src/chromantis/api/ui/app.js", "utf8");
const code = source.slice(source.indexOf("async function openPhotoReview("), source.indexOf("function albumPhotoGallery("));

async function verify(conflict) {
  const dialog = element("dialog");
  dialog.showModal = () => { dialog.open = true; };
  dialog.close = () => { dialog.open = false; dialog.onclose(); };
  const content = element("div");
  const close = button("Cerrar", () => dialog.close());
  const photos = Array.from({ length: 3 }, (_, i) => ({
    path: "fixture/Photo-" + i + ".jpg", identity: String(i), people: [],
  }));
  const writes = [];
  const api = async (path, options = {}) => {
    if (path.startsWith("/thumbnail?")) return {};
    if (path.startsWith("/photo-tags?")) return { items: photos };
    if (path === "/album-review/people") return { items: [{ id: 2, display_name: "Ana", aliases: ["Anita"] }] };
    assert.equal(path, "/photo-tags");
    writes.push(options.data);
    if (conflict) throw Object.assign(new Error("Synthetic conflict"), { status: 409 });
    return {};
  };
  const open = new Function("$", "element", "button", "api", "queryParams", "message", "URL",
    code + "; return openPhotoReview;")(
    id => ({ "photo-review": dialog, "photo-review-content": content, "close-photo-review": close })[id],
    element, button, api, pairs => "?" + new URLSearchParams(pairs), () => {},
    { createObjectURL: () => "blob:fixture", revokeObjectURL() {} },
  );
  const find = text => descendants(content).find(node => node.textContent === text);
  const image = () => descendants(content).find(node => node.tag === "img");
  const loaded = async () => { await Promise.resolve(); image().onload(); };
  await open(photos, new AbortController().signal);
  descendants(content).find(node => node.tag === "select").value = "2";
  find("Empezar").click();
  assert.equal(find("Sí, aparece").disabled, true);
  await loaded();
  find("Sí, aparece").click();
  await loaded();
  find("Saltar").click();
  find("Deshacer").click();
  await loaded();
  find("Saltar").click();
  await Promise.resolve();
  image().onerror();
  assert.equal(find("Sí, aparece").disabled, true);
  assert.equal(find("Saltar").disabled, false);
  find("Saltar").click();
  assert.deepEqual(writes, []);
  assert.equal(content.querySelector(".review-marked").textContent, "Photo-0.jpg");
  await find("Guardar revisión").click();
  assert.deepEqual(writes[0], { photos: [{ path: photos[0].path, identity: "0" }], add_people: [2] });
  assert.equal(dialog.open, conflict);
  if (conflict) {
    assert.equal(find("Guardar revisión").disabled, true);
    assert.equal(find("Deshacer").disabled, true);
    assert.equal(close.disabled, false);
  }
}

verify(false).then(() => verify(true)).then(() => {
  console.log("Photo review UI regression checks passed.");
}).catch(error => {
  console.error(error);
  process.exitCode = 1;
});
