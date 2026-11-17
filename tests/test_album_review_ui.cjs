const { readFileSync } = require("node:fs");

async function verifyBatchReview(source, failedReloads = 0) {
  function assert(condition, message) {
    if (!condition) throw new Error(message);
  }

  function element(tag, props, ...children) {
    return {
      tag, props, children, value: "", disabled: false, textContent: "", listeners: {},
      addEventListener(name, listener) { this.listeners[name] = listener; },
      append(...items) { this.children.push(...items); },
      replaceChildren(...items) { this.children = items; },
      querySelectorAll() {
        return this.children.flatMap(child => typeof child === "string" ? [] :
          ["button", "select"].includes(child.tag) ? [child] : child.querySelectorAll());
      },
    };
  }

  const content = element("div", {});
  const messages = {};
  const results = element("div", {});
  const browser = { view: "archive", refreshCount: 0 };
  const album = (id, revision) => ({
    id, revision, path: `2024/fixture-${id}`, title: `Album ${id}`, year: 2024, evidence: "fixture",
  });
  const group = (key, ...albums) => ({ key, label: key, albums });
  let groups = [
    group("playa", album(1, 3), album(5, 2)),
    group("familia", album(1, 3), album(2, 8), album(3, 0), album(4, 0)),
  ];
  const start = source.indexOf("async function loadAlbumReview(");
  const end = source.indexOf("\nfunction albumContextEditor(", start);
  const resultsStart = source.indexOf("function renderFolders(");
  const resultsEnd = source.indexOf("\nfunction renderBatch(", resultsStart);
  assert(start >= 0 && end > start && resultsStart >= 0 && resultsEnd > resultsStart,
    "Album review UI functions are missing");
  const posts = [];
  const detailPosts = [];
  const api = async (path, request) => {
    if (!request) {
      if (path === "/album-review/people") return { items: [] };
      if (path.startsWith("/album-review?path=")) {
        const item = groups.flatMap(group => group.albums).find(album => path === `/album-review?path=${album.path}`);
        assert(item, "Expected to open a specific album from the batch");
        return { item: {
          ...item, person_ids: [], manual_tags: [],
          suggestions: { familia: { label: "familia", state: "pending", evidence: "fixture" } },
        } };
      }
      assert(path === "/album-review/batch?limit=50", "Unexpected batch read");
      if (posts.length === 1 && failedReloads > 0) {
        failedReloads--;
        throw new Error("Simulated loss of connection");
      }
      return { groups };
    }
    if (path === "/album-review" && request.method === "POST") {
      detailPosts.push(request.data);
      groups = groups.map(group => ({
        ...group, albums: group.albums.filter(album => album.id !== request.data.id),
      }));
      return {};
    }
    assert(path === "/album-review/batch" && request.method === "POST", "Unexpected batch write");
    posts.push(request.data.items);
    if (posts.length === 2) throw new Error("Simulated conflict");
    groups = [group("familia", album(1, 4), album(2, 8), album(3, 1), album(4, 0))];
    return {};
  };
  const { loadAlbumReviewBatch: load, renderFolders } = new Function("$", "message", "element", "button", "api", "browser",
    `let albumRequest = 0;
     const closeAlbumReview = () => { albumRequest++; $("album-review-content").replaceChildren(); };
     const setAlbumReviewMode = () => {};
     const queryParams = ({ path }) => "?path=" + path;
     const albumContextEditor = () => element("div", {});
     const principal = { auth_mode: "family" };
     const isOwner = () => false;
     const resetPhotos = () => {};
     const showView = async (view, options) => {
       browser.view = view;
       if (view === "album-review") await loadAlbumReview(options);
     };
     ${source.slice(start, end)}
     ${source.slice(resultsStart, resultsEnd)}
     return { loadAlbumReviewBatch, renderFolders };`)(
    id => id === "results" ? results : content, (id, value) => { messages[id] = value; },
    element, (title, action) => {
      const control = element("button", {}, title);
      control.addEventListener("click", action);
      return control;
    }, api, browser,
  );

  const selectValues = form => form.querySelectorAll().filter(control => control.tag === "select");
  const submit = form => form.listeners.submit({ preventDefault() {} });

  const action = (panel, label) => {
    const control = panel.querySelectorAll().find(control => control.children[0] === label);
    assert(control, "Expected action: " + label);
    return control.listeners.click();
  };

  const reloadAttempts = failedReloads;
  await load();
  selectValues(content.children[0])[0].value = "accepted";
  await action(content.children[0], "Revisar");
  assert(selectValues(content.children.at(-1))[0].value === "pending",
    "The individual review should show its current server state");
  await action(content, "Volver a Por lotes");
  assert(selectValues(content.children[0])[0].value === "accepted",
    "Returning without saving should preserve the batch choice");
  assert(posts.length === 0 && detailPosts.length === 0, "Returning must not write either draft");
  assert(messages["album-review-status"] === "", "Returning must not claim that decisions were saved");

  await load();
  const [beach, family] = content.children;
  const beachChoices = selectValues(beach);
  beachChoices[1].value = "accepted";
  const acceptPending = beach.querySelectorAll().find(control => control.children[0] === "Aceptar los pendientes");
  const rejectPending = beach.querySelectorAll().find(control => control.children[0] === "Rechazar los pendientes");
  assert(acceptPending && rejectPending, "A group should offer both actions for its pending rows");
  rejectPending.listeners.click();
  assert(beachChoices.map(control => control.value).join() === "rejected,accepted",
    "Rejection should fill only rows without an existing choice");
  beachChoices[0].value = "";
  beachChoices[1].value = "rejected";
  beachChoices[0].listeners.change();
  assert(beach.children.some(child => child.textContent === "1 de 2 álbumes con una decisión."),
    "Clearing a choice should update the count before saving");
  acceptPending.listeners.click();
  assert(beachChoices.map(control => control.value).join() === "accepted,rejected",
    "Acceptance should leave an existing rejection intact");
  assert(beach.children.some(child => child.textContent === "2 de 2 álbumes con una decisión."),
    "Filling the remaining choices should update the count before saving");
  assert(posts.length === 0, "Filling the group must not write until Save");
  const familyChoices = selectValues(family);
  assert(familyChoices.every(control => !control.value), "A different group must remain untouched");
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

  await action(restoredFamily.children.filter(child => child.props?.class === "batch-review-row")[1], "Revisar");
  const detail = content.children.at(-1);
  assert(detail.querySelectorAll().some(control => control.children[0] === "Guardar y volver al lote"),
    "The individual save should return to the batch");
  selectValues(detail)[0].value = "accepted";
  await submit(detail);
  assert(detailPosts.length === 1 && detailPosts[0].id === 2 && detailPosts[0].decisions.familia === "familia",
    "The individual save should affect only the selected album");
  assert(posts.length === 2 && selectValues(content.children[0])[0].value === "rejected",
    "After the correction, return to the batch with decisions on the other albums still selected");

  results.classList = { toggle() {} };
  renderFolders([{ ...album(4, 0), reason: "" }], false, () => { browser.refreshCount++; });
  const openResult = () => results.children[0].listeners.click();
  await openResult();
  assert(browser.view === "album-review", "A family search result should open the individual album");
  await action(content, "Volver a resultados");
  assert(browser.view === "archive" && browser.refreshCount === 1 && detailPosts.length === 1,
    "Returning to the same search should refresh its results without saving a draft");

  await openResult();
  const resultEditor = content.children.at(-1);
  assert(resultEditor.querySelectorAll().some(control => control.children[0] === "Guardar y volver a resultados"),
    "The search result editor should offer to save and return");
  selectValues(resultEditor)[0].value = "rejected";
  await submit(resultEditor);
  assert(browser.view === "archive" && browser.refreshCount === 2 && detailPosts.length === 2
    && detailPosts[1].id === 4 && detailPosts[1].decisions.familia === null,
    "Saving the album should refresh the same search after the correction");
}

const source = readFileSync("src/chromantis/api/ui/app.js", "utf8");
verifyBatchReview(source).then(() => verifyBatchReview(source, 2)).then(() => {
  console.log("Album review UI regression checks passed.");
}).catch(error => {
  console.error(error);
  process.exitCode = 1;
});
