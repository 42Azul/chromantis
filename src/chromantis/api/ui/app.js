const $ = id => document.getElementById(id);
const views = ["archive", "people", "searches", "admin"];
const photoURLs = new Set();
let token = "";
let principal;
let pinnedOnly = false;
let requestNumber = 0;
let connectionNumber = 0;
let photoRequests;

function element(tag, attributes = {}, ...children) {
  const node = document.createElement(tag);
  for (const [key, value] of Object.entries(attributes)) node.setAttribute(key, value);
  node.append(...children);
  return node;
}

function button(label, action, className = "") {
  const node = element("button", { type: "button", class: className }, label);
  node.addEventListener("click", action);
  return node;
}

function message(id, text = "") {
  $(id).textContent = text;
}

async function api(path, { method = "GET", data, signal, raw = false } = {}) {
  const headers = { Authorization: `Bearer ${token}` };
  if (data !== undefined) headers["Content-Type"] = "application/json";
  const response = await fetch(`/api/v1${path}`, {
    method, headers, signal, cache: "no-store",
    body: data === undefined ? undefined : JSON.stringify(data),
  });
  if (!response.ok) {
    const payload = await response.json().catch(() => ({}));
    const error = new Error(payload.error || `Request failed (${response.status}).`);
    error.status = response.status;
    throw error;
  }
  return raw ? response.blob() : response.json();
}

function queryParams(values) {
  return `?${new URLSearchParams(values)}`;
}

function isAdmin() {
  return ["owner", "admin"].includes(principal?.role);
}

function resetPhotos() {
  photoRequests?.abort();
  photoRequests = new AbortController();
  for (const url of photoURLs) URL.revokeObjectURL(url);
  photoURLs.clear();
  if ($("lightbox").open) $("lightbox").close();
}

function signOut() {
  token = "";
  principal = undefined;
  requestNumber++;
  connectionNumber++;
  sessionStorage.removeItem("chromantis.chatToken");
  resetPhotos();
  for (const view of views) $(view).hidden = true;
  for (const id of ["results", "browsing", "statistics", "people-list", "add-person", "saved-list", "admin-content"]) {
    $(id).replaceChildren();
  }
  $("person-details").replaceChildren(element("h2", {}, "Person details"),
    element("p", {}, "Select a person to see their folders."));
  $("year").replaceChildren(element("option", { value: "" }, "All years"));
  $("search-form").reset();
  message("result-count");
  message("archive-status");
  message("results-title", "Results");
  $("navigation").hidden = true;
  $("connection").hidden = true;
  $("sign-in").hidden = false;
  $("token").focus();
}

async function signIn(value) {
  token = value;
  const connection = ++connectionNumber;
  const initialRequest = requestNumber;
  message("login-error");
  try {
    const { item } = await api("/auth/me");
    if (connection !== connectionNumber) return;
    principal = item;
    sessionStorage.setItem("chromantis.chatToken", token);
    $("token").value = "";
    $("sign-in").hidden = true;
    $("navigation").hidden = false;
    $("connection").hidden = false;
    $("admin-nav").hidden = !isAdmin();
    $("account").textContent = principal.first_name || principal.username || `Chat ${principal.chat_id}`;
    $("account-role").textContent = principal.role;
    await showView("archive");
    Promise.all([api("/stats"), api("/years")]).then(([{ item }, { items }]) => {
      if (connection !== connectionNumber) return;
      $("statistics").replaceChildren(...Object.entries({
        Photos: item.images, Folders: item.folders, Years: items.length,
      }).map(([label, count]) => element("div", { class: "stat" },
        element("strong", {}, count.toLocaleString()), element("span", {}, label))));
      $("year").replaceChildren(element("option", { value: "" }, "All years"),
        ...items.map(({ year }) => element("option", { value: year }, String(year))));
    }).catch(error => message("archive-status", error.message));

    if (token === value) {
      try {
        const batch = await api("/browse");
        if (requestNumber === initialRequest && connection === connectionNumber) renderBatch(batch);
      } catch (error) {
        if (requestNumber !== initialRequest || connection !== connectionNumber) return;
        if (error.status !== 404) message("archive-status", error.message);
        else message("archive-status", "Enter a search or choose a year to get started.");
      }
    }
  } catch (error) {
    if (connection !== connectionNumber) return;
    signOut();
    message("login-error", error.status === 401 ? "That chat token could not be verified." : error.message);
  }
}

async function showView(view) {
  if (!principal || (view === "admin" && !isAdmin())) return;
  for (const name of views) $(name).hidden = name !== view;
  for (const nav of document.querySelectorAll("[data-view]")) {
    if (nav.dataset.view === view) nav.setAttribute("aria-current", "page");
    else nav.removeAttribute("aria-current");
  }
  try {
    if (view === "people") await loadPeople();
    if (view === "searches") await loadSearches();
    if (view === "admin") await loadAdmin();
  } catch (error) {
    message(`${view}-status`, error.message);
  }
}

async function archiveRequest(action, arguments_ = {}) {
  const request = ++requestNumber;
  message("archive-status", "Loading…");
  try {
    if (action === "folders") {
      const { items } = await api("/folders" + queryParams({ q: arguments_.q, limit: 30 }));
      if (request === requestNumber) renderFolders(items);
    } else {
      const batch = await api("/browse", { method: "POST", data: { action, ...arguments_ } });
      if (request === requestNumber) {
        if (batch.items.length === 0 && ["more", "same_folder", "same_year", "related"].includes(action)) {
          message("archive-status", "No more photos in that selection.");
        } else renderBatch(batch);
      }
    }
  } catch (error) {
    if (request === requestNumber) message("archive-status", error.message);
  }
}

function renderFolders(items) {
  resetPhotos();
  message("archive-status", items.length ? "" : "No matching folders.");
  $("results-title").textContent = "Folders";
  $("result-count").textContent = `${items.length} shown`;
  $("browsing").replaceChildren();
  $("results").replaceChildren(...items.map(item => {
    const card = button("", () => archiveRequest("open_folder", { folder: item.path }), "folder-card");
    card.append(element("strong", {}, item.title), element("span", {}, item.path));
    return card;
  }));
}

function renderBatch(batch) {
  resetPhotos();
  message("archive-status", batch.items.length ? "" : "No matching photos.");
  $("results-title").textContent = "Photos";
  $("result-count").textContent = `${batch.items.length} shown`;
  const signal = photoRequests.signal;
  const cards = batch.items.map(item => photoCard(item, signal));
  $("results").replaceChildren(...cards);
  const actions = [];
  if (batch.items.length) {
    actions.push(button("More photos", () => archiveRequest("more")));
    if (batch.folders.length === 1) {
      actions.push(button("Same folder", () => archiveRequest("same_folder")));
    } else if (batch.folders.length > 1) {
      const pick = element("select", { "aria-label": "Browse a folder in this batch" },
        element("option", { value: "" }, "Jump to folder"), ...batch.folders.map(path =>
          element("option", { value: path }, path)));
      pick.addEventListener("change", () => pick.value && archiveRequest("open_folder", { folder: pick.value }));
      actions.push(pick);
    }
    if (batch.years.length === 1) actions.push(button("Same year", () => archiveRequest("same_year")));
    if (batch.folders.length === 1 && batch.years.length === 1) {
      actions.push(button("Related photos", () => archiveRequest("related")));
    }
  }
  if (batch.can_go_back) actions.push(button("Previous batch", () => archiveRequest("back")));
  $("browsing").replaceChildren(...actions);
}

function photoCard(item, signal) {
  const filename = item.path.split("/").at(-1);
  let sourceURL;
  const frame = button("Loading photo…", () => {
    if (!sourceURL) return;
    const box = $("lightbox");
    box.querySelector("img").src = sourceURL;
    box.querySelector("img").alt = item.title;
    box.querySelector("p").textContent = item.path;
    box.showModal();
  }, "frame");
  frame.setAttribute("aria-label", `Open ${filename}`);
  frame.disabled = true;
  const image = element("img", { alt: filename, decoding: "async" });
  image.addEventListener("load", () => {
    frame.replaceChildren(image);
    frame.disabled = false;
  });
  image.addEventListener("error", () => { frame.textContent = "Preview unavailable"; });
  const observer = new IntersectionObserver(entries => {
    if (!entries.some(entry => entry.isIntersecting)) return;
    observer.disconnect();
    api("/image" + queryParams({ path: item.path }), { raw: true, signal }).then(blob => {
      if (signal.aborted) return;
      sourceURL = URL.createObjectURL(blob);
      photoURLs.add(sourceURL);
      image.src = sourceURL;
    }).catch(() => { frame.textContent = "Preview unavailable"; });
  }, { rootMargin: "120px" });
  signal.addEventListener("abort", () => observer.disconnect(), { once: true });
  observer.observe(frame);
  return element("article", { class: "photo-card" }, frame,
    element("div", { class: "card-caption" }, element("h3", {}, filename),
      element("p", {}, item.folder_path || String(item.year)), element("p", {}, item.reason)));
}

function inlineForm(label, input, buttonText, submit, statusID) {
  const form = element("form", { class: "inline-form" },
    element("label", {}, label, input), element("button", { type: "submit" }, buttonText));
  form.addEventListener("submit", async event => {
    event.preventDefault();
    const submitButton = form.querySelector("button");
    submitButton.disabled = true;
    message(statusID);
    try {
      await submit(input.value.trim());
    } catch (error) {
      message(statusID, error.message);
    } finally {
      submitButton.disabled = false;
    }
  });
  return form;
}

function textInput(value = "") {
  return element("input", { value, required: "", maxlength: "240" });
}

function options(values, selected) {
  const select = element("select");
  for (const value of values) select.append(element("option", { value }, value));
  select.value = selected;
  return select;
}

async function loadPeople() {
  message("people-status");
  const { items } = await api("/people");
  if (!principal) return;
  $("people-list").replaceChildren(...items.map(person => button(person.display_name,
    () => loadPerson(person.id).catch(error => message("people-status", error.message)))));
  if (!items.length) $("people-list").append(element("p", {}, "No people have been added."));
  $("add-person").replaceChildren();
  if (isAdmin()) $("add-person").append(inlineForm("Display name", textInput(), "Add person", async display_name => {
    const { item } = await api("/admin/people", { method: "POST", data: { display_name } });
    await loadPeople();
    showPerson(item);
  }, "people-status"));
}

async function loadPerson(id) {
  const { item } = await api(`/people/${id}`);
  if (principal) showPerson(item);
}

function showPerson(person) {
  const detail = $("person-details");
  const base = `/admin/people/${person.id}`;
  const folders = element("div", { class: "stack" });
  detail.replaceChildren(element("h2", {}, person.display_name),
    element("p", {}, person.aliases.length ? `Aliases · ${person.aliases.join(", ")}` : "No aliases"),
    element("h3", {}, "Linked folders"), folders);
  if (!person.folder_paths.length) folders.append(element("p", {}, "No folders are linked."));
  for (const path of person.folder_paths) {
    const open = button(path, async () => {
      await showView("archive");
      await archiveRequest("open_folder", { folder: path });
    });
    const row = element("div", { class: "list-row" }, open);
    if (isAdmin()) row.append(button("Unlink", async () => {
      try {
        const { item } = await api(base + "/folders" + queryParams({ path }), { method: "DELETE" });
        showPerson(item);
      } catch (error) { message("people-status", error.message); }
    }));
    folders.append(row);
  }
  if (!isAdmin()) return;
  detail.append(
    inlineForm("Display name", textInput(person.display_name), "Rename", async display_name => {
      const { item } = await api(base, { method: "PATCH", data: { display_name } });
      await loadPeople();
      showPerson(item);
    }, "people-status"),
    inlineForm("New alias", textInput(), "Add alias", async alias => {
      const { item } = await api(base + "/aliases", { method: "POST", data: { alias } });
      showPerson(item);
    }, "people-status"),
    inlineForm("Indexed folder path", textInput(), "Link folder", async path => {
      const { item } = await api(base + "/folders", { method: "POST", data: { path } });
      showPerson(item);
    }, "people-status"),
  );
}

async function loadSearches() {
  message("searches-status");
  const { items } = await api("/searches" + queryParams({ pinned: String(pinnedOnly), limit: 50 }));
  if (!principal) return;
  $("recent").setAttribute("aria-pressed", String(!pinnedOnly));
  $("pinned").setAttribute("aria-pressed", String(pinnedOnly));
  $("saved-list").replaceChildren(...items.map(search => {
    const actions = element("div", { class: "actions" },
      button("Run", async () => {
        await showView("archive");
        $("query").value = search.query;
        $("year").value = "";
        $("scope").value = search.kind === "folders" ? "folders" : "images";
        const action = search.kind === "images" ? "search" : search.kind;
        await archiveRequest(action, { q: search.query, count: search.count });
      }),
      button(search.pinned ? "Unpin" : "Pin", async () => {
        try {
          await api(`/searches/${search.id}`, { method: "PATCH", data: { pinned: !search.pinned } });
          await loadSearches();
        } catch (error) { message("searches-status", error.message); }
      }));
    return element("div", { class: "list-row" },
      element("div", {}, element("strong", {}, search.query), element("p", {}, search.kind)), actions);
  }));
  if (!items.length) message("searches-status", pinnedOnly ? "No pinned searches yet." : "No recent searches yet.");
}

function definitionList(values) {
  return element("dl", { class: "kv" }, ...Object.entries(values).flatMap(([key, value]) =>
    [element("dt", {}, key), element("dd", {}, String(value))]));
}

function panel(title, ...items) {
  return element("section", { class: "panel" }, element("h2", {}, title), ...items);
}

function adminAction(action, feedback) {
  return async () => {
    try {
      await action();
      await loadAdmin();
      message("admin-status", feedback);
    } catch (error) { message("admin-status", error.message); }
  };
}

async function loadAdmin() {
  message("admin-status");
  const [chats, invites, config, sync, preferences] = await Promise.all([
    api("/admin/chats"), api("/admin/invites"), api("/admin/config"), api("/sync/runs?limit=3"),
    api("/auth/preferences"),
  ]);
  if (!isAdmin()) return;
  const owner = principal.role === "owner";
  const chatList = element("div", { class: "stack" });
  for (const chat of chats.items) {
    const name = chat.first_name || chat.username || String(chat.chat_id);
    const controls = element("div", { class: "actions" });
    if (chat.auth_mode === "dynamic" && chat.chat_id !== principal.chat_id) {
      if (owner) {
        const select = options(["viewer", "admin", "owner"], chat.role);
        select.setAttribute("aria-label", `Role for ${name}`);
        select.addEventListener("change", adminAction(
          () => api(`/admin/chats/${chat.chat_id}`, { method: "PATCH", data: { role: select.value } }),
          "Chat role updated.",
        ));
        controls.append(select);
      }
      if (owner || chat.role === "viewer") controls.append(button("Revoke", adminAction(async () => {
        if (!window.confirm(`Revoke access for ${name}?`)) throw new Error("Access unchanged.");
        await api(`/admin/chats/${chat.chat_id}`, { method: "DELETE" });
      }, "Chat access revoked."), "danger"));
    }
    chatList.append(element("div", { class: "list-row" }, element("div", {},
      element("strong", {}, name), element("p", {}, `${chat.role} · ${chat.auth_mode}`)), controls));
  }

  const inviteList = element("div", { class: "stack" });
  for (const invite of invites.items) {
    const expiry = new Date(invite.expires_at).toLocaleDateString();
    inviteList.append(element("div", { class: "list-row" }, element("div", {},
      element("strong", {}, invite.code), element("p", {}, `${invite.role} · Expires ${expiry}`)),
      button("Revoke", adminAction(() => api(`/admin/invites/${invite.code}`, { method: "DELETE" }),
        "Invitation revoked."), "danger")));
  }
  if (!invites.items.length) inviteList.append(element("p", {}, "No active invitations."));
  const createInvite = inlineForm("Invitation role", options(owner ? ["viewer", "admin"] : ["viewer"], "viewer"),
    "Create invitation", async role => {
      const { item } = await api("/admin/invites", { method: "POST", data: { role } });
      await loadAdmin();
      message("admin-status", `Invitation ${item.code} created. Redeem it in Telegram with /login.`);
    }, "admin-status");

  const info = config.item;
  const language = options(["en", "es"], preferences.item.language || "en");
  const preference = inlineForm("Telegram language", language, "Save", async value => {
    await api("/auth/preferences", { method: "PATCH", data: { language: value } });
    message("admin-status", "Language saved.");
  }, "admin-status");
  const syncList = element("div", { class: "stack" });
  for (const run of sync.items) {
    const counts = run.summary;
    const time = new Date(run.started_at).toLocaleString();
    syncList.append(element("div", { class: "list-row" }, element("div", {},
      element("strong", {}, `${run.mode} · ${run.status}`), element("p", {}, time),
      element("p", {}, counts ? `${counts.images_indexed} indexed · ${counts.unchanged_images} unchanged · ${counts.deleted_images} removed` : run.error || ""))));
  }
  if (!sync.items.length) syncList.append(element("p", {}, "No indexing runs have been recorded."));
  $("admin-content").replaceChildren(
    panel("Authorized chats", chatList), panel("Invitations", inviteList, createInvite),
    panel("Configuration", definitionList({
      "Archive source": info.source_type || "Unknown",
      "Query interpreter": info.query_interpreter || "rules",
      "Enrichment search": info.enrichment_search ? "Enabled" : "Disabled",
    }), preference),
    panel("Recent indexing runs", syncList),
  );
}

$("login-form").addEventListener("submit", async event => {
  event.preventDefault();
  const submit = event.currentTarget.querySelector("button");
  submit.disabled = true;
  await signIn($("token").value.trim());
  submit.disabled = false;
});
$("disconnect").addEventListener("click", signOut);
$("search-form").addEventListener("submit", event => {
  event.preventDefault();
  const year = $("year").value;
  const text = $("query").value.trim();
  const keywords = year ? text.replace(/\b(?:19|20)\d{2}(?:\s*[-–]\s*(?:19|20)\d{2})?\b/g, "").trim() : text;
  const q = [keywords, year].filter(Boolean).join(" ");
  archiveRequest($("scope").value === "folders" ? "folders" : "search", { q });
});
$("random").addEventListener("click", () => archiveRequest("random", { q: $("year").value }));
$("recent").addEventListener("click", () => { pinnedOnly = false; showView("searches"); });
$("pinned").addEventListener("click", () => { pinnedOnly = true; showView("searches"); });
for (const tab of document.querySelectorAll("[data-view]")) {
  tab.addEventListener("click", () => showView(tab.dataset.view));
}

const rememberedToken = sessionStorage.getItem("chromantis.chatToken");
if (rememberedToken) signIn(rememberedToken);
