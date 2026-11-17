const $ = id => document.getElementById(id);
const views = ["archive", "people", "album-review", "searches", "collections", "admin"];
const sharedSecret = decodeURIComponent(location.pathname.match(/^\/share\/([A-Za-z0-9_-]{43})$/)?.[1] || "");
const photoURLs = new Set();
let token = "";
let principal;
let pinnedOnly = false;
let requestNumber = 0;
let connectionNumber = 0;
let photoRequests;
let canCurateAlbums = false;
let albumRequest = 0;
let albumPhotoRequests;
const albumPhotoURLs = new Set();
let indexStatus;
let archiveSearch;
let collectionPick;
let collectionRequest = 0;
let originalRequest;
let originalURL;

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
  const connection = connectionNumber;
  const headers = token ? { Authorization: `Bearer ${token}` } : {};
  if (data !== undefined) headers["Content-Type"] = "application/json";
  const response = await fetch(`/api/v1${path}`, {
    method, headers, signal, cache: "no-store",
    body: data === undefined ? undefined : JSON.stringify(data),
  });
  if (!response.ok) {
    const payload = await response.json().catch(() => ({}));
    if (response.status === 401 && connection === connectionNumber && principal?.auth_mode === "family") {
      signOut();
      $("family-sign-in").open = true;
      message("family-login-error", "La sesión familiar ha caducado. Pide otro código para volver a entrar.");
    }
    const error = new Error(payload.error || `Request failed (${response.status}).`);
    error.status = response.status;
    error.code = payload.code;
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

function isOwner() {
  return principal?.role === "owner";
}

function resetPhotos() {
  photoRequests?.abort();
  photoRequests = new AbortController();
  for (const url of photoURLs) URL.revokeObjectURL(url);
  photoURLs.clear();
  if ($("lightbox").open) $("lightbox").close();
}

async function createAlbumShare(path) {
  const { item } = await api("/album-shares", { method: "POST", data: { path, ttl_days: 7 } });
  const url = new URL(item.url, location.href).href;
  const output = $("share-output");
  const link = element("a", { href: url }, url);
  const copy = button("Copy link", async () => {
    try {
      await navigator.clipboard.writeText(url);
      copy.textContent = "Copied";
    } catch {
      link.focus();
    }
  });
  const revoke = button("Revoke", async () => {
    await api(`/album-shares/${item.id}`, { method: "DELETE" });
    output.hidden = true;
    output.replaceChildren();
  }, "danger");
  output.hidden = false;
  output.replaceChildren(element("strong", {}, "Private album link"), link,
    element("p", {}, `Expires ${new Date(item.expires_at).toLocaleString()}`),
    element("div", { class: "actions" }, copy, revoke));
  output.scrollIntoView({ behavior: "smooth", block: "nearest" });
}

async function showAlbumShares(path, title) {
  const { items } = await api("/album-shares" + queryParams({ path }));
  const output = $("share-output");
  const active = element("div", { class: "stack" }, ...items.map(item =>
    element("div", { class: "list-row" },
      element("div", {}, element("strong", {}, "Active private link"),
        element("p", {}, `Expires ${new Date(item.expires_at).toLocaleString()}`)),
      button("Revoke", async () => {
        await api(`/album-shares/${item.id}`, { method: "DELETE" });
        await showAlbumShares(path, title);
      }, "danger"))));
  if (!items.length) active.append(element("p", {}, "No active links for this album."));
  output.hidden = false;
  output.replaceChildren(element("h3", {}, `Share ${title}`), active,
    button("Create 7-day link", () => createAlbumShare(path).catch(error =>
      message("archive-status", error.message)), "primary"));
  output.scrollIntoView({ behavior: "smooth", block: "nearest" });
}

async function loadSharedAlbum(offset = 0) {
  document.body.classList.add("shared-view");
  $("sign-in").hidden = true;
  $("shared-album").hidden = false;
  message("shared-status", "Cargando álbum…");
  try {
    const response = await fetch(`/api/v1/shared/${sharedSecret}?limit=30&offset=${offset}`,
      { cache: "no-store" });
    const payload = await response.json();
    if (!response.ok) throw new Error(payload.error || "No se pudo abrir el álbum.");
    message("shared-title", payload.item.title);
    const meta = [];
    if (payload.item.event_date) {
      const date = new Date(`${payload.item.event_date}T12:00:00`);
      meta.push(new Intl.DateTimeFormat("es", { dateStyle: "long" }).format(date));
    } else if (payload.item.year) meta.push(String(payload.item.year));
    if (payload.item.place) meta.push(payload.item.place);
    meta.push(`Disponible hasta ${new Date(payload.item.expires_at).toLocaleDateString("es")}`);
    $("shared-meta").replaceChildren(...meta.map(value => element("span", {}, value)));
    message("shared-note", payload.item.note || "");
    $("shared-note").hidden = !payload.item.note;
    message("shared-status", payload.items.length ? "" : "Este álbum no contiene fotos indexadas.");
    $("shared-photos").replaceChildren(...payload.items.map((item, index) => {
      const filename = item.filename;
      const base = `/api/v1/shared/${sharedSecret}`;
      const original = base + "/image" + queryParams({ path: item.path });
      const cover = offset === 0 && index === 0;
      const preview = payload.thumbnails
        ? element("img", {
          src: base + "/thumbnail" + queryParams({ path: item.path }), alt: filename,
          loading: cover ? "eager" : "lazy", decoding: "async",
        })
        : element("div", { class: "shared-placeholder", role: "img", "aria-label": filename },
          "Vista previa no generada");
      return element("article", { class: `photo-card shared-photo${cover ? " shared-cover" : ""}` },
        element("div", { class: "shared-preview" }, preview),
        element("div", { class: "card-caption" }, element("h3", {}, filename),
          element("a", { class: "shared-original", href: original, target: "_blank", rel: "noreferrer" },
            "Abrir original")));
    }));
    const actions = [];
    if (offset) actions.push(button("Página anterior", () => loadSharedAlbum(Math.max(0, offset - 30))));
    if (payload.has_more) actions.push(button("Página siguiente", () => loadSharedAlbum(offset + 30)));
    $("shared-actions").replaceChildren(...actions);
  } catch (error) {
    message("shared-status", error.message);
    $("shared-photos").replaceChildren();
    $("shared-actions").replaceChildren();
  }
}

function signOut() {
  token = "";
  principal = undefined;
  indexStatus = undefined;
  canCurateAlbums = false;
  requestNumber++;
  connectionNumber++;
  collectionRequest++;
  collectionPick = undefined;
  if ($("collection-picker").open) $("collection-picker").close();
  sessionStorage.removeItem("chromantis.chatToken");
  resetPhotos();
  closeAlbumReview();
  for (const view of views) $(view).hidden = true;
  for (const id of ["results", "browsing", "statistics", "people-list", "add-person", "saved-list",
    "collection-list", "collection-detail", "admin-content"]) {
    $(id).replaceChildren();
  }
  $("person-details").replaceChildren(element("h2", {}, "Person details"),
    element("p", {}, "Select a person to see their folders."));
  $("year").replaceChildren(element("option", { value: "" }, "All years"));
  $("search-form").reset();
  setRecallSearch();
  $("refine-choices").replaceChildren();
  $("timeline-form").reset();
  $("timeline").open = false;
  message("result-count");
  message("archive-status");
  message("album-review-status");
  message("collections-status");
  message("archive-health");
  message("results-title", "Results");
  message("account");
  message("account-role");
  $("navigation").hidden = true;
  $("connection").hidden = true;
  $("sign-in").hidden = false;
  $("token").focus();
}

function setArchiveMode(family) {
  $("archive").lang = family ? "es" : "en";
  $("archive-nav").lang = $("archive").lang;
  $("archive-nav").textContent = family ? "Buscar álbumes" : "Archive";
  message("archive-title", family ? "Buscar álbumes" : "Photo archive");
  message("archive-description", family ? "Busca por nombre, persona o año." : "Search by folder name, person, or year.");
  message("query-label", family ? "Buscar en el archivo" : "Search the archive");
  message("archive-search", family ? "Buscar" : "Search");
  message("results-title", family ? "Álbumes" : "Results");
  message("timeline-label", family ? "Cronología de álbumes" : "Album timeline");
  message("timeline-search", family ? "Ver cronología" : "Show timeline");
  message("place-filter-label", family ? "Lugar" : "Place");
  message("date-from-label", family ? "Desde" : "From");
  message("date-to-label", family ? "Hasta" : "To");
  $("query").placeholder = family ? "Ana, playa, 2024" : "Try beach 2021";
  const scope = $("scope");
  scope.setAttribute("aria-label", family ? "Tipo de resultado" : "Result type");
  scope.replaceChildren(...(family ? [["folders", "Álbumes"], ["confirmed", "Fotos por persona"]]
    : [["images", "Photos"], ["folders", "Folders"]]).map(([value, label]) => element("option", { value }, label)));
  $("confirmed-photo-hint").hidden = true;
  $("timeline").hidden = false;
  for (const id of ["year", "random", "people-nav", "searches-nav"]) $(id).hidden = family;
  $("search-form").classList.toggle("family-search", family);
}

function archiveHealth(offline = false) {
  if (!indexStatus) return;
  const spanish = principal?.auth_mode === "family";
  $("archive-health").lang = spanish ? "es" : "en";
  const parts = [];
  if (offline) parts.push(spanish ? "Archivo no disponible" : "Archive unavailable");
  if (indexStatus.indexed_at) {
    const time = new Date(indexStatus.indexed_at).toLocaleString(spanish ? "es" : undefined);
    parts.push(spanish ? `Último índice: ${time}` : `Last indexed: ${time}`);
  }
  if (!offline && indexStatus.sync_status === "failed") {
    parts.push(spanish ? "La última indexación falló" : "The last indexing run failed");
  }
  message("archive-health", parts.join(" · "));
}

async function signIn(value, { quiet = false, familyLogin = false } = {}) {
  token = value;
  const connection = ++connectionNumber;
  const initialRequest = requestNumber;
  message("login-error");
  try {
    const { item, can_curate_albums } = await api("/auth/me");
    const status = await api("/archive-status").catch(() => null);
    if (connection !== connectionNumber) return;
    principal = item;
    indexStatus = status?.item;
    canCurateAlbums = can_curate_albums;
    if (token) sessionStorage.setItem("chromantis.chatToken", token);
    else sessionStorage.removeItem("chromantis.chatToken");
    const family = principal.auth_mode === "family";
    setArchiveMode(family);
    archiveHealth();
    $("token").value = "";
    $("sign-in").hidden = true;
    $("navigation").hidden = false;
    $("connection").hidden = false;
    $("admin-nav").hidden = !isAdmin();
    $("collections-nav").hidden = !isOwner();
    $("album-review-nav").hidden = !canCurateAlbums;
    $("account").textContent = principal.first_name || principal.username || `Chat ${principal.chat_id}`;
    $("account-role").textContent = family ? "Acceso familiar" : principal.role;
    $("disconnect").textContent = family ? "Cerrar sesión" : "Sign out";
    const initialView = canCurateAlbums && principal.role === "viewer" ? "album-review" : "archive";
    await showView(initialView);
    if (family) return;
    Promise.all([api("/stats"), api("/years")]).then(([{ item }, { items }]) => {
      if (connection !== connectionNumber) return;
      $("statistics").replaceChildren(...Object.entries({
        Photos: item.images, Folders: item.folders, Years: items.length,
      }).map(([label, count]) => element("div", { class: "stat" },
        element("strong", {}, count.toLocaleString()), element("span", {}, label))));
      $("year").replaceChildren(element("option", { value: "" }, "All years"),
        ...items.map(({ year }) => element("option", { value: year }, String(year))));
    }).catch(error => message("archive-status", error.message));

    if (token === value && initialView === "archive" && !$("archive").hidden) {
      try {
        const batch = await api("/browse");
        if (requestNumber === initialRequest && connection === connectionNumber && !$("archive").hidden) {
          if (batch.scope === "search_images") setRecallSearch("search", batch.q, batch.count);
          renderBatch(batch);
        }
      } catch (error) {
        if (requestNumber !== initialRequest || connection !== connectionNumber) return;
        if (error.status !== 404) message("archive-status", error.message);
        else message("archive-status", "Enter a search or choose a year to get started.");
      }
    }
  } catch (error) {
    if (connection !== connectionNumber) return;
    if (quiet && error.status === 401) return;
    signOut();
    if (familyLogin) message("family-login-error", error.message);
    else message("login-error", error.status === 401 ? "That chat token could not be verified." : error.message);
  }
}

async function showView(view, albumOptions) {
  if (!principal || (view === "admin" && !isAdmin()) || (view === "album-review" && !canCurateAlbums)
      || (view === "collections" && !isOwner())) return;
  if (view !== "album-review" && !$("album-review").hidden) closeAlbumReview();
  for (const name of views) $(name).hidden = name !== view;
  for (const nav of document.querySelectorAll("[data-view]")) {
    if (nav.dataset.view === view) nav.setAttribute("aria-current", "page");
    else nav.removeAttribute("aria-current");
  }
  try {
    if (view === "people") await loadPeople();
    if (view === "album-review") await loadAlbumReview(albumOptions);
    if (view === "searches") await loadSearches();
    if (view === "collections") await loadCollections();
    if (view === "admin") await loadAdmin();
  } catch (error) {
    message(`${view}-status`, error.message);
  }
}

async function archiveRequest(action, arguments_ = {}) {
  const request = ++requestNumber;
  const family = principal?.auth_mode === "family";
  $("refine-choices").replaceChildren();
  message("archive-status", family ? "Buscando…" : "Loading…");
  try {
    if (action === "confirmed") {
      const { person, offset = 0 } = arguments_;
      const pageSize = 24;
      const page = await api("/confirmed-images" + queryParams({ person, offset, limit: pageSize }));
      if (request !== requestNumber) return;
      setRecallSearch();
      renderConfirmedPhotos(page, person, offset, pageSize);
    } else if (action === "folders" || action === "timeline") {
      const timeline = action === "timeline";
      const params = timeline ? { ...arguments_, sort: "timeline", limit: 31 } : { q: arguments_.q, limit: 30 };
      if (family && !timeline) params.filters = 1;
      const { items, filters } = await api("/folders" + queryParams(params));
      if (request !== requestNumber) return;
      if (timeline) setRecallSearch();
      else {
        setRecallSearch("folders", filters?.q ?? arguments_.q, undefined, filters?.active);
        if (arguments_.updateInput) $("query").value = filters?.text ?? arguments_.q;
      }
      renderFolders(items.slice(0, 30), timeline, () => archiveRequest(action, arguments_));
      if (timeline) {
        const offset = arguments_.offset || 0;
        if (offset) $("browsing").append(button(family ? "Página anterior" : "Previous page",
          () => archiveRequest("timeline", { ...arguments_, offset: offset - 30 })));
        if (items.length > 30) $("browsing").append(button(family ? "Página siguiente" : "Next page",
          () => archiveRequest("timeline", { ...arguments_, offset: offset + 30 })));
      }
    } else {
      const batch = await api("/browse", { method: "POST", data: { action, ...arguments_ } });
      if (request === requestNumber) {
        if (action === "search") setRecallSearch(action, batch.q, batch.count);
        if (action === "random") setRecallSearch();
        if (batch.items.length === 0 && ["more", "same_folder", "same_year", "related"].includes(action)) {
          message("archive-status", "No more photos in that selection.");
        } else renderBatch(batch);
      }
    }
  } catch (error) {
    if (request === requestNumber) message("archive-status", error.message);
  }
}

function setRecallSearch(action, q, count, filters = []) {
  archiveSearch = q ? { action, q, count } : undefined;
  const family = principal?.auth_mode === "family";
  $("refine-hint").hidden = !archiveSearch;
  message("refine-hint", family ? "Puedes acotar esta búsqueda con «antes de 2020» o «con Ana»."
    : "Refine this search with “before 2020” or “with Ana”.");
  const filterNames = { year: "Año", person: "Persona", album: "Álbum" };
  $("active-search-filters").replaceChildren(...filters.map(filter => {
    const label = `${filterNames[filter.kind]}: ${filter.label}`;
    const remove = button(`${label} ×`, async () => {
      const controls = Array.from($("active-search-filters").children);
      for (const control of controls) control.disabled = true;
      try {
        await archiveRequest("folders", { q: filter.without, updateInput: true });
        if (!remove.isConnected && document.activeElement === document.body) {
          ($("active-search-filters").querySelector("button") || $("archive-search")).focus();
        }
      } finally {
        for (const control of controls) control.disabled = false;
      }
    });
    remove.setAttribute("aria-label", `Quitar filtro de ${label}`);
    return remove;
  }));
}

async function refineArchive(text) {
  const family = principal?.auth_mode === "family";
  const previous = archiveSearch;
  if (!previous) {
    message("archive-status", family ? "Busca primero fotos o álbumes." : "Start a search before refining it.");
    return;
  }
  const request = ++requestNumber;
  $("refine-choices").replaceChildren();
  message("archive-status", family ? "Buscando…" : "Loading…");
  try {
    const { q, choices } = await api("/refine", { method: "POST", data: { q: previous.q, text } });
    if (request !== requestNumber) return;
    if (choices.length) {
      message("archive-status", family ? "¿A qué álbum te refieres?" : "Which album did you mean?");
      $("refine-choices").replaceChildren(...choices.map(item =>
        button(`${item.title} · ${item.path}`, () => refineArchive(`album ${item.path}`))));
      return;
    }
    await archiveRequest(previous.action, previous.count ? { q, count: previous.count } : { q });
  } catch (error) {
    if (request !== requestNumber) return;
    const translations = {
      year: "Escribe un año de cuatro cifras.", year_conflict: "Ese año queda fuera de la búsqueda actual.",
      person: "Ese nombre o alias no figura en Personas.", album: "No se encuentra ese álbum.",
    };
    message("archive-status", (family && translations[error.code]) || error.message);
  }
}

function renderFolders(items, timeline, refresh) {
  const family = principal?.auth_mode === "family";
  resetPhotos();
  message("archive-status", items.length ? "" : family ? "No se han encontrado álbumes." : "No matching folders.");
  $("results-title").textContent = timeline ? (family ? "Cronología" : "Timeline") : (family ? "Álbumes" : "Folders");
  $("result-count").textContent = family ? String(items.length) : `${items.length} shown`;
  $("browsing").replaceChildren();
  $("results").classList.toggle("timeline-results", timeline);
  $("results").replaceChildren(...items.map(item => {
    const card = button("", () => family ? showView("album-review", {
      path: item.path,
      returnTo: {
        label: "Volver a resultados",
        saveLabel: "Guardar y volver a resultados",
        async open() {
          await showView("archive");
          await refresh();
        },
      },
    }) : archiveRequest("open_folder", { folder: item.path }), "folder-card");
    card.append(element("strong", {}, item.title));
    const details = [];
    if (timeline) {
      const sources = family
        ? { album_correction: "fecha corregida", folder_name: "fecha de carpeta", year: "año del índice" }
        : { album_correction: "corrected date", folder_name: "folder date", year: "indexed year" };
      details.push(`${item.event_date || item.year} (${sources[item.event_date_source || "year"]})`);
    }
    if (item.place) details.push(item.place);
    if (details.length) card.append(element("span", {}, details.join(" · ")));
    card.append(element("span", {}, item.path));
    if (/album_alias=|album_title[=~]|year_corrected=/.test(item.reason)) {
      const reason = family ? item.reason
        .replaceAll("album_alias=", "Alias ")
        .replaceAll(/album_title[=~]/g, "Título corregido ")
        .replaceAll("year_corrected=", "Año corregido ") : item.reason;
      card.append(element("small", {}, reason));
    }
    if (!isOwner()) return card;
    return element("article", { class: "collection-card" }, card,
      element("div", { class: "actions" },
        collectionButton("folder", item.path, item.title, "archive-status"),
        button("Share album", () => showAlbumShares(item.path, item.title).catch(error =>
          message("archive-status", error.message)))));
  }));
}

function renderConfirmedPhotos(page, person, offset, pageSize) {
  resetPhotos();
  $("results").classList.remove("timeline-results");
  message("results-title", "Fotos por persona");
  message("result-count", String(page.items.length));
  message("archive-status", page.items.length ? "" : "No hay fotos etiquetadas con ese nombre o alias.");
  $("results").replaceChildren(...page.items.map(item =>
    photoCard(item, photoRequests.signal, { spanish: true, originalOnClick: true })));
  const actions = [];
  if (offset) actions.push(button("Página anterior",
    () => archiveRequest("confirmed", { person, offset: Math.max(0, offset - pageSize) })));
  if (page.next_offset !== null) actions.push(button("Página siguiente",
    () => archiveRequest("confirmed", { person, offset: page.next_offset })));
  $("browsing").replaceChildren(...actions);
}

function renderBatch(batch) {
  resetPhotos();
  $("results").classList.remove("timeline-results");
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
      if (isOwner()) actions.push(collectionButton("folder", batch.folders[0], batch.folders[0], "archive-status"));
      if (canCurateAlbums) actions.push(button("Etiquetar este álbum",
        () => showView("album-review", { path: batch.folders[0] })));
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

async function openPhoto(item, filename, previewURL, fetchOriginal, spanish) {
  const box = $("lightbox");
  const image = box.querySelector("img");
  const download = $("download-original");
  const request = new AbortController();
  originalRequest = request;
  download.hidden = true;
  image.removeAttribute("src");
  image.hidden = !previewURL;
  if (previewURL) image.src = previewURL;
  image.alt = item.title;
  box.querySelector("p").textContent = item.path;
  box.lang = spanish ? "es" : "en";
  message("close-photo", spanish ? "Cerrar" : "Close");
  message("download-original", spanish ? "Descargar original" : "Download original");
  message("original-status", fetchOriginal ? (spanish ? "Cargando original…" : "Loading original…") : "");
  $("photo-dates").replaceChildren();
  box.showModal();
  loadPhotoDates(item.path, request, spanish);
  try {
    if (fetchOriginal) {
      const blob = await api("/image" + queryParams({ path: item.path }), { raw: true, signal: request.signal });
      if (request.signal.aborted || originalRequest !== request || !box.open) return;
      originalURL = URL.createObjectURL(blob);
      image.src = originalURL;
      image.hidden = false;
      archiveHealth();
    }
    download.href = originalURL || previewURL;
    download.download = filename;
    download.hidden = false;
    message("original-status");
  } catch (error) {
    if (request.signal.aborted || originalRequest !== request) return;
    if (error.status === 502) archiveHealth(true);
    message("original-status", spanish ? "No se pudo abrir el original." : "Could not open the original.");
  }
}

async function loadPhotoDates(path, request, spanish) {
  try {
    const { item } = await api("/image-dates" + queryParams({ path }), { signal: request.signal });
    if (request.signal.aborted || originalRequest !== request || !$("lightbox").open) return;
    const dates = {};
    if (item.capture_date) {
      dates[spanish ? "Captura (EXIF)" : "Capture (EXIF)"] = item.capture_date;
    }
    if (item.event_date) {
      const corrected = item.event_date_source === "album_correction";
      const label = corrected ? (spanish ? "Fecha corregida del álbum" : "Corrected album date")
        : (spanish ? "Fecha del álbum (carpeta)" : "Album date (folder name)");
      dates[label] = item.event_date;
      if (corrected && item.indexed_event_date) {
        dates[spanish ? "Fecha de la carpeta" : "Folder date"] = item.indexed_event_date;
      }
    }
    if (item.source_modified_at) {
      dates[spanish ? "Archivo modificado" : "File modified"] =
        new Date(item.source_modified_at).toLocaleString(spanish ? "es" : undefined);
    }
    if (Object.keys(dates).length) $("photo-dates").append(definitionList(dates));
  } catch (error) {
    if (!request.signal.aborted && originalRequest === request) {
      $("photo-dates").replaceChildren();
    }
  }
}

$("lightbox").addEventListener("close", () => {
  originalRequest?.abort();
  originalRequest = undefined;
  if (originalURL) URL.revokeObjectURL(originalURL);
  originalURL = undefined;
  $("download-original").removeAttribute("href");
  $("lightbox").querySelector("img").removeAttribute("src");
  $("photo-dates").replaceChildren();
});

function photoCard(item, signal, { urls = photoURLs, spanish = false, originalOnClick = false } = {}) {
  const filename = item.path.split("/").at(-1);
  const isThumbnail = !!indexStatus?.thumbnails;
  const deferOriginal = originalOnClick && !isThumbnail;
  let previewURL;
  const unavailable = spanish ? "Foto no disponible" : "Preview unavailable";
  const frame = button(deferOriginal ? "Abrir foto" : spanish ? "Cargando foto…" : "Loading photo…",
    () => openPhoto(item, filename, previewURL, isThumbnail || deferOriginal, spanish), "frame");
  frame.setAttribute("aria-label", `${spanish ? "Abrir" : "Open"} ${filename}`);
  const card = element("article", { class: "photo-card" }, frame,
    element("div", { class: "card-caption" }, element("h3", {}, filename),
      ...(spanish ? [] : [element("p", {}, item.folder_path || String(item.year)), element("p", {}, item.reason)])),
    ...(isOwner() ? [collectionButton("image", item.path, filename,
      spanish ? "album-review-status" : "archive-status")] : []));
  if (deferOriginal) return card;
  frame.disabled = true;
  const image = element("img", { alt: filename, decoding: "async" });
  image.addEventListener("load", () => {
    frame.replaceChildren(image);
    frame.disabled = false;
  });
  const failed = error => {
    if (signal.aborted) return;
    if (error?.status === 502) archiveHealth(true);
    frame.textContent = isThumbnail ? (spanish ? "Abrir original" : "Open original") : unavailable;
    frame.disabled = !isThumbnail;
  };
  image.addEventListener("error", failed);
  const observer = new IntersectionObserver(entries => {
    if (!entries.some(entry => entry.isIntersecting)) return;
    observer.disconnect();
    api((isThumbnail ? "/thumbnail" : "/image") + queryParams({ path: item.path }), { raw: true, signal }).then(blob => {
      if (signal.aborted) return;
      previewURL = URL.createObjectURL(blob);
      urls.add(previewURL);
      image.src = previewURL;
    }).catch(failed);
  }, { rootMargin: "120px" });
  signal.addEventListener("abort", () => observer.disconnect(), { once: true });
  observer.observe(frame);
  return card;
}

function closeAlbumReview() {
  albumRequest++;
  albumPhotoRequests?.abort();
  for (const url of albumPhotoURLs) URL.revokeObjectURL(url);
  albumPhotoURLs.clear();
  if ($("lightbox").open) $("lightbox").close();
  $("album-review-content").replaceChildren();
}

function setAlbumReviewMode(mode) {
  $("pending-albums").setAttribute("aria-pressed", String(mode === "pending"));
  $("reviewed-albums").setAttribute("aria-pressed", String(mode === "reviewed"));
  $("batch-albums").setAttribute("aria-pressed", String(mode === "batch"));
}

async function loadAlbumReview({ after = 0, reviewed = false, directory, saved = false, path, returnTo } = {}) {
  closeAlbumReview();
  const request = albumRequest;
  setAlbumReviewMode(path ? "album" : reviewed ? "reviewed" : "pending");
  message("album-review-status", "Cargando álbum…");
  const returnButton = returnTo ? button(returnTo.label, () => returnTo.open(false)) : null;
  if (returnButton) $("album-review-content").append(returnButton);
  try {
    const [{ item }, { items: people }] = await Promise.all([
      api("/album-review" + queryParams(path ? { path } : { after, reviewed })),
      directory ? { items: directory } : api("/album-review/people"),
    ]);
    if (request !== albumRequest) return;
    message("album-review-status", saved ? "Álbum guardado." : "");
    if (item) renderAlbumReview(item, people, reviewed, returnTo, returnButton);
    else $("album-review-content").append(element("p", {},
      path ? "No se encuentra ese álbum." : reviewed ? "No hay más álbumes revisados." : "No hay más álbumes pendientes en esta vuelta."
    ));
  } catch (error) {
    if (request === albumRequest) message("album-review-status", error.message);
  }
}

async function loadAlbumReviewBatch(saved = false, drafts = []) {
  closeAlbumReview();
  const request = albumRequest;
  setAlbumReviewMode("batch");
  message("album-review-status", "Cargando sugerencias…");
  try {
    const { groups } = await api("/album-review/batch?limit=50");
    if (request !== albumRequest) return;
    message("album-review-status", saved ? "Decisiones guardadas." : "");
    if (!groups.length) {
      $("album-review-content").append(element("p", {},
        "No hay sugerencias pendientes para revisar por lotes. Los álbumes ambiguos siguen en Pendientes."));
      if (drafts.length) message("album-review-status", saved
        ? "Decisiones guardadas. Las demás selecciones ya no están pendientes."
        : "Las selecciones anteriores ya no están pendientes.");
      return;
    }
    const renderedRows = [];
    const content = $("album-review-content");
    let saving = false;
    let restored = 0;
    const selected = ({ album, select, label }) => ({
      id: album.id, path: album.path, revision: album.revision,
      label, decision: select.value,
    });
    const openAlbum = album => {
      const pending = renderedRows.filter(row => row.select.value).map(selected);
      return loadAlbumReview({
        path: album.path,
        returnTo: {
          label: "Volver a Por lotes",
          saveLabel: "Guardar y volver al lote",
          open: savedAlbum => loadAlbumReviewBatch(savedAlbum, pending),
        },
      });
    };
    content.replaceChildren(...groups.map(group => {
      const rows = group.albums.map(album => {
        const select = element("select", { "aria-label": `Decisión para ${album.title}` },
          element("option", { value: "" }, "Pendiente"),
          element("option", { value: "accepted" }, "Aceptar"),
          element("option", { value: "rejected" }, "Rechazar"));
        const row = element("div", { class: "batch-review-row" },
          element("div", {}, element("strong", {}, album.title),
            element("p", {}, `${album.event_date || album.year} · encontró «${album.evidence}»`)),
          select, button("Revisar", () => openAlbum(album)));
        const draft = drafts.find(entry => entry.label === group.key && entry.id === album.id &&
          entry.path === album.path && entry.revision === album.revision);
        if (draft) {
          select.value = draft.decision;
          restored++;
        }
        const decisionRow = { album, select, row, label: group.key };
        renderedRows.push(decisionRow);
        return decisionRow;
      });
      const submit = element("button", { class: "primary", type: "submit" }, "Guardar decisiones");
      const status = element("p", { class: "message", "aria-live": "polite" });
      const selectionCount = element("p", { class: "meta", "aria-live": "polite" });
      function updateSelectionCount() {
        const count = rows.filter(row => row.select.value).length;
        selectionCount.textContent = `${count} de ${rows.length} álbumes con una decisión.`;
      }
      function fillPending(decision) {
        for (const { select } of rows) {
          if (!select.value) select.value = decision;
        }
        updateSelectionCount();
      }
      for (const { select } of rows) select.addEventListener("change", updateSelectionCount);
      updateSelectionCount();
      const form = element("form", { class: "panel batch-review-group" },
        element("h3", {}, `Etiqueta sugerida: ${group.label}`),
        element("p", {}, "Decide solo los álbumes claros. Deja el resto pendiente o ábrelo para corregir."),
        ...(rows.length > 1 ? [element("div", { class: "actions" },
          button("Aceptar los pendientes", () => fillPending("accepted")),
          button("Rechazar los pendientes", () => fillPending("rejected")))] : []),
        ...rows.map(row => row.row), selectionCount, element("div", { class: "actions" }, submit), status);
      form.addEventListener("submit", async event => {
        event.preventDefault();
        if (saving) return;
        const items = rows.filter(row => row.select.value).map(selected);
        if (!items.length) {
          status.textContent = "Elige al menos una decisión.";
          return;
        }
        saving = true;
        const controls = content.querySelectorAll("button, select");
        for (const control of controls) control.disabled = true;
        status.textContent = "";
        try {
          await api("/album-review/batch", { method: "POST", data: { items } });
          if (request === albumRequest) {
            const savedIds = new Set(items.map(item => item.id));
            const remaining = renderedRows.filter(row => row.label !== group.key && row.select.value)
              .map(row => {
                const entry = selected(row);
                // The server increments the revision once for each album in this save.
                if (savedIds.has(entry.id)) entry.revision++;
                return entry;
              });
            await loadAlbumReviewBatch(true, remaining);
          }
        } catch (error) {
          if (request === albumRequest) status.textContent = error.message;
        } finally {
          saving = false;
          for (const control of controls) control.disabled = false;
        }
      });
      return form;
    }));
    if (restored < drafts.length) {
      const warning = "Revisa las selecciones que ya no están disponibles o han cambiado.";
      message("album-review-status", saved ? `Decisiones guardadas. ${warning}` : warning);
    }
  } catch (error) {
    if (request !== albumRequest) return;
    message("album-review-status", saved ? "Decisiones guardadas. No se pudo recargar la cola." : error.message);
    $("album-review-content").append(button("Reintentar la carga", () => {
      if (request === albumRequest) return loadAlbumReviewBatch(saved, drafts);
    }));
  }
}

function reviewPersonPicker(people, selected) {
  const filter = element("input", { type: "search", autocomplete: "off", placeholder: "Escribe un nombre o alias" });
  const matches = element("div", { class: "review-people" });
  const chosen = element("div", { class: "actions", "aria-label": "Personas seleccionadas" });
  const fold = text => text.normalize("NFKD").replace(/\p{M}/gu, "").toLowerCase().replace(/[_-]+/g, " ");
  function draw() {
    const query = fold(filter.value.trim());
    const results = query ? people.filter(person => !selected.has(person.id) &&
      [person.display_name, ...person.aliases].some(name => fold(name).includes(query))).slice(0, 8) : [];
    matches.replaceChildren(...results.map(person => button(
      [person.display_name, ...person.aliases].join(" · "), () => {
        selected.add(person.id);
        filter.value = "";
        draw();
        filter.focus();
      }
    )));
    if (query && !results.length) matches.append(element("p", {}, "No hay coincidencias."));
    chosen.replaceChildren(...people.filter(person => selected.has(person.id)).map(person => {
      const remove = button(`${person.display_name} ×`, () => {
        selected.delete(person.id);
        draw();
        filter.focus();
      });
      remove.setAttribute("aria-label", `Quitar a ${person.display_name} del álbum`);
      return remove;
    }));
  }
  filter.addEventListener("input", draw);
  filter.addEventListener("keydown", event => {
    if (event.key === "Enter") {
      event.preventDefault();
      if (matches.querySelectorAll("button").length === 1) matches.querySelector("button").click();
    }
  });
  draw();
  return element("div", { class: "stack" }, chosen, element("label", {}, "Buscar personas", filter), matches);
}

function renderAlbumReview(album, directory, reviewed, returnTo, returnButton) {
  const request = albumRequest;
  const initial = new Set(album.person_ids);
  const selected = new Set(initial);
  const newPerson = element("input", { type: "text", maxlength: 100, autocomplete: "off" });
  const people = element("div", { class: "stack" },
    element("h3", {}, "¿Quién aparece en el álbum?"),
    reviewPersonPicker(directory, selected),
    element("details", {}, element("summary", {}, "Añadir una persona"), element("label", {}, "Nombre", newPerson))
  );
  const photoGrid = element("div", { class: "photo-grid", hidden: "" });
  const photos = button("Ver hasta 3 fotos", async () => {
    if (!photoGrid.hidden) {
      albumPhotoRequests.abort();
      for (const url of albumPhotoURLs) URL.revokeObjectURL(url);
      albumPhotoURLs.clear();
      photoGrid.replaceChildren();
      photoGrid.hidden = true;
      photos.textContent = "Ver hasta 3 fotos";
      return;
    }
    photos.disabled = true;
    albumPhotoRequests = new AbortController();
    const { signal } = albumPhotoRequests;
    try {
      const { items } = await api("/album-review/photos" + queryParams({ path: album.path }), { signal });
      if (signal.aborted) return;
      photoGrid.hidden = false;
      photoGrid.replaceChildren(...items.map(item => photoCard(item, signal, { urls: albumPhotoURLs, spanish: true })));
      if (!items.length) photoGrid.append(element("p", {}, "No hay fotos disponibles."));
      photos.textContent = "Ocultar fotos";
    } catch (error) {
      if (!signal.aborted) message("album-review-status", error.message);
    } finally {
      photos.disabled = false;
    }
  });

  const tags = element("div", { class: "stack" }, element("h3", {}, "Etiquetas"));
  const choices = Object.entries(album.suggestions).map(([key, suggestion]) => {
    const select = element("select", { "aria-label": `Decisión para ${suggestion.label}` },
      ...[["pending", "Pendiente"], ["accepted", "Aceptar"], ["corrected", "Corregir"], ["rejected", "Rechazar"]]
        .filter(([state]) => state !== "pending" || suggestion.state === "pending")
        .map(([value, label]) => element("option", { value }, label)));
    const correction = element("input", {
      type: "text", maxlength: 40, "aria-label": `Etiqueta para ${suggestion.label}`, placeholder: "Nueva etiqueta",
    });
    select.value = suggestion.state;
    if (suggestion.state === "corrected") correction.value = suggestion.tag;
    const update = () => {
      correction.hidden = select.value !== "corrected";
      correction.required = !correction.hidden;
    };
    select.addEventListener("change", update);
    update();
    tags.append(element("div", { class: "review-suggestion" },
      element("span", {}, `${suggestion.label} · del nombre «${suggestion.evidence}»`), select, correction));
    return { key, select, correction };
  });
  if (!choices.length) tags.append(element("p", {}, "El nombre de la carpeta no da pistas claras."));
  if (choices.filter(choice => choice.select.value === "pending").length > 1) {
    const apply = state => {
      for (const { select } of choices) {
        if (select.value === "pending") select.value = state;
      }
    };
    tags.append(element("div", { class: "actions" },
      button("Aceptar las pendientes", () => apply("accepted")),
      button("Rechazar las pendientes", () => apply("rejected"))));
  }
  const manual = element("input", { type: "text", maxlength: 240, placeholder: "romería, familia" });
  const removeTags = album.manual_tags.map(tag => {
    const checkbox = element("input", { type: "checkbox", value: tag });
    tags.append(element("label", { class: "review-checkbox" }, checkbox, `Quitar «${tag}»`));
    return checkbox;
  });
  tags.append(element("details", {}, element("summary", {}, "Añadir etiquetas"),
    element("label", {}, "Una palabra por etiqueta, separadas por comas", manual)));

  const form = element("form", { class: "panel review-form" }, people, tags);
  const next = saved => returnTo ? returnTo.open(saved) : loadAlbumReview({
    after: album.id, reviewed, directory: saved && newPerson.value.trim() ? undefined : directory, saved,
  });
  const save = element("button", { class: "primary", type: "submit" },
    returnTo?.saveLabel || "Guardar y siguiente");
  const skip = returnTo ? null : button("Saltar", () => next(false));
  form.append(element("div", { class: "actions" }, save, ...(skip ? [skip] : [])));
  form.addEventListener("submit", async event => {
    event.preventDefault();
    if (save.disabled) return;
    save.disabled = true;
    const otherAction = returnButton || skip;
    if (otherAction) otherAction.disabled = true;
    const { id, path, revision } = album;
    const decisions = Object.fromEntries(choices.filter(({ select }) => select.value !== "pending")
      .map(({ key, select, correction }) => [key,
        select.value === "accepted" ? key : select.value === "rejected" ? null : correction.value]));
    try {
      await api("/album-review", { method: "POST", data: {
        id, path, revision, decisions, new_person: newPerson.value.trim() || null,
        add_people: [...selected].filter(id => !initial.has(id)),
        remove_people: [...initial].filter(id => !selected.has(id)),
        manual_add: manual.value.split(",").map(tag => tag.trim()).filter(Boolean),
        manual_remove: removeTags.filter(input => input.checked).map(input => input.value),
      } });
      if (request === albumRequest) await next(true);
    } catch (error) {
      if (request === albumRequest) message("album-review-status", error.message);
    } finally {
      save.disabled = false;
      if (otherAction) otherAction.disabled = false;
    }
  });
  const heading = element("h2", {}, album.title);
  const date = element("p", {}, album.event_date || String(album.year));
  $("album-review-content").append(
    element("div", { class: "panel album-heading" }, heading, date, photos, photoGrid,
      albumContextEditor(album, heading, date, request)),
    form
  );
}

function albumContextEditor(album, heading, date, request) {
  const titleInput = element("input", { type: "text", maxlength: 160, placeholder: album.indexed_title });
  const dateInput = element("input", { type: "date" });
  const aliasInput = element("textarea", { rows: 3, maxlength: 647 });
  const noteInput = element("textarea", { rows: 3, maxlength: 500 });
  const placeInput = element("input", { type: "text", maxlength: 120 });
  const submit = element("button", { type: "submit" }, "Guardar detalles");
  const status = element("p", { class: "message", "aria-live": "polite" });
  let revision = album.context_revision;
  function populate(item) {
    titleInput.value = item.title_override || "";
    dateInput.value = item.date_override || "";
    aliasInput.value = item.aliases.join("\n");
    noteInput.value = item.note || "";
    placeInput.value = item.place || "";
  }
  populate(album);
  const form = element("form", { class: "stack album-context" },
    element("p", {}, `Del índice: ${album.indexed_title} · ${album.indexed_date || album.indexed_year}`),
    element("label", {}, "Título corregido", titleInput),
    element("label", {}, "Fecha corregida", dateInput),
    element("p", {}, "Deja vacío el título o la fecha para usar el valor del índice."),
    element("label", {}, "Alias, uno por línea", aliasInput),
    element("label", {}, "Lugar del álbum", placeInput),
    element("label", {}, "Nota del álbum", noteInput), submit, status);
  form.addEventListener("submit", async event => {
    event.preventDefault();
    submit.disabled = true;
    status.textContent = "";
    try {
      const { item } = await api("/album-review/context", { method: "PATCH", data: {
        id: album.id, path: album.path, revision,
        changes: {
          title: titleInput.value, event_date: dateInput.value, note: noteInput.value, place: placeInput.value,
          aliases: aliasInput.value.split("\n").map(alias => alias.trim()).filter(Boolean),
        },
      } });
      if (request !== albumRequest) return;
      revision = item.context_revision;
      heading.textContent = item.title;
      date.textContent = item.event_date || String(item.year);
      populate(item);
      status.textContent = "Detalles guardados.";
    } catch (error) {
      if (request === albumRequest) status.textContent = error.message;
    } finally {
      submit.disabled = false;
    }
  });
  return element("details", {}, element("summary", {}, "Detalles del álbum"), form);
}

$("pending-albums").addEventListener("click", () => loadAlbumReview());
$("reviewed-albums").addEventListener("click", () => loadAlbumReview({ reviewed: true }));
$("batch-albums").addEventListener("click", () => loadAlbumReviewBatch());

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

function collectionButton(kind, path, title, status) {
  const label = kind === "folder" ? "Add album to collection" : "Add photo to collection";
  const save = button(label, () => openCollectionPicker({ kind, path }, status), "collection-save");
  save.setAttribute("aria-label", `${label}: ${title}`);
  return save;
}

function updateCollectionPicker() {
  const creates = !$("collection-selection").value;
  $("collection-name-label").hidden = !creates;
  $("collection-name").required = creates;
}

async function openCollectionPicker(entry = null, status = "collections-status") {
  if (!isOwner()) return;
  const pick = { entry, status };
  collectionPick = pick;
  $("collection-picker-form").reset();
  $("collection-selection").replaceChildren(element("option", { value: "" }, "New collection"));
  $("collection-selection-label").hidden = !entry;
  $("save-collection").disabled = !!entry;
  message("collection-picker-title", entry ? "Add to collection" : "New collection");
  message("collection-picker-status");
  updateCollectionPicker();
  $("collection-picker").showModal();
  if (!entry) return;
  try {
    const { items } = await api("/collections");
    if (collectionPick !== pick) return;
    $("collection-selection").prepend(...items.map(item => element("option", { value: item.id }, item.name)));
    $("collection-selection").selectedIndex = 0;
    updateCollectionPicker();
    $("save-collection").disabled = false;
  } catch (error) {
    if (collectionPick === pick) message("collection-picker-status", error.message);
  }
}

$("collection-selection").addEventListener("change", updateCollectionPicker);
$("new-collection").addEventListener("click", () => openCollectionPicker());
$("cancel-collection-picker").addEventListener("click", () => $("collection-picker").close());
$("collection-picker").addEventListener("close", () => {
  collectionPick = undefined;
  $("collection-selection").replaceChildren();
  $("collection-name").value = "";
  message("collection-picker-status");
});
$("collection-picker-form").addEventListener("submit", async event => {
  event.preventDefault();
  const pick = collectionPick;
  if (!pick || !isOwner()) return;
  const selected = $("collection-selection").value;
  const name = $("collection-name").value.trim();
  $("save-collection").disabled = true;
  message("collection-picker-status");
  try {
    const existing = pick.entry && selected;
    const data = existing ? pick.entry : { name, ...(pick.entry ? { entry: pick.entry } : {}) };
    const { item } = await api(existing ? `/collections/${selected}/entries` : "/collections", {
      method: "POST", data,
    });
    if (collectionPick !== pick) return;
    $("collection-picker").close();
    if (!pick.entry) await loadCollections(item.id);
    message(pick.status, pick.entry ? `Saved to ${item.name}.` : "Collection created.");
  } catch (error) {
    if (collectionPick === pick) message("collection-picker-status", error.message);
  } finally {
    if (collectionPick === pick) $("save-collection").disabled = false;
  }
});

async function loadCollections(selectedId) {
  const request = ++collectionRequest;
  message("collections-status");
  try {
    const { items } = await api("/collections");
    if (request !== collectionRequest || !isOwner()) return;
    const selected = items.find(item => item.id === selectedId) || items[0];
    $("collection-list").replaceChildren(...items.map(item => {
      const link = button(`${item.name} · ${item.count}`, () => loadCollections(item.id));
      link.setAttribute("aria-pressed", String(item.id === selected?.id));
      return link;
    }));
    $("collection-detail").replaceChildren();
    if (!selected) {
      $("collection-list").append(element("p", {}, "No collections yet."));
      return;
    }
    const { item } = await api(`/collections/${selected.id}`);
    if (request !== collectionRequest || !isOwner()) return;
    renderCollection(item, request);
  } catch (error) {
    if (request === collectionRequest && isOwner()) message("collections-status", error.message);
  }
}

function renderCollection(collection, request) {
  const base = `/collections/${collection.id}`;
  const remove = (path, select) => async event => {
    const control = event.currentTarget;
    control.disabled = true;
    try {
      await api(path, { method: "DELETE" });
      if (request === collectionRequest) await loadCollections(select);
    } catch (error) {
      if (request === collectionRequest) message("collections-status", error.message);
    } finally {
      control.disabled = false;
    }
  };
  const rows = collection.entries.map(entry => {
    const label = entry.kind === "folder" ? "Album" : "Photo";
    const actions = element("div", { class: "actions" });
    if (entry.available) actions.append(button(`Open ${label.toLowerCase()}`, async () => {
      if (entry.kind === "folder") {
        await showView("archive");
        await archiveRequest("open_folder", { folder: entry.path });
      } else {
        await openPhoto(entry, entry.path.split("/").at(-1), undefined, true, false);
      }
    }));
    const removeEntry = button("Remove", remove(`${base}/entries/${entry.id}`, collection.id));
    removeEntry.setAttribute("aria-label", `Remove ${label.toLowerCase()}: ${entry.title}`);
    actions.append(removeEntry);
    return element("div", { class: "list-row" }, element("div", {},
      element("strong", {}, entry.title),
      element("p", {}, entry.available ? label : `${label} · Missing from index`),
      element("p", {}, entry.path)), actions);
  });
  $("collection-detail").replaceChildren(element("h2", {}, collection.name),
    rows.length ? element("div", { class: "stack" }, ...rows)
      : element("p", {}, "Add photos or albums from the archive."),
    button("Delete collection", event => {
      if (window.confirm(`Delete “${collection.name}”?`)) return remove(base)(event);
    }, "danger"));
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
      element("strong", {}, `#${run.id} · ${run.mode} · ${run.status}`), element("p", {}, time),
      element("p", {}, counts ? `${counts.images_indexed} indexed · ${counts.unchanged_images} unchanged · ${counts.deleted_images} removed` : run.error || ""))));
  }
  if (!sync.items.length) syncList.append(element("p", {}, "No indexing runs have been recorded."));
  const syncActions = element("div", { class: "actions" },
    button("Refresh status", adminAction(async () => {}, "Index status refreshed.")));
  if (owner && info.incremental_index) {
    syncActions.prepend(button("Find new folders", async event => {
      const start = event.currentTarget;
      start.disabled = true;
      try {
        const { item } = await api("/sync/runs", { method: "POST" });
        await loadAdmin();
        message("admin-status", `Index scan #${item.id} started. Refresh status to check it.`);
      } catch (error) {
        message("admin-status", error.message);
      } finally {
        start.disabled = false;
      }
    }, "primary"));
  }
  $("admin-content").replaceChildren(
    panel("Authorized chats", chatList), panel("Invitations", inviteList, createInvite),
    panel("Configuration", definitionList({
      "Archive source": info.source_type || "Unknown",
      "Query interpreter": info.query_interpreter || "rules",
      "Enrichment search": info.enrichment_search ? "Enabled" : "Disabled",
    }), preference),
    panel("Recent indexing runs", syncActions, syncList),
  );
}

$("login-form").addEventListener("submit", async event => {
  event.preventDefault();
  const submit = event.currentTarget.querySelector("button");
  submit.disabled = true;
  await signIn($("token").value.trim());
  submit.disabled = false;
});
$("family-login-form").addEventListener("submit", async event => {
  event.preventDefault();
  const submit = event.currentTarget.querySelector("button");
  const code = $("family-code").value.trim();
  $("family-code").value = "";
  message("family-login-error");
  submit.disabled = true;
  try {
    await api("/family/session", { method: "POST", data: { code } });
    await signIn("", { familyLogin: true });
  } catch (error) {
    message("family-login-error", error.message);
  } finally {
    submit.disabled = false;
  }
});
$("disconnect").addEventListener("click", async () => {
  if (principal?.auth_mode === "family") {
    try {
      await api("/family/session", { method: "DELETE" });
    } catch (error) {
      message("account-role", error.message);
      return;
    }
  }
  signOut();
});
$("scope").addEventListener("change", () => {
  if (principal?.auth_mode !== "family") return;
  const confirmed = $("scope").value === "confirmed";
  requestNumber++;
  resetPhotos();
  setRecallSearch();
  for (const id of ["results", "browsing", "refine-choices"]) $(id).replaceChildren();
  message("archive-status");
  message("result-count");
  message("results-title", confirmed ? "Fotos por persona" : "Álbumes");
  $("timeline").hidden = confirmed;
  $("confirmed-photo-hint").hidden = !confirmed;
  $("query").placeholder = confirmed ? "Nombre o alias" : "Ana, playa, 2024";
});

$("search-form").addEventListener("submit", event => {
  event.preventDefault();
  const year = $("year").value;
  const text = $("query").value.trim();
  if (principal?.auth_mode === "family" && $("scope").value === "confirmed") {
    if (!text) {
      message("archive-status", "Escribe un nombre o alias.");
      $("query").focus();
      return;
    }
    archiveRequest("confirmed", { person: text });
    return;
  }
  if (/^(?:antes de|despu[eé]s de|s[oó]lo|en el [aá]lbum|[aá]lbum|con|before|after|only|in album|with)\s+\S/i.test(text)) {
    refineArchive(text);
    return;
  }
  const keywords = year ? text.replace(/\b(?:19|20)\d{2}(?:\s*[-–]\s*(?:19|20)\d{2})?\b/g, "").trim() : text;
  const q = [keywords, year].filter(Boolean).join(" ");
  const folders = principal?.auth_mode === "family" || $("scope").value === "folders";
  archiveRequest(folders ? "folders" : "search", { q });
});
$("timeline-form").addEventListener("submit", event => {
  event.preventDefault();
  archiveRequest("timeline", {
    place: $("place-filter").value.trim(), date_from: $("timeline-from").value, date_to: $("timeline-to").value,
  });
});
$("random").addEventListener("click", () => archiveRequest("random", { q: $("year").value }));
$("recent").addEventListener("click", () => { pinnedOnly = false; showView("searches"); });
$("pinned").addEventListener("click", () => { pinnedOnly = true; showView("searches"); });
for (const tab of document.querySelectorAll("[data-view]")) {
  tab.addEventListener("click", () => showView(tab.dataset.view));
}

if (sharedSecret) {
  loadSharedAlbum();
} else {
  const rememberedToken = sessionStorage.getItem("chromantis.chatToken");
  signIn(rememberedToken || "", { quiet: !rememberedToken });
}
