(function () {
  "use strict";
  const $ = (id) => document.getElementById(id);
  const esc = window.Markdown.escape;

  const svg = (d) => `<svg viewBox="0 0 24 24">${d}</svg>`;
  const ICONS = {
    auto: svg('<path d="M12 3l1.9 5.1L19 10l-5.1 1.9L12 17l-1.9-5.1L5 10l5.1-1.9z"/><path d="M19 15l.8 2.2L22 18l-2.2.8L19 21l-.8-2.2L16 18l2.2-.8z"/>'),
    general: svg('<path d="M9.5 3a5.5 5.5 0 0 0-3.2 10v2.5A1.5 1.5 0 0 0 7.8 17h8.4a1.5 1.5 0 0 0 1.5-1.5V13A5.5 5.5 0 0 0 14.5 3z"/><path d="M9 21h6"/>'),
    web: svg('<circle cx="12" cy="12" r="9"/><path d="M3 12h18M12 3a14 14 0 0 1 0 18M12 3a14 14 0 0 0 0 18"/>'),
    company: svg('<path d="M3 21h18M5 21V7l7-4 7 4v14M9 21v-4h6v4M9 10h.01M15 10h.01M9 14h.01M15 14h.01"/>'),
    document: svg('<path d="M14 3H7a2 2 0 0 0-2 2v14a2 2 0 0 0 2 2h10a2 2 0 0 0 2-2V8z"/><path d="M14 3v5h5"/>'),
    image: svg('<rect x="3" y="3" width="18" height="18" rx="2"/><circle cx="8.5" cy="8.5" r="1.5"/><path d="M21 15l-5-5L5 21"/>'),
    os: svg('<ellipse cx="12" cy="5" rx="8" ry="3"/><path d="M4 5v14c0 1.7 3.6 3 8 3s8-1.3 8-3V5M4 12c0 1.7 3.6 3 8 3s8-1.3 8-3"/>'),
    attachment: svg('<path d="M21.4 11.1l-9.2 9.2a6 6 0 0 1-8.5-8.5l9.2-9.2a4 4 0 0 1 5.7 5.7l-9.2 9.2a2 2 0 0 1-2.8-2.8l8.5-8.5"/>'),
    check: svg('<path d="M5 12l5 5 9-10"/>'),
    checkCircle: svg('<circle cx="12" cy="12" r="9"/><path d="M8 12.5l2.8 2.8L16.5 9.5"/>'),
    alert: svg('<circle cx="12" cy="12" r="9"/><path d="M12 7v6M12 16.5h.01"/>'),
    stopCircle: svg('<circle cx="12" cy="12" r="9"/><rect x="9" y="9" width="6" height="6" rx="1"/>'),
    copy: svg('<rect x="9" y="9" width="11" height="11" rx="2"/><path d="M5 15V5a2 2 0 0 1 2-2h10"/>'),
    edit: svg('<path d="M12 20h9"/><path d="M16.5 3.5a2.1 2.1 0 0 1 3 3L7 19l-4 1 1-4z"/>'),
    refresh: svg('<path d="M20 11a8 8 0 0 0-14.9-3M4 4v4h4M4 13a8 8 0 0 0 14.9 3M20 20v-4h-4"/>'),
    up: svg('<path d="M7 10v11H4V10zM7 10l4-7a2 2 0 0 1 2.9 2.2L13 9h5.6a2 2 0 0 1 2 2.4l-1.4 7A2 2 0 0 1 17.2 20H7"/>'),
    down: svg('<path d="M17 14V3h3v11zM17 14l-4 7a2 2 0 0 1-2.9-2.2L11 15H5.4a2 2 0 0 1-2-2.4l1.4-7A2 2 0 0 1 6.8 4H17"/>'),
    speaker: svg('<path d="M11 5L6 9H3v6h3l5 4z"/><path d="M15.5 8.5a5 5 0 0 1 0 7M18.5 5.5a9 9 0 0 1 0 13"/>'),
    download: svg('<path d="M12 4v12M7 11l5 5 5-5M5 20h14"/>'),
    eye: svg('<path d="M2 12s3.6-7 10-7 10 7 10 7-3.6 7-10 7S2 12 2 12z"/><circle cx="12" cy="12" r="3"/>'),
    trash: svg('<path d="M4 7h16M10 11v6M14 11v6M6 7l1 12a2 2 0 0 0 2 2h6a2 2 0 0 0 2-2l1-12M9 7V4h6v3"/>'),
    more: svg('<circle cx="5" cy="12" r="1"/><circle cx="12" cy="12" r="1"/><circle cx="19" cy="12" r="1"/>'),
    pin: svg('<path d="M12 17v5M5 17h14l-2-4V6h1V3H6v3h1v7z"/>'),
    clock: svg('<circle cx="12" cy="12" r="9"/><path d="M12 7v5l3 2"/>'),
    bolt: svg('<path d="M13 2L4 14h7l-1 8 9-12h-7z"/>'),
    x: svg('<path d="M6 6l12 12M18 6L6 18"/>'),
  };
  const MODES = [
    { id: "auto", label: "Auto", title: "Automatically choose the best source" },
    { id: "general", label: "General", title: "Answer from the model's own knowledge" },
    { id: "web", label: "Web", title: "Search the public web for current information" },
    { id: "company", label: "Company", title: "Enfactum documents and live OS data only" },
  ];
  const IMAGE_EXT = [".png", ".jpg", ".jpeg", ".webp", ".gif", ".bmp", ".tif", ".tiff"];
  const BROWSER_IMAGE = [".png", ".jpg", ".jpeg", ".webp", ".gif", ".bmp"];
  const FILE_COLORS = { pdf: "#e5484d", docx: "#2f6fea", doc: "#2f6fea", xlsx: "#1f9d55", csv: "#1f9d55",
    pptx: "#e8730c", md: "#6b7280", txt: "#6b7280", html: "#9333ea", json: "#0e7490", png: "#0891b2", jpg: "#0891b2" };
  const PANEL_TITLES = { general: "General", personalization: "Personalization", history: "Chats & history",
    knowledge: "Knowledge base", account: "Account", about: "About" };
  const ACTION_STATUS = { pending: "Awaiting your confirmation", running: "Working…", done: "Completed",
    failed: "Failed", cancelled: "Cancelled", expired: "Expired" };
  const params = new URLSearchParams(location.search);
  const EMBED = params.get("embed") || "";

  const state = {
    config: null, me: null, prefs: {}, mode: "auto", conversationId: null, conversations: [],
    live: null, runs: {}, pollTimer: null, pending: [], context: { used: 0, window: 0, estimated: false },
    token: sessionStorage.getItem("enfactum_ai_token") || "", menuConv: null, menuMsg: null, speaking: null,
  };

  // ------------------------------------------------------------------ API
  function headers(extra) {
    const h = Object.assign({}, extra || {});
    if (state.token) h.Authorization = "Bearer " + state.token;
    return h;
  }
  async function api(path, opts = {}) {
    const res = await fetch(path, Object.assign({}, opts, { headers: headers(opts.headers), credentials: "same-origin" }));
    if (res.status === 401 && state.config && state.config.auth_mode !== "demo") {
      postToHost({ type: "enfactum-ai-auth-required" });
      if (!EMBED) showTokenModal();
      throw new Error("Please sign in.");
    }
    if (!res.ok) {
      let detail = res.statusText;
      try { detail = (await res.json()).detail || detail; } catch (_) { /* not JSON */ }
      const err = new Error(typeof detail === "string" ? detail : "Request failed");
      err.status = res.status;
      throw err;
    }
    return res;
  }
  const getJSON = async (path) => (await api(path)).json();
  const sendJSON = async (path, method, body) =>
    (await api(path, { method, headers: { "Content-Type": "application/json" }, body: JSON.stringify(body || {}) })).json();
  const blobCache = {};
  function blobUrl(path) {
    if (!blobCache[path]) blobCache[path] = api(path).then((r) => r.blob()).then(URL.createObjectURL)
      .catch((e) => { delete blobCache[path]; throw e; });
    return blobCache[path];
  }
  async function downloadFile(path, name) {
    try {
      const res = await api(path + (path.includes("?") ? "&" : "?") + "download=1");
      saveBlob(await res.blob(), name);
    } catch (e) { toast(e.message, true); }
  }
  function saveBlob(blob, name) {
    const a = document.createElement("a");
    a.href = URL.createObjectURL(blob);
    a.download = name;
    document.body.appendChild(a);
    a.click();
    a.remove();
    setTimeout(() => URL.revokeObjectURL(a.href), 2000);
  }
  function postToHost(msg) {
    if (window.parent === window) return;
    const targets = (state.config && state.config.trusted_origins) || [];
    (targets.length ? targets : [location.origin]).forEach((o) => { try { window.parent.postMessage(msg, o); } catch (_) { /* ignore */ } });
  }

  // ------------------------------------------------------------------ helpers
  function toast(message, isError) {
    const el = document.createElement("div");
    el.className = "toast" + (isError ? " error" : "");
    el.textContent = message;
    $("toasts").appendChild(el);
    setTimeout(() => el.remove(), isError ? 7000 : 3500);
  }
  const initials = (name) => (name || "?").split(/\s+/).map((p) => p[0]).slice(0, 2).join("").toUpperCase();
  const hostOf = (url) => { try { return new URL(url).hostname.replace(/^www\./, ""); } catch (_) { return ""; } };
  const extOf = (name) => ((name || "").match(/\.[^.]+$/) || [""])[0].toLowerCase();
  const fmtSize = (b) => b > 1048576 ? (b / 1048576).toFixed(1) + " MB" : Math.max(1, Math.round(b / 1024)) + " KB";
  const fmtTokens = (n) => n >= 1e6 ? (n / 1e6).toFixed(n % 1e6 ? 1 : 0) + "M" : n >= 1000 ? (n / 1000).toFixed(n >= 1e4 ? 0 : 1) + "k" : String(n);
  const fmtSecs = (ms) => ms >= 60000 ? `${Math.floor(ms / 60000)}m ${Math.round((ms % 60000) / 1000)}s` : `${(ms / 1000).toFixed(1)}s`;
  const plainText = (md) => (md || "").replace(/\[(\d{1,3})\]/g, "").replace(/```[\s\S]*?```/g, (m) => m.replace(/```\w*/g, ""))
    .replace(/[*_`#>|]/g, "").replace(/\n{3,}/g, "\n\n").trim();
  function fileBadge(name) {
    const ext = extOf(name).slice(1) || "file";
    return `<span class="file-badge" style="--fc:${FILE_COLORS[ext] || "#64748b"}">${esc(ext.slice(0, 4).toUpperCase())}</span>`;
  }
  function scrollToBottom(force) {
    const t = $("thread");
    if (force || t.scrollHeight - t.scrollTop - t.clientHeight < 160) t.scrollTop = t.scrollHeight;
  }
  function greeting() {
    const h = new Date().getHours();
    const part = h < 12 ? "Good morning" : h < 18 ? "Good afternoon" : "Good evening";
    const first = state.me ? state.me.user.name.split(" ")[0] : "";
    return first ? `${part}, ${first}` : part;
  }

  // ------------------------------------------------------------------ routing
  function convFromUrl() {
    const m = location.pathname.match(/\/c\/([A-Za-z0-9_-]{6,64})\/?$/);
    return m ? m[1] : null;
  }
  function setUrl(convId, replace) {
    const url = (convId ? `/c/${encodeURIComponent(convId)}` : "/") + location.search;
    if (location.pathname + location.search === url) return;
    history[replace ? "replaceState" : "pushState"]({ convId }, "", url);
  }

  // ------------------------------------------------------------------ bootstrap
  async function init() {
    if (EMBED === "1" || EMBED === "widget") $("app").classList.add("embed");
    if (EMBED === "app") $("app").classList.add("embed-app");
    const hash = new URLSearchParams(location.hash.slice(1));
    if (hash.get("token")) {
      state.token = hash.get("token");
      sessionStorage.setItem("enfactum_ai_token", state.token);
      history.replaceState(null, "", location.pathname + location.search);
    }
    let configLoaded;
    const configReady = new Promise((resolve) => (configLoaded = resolve));
    window.addEventListener("message", async (e) => {
      if (!e.data || typeof e.data.type !== "string") return;
      await configReady;
      if (e.origin !== location.origin && !(state.config.trusted_origins || []).includes(e.origin)) return;
      if (e.data.type === "enfactum-ai-token" && typeof e.data.token === "string" && e.data.token) {
        state.token = e.data.token;
        sessionStorage.setItem("enfactum_ai_token", state.token);
        loadIdentity();
      } else if (e.data.type === "enfactum-ai-theme" && ["light", "dark", "system"].includes(e.data.theme)) {
        applyTheme(e.data.theme);
      }
    });

    renderModes();
    bindEvents();
    try {
      state.config = await (await fetch("/api/config")).json();
    } catch (_) {
      toast("Cannot reach the assistant server.", true);
      return;
    }
    configLoaded();
    document.title = state.config.app_name;
    $("brandName").textContent = state.config.app_name.replace(/ Assistant$/, "");
    $("dropHint").textContent = `Documents and images (text in images and scanned PDFs is read automatically) · max ${state.config.max_upload_mb} MB`;
    $("attachInput").accept = state.config.attachment_extensions.join(",");
    $("kbQuickInput").accept = state.config.supported_extensions.join(",");
    $("fileInput").accept = state.config.supported_extensions.join(",");
    if (state.config.auth_mode !== "demo" && !state.token && !state.config.cookie_auth) {
      postToHost({ type: "enfactum-ai-auth-required" });
      if (!EMBED) showTokenModal();
      return;
    }
    await loadIdentity();
  }

  async function loadIdentity() {
    try {
      state.me = await getJSON("/api/me");
    } catch (e) {
      if (e.status === 403) { showGate(e.message); return; }
      toast(e.message, true);
      return;
    }
    $("gate").classList.add("hidden");
    const u = state.me.user;
    state.prefs = state.me.settings || {};
    applyTheme(state.prefs.theme);
    document.body.classList.toggle("hide-timing", state.prefs.show_timing === false);
    $("userName").textContent = u.name;
    $("userRoles").textContent = u.roles.join(", ") || "employee";
    $("userAvatar").textContent = initials(u.name);
    $("greeting").textContent = greeting();
    $("attachKb").classList.toggle("hidden", !state.me.capabilities.documents_manage);
    state.context.window = state.me.model.context_window;
    if (!state.me.model.configured) toast("The AI model is not configured: set LLM_API_KEY in .env and restart the server.", true);
    const fromUrl = convFromUrl();
    if (fromUrl) openConversation(fromUrl, { replace: true });
    else newChat({ replace: true });
    loadConversations();
    pollRuns();
    postToHost({ type: "enfactum-ai-ready", version: state.me.version });
  }
  function showGate(detail) {
    $("gate").classList.remove("hidden");
    if (detail && detail !== "employees_only") $("gateText").textContent = detail;
  }

  // ------------------------------------------------------------------ preferences
  function applyTheme(theme) {
    if (theme === "light" || theme === "dark") document.documentElement.setAttribute("data-theme", theme);
    else document.documentElement.removeAttribute("data-theme");
    localStorage.setItem("enfactum_ai_theme", theme || "system");
  }
  let saveTimer = null;
  function setPref(key, value) {
    state.prefs[key] = value;
    if (key === "theme") applyTheme(value);
    if (key === "show_context_meter") updateMeter();
    if (key === "show_timing") document.body.classList.toggle("hide-timing", value === false);
    clearTimeout(saveTimer);
    saveTimer = setTimeout(async () => {
      try {
        state.prefs = await sendJSON("/api/settings", "PUT", state.prefs);
        $("savedHint").classList.remove("hidden");
        setTimeout(() => $("savedHint").classList.add("hidden"), 1500);
      } catch (e) { toast(e.message, true); }
    }, 350);
  }

  function renderModes() {
    const webOff = state.me && !state.me.capabilities.web_search;
    if (webOff && state.mode === "web") state.mode = "auto";
    $("modes").innerHTML = MODES.map((m) => {
      const disabled = m.id === "web" && webOff;
      return `<button type="button" role="radio" class="mode${state.mode === m.id ? " active" : ""}" data-mode="${m.id}"` +
        ` aria-checked="${state.mode === m.id}" title="${esc(disabled ? "Web search is not available for your account" : m.title)}"${disabled ? " disabled" : ""}>${ICONS[m.id]}<span>${m.label}</span></button>`;
    }).join("");
  }

  // ------------------------------------------------------------------ context meter
  function updateMeter() {
    const meter = $("ctxMeter");
    const show = state.prefs.show_context_meter !== false && state.context.window > 0;
    meter.classList.toggle("hidden", !show);
    if (!show) return;
    const pendingTokens = state.pending.filter((a) => a.status === "ready").reduce((s, a) => s + (a.tokens || 0), 0);
    const draft = Math.ceil($("input").value.length / 4);
    const used = state.context.used;
    const next = used + pendingTokens + draft;
    const pct = Math.min(100, (next / state.context.window) * 100);
    $("ctxRing").style.strokeDashoffset = String(94.25 * (1 - pct / 100));
    $("ctxLabel").textContent = pct < 1 && next > 0 ? "<1%" : `${Math.round(pct)}%`;
    meter.classList.toggle("warn", pct >= 70 && pct < 90);
    meter.classList.toggle("full", pct >= 90);
    const extra = pendingTokens + draft;
    $("ctxPop").innerHTML = `<b>Context window</b>` +
      `<span>${fmtTokens(used)} of ${fmtTokens(state.context.window)} tokens used${state.context.estimated ? " (estimated)" : ""}</span>` +
      `<div class="bar"><i style="width:${pct.toFixed(1)}%"></i></div>` +
      (extra ? `<small>+ ~${fmtTokens(extra)} in your next message and attachments</small>` : "") +
      `<small>Includes instructions, chat history, attachments and search results. Older messages are trimmed automatically when it fills up.</small>` +
      (pct >= 70 ? `<small class="tip">Start a new chat for the most accurate answers.</small>` : "");
  }

  // ------------------------------------------------------------------ background runs (sidebar spinner / blue tick)
  async function pollRuns() {
    clearTimeout(state.pollTimer);
    try {
      const { runs } = await getJSON("/api/runs");
      const prev = state.runs;
      const next = {};
      for (const r of runs) {
        const st = r.status === "running" ? "running" : r.status === "error" ? "error" : "done";
        if (r.conversation_id === state.conversationId && st !== "running") {
          if (!state.live && prev[r.conversation_id] === "running") openConversation(r.conversation_id, { keepUrl: true, keepScroll: true });
          api(`/api/conversations/${encodeURIComponent(r.conversation_id)}/seen`, { method: "POST" }).catch(() => {});
          continue;
        }
        next[r.conversation_id] = st;
        if (prev[r.conversation_id] === "running" && st !== "running") {
          const conv = state.conversations.find((c) => c.id === r.conversation_id);
          toast(st === "error" ? `Answer failed in “${conv ? conv.title : "a chat"}”` : `Answer ready in “${conv ? conv.title : "a chat"}”`, st === "error");
          if (document.hidden) document.title = "✓ " + state.config.app_name;
        }
      }
      if (state.live && state.live.convId) next[state.live.convId] = "running";
      state.runs = next;
      renderConversations();
    } catch (_) { /* transient */ }
    const busy = state.live || Object.values(state.runs).includes("running");
    state.pollTimer = setTimeout(pollRuns, busy ? 2000 : 15000);
  }

  // ------------------------------------------------------------------ conversations
  async function loadConversations() {
    try {
      state.conversations = (await getJSON("/api/conversations")).conversations;
      renderConversations();
    } catch (_) { /* surfaced elsewhere */ }
  }
  function convStatus(id) {
    if (state.live && state.live.convId === id) return "running";
    return state.runs[id] || "";
  }
  function renderConversations() {
    const q = $("convSearch").value.trim().toLowerCase();
    const list = state.conversations.filter((c) => !q || c.title.toLowerCase().includes(q));
    const el = $("convList");
    if (!list.length) {
      el.innerHTML = `<div class="conv-empty">${q ? "No matching chats" : "No conversations yet"}</div>`;
      return;
    }
    const badge = (st) => st === "running" ? '<span class="conv-status running" title="Generating answer…"><span class="spinner"></span></span>' :
      st === "done" ? `<span class="conv-status done" title="New answer">${ICONS.checkCircle}</span>` :
      st === "error" ? `<span class="conv-status error" title="Answer failed">${ICONS.alert}</span>` : "";
    const item = (c) => {
      const st = convStatus(c.id);
      return `<div class="conv-item${c.id === state.conversationId ? " active" : ""}${st ? " has-status" : ""}" data-id="${esc(c.id)}" role="button" tabindex="0">` +
        `<span class="conv-title">${esc(c.title)}</span>${badge(st)}<button class="more" type="button" data-more="${esc(c.id)}" aria-label="Options">${ICONS.more}</button></div>`;
    };
    const pinned = list.filter((c) => c.pinned);
    const recent = list.filter((c) => !c.pinned);
    el.innerHTML = (pinned.length ? `<div class="conv-label">${ICONS.pin}Pinned</div>` + pinned.map(item).join("") : "") +
      (recent.length ? `<div class="conv-label">${ICONS.clock}${q ? "Results" : "Recent"}</div>` + recent.map(item).join("") : "");
  }

  function openFloatingMenu(menu, anchor) {
    menu.classList.remove("hidden");
    const r = anchor.getBoundingClientRect();
    const top = r.bottom + 4 + menu.offsetHeight > window.innerHeight ? r.top - menu.offsetHeight - 4 : r.bottom + 4;
    menu.style.top = Math.max(8, top) + "px";
    menu.style.left = Math.max(8, Math.min(r.left, window.innerWidth - menu.offsetWidth - 8)) + "px";
  }
  function openConvMenu(id, anchor) {
    const conv = state.conversations.find((c) => c.id === id);
    if (!conv) return;
    closeMenus();
    state.menuConv = conv;
    const menu = $("convMenu");
    menu.querySelector('[data-act="pin"] span').textContent = conv.pinned ? "Unpin" : "Pin";
    openFloatingMenu(menu, anchor);
    anchor.closest(".conv-item").classList.add("menu-open");
  }
  function closeMenus() {
    $("convMenu").classList.add("hidden");
    $("msgMenu").classList.add("hidden");
    $("attachMenu").classList.add("hidden");
    $("attachBtn").classList.remove("open");
    document.querySelectorAll(".conv-item.menu-open").forEach((x) => x.classList.remove("menu-open"));
  }
  async function convAction(act) {
    const conv = state.menuConv;
    closeMenus();
    if (!conv) return;
    try {
      if (act === "pin") {
        await sendJSON(`/api/conversations/${encodeURIComponent(conv.id)}`, "PATCH", { pinned: !conv.pinned });
        loadConversations();
      } else if (act === "delete") {
        if (!confirm("Delete this conversation?")) return;
        await api(`/api/conversations/${encodeURIComponent(conv.id)}`, { method: "DELETE" });
        delete state.runs[conv.id];
        if (conv.id === state.conversationId) newChat();
        loadConversations();
      } else if (act === "rename") {
        startRename(conv);
      }
    } catch (e) { toast(e.message, true); }
  }
  function startRename(conv) {
    const row = $("convList").querySelector(`.conv-item[data-id="${CSS.escape(conv.id)}"]`);
    if (!row) return;
    const span = row.querySelector(".conv-title");
    const input = document.createElement("input");
    input.value = conv.title;
    input.maxLength = 120;
    span.replaceWith(input);
    input.focus();
    input.select();
    let done = false;
    const finish = async (save) => {
      if (done) return;
      done = true;
      const title = input.value.trim();
      if (save && title && title !== conv.title) {
        try {
          await sendJSON(`/api/conversations/${encodeURIComponent(conv.id)}`, "PATCH", { title });
          if (conv.id === state.conversationId) $("convTitle").textContent = title;
        } catch (e) { toast(e.message, true); }
      }
      loadConversations();
    };
    input.addEventListener("keydown", (e) => {
      e.stopPropagation();
      if (e.key === "Enter") finish(true);
      if (e.key === "Escape") finish(false);
    });
    input.addEventListener("click", (e) => e.stopPropagation());
    input.addEventListener("blur", () => finish(true));
  }

  /** Stop listening to the current stream. The answer keeps generating on the server. */
  function detach() {
    if (state.live) {
      state.live.detached = true;
      state.live.ctrl.abort();
      state.live = null;
    }
    setStreaming(false);
    stopSpeaking();
  }

  function newChat(opts = {}) {
    detach();
    state.conversationId = null;
    state.mode = state.prefs.default_mode || "auto";
    state.context.used = 0;
    state.context.estimated = false;
    clearPending(true);
    renderModes();
    updateMeter();
    $("messages").innerHTML = "";
    $("welcome").classList.remove("hidden");
    $("convTitle").textContent = "New chat";
    setUrl(null, opts.replace);
    renderConversations();
    $("input").focus();
    closeNav();
  }

  async function openConversation(id, opts = {}) {
    const keepScroll = opts.keepScroll && id === state.conversationId ? $("thread").scrollTop : null;
    const switching = id !== state.conversationId;
    detach();
    let conv;
    try {
      conv = await getJSON(`/api/conversations/${encodeURIComponent(id)}`);
    } catch (e) {
      toast(e.status === 404 ? "That conversation no longer exists." : e.message, true);
      if (e.status === 404) newChat({ replace: true });
      return;
    }
    state.conversationId = conv.id;
    if (!opts.keepUrl) setUrl(conv.id, opts.replace);
    if (switching) clearPending(true);
    $("convTitle").textContent = conv.title;
    $("welcome").classList.add("hidden");
    $("messages").innerHTML = "";
    state.context.used = 0;
    for (const m of conv.messages) {
      const meta = m.meta || {};
      if (meta.action_result) continue; // shown on the action card itself
      if (m.role === "user") addUserMessage(m.content, meta.attachments || [], m.id);
      else {
        const view = addAssistantMessage(false);
        view.id = m.id;
        view.text = m.content;
        view.feedback = m.feedback;
        (meta.artifacts || []).forEach((a) => view.artifact(a));
        view.finish(m.sources, Object.assign({ status: meta.stopped ? "cancelled" : meta.incomplete ? "error" : "done" }, meta));
        if (meta.context) state.context = Object.assign({}, state.context, meta.context);
      }
    }
    delete state.runs[conv.id];
    if (conv.active_run) {
      const view = addAssistantMessage(true);
      attachRun(conv.active_run.id, conv.id, view, 0);
    }
    updateMeter();
    renderConversations();
    if (keepScroll != null) $("thread").scrollTop = keepScroll; else scrollToBottom(true);
    closeNav();
  }

  // ------------------------------------------------------------------ attachments
  function attChip(a, removable) {
    const el = document.createElement("div");
    el.className = "att" + (a.status === "error" ? " error" : "") + (a.id ? " clickable" : "");
    const isImg = a.kind === "image";
    const sub = a.status === "uploading" ? (isImg ? "Reading image…" : "Reading file…") : a.status === "error" ? a.error || "Failed" :
      isImg ? (a.ocr ? "Image · text read" : "Image") :
      `${extOf(a.name).slice(1).toUpperCase() || "File"}${a.ocr ? " · OCR" : ""}${a.tokens ? " · ~" + fmtTokens(a.tokens) + " tokens" : ""}`;
    el.innerHTML = `<span class="att-icon">${a.status === "uploading" ? '<span class="spinner"></span>' : isImg ? ICONS.image : fileBadge(a.name)}</span>` +
      `<span class="att-meta"><b></b><small></small></span>` + (removable ? `<button type="button" class="att-x" aria-label="Remove">${ICONS.x}</button>` : "");
    el.querySelector("b").textContent = a.name;
    el.querySelector("small").textContent = sub;
    el.title = a.name;
    if (isImg && a.status !== "uploading") {
      const setImg = (src) => { el.querySelector(".att-icon").innerHTML = `<img alt="">`; el.querySelector("img").src = src; };
      if (a.previewUrl) setImg(a.previewUrl);
      else if (a.id) blobUrl(`/api/files/${encodeURIComponent(a.id)}`).then(setImg).catch(() => {});
    }
    if (a.id && !removable) el.addEventListener("click", () => openPreview(fileSpec(a)));
    return el;
  }
  function renderPending() {
    const box = $("attChips");
    box.innerHTML = "";
    state.pending.forEach((a, i) => {
      const chip = attChip(a, true);
      chip.querySelector(".att-x").addEventListener("click", () => removePending(i));
      box.appendChild(chip);
    });
    box.classList.toggle("hidden", !state.pending.length);
    updateSendState();
    updateMeter();
  }
  async function addFiles(fileList) {
    const files = Array.from(fileList || []);
    const allowed = state.config.attachment_extensions;
    for (const file of files) {
      if (state.pending.length >= 10) { toast("Up to 10 attachments per message.", true); break; }
      const ext = extOf(file.name);
      if (!allowed.includes(ext)) { toast(`${file.name}: unsupported file type`, true); continue; }
      if (file.size > state.config.max_attachment_mb * 1048576) { toast(`${file.name}: larger than ${state.config.max_attachment_mb} MB`, true); continue; }
      const isImg = IMAGE_EXT.includes(ext);
      const item = { name: file.name, kind: isImg ? "image" : "document", status: "uploading",
        previewUrl: BROWSER_IMAGE.includes(ext) ? URL.createObjectURL(file) : null };
      state.pending.push(item);
      renderPending();
      const fd = new FormData();
      fd.append("file", file);
      fd.append("conversation_id", state.conversationId || "");
      api("/api/attachments", { method: "POST", body: fd }).then((r) => r.json()).then((res) => {
        Object.assign(item, res, { status: "ready" });
      }).catch((e) => {
        Object.assign(item, { status: "error", error: e.message });
      }).finally(renderPending);
    }
  }
  function removePending(i) {
    const [a] = state.pending.splice(i, 1);
    if (a && a.id) api(`/api/attachments/${encodeURIComponent(a.id)}`, { method: "DELETE" }).catch(() => {});
    renderPending();
  }
  function clearPending(deleteUploaded) {
    if (deleteUploaded) state.pending.forEach((a) => a.id && api(`/api/attachments/${encodeURIComponent(a.id)}`, { method: "DELETE" }).catch(() => {}));
    state.pending = [];
    renderPending();
  }

  // ------------------------------------------------------------------ messages
  function addUserMessage(text, atts, id) {
    const wrap = document.createElement("div");
    wrap.className = "msg-user-wrap";
    if (id) wrap.dataset.id = id;
    wrap._text = text;
    wrap._atts = atts || [];
    if (atts && atts.length) {
      const row = document.createElement("div");
      row.className = "msg-atts";
      atts.forEach((a) => row.appendChild(attChip(Object.assign({ status: "ready" }, a), false)));
      wrap.appendChild(row);
    }
    const el = document.createElement("div");
    el.className = "msg-user";
    el.textContent = text;
    wrap.appendChild(el);
    const actions = document.createElement("div");
    actions.className = "msg-actions user-actions";
    actions.innerHTML = `<button type="button" data-act="copy-user" title="Copy">${ICONS.copy}</button>` +
      `<button type="button" data-act="edit" title="Edit">${ICONS.edit}</button>`;
    wrap.appendChild(actions);
    $("messages").appendChild(wrap);
    return wrap;
  }

  function startEdit(wrap) {
    if (state.live) { toast("Wait for the current answer to finish, or stop it first."); return; }
    if (!wrap.dataset.id) { toast("This message cannot be edited yet."); return; }
    if (wrap.querySelector(".edit-box")) return;
    const bubble = wrap.querySelector(".msg-user");
    const box = document.createElement("div");
    box.className = "edit-box";
    box.innerHTML = `<textarea rows="3" maxlength="12000"></textarea><div class="edit-actions">` +
      `<button type="button" class="btn" data-edit="cancel">Cancel</button><button type="button" class="btn btn-primary" data-edit="save">Send</button></div>`;
    const ta = box.querySelector("textarea");
    ta.value = wrap._text;
    bubble.classList.add("hidden");
    wrap.querySelector(".user-actions").classList.add("hidden");
    wrap.appendChild(box);
    const fit = () => { ta.style.height = "auto"; ta.style.height = Math.min(ta.scrollHeight, 320) + "px"; };
    fit();
    ta.focus();
    ta.setSelectionRange(ta.value.length, ta.value.length);
    ta.addEventListener("input", fit);
    const cancel = () => { box.remove(); bubble.classList.remove("hidden"); wrap.querySelector(".user-actions").classList.remove("hidden"); };
    box.querySelector('[data-edit="cancel"]').addEventListener("click", cancel);
    const save = () => {
      const text = ta.value.trim();
      if (!text) return;
      resubmit(wrap, text);
    };
    box.querySelector('[data-edit="save"]').addEventListener("click", save);
    ta.addEventListener("keydown", (e) => {
      if (e.key === "Escape") cancel();
      if (e.key === "Enter" && !e.shiftKey && !e.isComposing) { e.preventDefault(); save(); }
    });
  }
  /** Edit or regenerate: drop this user message and everything after it, then ask again. */
  function resubmit(wrap, text) {
    if (state.live) { toast("Wait for the current answer to finish, or stop it first."); return; }
    const atts = wrap._atts || [];
    const msgId = wrap.dataset.id;
    let node = wrap;
    while (node) { const next = node.nextSibling; node.remove(); node = next; }
    send(text, { replaceFrom: msgId, displayAtts: atts });
  }

  function addAssistantMessage(live) {
    const root = document.createElement("div");
    root.className = "msg-ai" + (live ? " live" : "");
    root.innerHTML = '<div class="welcome-logo ai-avatar">E</div><div class="msg-body">' +
      '<div class="msg-status"></div><div class="steps"></div>' +
      '<div class="typing"><i></i><i></i><i></i></div><div class="md"></div><div class="artifacts hidden"></div>' +
      '<div class="sources hidden"></div><div class="msg-actions hidden"></div></div>';
    $("messages").appendChild(root);
    const q = (s) => root.querySelector(s);
    if (!live) q(".typing").classList.add("hidden");
    const setStatus = (html, cls) => { const s = q(".msg-status"); s.className = "msg-status " + (cls || ""); s.innerHTML = html; };
    if (live) setStatus('<span class="spinner"></span><span>Thinking…</span>', "running");
    const view = {
      root, text: "", steps: {}, pending: false, id: null, feedback: null, sources: [], meta: {}, started: Date.now(),
      label(text) {
        if (!root.classList.contains("live")) return;
        setStatus(`<span class="spinner"></span><span></span>`, "running");
        q(".msg-status span:last-child").textContent = text;
      },
      step(ev) {
        q(".typing").classList.add("hidden");
        if (ev.state === "running") {
          const s = document.createElement("div");
          s.className = "step";
          s.innerHTML = `<span class="dot"><span class="spinner"></span></span><span></span>`;
          s.lastChild.textContent = ev.label;
          q(".steps").appendChild(s);
          view.steps[ev.id] = s;
          view.label(ev.label + "…");
        } else if (view.steps[ev.id]) {
          view.steps[ev.id].classList.add("done");
          view.steps[ev.id].querySelector(".dot").innerHTML = ICONS.check;
        }
        scrollToBottom();
      },
      append(token) {
        if (!view.text) view.label("Writing…");
        view.text += token;
        q(".typing").classList.add("hidden");
        if (!view.pending) {
          view.pending = true;
          requestAnimationFrame(() => {
            view.pending = false;
            const md = q(".md");
            md.innerHTML = window.Markdown.render(view.text);
            md.classList.add("caret");
            scrollToBottom();
          });
        }
      },
      artifact(a) {
        q(".typing").classList.add("hidden");
        const box = q(".artifacts");
        box.appendChild(artifactEl(a));
        box.classList.remove("hidden");
        scrollToBottom();
      },
      error(message) {
        q(".typing").classList.add("hidden");
        const e = document.createElement("div");
        e.className = "msg-error";
        e.textContent = message;
        q(".msg-body").insertBefore(e, q(".artifacts"));
      },
      finish(sources, meta) {
        meta = meta || {};
        root.classList.remove("live");
        q(".typing").classList.add("hidden");
        const md = q(".md");
        md.classList.remove("caret");
        md.innerHTML = window.Markdown.render(view.text);
        view.sources = sources || [];
        view.meta = meta;
        renderSources(q(".sources"), view.sources);
        const ms = meta.latency_ms || (meta.status ? Date.now() - view.started : 0);
        const t = meta.timing || {};
        const time = ms ? `<span class="timing" title="${esc(timingTitle(t))}"> · ${fmtSecs(ms)}</span>` : "";
        if (meta.status === "cancelled") setStatus(`${ICONS.stopCircle}<span>Stopped</span>${time}`, "stopped");
        else if (meta.status === "error") setStatus(`${ICONS.alert}<span>Not completed</span>${time}`, "failed");
        else setStatus(`${ICONS.checkCircle}<span>Completed</span>${time}`, "done");
        renderActions(view);
      },
    };
    return view;
  }
  function timingTitle(t) {
    const parts = [];
    if (t.first_token_ms != null) parts.push(`first words ${fmtSecs(t.first_token_ms)}`);
    if (t.llm_ms) parts.push(`model ${fmtSecs(t.llm_ms)}`);
    if (t.tools_ms) parts.push(`sources ${fmtSecs(t.tools_ms)}`);
    return parts.join(" · ");
  }
  function renderActions(view) {
    const actions = view.root.querySelector(".msg-actions");
    if (!view.text && !view.id) { actions.classList.add("hidden"); return; }
    const fb = view.feedback;
    actions.innerHTML =
      `<button type="button" data-act="copy" title="Copy">${ICONS.copy}</button>` +
      (view.id ? `<button type="button" data-act="regen" title="Regenerate">${ICONS.refresh}</button>` +
        `<button type="button" data-act="up" class="${fb === "up" ? "on" : ""}" title="Good response">${ICONS.up}</button>` +
        `<button type="button" data-act="down" class="${fb === "down" ? "on" : ""}" title="Bad response">${ICONS.down}</button>` : "") +
      (window.speechSynthesis ? `<button type="button" data-act="speak" title="Read aloud">${ICONS.speaker}</button>` : "") +
      (view.id ? `<button type="button" data-act="export" title="Download answer">${ICONS.download}</button>` : "");
    actions.classList.remove("hidden");
    view.root._view = view;
  }

  function fileSpec(a) {
    return { name: a.name, mime: a.mime, size: a.size_bytes, url: `/api/files/${encodeURIComponent(a.id)}`,
      textUrl: `/api/files/${encodeURIComponent(a.id)}/text` };
  }
  function artifactEl(a) {
    if (a.type === "action") return actionCard(a);
    if (a.type === "image") {
      const fig = document.createElement("figure");
      fig.className = "art-image";
      fig.innerHTML = `<div class="art-img-box"><span class="spinner"></span></div><figcaption><span></span>` +
        `<button type="button" class="link-btn">${ICONS.download}Download</button></figcaption>`;
      fig.querySelector("figcaption span").textContent = a.title || a.name;
      blobUrl(a.url).then((src) => {
        const box = fig.querySelector(".art-img-box");
        box.innerHTML = '<img alt="">';
        box.querySelector("img").src = src;
        box.querySelector("img").alt = a.title || a.name;
      }).catch(() => { fig.querySelector(".art-img-box").textContent = "Image unavailable"; });
      fig.querySelector(".art-img-box").addEventListener("click", () => openPreview(fileSpec(a)));
      fig.querySelector(".link-btn").addEventListener("click", () => downloadFile(a.url, a.name));
      return fig;
    }
    const card = document.createElement("div");
    card.className = "art-file";
    card.innerHTML = `${fileBadge(a.name)}<div class="art-meta"><b></b><small>${esc(extOf(a.name).slice(1).toUpperCase())} · ${fmtSize(a.size_bytes || 0)}</small></div>` +
      `<button type="button" class="btn" data-a="preview">${ICONS.eye}Preview</button>` +
      `<button type="button" class="btn btn-primary" data-a="download">${ICONS.download}Download</button>`;
    card.querySelector("b").textContent = a.name;
    card.querySelector('[data-a="preview"]').addEventListener("click", () => openPreview(fileSpec(a)));
    card.querySelector('[data-a="download"]').addEventListener("click", () => downloadFile(a.url, a.name));
    return card;
  }
  function actionCard(a) {
    const card = document.createElement("div");
    card.className = "action-card";
    const render = () => {
      const st = a.status || "pending";
      card.dataset.status = st;
      const result = a.result && a.result.message ? `<div class="ac-result"></div>` : "";
      card.innerHTML = `<div class="ac-head">${ICONS.bolt}<b></b><span class="ac-badge">${esc(ACTION_STATUS[st] || st)}</span></div>` +
        `<div class="ac-summary"></div><dl class="ac-fields"></dl>${result}` +
        (st === "pending" ? `<div class="ac-foot"><small>Nothing changes in Enfactum OS until you confirm.</small>` +
          `<button type="button" class="btn" data-ac="cancel">Cancel</button><button type="button" class="btn btn-primary" data-ac="confirm">Confirm</button></div>` : "");
      card.querySelector("b").textContent = a.title;
      card.querySelector(".ac-summary").textContent = a.summary || "";
      const dl = card.querySelector(".ac-fields");
      (a.fields || []).forEach((f) => {
        const dt = document.createElement("dt"); dt.textContent = f.label;
        const dd = document.createElement("dd"); dd.textContent = typeof f.value === "object" ? JSON.stringify(f.value) : String(f.value);
        dl.append(dt, dd);
      });
      if (result) card.querySelector(".ac-result").textContent = a.result.message;
      const go = async (what) => {
        card.querySelectorAll("[data-ac]").forEach((b) => (b.disabled = true));
        if (what === "confirm") { a.status = "running"; render(); }
        try {
          const r = await sendJSON(`/api/actions/${encodeURIComponent(a.id)}/${what}`, "POST", {});
          a.status = r.status;
          a.result = r.result || (r.message ? { message: r.message } : null);
          if (what === "confirm") toast(r.message || (r.ok ? "Done" : "Action failed"), !r.ok);
        } catch (e) { a.status = "pending"; toast(e.message, true); }
        render();
      };
      card.querySelectorAll("[data-ac]").forEach((b) => b.addEventListener("click", () => go(b.dataset.ac)));
    };
    render();
    return card;
  }

  function renderSources(el, sources) {
    el.innerHTML = "";
    el.classList.add("hidden");
    if (!sources.length) return;
    el.innerHTML = '<div class="sources-title">Sources</div><div class="source-grid"></div>';
    const grid = el.lastChild;
    for (const s of sources) {
      const isLink = s.url && /^https?:\/\//.test(s.url);
      const card = document.createElement(isLink ? "a" : "div");
      card.className = "source";
      card.dataset.n = s.n;
      if (isLink) { card.href = s.url; card.target = "_blank"; card.rel = "noopener noreferrer"; }
      const icon = s.type === "web" ? ICONS.web : s.type === "os" ? ICONS.os : s.type === "attachment" ? ICONS.attachment : ICONS.document;
      const sub = s.type === "web" ? hostOf(s.url) : s.type === "os" ? "Enfactum OS · live data" :
        s.type === "attachment" ? "Your attachment" : "Company document";
      card.innerHTML = `<span class="num">${Number(s.n)}</span><span class="s-body"><strong></strong><small>${icon}<span></span></small></span>`;
      card.querySelector("strong").textContent = s.title;
      card.querySelector("small span").textContent = sub;
      if (s.snippet) card.title = s.snippet;
      grid.appendChild(card);
    }
    el.classList.remove("hidden");
  }

  async function messageAction(act, btn) {
    const root = btn.closest(".msg-ai, .msg-user-wrap");
    if (!root) return;
    if (act === "copy-user") { copyText(root._text); return; }
    if (act === "edit") { startEdit(root); return; }
    const view = root._view;
    if (!view) return;
    if (act === "copy") copyText(view.text.replace(/\[(\d{1,3})\]/g, ""));
    else if (act === "regen") {
      let prev = root.previousElementSibling;
      while (prev && !prev.classList.contains("msg-user-wrap")) prev = prev.previousElementSibling;
      if (!prev || !prev.dataset.id) { toast("Nothing to regenerate."); return; }
      resubmit(prev, prev._text);
    } else if (act === "up" || act === "down") {
      const rating = view.feedback === act ? "none" : act;
      try {
        await sendJSON(`/api/messages/${encodeURIComponent(view.id)}/feedback`, "POST", { rating });
        view.feedback = rating === "none" ? null : rating;
        renderActions(view);
        if (rating !== "none") toast("Thanks for the feedback");
      } catch (e) { toast(e.message, true); }
    } else if (act === "speak") speak(view, btn);
    else if (act === "export") { closeMenus(); state.menuMsg = view; openFloatingMenu($("msgMenu"), btn); }
  }
  function copyText(text) {
    navigator.clipboard.writeText(text || "").then(() => toast("Copied")).catch(() => toast("Copy failed", true));
  }
  function speak(view, btn) {
    if (!window.speechSynthesis) return;
    const same = state.speaking === view;
    stopSpeaking();
    if (same) return;
    const u = new SpeechSynthesisUtterance(plainText(view.text));
    u.onend = u.onerror = () => { if (state.speaking === view) stopSpeaking(); };
    state.speaking = view;
    btn.classList.add("on");
    speechSynthesis.speak(u);
  }
  function stopSpeaking() {
    if (window.speechSynthesis) speechSynthesis.cancel();
    document.querySelectorAll('[data-act="speak"].on').forEach((b) => b.classList.remove("on"));
    state.speaking = null;
  }
  async function exportMessage(fmt) {
    const view = state.menuMsg;
    closeMenus();
    if (!view || !view.id) return;
    try {
      const res = await api(`/api/messages/${encodeURIComponent(view.id)}/export`, {
        method: "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify({ format: fmt }) });
      const cd = res.headers.get("Content-Disposition") || "";
      const m = cd.match(/filename\*=UTF-8''([^;]+)/);
      saveBlob(await res.blob(), m ? decodeURIComponent(m[1]) : `answer.${fmt}`);
    } catch (e) { toast(e.message, true); }
  }

  // ------------------------------------------------------------------ chat + streaming
  async function readEvents(res, onEvent) {
    const reader = res.body.getReader();
    const decoder = new TextDecoder();
    let buffer = "";
    for (;;) {
      const { value, done } = await reader.read();
      if (done) return;
      buffer += decoder.decode(value, { stream: true });
      let idx;
      while ((idx = buffer.indexOf("\n\n")) >= 0) {
        const raw = buffer.slice(0, idx);
        buffer = buffer.slice(idx + 2);
        const line = raw.split("\n").find((l) => l.startsWith("data: "));
        if (line) onEvent(JSON.parse(line.slice(6)));
      }
    }
  }

  function handleEvent(live, ev) {
    if (typeof ev.seq === "number") live.seq = ev.seq;
    const view = live.view;
    switch (ev.type) {
      case "run":
        live.runId = ev.id;
        break;
      case "conversation":
        if (!live.convId) {
          live.convId = ev.id;
          if (state.live === live) {
            state.conversationId = ev.id;
            setUrl(ev.id);
            if (ev.title) $("convTitle").textContent = ev.title;
          }
          loadConversations();
        }
        break;
      case "user_message":
        if (live.userWrap) live.userWrap.dataset.id = ev.id;
        break;
      case "token": view.append(ev.text); break;
      case "status": view.step(ev); break;
      case "artifact": view.artifact(ev.artifact); break;
      case "usage":
        if (state.live === live) { state.context = { used: ev.used, window: ev.window, estimated: ev.estimated }; updateMeter(); }
        break;
      case "sources": live.sources = ev.sources; break;
      case "error": view.error(ev.message); break;
      case "done":
        live.meta = ev;
        view.id = ev.message_id;
        if (live.userWrap && ev.user_message_id) live.userWrap.dataset.id = ev.user_message_id;
        break;
      case "run_end":
        finishLive(live, ev.status);
        break;
      default: break;
    }
  }
  function finishLive(live, status) {
    if (live.ended) return;
    live.ended = true;
    live.view.finish(live.sources || [], Object.assign({}, live.meta || {}, { status }));
    if (state.live === live) {
      state.live = null;
      setStreaming(false);
      if (live.convId) api(`/api/conversations/${encodeURIComponent(live.convId)}/seen`, { method: "POST" }).catch(() => {});
    }
    if (live.convId) delete state.runs[live.convId];
    renderConversations();
    loadConversations();
  }
  async function consume(live, request) {
    try {
      const res = await request();
      await readEvents(res, (ev) => handleEvent(live, ev));
    } catch (e) {
      if (live.detached || e.name === "AbortError") return;
      if (!live.runId) { live.view.error(e.message || "Connection lost."); finishLive(live, "error"); return; }
      if (e.status === 404) { finishLive(live, "error"); openConversation(live.convId, { keepUrl: true }); return; }
    }
    if (live.ended || live.detached) return;
    // Stream dropped (network blip / server restart): re-attach and replay from the last event we saw.
    setTimeout(() => {
      if (live.detached || live.ended || state.live !== live) return;
      consume(live, () => api(`/api/runs/${encodeURIComponent(live.runId)}/events?from=${live.seq + 1}`, { signal: live.ctrl.signal }));
    }, 1000);
  }
  function attachRun(runId, convId, view, from) {
    const live = { runId, convId, view, ctrl: new AbortController(), seq: from - 1, sources: [], meta: {} };
    state.live = live;
    setStreaming(true);
    consume(live, () => api(`/api/runs/${encodeURIComponent(runId)}/events?from=${from}`, { signal: live.ctrl.signal }));
  }

  async function send(text, opts = {}) {
    text = (text || "").trim();
    if (!text || state.live) return;
    if (state.pending.some((a) => a.status === "uploading")) { toast("Wait for attachments to finish reading."); return; }
    const atts = state.pending.filter((a) => a.status === "ready");
    $("welcome").classList.add("hidden");
    if (!opts.replaceFrom) { $("input").value = ""; autosize(); }
    const userWrap = addUserMessage(text, opts.displayAtts || atts, null);
    state.pending = [];
    renderPending();
    const view = addAssistantMessage(true);
    scrollToBottom(true);
    const live = { runId: null, convId: state.conversationId, view, userWrap, ctrl: new AbortController(), seq: -1, sources: [], meta: {} };
    state.live = live;
    setStreaming(true);
    renderConversations();
    const body = { message: text, conversation_id: state.conversationId, mode: state.mode,
      attachment_ids: atts.map((a) => a.id), replace_from_message_id: opts.replaceFrom || null };
    await consume(live, () => api("/api/chat", { method: "POST", headers: { "Content-Type": "application/json" },
      body: JSON.stringify(body), signal: live.ctrl.signal }));
    pollRuns();
  }
  async function stop() {
    const live = state.live;
    if (!live) return;
    if (live.runId) {
      try { await api(`/api/runs/${encodeURIComponent(live.runId)}/cancel`, { method: "POST" }); } catch (_) { /* finished already */ }
    } else {
      live.ctrl.abort();
      finishLive(live, "cancelled");
    }
  }
  function setStreaming(on) {
    $("sendBtn").classList.toggle("stop", on);
    $("sendBtn").setAttribute("aria-label", on ? "Stop generating" : "Send");
    $("sendBtn").title = on ? "Stop generating" : "Send";
    updateSendState();
  }
  function updateSendState() {
    const uploading = state.pending.some((a) => a.status === "uploading");
    $("sendBtn").disabled = !state.live && (!$("input").value.trim() || uploading);
  }
  function autosize() {
    const t = $("input");
    t.style.height = "auto";
    t.style.height = Math.min(t.scrollHeight, 220) + "px";
    updateSendState();
    updateMeter();
  }

  // ------------------------------------------------------------------ preview
  function parseCsv(text) {
    const rows = [];
    let row = [], cell = "", quoted = false;
    for (let i = 0; i < text.length && rows.length < 500; i++) {
      const ch = text[i];
      if (quoted) {
        if (ch === '"' && text[i + 1] === '"') { cell += '"'; i++; } else if (ch === '"') quoted = false; else cell += ch;
      } else if (ch === '"') quoted = true;
      else if (ch === ",") { row.push(cell); cell = ""; }
      else if (ch === "\n") { row.push(cell.replace(/\r$/, "")); rows.push(row); row = []; cell = ""; }
      else cell += ch;
    }
    if (cell || row.length) { row.push(cell); rows.push(row); }
    return rows;
  }
  function tableHtml(rows) {
    if (!rows.length) return '<div class="empty">Empty file</div>';
    const [head, ...body] = rows;
    return `<div class="pv-table"><table><thead><tr>${head.map((c) => `<th>${esc(c)}</th>`).join("")}</tr></thead><tbody>` +
      body.map((r) => `<tr>${r.map((c) => `<td>${esc(c)}</td>`).join("")}</tr>`).join("") + "</tbody></table></div>";
  }
  /** spec: {name, mime, size, url, textUrl} */
  async function openPreview(spec) {
    const ext = extOf(spec.name);
    const body = $("pvBody");
    $("pvIcon").innerHTML = fileBadge(spec.name);
    $("pvTitle").textContent = spec.title || spec.name;
    $("pvSub").textContent = [spec.title && spec.title !== spec.name ? spec.name : "", spec.size ? fmtSize(spec.size) : ""].filter(Boolean).join(" · ");
    $("pvDownload").onclick = () => downloadFile(spec.url, spec.name);
    body.className = "pv-body";
    body.innerHTML = '<div class="pv-loading"><span class="spinner"></span>Loading preview…</div>';
    $("previewModal").classList.remove("hidden");
    try {
      if (ext === ".pdf") {
        const src = await blobUrl(spec.url);
        body.innerHTML = '<iframe class="pv-frame" title="PDF preview"></iframe>';
        body.querySelector("iframe").src = src;
      } else if (BROWSER_IMAGE.includes(ext)) {
        const src = await blobUrl(spec.url);
        body.classList.add("center");
        body.innerHTML = '<img class="pv-img" alt="">';
        body.querySelector("img").src = src;
      } else if ([".html", ".htm"].includes(ext)) {
        const src = await blobUrl(spec.url);
        body.innerHTML = '<iframe class="pv-frame white" sandbox="" title="HTML preview"></iframe>';
        body.querySelector("iframe").src = src;
      } else if ([".txt", ".log", ".md", ".markdown", ".csv", ".json"].includes(ext)) {
        const text = await (await api(spec.url)).text();
        if (ext === ".csv") body.innerHTML = tableHtml(parseCsv(text.replace(/^\ufeff/, "")));
        else if (ext === ".json") { let pretty = text; try { pretty = JSON.stringify(JSON.parse(text), null, 2); } catch (_) { /* raw */ } body.innerHTML = `<pre class="pv-pre"></pre>`; body.firstChild.textContent = pretty; }
        else if (ext === ".md" || ext === ".markdown") body.innerHTML = `<div class="md pv-md">${window.Markdown.render(text)}</div>`;
        else { body.innerHTML = `<pre class="pv-pre"></pre>`; body.firstChild.textContent = text; }
      } else {
        const data = await getJSON(spec.textUrl);
        if (!data.text) { body.innerHTML = `<div class="empty">Preview is not available for this file type. Use Download to open it.</div>`; return; }
        const looksMd = /^#{1,3} |\n#{1,3} |\n\|.+\|\n/.test(data.text);
        body.innerHTML = `<div class="pv-note">${ICONS.eye}Text preview. Download the file to see the original formatting.</div>` +
          (looksMd ? `<div class="md pv-md">${window.Markdown.render(data.text)}</div>` : `<pre class="pv-pre"></pre>`);
        if (!looksMd) body.querySelector("pre").textContent = data.text + (data.truncated ? "\n…" : "");
      }
    } catch (e) {
      body.innerHTML = `<div class="empty"></div>`;
      body.firstChild.textContent = "Could not load the preview: " + e.message;
    }
  }
  function closePreview() { $("previewModal").classList.add("hidden"); $("pvBody").innerHTML = ""; }

  // ------------------------------------------------------------------ settings
  function openSettings(tab) {
    $("settingsModal").classList.remove("hidden");
    showTab(tab || "general");
    closeNav();
  }
  function closeSettings() { $("settingsModal").classList.add("hidden"); }
  function showTab(tab) {
    document.querySelectorAll("#settingsNav button").forEach((b) => b.classList.toggle("active", b.dataset.tab === tab));
    document.querySelectorAll(".panel").forEach((p) => p.classList.toggle("hidden", p.dataset.panel !== tab));
    $("settingsPanelTitle").textContent = PANEL_TITLES[tab];
    syncPrefControls();
    if (tab === "knowledge") loadDocs();
    if (tab === "history") renderHistoryStats();
    if (tab === "account") renderAccount();
    if (tab === "about") renderAbout();
  }
  function syncPrefControls() {
    document.querySelectorAll("[data-pref]").forEach((el) => {
      const v = state.prefs[el.dataset.pref];
      if (el.classList.contains("seg")) el.querySelectorAll("button").forEach((b) => b.classList.toggle("active", b.dataset.v === v));
      else if (el.type === "checkbox") el.checked = v !== false;
      else if (document.activeElement !== el) el.value = v == null ? "" : v;
    });
  }
  function renderHistoryStats() {
    const total = state.conversations.length;
    const pinned = state.conversations.filter((c) => c.pinned).length;
    const week = state.conversations.filter((c) => Date.now() / 1000 - c.updated_at < 7 * 86400).length;
    $("historyStats").innerHTML = [[total, "Conversations"], [pinned, "Pinned"], [week, "Active this week"]]
      .map(([n, l]) => `<div class="stat"><b>${n}</b><small>${l}</small></div>`).join("");
  }
  function renderAccount() {
    const u = state.me.user;
    $("accAvatar").textContent = initials(u.name);
    $("accName").textContent = u.name;
    $("accEmail").textContent = u.email || "";
    $("accRoles").innerHTML = (u.roles.length ? u.roles : ["employee"]).map((r) => `<span class="chip">${esc(r)}</span>`).join("");
    const c = state.me.capabilities;
    const access = ["Company documents"].concat(c.web_search ? ["Web search"] : [], c.os_tools,
      c.actions.length ? c.actions.map((a) => a + " (with confirmation)") : [], c.documents_manage ? ["Manage knowledge base"] : []);
    $("accAccess").innerHTML = access.map((r) => `<span class="chip">${esc(r)}</span>`).join("");
    $("signOutRow").classList.toggle("hidden", !state.token);
  }
  function renderAbout() {
    const m = state.me.model;
    const c = state.me.capabilities;
    const rows = [["Version", state.me.version], ["AI provider", m.provider], ["Model", m.name],
      ["Context window", fmtTokens(m.context_window) + " tokens"], ["Image understanding", m.vision ? "Enabled" : "Disabled"],
      ["Text from images / scans", c.ocr ? `Enabled (${c.ocr === "llm" ? "AI vision" : "Tesseract"})` : "Disabled"],
      ["File creation", c.files ? "PDF, Word, PowerPoint, Excel, CSV, text" : "Disabled"],
      ["Charts", c.charts ? "Enabled" : "Disabled"], ["Image generation", c.image_generation ? "Enabled" : "Disabled"],
      ["Sign-in", state.config.auth_mode === "demo" ? "Local test mode" : "Enfactum OS"]];
    $("aboutList").innerHTML = rows.map(([k, v]) => `<dt>${esc(k)}</dt><dd>${esc(String(v))}</dd>`).join("");
  }
  async function testLlm() {
    const el = $("llmStatus");
    el.className = "";
    el.textContent = "Testing…";
    const t0 = performance.now();
    try {
      const r = await getJSON("/api/health/llm");
      el.textContent = r.ok ? `Connected. The model responded in ${fmtSecs(performance.now() - t0)}.` : r.error;
      el.className = r.ok ? "ok" : "bad";
    } catch (e) { el.textContent = e.message; el.className = "bad"; }
  }
  async function exportChats() {
    try {
      saveBlob(await (await api("/api/export")).blob(), "enfactum-ai-chats.json");
    } catch (e) { toast(e.message, true); }
  }
  async function deleteAllChats() {
    if (!confirm("Delete ALL your conversations? This cannot be undone.")) return;
    try {
      const r = await sendJSON("/api/conversations", "DELETE", {});
      toast(`Deleted ${r.deleted} conversation(s)`);
      state.runs = {};
      newChat();
      await loadConversations();
      renderHistoryStats();
    } catch (e) { toast(e.message, true); }
  }

  // ------------------------------------------------------------------ knowledge base
  function docSpec(d) {
    return { name: d.has_file ? d.filename : d.filename.replace(/\.[^.]+$/, "") + ".txt", title: d.title, mime: d.mime,
      size: d.size_bytes, url: `/api/documents/${encodeURIComponent(d.id)}/file`, textUrl: `/api/documents/${encodeURIComponent(d.id)}/text` };
  }
  async function loadDocs() {
    const list = $("docList");
    list.innerHTML = '<div class="empty">Loading…</div>';
    try {
      const data = await getJSON("/api/documents");
      $("uploadForm").classList.toggle("hidden", !data.can_manage);
      if (!data.documents.length) { list.innerHTML = '<div class="empty">No documents available to you yet.</div>'; return; }
      list.innerHTML = "";
      for (const d of data.documents) {
        const row = document.createElement("div");
        row.className = "doc";
        const restricted = d.visibility && d.visibility.scope === "restricted";
        const date = new Date(d.created_at * 1000).toLocaleDateString();
        row.innerHTML = `<div class="doc-icon">${fileBadge(d.filename)}</div><div class="doc-meta"><strong></strong>` +
          `<small>${esc(d.filename)} · ${fmtSize(d.size_bytes)} · ${d.chunk_count} sections · ${esc(date)}</small>` +
          (restricted ? `<span class="badge lock" title="Visible to: ${esc((d.visibility.roles || []).join(", "))}">Restricted</span>` : "") +
          `</div><div class="doc-actions">` +
          `<button class="icon-btn" type="button" data-d="preview" title="Preview" aria-label="Preview">${ICONS.eye}</button>` +
          `<button class="icon-btn" type="button" data-d="download" title="Download" aria-label="Download">${ICONS.download}</button>` +
          (data.can_manage ? `<button class="icon-btn danger" type="button" data-d="delete" title="Delete" aria-label="Delete">${ICONS.trash}</button>` : "") +
          `</div>`;
        row.querySelector("strong").textContent = d.title;
        const spec = docSpec(d);
        row.querySelector('[data-d="preview"]').addEventListener("click", () => openPreview(spec));
        row.querySelector('[data-d="download"]').addEventListener("click", () => downloadFile(spec.url, spec.name));
        const del = row.querySelector('[data-d="delete"]');
        if (del) del.addEventListener("click", () => deleteDoc(d));
        row.querySelector(".doc-meta").addEventListener("click", () => openPreview(spec));
        list.appendChild(row);
      }
    } catch (e) { list.innerHTML = ""; toast(e.message, true); }
  }
  async function deleteDoc(d) {
    if (!confirm(`Remove “${d.title}” from the knowledge base?`)) return;
    try {
      await api(`/api/documents/${encodeURIComponent(d.id)}`, { method: "DELETE" });
      toast("Document removed");
      loadDocs();
    } catch (e) { toast(e.message, true); }
  }
  let kbFile = null;
  function pickKbFile(file) {
    kbFile = file || null;
    $("dropText").textContent = file ? file.name : "Drop a file or browse";
    $("uploadBtn").disabled = !file;
  }
  async function uploadKb(e) {
    e.preventDefault();
    if (!kbFile) return;
    const fd = new FormData();
    fd.append("file", kbFile);
    fd.append("title", $("docTitle").value.trim());
    fd.append("visibility", $("docVisibility").value);
    fd.append("roles", $("docRoles").value.trim());
    const btn = $("uploadBtn");
    btn.disabled = true;
    btn.textContent = IMAGE_EXT.includes(extOf(kbFile.name)) || extOf(kbFile.name) === ".pdf" ? "Reading & indexing…" : "Indexing…";
    try {
      const r = await (await api("/api/documents", { method: "POST", body: fd })).json();
      toast(`Added “${r.title}” to the knowledge base (${r.chunks} sections${r.ocr ? ", text read with OCR" : ""})`);
      $("uploadForm").reset();
      $("docRoles").classList.add("hidden");
      pickKbFile(null);
      loadDocs();
    } catch (err) { toast(err.message, true); btn.disabled = false; }
    finally { btn.textContent = "Upload & index"; }
  }

  // ------------------------------------------------------------------ misc
  function showTokenModal() { $("tokenModal").classList.remove("hidden"); $("tokenInput").focus(); }
  function closeNav() { $("app").classList.remove("nav-open"); }

  function bindEvents() {
    $("composer").addEventListener("submit", (e) => { e.preventDefault(); state.live ? stop() : send($("input").value); });
    $("input").addEventListener("input", autosize);
    $("input").addEventListener("keydown", (e) => {
      if (e.key !== "Enter" || e.isComposing) return;
      const enterSends = state.prefs.enter_to_send !== false;
      if ((enterSends && !e.shiftKey) || (!enterSends && (e.ctrlKey || e.metaKey))) {
        e.preventDefault();
        if (!state.live) send($("input").value);
      }
    });
    $("input").addEventListener("paste", (e) => {
      const files = Array.from(e.clipboardData && e.clipboardData.files || []);
      if (files.length) { e.preventDefault(); addFiles(files); }
    });
    const composer = $("composer");
    let dragDepth = 0;
    $("main").addEventListener("dragenter", (e) => { if (e.dataTransfer.types.includes("Files")) { dragDepth++; composer.classList.add("dragging"); } });
    $("main").addEventListener("dragleave", () => { if (--dragDepth <= 0) { dragDepth = 0; composer.classList.remove("dragging"); } });
    $("main").addEventListener("dragover", (e) => e.preventDefault());
    $("main").addEventListener("drop", (e) => {
      e.preventDefault();
      dragDepth = 0;
      composer.classList.remove("dragging");
      if (e.dataTransfer.files.length) addFiles(e.dataTransfer.files);
    });

    $("attachBtn").addEventListener("click", (e) => {
      e.stopPropagation();
      if (!state.me || !state.me.capabilities.documents_manage) { $("attachInput").click(); return; }
      const open = $("attachMenu").classList.contains("hidden");
      closeMenus();
      if (open) { $("attachMenu").classList.remove("hidden"); $("attachBtn").classList.add("open"); }
    });
    $("attachChat").addEventListener("click", () => { closeMenus(); $("attachInput").click(); });
    $("attachKb").addEventListener("click", () => { closeMenus(); $("kbQuickInput").click(); });
    $("attachInput").addEventListener("change", (e) => { addFiles(e.target.files); e.target.value = ""; });
    $("kbQuickInput").addEventListener("change", (e) => {
      const f = e.target.files[0];
      e.target.value = "";
      if (!f) return;
      openSettings("knowledge");
      pickKbFile(f);
      $("docTitle").focus();
    });

    $("modes").addEventListener("click", (e) => {
      const b = e.target.closest(".mode");
      if (!b || b.disabled) return;
      state.mode = b.dataset.mode;
      renderModes();
      $("input").focus();
    });
    $("newChat").addEventListener("click", () => newChat());
    $("convSearch").addEventListener("input", renderConversations);
    $("convList").addEventListener("click", (e) => {
      const more = e.target.closest("[data-more]");
      if (more) { e.stopPropagation(); openConvMenu(more.dataset.more, more); return; }
      const item = e.target.closest(".conv-item");
      if (item && !item.querySelector("input")) openConversation(item.dataset.id);
    });
    $("convList").addEventListener("keydown", (e) => {
      const item = e.target.closest(".conv-item");
      if (item && e.key === "Enter" && e.target === item) openConversation(item.dataset.id);
    });
    $("convMenu").addEventListener("click", (e) => { const b = e.target.closest("[data-act]"); if (b) convAction(b.dataset.act); });
    $("msgMenu").addEventListener("click", (e) => { const b = e.target.closest("[data-fmt]"); if (b) exportMessage(b.dataset.fmt); });
    document.addEventListener("click", (e) => { if (!e.target.closest(".menu") && !e.target.closest('[data-act="export"]')) closeMenus(); });
    $("convList").addEventListener("scroll", closeMenus);
    $("thread").addEventListener("scroll", () => $("msgMenu").classList.add("hidden"));

    $("messages").addEventListener("click", (e) => {
      const act = e.target.closest(".msg-actions [data-act]");
      if (act) { e.stopPropagation(); messageAction(act.dataset.act, act); return; }
      const cite = e.target.closest(".cite");
      if (cite) {
        const card = cite.closest(".msg-body").querySelector(`.source[data-n="${cite.dataset.n}"]`);
        if (card) {
          card.scrollIntoView({ behavior: "smooth", block: "nearest" });
          card.classList.add("flash");
          setTimeout(() => card.classList.remove("flash"), 1400);
        }
        return;
      }
      const copy = e.target.closest(".copy-code");
      if (copy) {
        navigator.clipboard.writeText(copy.closest(".code").querySelector("code").textContent)
          .then(() => { copy.textContent = "Copied"; setTimeout(() => (copy.textContent = "Copy"), 1200); });
      }
    });

    window.addEventListener("popstate", () => {
      const id = convFromUrl();
      if (id && id !== state.conversationId) openConversation(id, { keepUrl: true });
      else if (!id && state.conversationId) newChat({ replace: true });
    });
    document.addEventListener("visibilitychange", () => {
      if (!document.hidden) {
        if (state.config) document.title = state.config.app_name;
        if (state.me) pollRuns();
      }
    });

    // preview
    $("pvClose").addEventListener("click", closePreview);
    $("previewModal").addEventListener("click", (e) => { if (e.target.id === "previewModal") closePreview(); });

    // settings
    $("openSettings").addEventListener("click", () => openSettings("general"));
    $("openKb").addEventListener("click", () => openSettings("knowledge"));
    $("userCard").addEventListener("click", () => openSettings("account"));
    $("closeSettings").addEventListener("click", closeSettings);
    $("settingsModal").addEventListener("click", (e) => { if (e.target.id === "settingsModal") closeSettings(); });
    $("settingsNav").addEventListener("click", (e) => { const b = e.target.closest("[data-tab]"); if (b) showTab(b.dataset.tab); });
    document.querySelectorAll(".seg[data-pref]").forEach((seg) => seg.addEventListener("click", (e) => {
      const b = e.target.closest("button");
      if (!b) return;
      setPref(seg.dataset.pref, b.dataset.v);
      syncPrefControls();
    }));
    document.querySelectorAll("select[data-pref], input[type=checkbox][data-pref]").forEach((el) =>
      el.addEventListener("change", () => setPref(el.dataset.pref, el.type === "checkbox" ? el.checked : el.value)));
    document.querySelectorAll("textarea[data-pref]").forEach((el) => el.addEventListener("input", () => setPref(el.dataset.pref, el.value)));
    $("exportChats").addEventListener("click", exportChats);
    $("deleteAllChats").addEventListener("click", deleteAllChats);
    $("testLlm").addEventListener("click", testLlm);
    $("signOut").addEventListener("click", () => {
      sessionStorage.removeItem("enfactum_ai_token");
      state.token = "";
      location.href = "/" + location.search;
    });

    // knowledge base upload
    $("docVisibility").addEventListener("change", (e) => $("docRoles").classList.toggle("hidden", e.target.value !== "restricted"));
    $("fileInput").addEventListener("change", (e) => pickKbFile(e.target.files[0]));
    const dz = $("dropzone");
    ["dragenter", "dragover"].forEach((t) => dz.addEventListener(t, (e) => { e.preventDefault(); dz.classList.add("over"); }));
    ["dragleave", "drop"].forEach((t) => dz.addEventListener(t, (e) => { e.preventDefault(); dz.classList.remove("over"); }));
    dz.addEventListener("drop", (e) => pickKbFile(e.dataTransfer.files[0]));
    $("uploadForm").addEventListener("submit", uploadKb);

    $("tokenForm").addEventListener("submit", (e) => {
      e.preventDefault();
      const t = $("tokenInput").value.trim();
      if (!t) return;
      state.token = t;
      sessionStorage.setItem("enfactum_ai_token", t);
      $("tokenInput").value = "";
      $("tokenModal").classList.add("hidden");
      loadIdentity();
    });
    $("menuBtn").addEventListener("click", () => $("app").classList.add("nav-open"));
    $("scrim").addEventListener("click", closeNav);
    document.addEventListener("keydown", (e) => {
      if (e.key === "Escape") { closeMenus(); closePreview(); closeSettings(); closeNav(); }
    });
  }

  init();
})();
