const { readFileSync } = require("node:fs");

async function verifyBatchReview(source, failedReloads = 0) {
  function assert(condition, message) {
    if (!condition) throw new Error(message);
  }

  function element(tag, props, ...children) {
    return {
      tag, props, children, value: "", disabled: false, textContent: "", listeners: {},
      addEventListener(name, listener) { this.listeners[name] = listener; },
      append(child) { this.children.push(child); },
      replaceChildren(...items) { this.children = items; },
      querySelectorAll() {
        return this.children.flatMap(child => typeof child === "string" ? [] :
          ["button", "select"].includes(child.tag) ? [child] : child.querySelectorAll());
      },
    };
  }

  const content = element("div", {});
  const messages = {};
  const album = (id, revision) => ({
    id, revision, path: `2024/fixture-${id}`, title: `Album ${id}`, year: 2024, evidence: "fixture",
  });
  const group = (key, ...albums) => ({ key, label: key, albums });
  let groups = [
    group("playa", album(1, 3), album(5, 2)),
    group("familia", album(1, 3), album(2, 8), album(3, 0), album(4, 0)),
  ];
  const start = source.indexOf("async function loadAlbumReviewBatch(");
  const end = source.indexOf("\nfunction reviewPersonPicker(", start);
  assert(start >= 0 && end > start, "Batch UI function is missing");
  const posts = [];
  const api = async (path, request) => {
    if (!request) {
      assert(path === "/album-review/batch?limit=50", "Unexpected batch read");
      if (posts.length === 1 && failedReloads > 0) {
        failedReloads--;
        throw new Error("Simulated loss of connection");
      }
      return { groups };
    }
    assert(path === "/album-review/batch" && request.method === "POST", "Unexpected batch write");
    posts.push(request.data.items);
    if (posts.length === 2) throw new Error("Simulated conflict");
    groups = [group("familia", album(1, 4), album(2, 8), album(3, 1), album(4, 0))];
    return {};
  };
  const load = new Function("$", "message", "element", "button", "api",
    `let albumRequest = 0;
     const closeAlbumReview = () => { albumRequest++; $("album-review-content").replaceChildren(); };
     const setAlbumReviewMode = () => {};
     ${source.slice(start, end)}
     return loadAlbumReviewBatch;`)(
    () => content, (id, value) => { messages[id] = value; },
    element, (title, action) => {
      const control = element("button", {}, title);
      control.addEventListener("click", action);
      return control;
    }, api,
  );

  const selectValues = form => form.querySelectorAll().filter(control => control.tag === "select");
  const submit = form => form.listeners.submit({ preventDefault() {} });

  const reloadAttempts = failedReloads;
  await load();
  const [beach, family] = content.children;
  const beachChoices = selectValues(beach);
  beachChoices[0].value = "accepted";
  beachChoices[1].value = "rejected";
  const familyChoices = selectValues(family);
  familyChoices[0].value = "rejected";
  familyChoices[1].value = "accepted";
  familyChoices[2].value = "accepted";

  const firstSave = submit(beach);
  await submit(family);
  await firstSave;
  assert(posts.length === 1 && posts[0].length === 2, "The submitted group alone should be written once");
  assert(posts[0].map(item => item.decision).join() === "accepted,rejected", "Mixed batch decisions must be kept");
  assert(posts[0].every(item => item.label === "playa"), "A different group was submitted prematurely");

  for (let attempt = 0; attempt < reloadAttempts; attempt++) {
    const retry = content.children.find(control =>
      control.tag === "button" && control.children[0] === "Reintentar la carga");
    assert(retry, "A failed refresh must offer a retry");
    assert(messages["album-review-status"] === "Decisiones guardadas. No se pudo recargar la cola.",
      "A failed refresh must distinguish the successful save");
    await retry.listeners.click();
    assert(posts.length === 1, "Retrying a refresh must not send the save again");
  }

  const [restoredFamily] = content.children;
  const restored = selectValues(restoredFamily);
  assert(restored[0].value === "rejected", "The same album's own revision change should preserve its other selection");
  assert(restored[1].value === "accepted", "A choice on an unchanged album should be preserved");
  assert(restored[2].value === "", "A choice on an externally revised album must be cleared");
  assert(restored[3].value === "", "An untouched row must remain pending");
  assert(messages["album-review-status"].includes("han cambiado"), "Discarded choices must be announced");

  await submit(restoredFamily);
  assert(posts[1].map(item => item.revision).join() === "4,8", "Restored choices must submit the current revisions");
  assert(restored[0].value === "rejected" && restored[1].value === "accepted",
    "A failed save must leave the pending choices available");
  assert(!restoredFamily.querySelectorAll().some(control => control.disabled), "A failed save must restore controls");
}

const source = readFileSync("src/chromantis/api/ui/app.js", "utf8");
verifyBatchReview(source).then(() => verifyBatchReview(source, 2)).then(() => {
  console.log("Album review batch regression checks passed.");
}).catch(error => {
  console.error(error);
  process.exitCode = 1;
});
