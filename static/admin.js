import { createBusinessViews } from "./admin_business.js?v=20261010-1";
(() => {
  "use strict";

  const $ = (id) => document.getElementById(id);
  const BASE = "";
  const LIMIT = 50;
  const RECENT_LIMIT = 10;
  const QUEUE_LIMIT = 200;
  const POLL_MS = 10000;

  const VIEWS = {
    overview: { title: "Overview", parts: ["summary", "recent"] },
    transactions: { title: "Transactions", parts: ["summary", "payouts"] },
    queue: { title: "Queue monitor", parts: ["summary", "queue"] },
    earnings: { title: "Earnings", parts: ["earnings", "earningsPartners", "feeDetails"] },
    funds: { title: "Partner funds", parts: ["funds"] },
    enquiries: { title: "Partnership enquiries", parts: ["enquiries"] },
  };
  const PAYOUT_TONE = { RECEIVED: "neutral", PROCESSING: "pending", SENT: "success", FAILED: "failure", UNKNOWN: "pending", CANCELLED: "neutral", REJECTED: "failure" };
  const PAYOUT_LABEL = { RECEIVED: "Received", PROCESSING: "Processing", SENT: "Sent", FAILED: "Failed", UNKNOWN: "Outcome unknown", CANCELLED: "Cancelled", REJECTED: "Rejected" };
  const PAYOUT_MEANING = {
    RECEIVED: "Instruction recorded; not yet processing.",
    PROCESSING: "Payout execution in progress.",
    SENT: "Recorded as sent to the receiving channel.",
    FAILED: "Recorded as failed by the backend.",
    UNKNOWN: "Outcome uncertain; held for reconciliation.",
    CANCELLED: "Instruction cancelled before delivery.",
    REJECTED: "Instruction rejected by the backend.",
  };
  const SECRET_KEY = /token|secret|password|passwd|api[_-]?key|authorization|signature|credential/i;

  const state = {
    view: "overview", q: "", status: "", offset: 0, tech: false,
    summary: null, payouts: null, recent: null, queue: null,
    earnings: null, feeDetails: null, funds: null, enquiries: null, session: null, sessionPending: true,
    updated: {}, stale: {}, conn: "none", busy: 0,
  };

  // Same-origin, HttpOnly administrator session; no worker credentials in the browser.
  try { localStorage.removeItem("admin_executor_token"); } catch { /* Storage may be disabled. */ }
  const hasSession = () => state.sessionPending || state.session?.role === "admin";
  let sessionGeneration = 0;
  function csrfToken() {
    return decodeURIComponent(document.cookie.split("; ").find(c => c.startsWith("csrf_token="))?.slice(11) || "");
  }
  function expireSession() {
    sessionGeneration++;
    state.session = null; state.sessionPending = false; state.conn = "bad";
    Object.assign(state, { summary: null, payouts: null, recent: null, queue: null, earnings: null, feeDetails: null, funds: null, enquiries: null, updated: {} });
    business.clear(); stopPolling(); closeDialog(); $("drawerBody").replaceChildren(); showView();
  }
  async function api(path, signal, options = {}) {
    const generation = sessionGeneration;
    const headers = { Accept: "application/json", ...(options.headers || {}) };
    if (options.method && options.method !== "GET") headers["X-CSRF-Token"] = csrfToken();
    const timeout = AbortSignal.timeout(20000);
    const res = await fetch(BASE + path, { ...options, headers, credentials: "same-origin", cache: "no-store", signal: signal ? AbortSignal.any([signal, timeout]) : timeout });
    if (!res.ok) {
      if (res.status === 401 || res.status === 403) expireSession();
      let detail;
      try { detail = (await res.json()).detail; } catch { /* Use status when no JSON error is available. */ }
      const err = new Error(res.status === 401 || res.status === 403
        ? "Your administrator session expired or access was denied. Sign in again."
        : typeof detail === "string" ? detail : `The server responded with HTTP ${res.status}.`);
      err.status = res.status;
      throw err;
    }
    const data = await res.json();
    if (generation !== sessionGeneration) throw new DOMException("Session changed", "AbortError");
    return data;
  }

  // ---------- formatting ----------
  const df = new Intl.DateTimeFormat(undefined, { year: "numeric", month: "short", day: "2-digit" });
  const hm = new Intl.DateTimeFormat(undefined, { hour: "2-digit", minute: "2-digit", hour12: false, timeZoneName: "short" });
  function dateCell(x) {
    if (!x) return dash();
    const d = new Date(x);
    if (isNaN(d)) return String(x);
    return h("time", { datetime: d.toISOString(), title: dtf.format(d) }, h("span", { class: "d" }, df.format(d)), h("span", { class: "t" }, hm.format(d)));
  }
  const dtf = new Intl.DateTimeFormat(undefined, { year: "numeric", month: "short", day: "2-digit", hour: "2-digit", minute: "2-digit", hour12: false, timeZoneName: "short" });
  const tf = new Intl.DateTimeFormat(undefined, { hour: "2-digit", minute: "2-digit", second: "2-digit", hour12: false, timeZoneName: "short" });
  const nf = new Intl.NumberFormat("en-US", { minimumFractionDigits: 2, maximumFractionDigits: 2 });
  const cf = new Intl.NumberFormat("en-US");
  const fmtCount = (n) => (n == null || n === "" || isNaN(Number(n)) ? "—" : cf.format(Number(n)));
  function fmtDate(x) {
    if (!x) return null;
    const d = new Date(x);
    return isNaN(d) ? String(x) : dtf.format(d);
  }
  function fmtMoney(a, c) {
    if (a == null || a === "") return null;
    const value = String(a);
    const match = /^(-?)(\d+)(?:\.(\d{1,2})0*)?$/.exec(value);
    if (!match) return value;
    const integer = match[2].replace(/\B(?=(\d{3})+(?!\d))/g, ",");
    return `${String(c || "USD").toUpperCase()} ${match[1]}${integer}.${(match[3] || "").padEnd(2, "0")}`;
  }
  const isPast = (x) => { const d = new Date(x); return x && !isNaN(d) && d.getTime() < Date.now(); };

  // ---------- DOM helpers ----------
  function h(tag, attrs, ...kids) {
    const e = document.createElement(tag);
    for (const [k, v] of Object.entries(attrs || {})) {
      if (v == null || v === false) continue;
      if (k === "class") e.className = v;
      else if (k.startsWith("on")) e.addEventListener(k.slice(2), v);
      else e.setAttribute(k, v === true ? "" : v);
    }
    for (const c of kids.flat()) {
      if (c == null || c === false) continue;
      e.append(c instanceof Node ? c : document.createTextNode(String(c)));
    }
    return e;
  }
  const ICONS = {
    copy: '<rect x="9" y="9" width="13" height="13" rx="2"/><path d="M5 15H4a2 2 0 0 1-2-2V4a2 2 0 0 1 2-2h9a2 2 0 0 1 2 2v1"/>',
    x: '<path d="M18 6 6 18M6 6l12 12"/>',
    menu: '<path d="M4 6h16M4 12h16M4 18h16"/>',
    search: '<circle cx="11" cy="11" r="7"/><path d="m21 21-4.3-4.3"/>',
    chevron: '<path d="m9 18 6-6-6-6"/>',
    overview: '<rect x="3" y="3" width="7" height="9" rx="1"/><rect x="14" y="3" width="7" height="5" rx="1"/><rect x="14" y="12" width="7" height="9" rx="1"/><rect x="3" y="16" width="7" height="5" rx="1"/>',
    transactions: '<path d="M8 3 4 7l4 4"/><path d="M4 7h16"/><path d="m16 21 4-4-4-4"/><path d="M20 17H4"/>',
    queue: '<path d="m12 2 9 5-9 5-9-5 9-5Z"/><path d="m3 12 9 5 9-5"/><path d="m3 17 9 5 9-5"/>',
    earnings: '<path d="M4 2v20l2-1 2 1 2-1 2 1 2-1 2 1 2-1 2 1V2l-2 1-2-1-2 1-2-1-2 1-2-1-2 1Z"/><path d="M8 8h8M8 12h8M8 16h5"/>',
    funds: '<path d="M19 7V4a1 1 0 0 0-1-1H5a2 2 0 0 0 0 4h15a1 1 0 0 1 1 1v4h-3a2 2 0 0 0 0 4h3a1 1 0 0 0 1-1v-2a1 1 0 0 0-1-1"/><path d="M3 5v14a2 2 0 0 0 2 2h15a1 1 0 0 0 1-1v-4"/>',
    enquiries: '<path d="M22 12h-6l-2 3h-4l-2-3H2"/><path d="M5.45 5.11 2 12v6a2 2 0 0 0 2 2h16a2 2 0 0 0 2-2v-6l-3.45-6.89A2 2 0 0 0 16.76 4H7.24a2 2 0 0 0-1.79 1.11Z"/>',
  };
  function icon(name) {
    const s = document.createElementNS("http://www.w3.org/2000/svg", "svg");
    s.setAttribute("viewBox", "0 0 24 24"); s.setAttribute("fill", "none"); s.setAttribute("stroke", "currentColor");
    s.setAttribute("stroke-width", "2"); s.setAttribute("stroke-linecap", "round"); s.setAttribute("stroke-linejoin", "round");
    s.setAttribute("aria-hidden", "true"); s.innerHTML = ICONS[name];
    return s;
  }
  const dash = () => h("span", { class: "dash", "aria-label": "Not available" }, "—");
  const missing = (txt = "Not available") => h("span", { class: "missing" }, txt);
  const text = (v) => (v == null || v === "" ? dash() : String(v));

  function badge(status, kind = "payout") {
    if (!status) return dash();
    const s = String(status);
    if (kind === "queue") return h("span", { class: "badge queue", title: "Queue job state (not a payout outcome)" }, s);
    return h("span", { class: `badge ${PAYOUT_TONE[s] || "neutral"}`, title: PAYOUT_MEANING[s] || "Payout status reported by the backend" }, PAYOUT_LABEL[s] || s);
  }

  function toast(msg) {
    const t = h("div", { class: "toast" }, msg);
    $("toasts").append(t);
    setTimeout(() => t.remove(), 2600);
  }

  async function copy(value, label) {
    try {
      await navigator.clipboard.writeText(value);
    } catch {
      const ta = h("textarea", { "aria-hidden": "true", style: "position:fixed;opacity:0" });
      ta.value = value; document.body.append(ta); ta.select();
      try { document.execCommand("copy"); } catch { /* ignore */ }
      ta.remove();
    }
    toast(`${label[0].toUpperCase()}${label.slice(1)} copied`);
  }
  function copyBtn(value, label, testid) {
    return h("button", { type: "button", class: "copy", "aria-label": `Copy ${label}`, title: `Copy ${label}`, "data-testid": testid,
      onclick: (e) => { e.stopPropagation(); copy(String(value), label); } }, icon("copy"));
  }
  function refCell(value, label, testid) {
    if (!value) return dash();
    return h("span", { class: "ref" }, h("span", { class: "mono trunc", title: String(value) }, String(value)), copyBtn(value, label, testid));
  }

  // ---------- field lookup (detail payload shape is not fixed) ----------
  function makeLookup(...sources) {
    const layers = [];
    const isObj = (o) => o && typeof o === "object" && !Array.isArray(o);
    for (const src of sources) {
      if (!isObj(src)) continue;
      layers.push(src);
      for (const v of Object.values(src)) if (isObj(v)) { layers.push(v); for (const w of Object.values(v)) if (isObj(w)) layers.push(w); }
    }
    return (...keys) => {
      for (const L of layers) for (const k of keys) if (L[k] != null && L[k] !== "") return L[k];
      return null;
    };
  }
  const partnerOf = (r) => r.partner_name || r.partner || r.partner_id || null;
  const channelOf = (r) => r.receiving_channel || r.channel || r.wallet || r.bank || r.provider || r.method || null;

  function redact(obj) {
    if (Array.isArray(obj)) return obj.map(redact);
    if (obj && typeof obj === "object") {
      const out = {};
      for (const [k, v] of Object.entries(obj)) out[k] = SECRET_KEY.test(k) ? "[redacted]" : redact(v);
      return out;
    }
    return obj;
  }

  // ---------- refresh model ----------
  const inflight = {};
  let payoutCtrl = null, payoutKey = "";
  let pollTimer = null;

  function once(key, fn) {
    if (inflight[key]) return inflight[key];
    inflight[key] = fn().finally(() => { delete inflight[key]; });
    return inflight[key];
  }
  const business = createBusinessViews({ $, state, api, h, fmtMoney, dateCell, fmtDate, text, badge, refCell,
    renderTable, skeletonRows, kv, section, toast, openDialog, closeDialog,
    refresh: parts => refresh(parts), writeHash: () => writeHash(), openDrawer });
  const LOADERS = {
    ...business.loaders,
    summary: () => once("summary", async () => { state.summary = await api("/admin/api/summary"); renderSummary(); }),
    recent: () => once("recent", async () => { state.recent = await api(`/admin/api/payouts?limit=${RECENT_LIMIT}&offset=0`); renderRecent(); }),
    queue: () => once("queue", async () => { state.queue = await api(`/admin/api/queue?limit=${QUEUE_LIMIT}`); renderQueue(); }),
    payouts: loadPayouts,
  };

  async function loadPayouts() {
    const key = `${state.q}|${state.status}|${state.offset}`;
    if (payoutCtrl && key === payoutKey) return inflight.payouts;
    if (payoutCtrl) payoutCtrl.abort();
    const ctrl = payoutCtrl = new AbortController();
    payoutKey = key;
    const p = new URLSearchParams({ limit: LIMIT, offset: state.offset });
    if (state.q) p.set("q", state.q);
    if (state.status) p.set("status", state.status);
    inflight.payouts = (async () => {
      try {
        const data = await api(`/admin/api/payouts?${p}`, ctrl.signal);
        if (payoutCtrl !== ctrl) return;
        state.payouts = { ...data, key };
        renderPayouts();
      } finally {
        if (payoutCtrl === ctrl) { payoutCtrl = null; delete inflight.payouts; }
      }
    })();
    return inflight.payouts;
  }

  async function refresh(parts, { silent = false } = {}) {
    if (!hasSession() || !parts.length) return true;
    state.busy++; renderBusy();
    const results = await Promise.allSettled(parts.map((p) => LOADERS[p]()));
    state.busy--;
    let firstErr = null; const failed = [];
    results.forEach((r, i) => {
      const part = parts[i];
      if (r.status === "fulfilled") { state.updated[part] = new Date(); state.stale[part] = false; return; }
      if (r.reason && r.reason.name === "AbortError") return;
      state.stale[part] = true; failed.push(part); firstErr = firstErr || r.reason;
    });
    if (firstErr && firstErr.status && (firstErr.status === 401 || firstErr.status === 403)) state.conn = "bad";
    else if (results.some((r) => r.status === "fulfilled")) state.conn = "ok";
    if (failed.length) showBanner(firstErr, failed);
    else if (!silent || !Object.values(state.stale).some(Boolean)) hideBanner();
    renderBusy(); renderStale(); renderConn();
    if (!failed.length) renderAll();
    return !failed.length;
  }
  const currentParts = () => VIEWS[state.view].parts;

  function startPolling() {
    stopPolling();
    pollTimer = setInterval(() => {
      if (document.hidden || !hasSession() || inflight.summary || activeDialog || document.activeElement?.matches("input,select,textarea")) return;
      refresh(currentParts(), { silent: true });
    }, POLL_MS);
  }
  function stopPolling() { if (pollTimer) clearInterval(pollTimer); pollTimer = null; }

  // ---------- banner / freshness ----------
  const PART_NAMES = { summary: "summary counts", payouts: "transactions", recent: "recent transactions", queue: "queue jobs", earnings: "fee revenue", earningsPartners: "partner fee revenue", feeDetails: "fee audit", funds: "partner funds", enquiries: "partnership enquiries" };
  function showBanner(err, failed) {
    const names = failed.map((p) => PART_NAMES[p]).join(", ");
    const last = latestUpdate();
    const keep = failed.some((p) => state[p]) ? ` Showing data from ${last ? tf.format(last) : "the last successful load"}.` : "";
    $("bannerText").textContent = `Couldn't refresh ${names}. ${err ? err.message : ""}${keep}`;
    $("banner").hidden = false;
  }
  function hideBanner() { $("banner").hidden = true; }
  function latestUpdate() {
    const ds = currentParts().map((p) => state.updated[p]).filter(Boolean);
    return ds.length ? new Date(Math.min(...ds.map(Number))) : null;
  }
  function renderBusy() {
    const busy = state.busy > 0;
    const f = $("freshness");
    f.classList.toggle("busy", busy);
    const anyStale = currentParts().some((p) => state.stale[p]);
    f.classList.toggle("stale", !busy && anyStale);
    f.classList.toggle("ok", !busy && !anyStale && !!latestUpdate());
    const last = latestUpdate();
    if (!hasSession()) f.textContent = "Not connected";
    else if (busy) f.textContent = "Refreshing…";
    else if (anyStale) f.textContent = last ? `Stale · last updated ${tf.format(last)}` : "Stale · not loaded";
    else if (!currentParts().length) f.textContent = "No data source";
    else f.textContent = last ? `Updated ${tf.format(last)}` : "Not loaded";
    for (const id of ["refresh", "refreshQueue", "refreshEarnings", "refreshFunds", "refreshEnquiries"]) {
      $(id).disabled = busy; $(id).setAttribute("aria-busy", String(busy));
    }
  }
  function renderStale() {
    document.querySelectorAll("[data-part]").forEach((el) => {
      el.classList.toggle("stale-mark", !!state.stale[el.dataset.part] && !!state[el.dataset.part]);
    });
  }
  function renderConn() {
    const has = !!hasSession();
    const s = !has ? "none" : state.conn;
    $("connDot").className = `dot ${s === "ok" ? "ok" : s === "bad" ? "bad" : ""}`;
    $("connLabel").textContent = !has ? "Not connected" : s === "ok" ? "Connected" : s === "bad" ? "Connection failed" : state.sessionPending ? "Connecting…" : "Signed in";
  }

  // ---------- summary ----------
  const SUM_CARDS = [
    ["received", "RECEIVED"], ["processing", "PROCESSING"], ["sent", "SENT"], ["failed", "FAILED"],
  ];
  function renderSummary() {
    const s = state.summary;
    $("summaryCards").replaceChildren(...SUM_CARDS.map(([k, st]) => h("div", { class: "card", "data-testid": `summary-${k}` },
      h("div", { class: "cardTop" }, h("i", { class: PAYOUT_TONE[st], "aria-hidden": "true" }), PAYOUT_LABEL[st]),
      s ? h("div", { class: "metric", "data-testid": `summary-${k}-count` }, fmtCount(s.payouts && s.payouts[k])) : h("span", { class: "skel lg" }),
      h("p", {}, PAYOUT_MEANING[st]))));
    $("extraPayoutStates").textContent = s ? `Outcome unknown: ${fmtCount(s.payouts.unknown)} · Cancelled: ${fmtCount(s.payouts.cancelled)} · Rejected: ${fmtCount(s.payouts.rejected)}` : "";
    const q = s && s.queue;
    const items = [["pending", "Pending jobs", "Waiting for a worker"], ["in_progress", "In-progress jobs", "Leased by a worker"], ["expired", "Expired leases", "Lease ended before completion"], ["held", "Held jobs", "Requires reconciliation"]];
    $("queueStrip").replaceChildren(...items.map(([k, label, hint]) => h("div", { class: "stripItem", "data-testid": `queue-${k}` },
      q ? h("b", { "data-testid": `queue-${k}-count` }, fmtCount(q[k])) : h("span", { class: "skel", style: "width:32px;height:18px" }),
      h("span", {}, label, h("small", {}, hint)))));
  }

  // ---------- tables ----------
  function txColumns(items, tech) {
    const cols = [
      { label: "Created", cls: "date", cell: (r) => dateCell(r.created_at) },
      items.some(partnerOf) && { label: "Partner", cell: (r) => text(partnerOf(r)) },
      { label: "Transaction reference", cell: (r, i, t) => refCell(r.partner_tx_id, "transaction reference", `${t}-copy-ref-${i}`) },
      { label: "Recipient", cell: (r) => text(r.recipient) },
      items.some(channelOf) && { label: "Receiving channel", cell: (r) => text(channelOf(r)) },
      { label: "Amount", cls: "num", cell: (r) => text(fmtMoney(r.amount, r.currency)) },
      { label: "Payout status", cell: (r) => badge(r.status) },
      tech && { label: "Queue status", cell: (r) => badge(r.queue_status, "queue") },
      tech && { label: "Worker", cell: (r) => (r.worker_id ? h("span", { class: "mono trunc", title: r.worker_id }, r.worker_id) : dash()) },
      { label: "Actions", cls: "actions", cell: (r, i, t) => detailsBtn(r.id, r, `${t}-details-btn-${i}`) },
    ];
    return cols.filter(Boolean);
  }
  function detailsBtn(id, row, testid) {
    if (!id) return dash();
    return h("button", { type: "button", class: "link", "data-testid": testid,
      "aria-label": `View details for ${row.partner_tx_id || "payout"}`,
      onclick: (e) => openDrawer(id, row, e.currentTarget) }, "Details", icon("chevron"));
  }
  function renderTable(table, cols, items, testPrefix, emptyRow) {
    table.tHead.replaceChildren(h("tr", {}, cols.map((c) => h("th", { scope: "col", class: c.cls || null }, c.label))));
    const tb = table.tBodies[0];
    if (!items.length) { tb.replaceChildren(h("tr", { class: "emptyRow" }, h("td", { colspan: cols.length }, emptyRow))); return; }
    tb.replaceChildren(...items.map((r, i) => h("tr", { "data-testid": `${testPrefix}-row-${i}` },
      cols.map((c) => h("td", { class: c.cls || null }, c.cell(r, i, testPrefix))))));
  }
  function skeletonRows(table, n, widths) {
    table.tHead.replaceChildren(h("tr", {}, widths.map(([label, , cls]) => h("th", { scope: "col", class: cls || null }, label))));
    table.tBodies[0].replaceChildren(...Array.from({ length: n }, () => h("tr", { "aria-hidden": "true" },
      widths.map(([, w, cls]) => h("td", { class: cls || null }, h("span", { class: "skel", style: `width:${w}px` }))))));
  }
  const TX_SKEL = [["Created", 120], ["Transaction reference", 150], ["Recipient", 110], ["Amount", 80, "num"], ["Payout status", 70], ["Actions", 64, "actions"]];

  const filtersActive = () => !!(state.q || state.status);
  function renderPayouts() {
    const d = state.payouts;
    const table = $("txTable"), wrap = $("txWrap");
    renderChips();
    if (!d) { skeletonRows(table, 8, TX_SKEL); $("txCount").textContent = ""; $("pageInfo").textContent = ""; $("prev").disabled = $("next").disabled = true; return; }
    const sl = wrap.scrollLeft;
    const items = d.items || [];
    const empty = filtersActive()
      ? [h("h3", {}, "No matching transactions"), h("p", {}, "No transactions match the current search or payout status."),
         h("button", { type: "button", class: "btn secondary sm", "data-testid": "empty-clear-filters", onclick: clearFilters }, "Clear filters")]
      : [h("h3", {}, "No transactions yet"), h("p", {}, "Payout instructions submitted by partners will appear here.")];
    renderTable(table, txColumns(items, state.tech), items, "tx", empty);
    wrap.scrollLeft = sl;
    const total = Number(d.total) || 0;
    const lim = Number(d.limit) || LIMIT, off = Number(d.offset) || 0;
    $("txCount").textContent = `${cf.format(total)} ${total === 1 ? "result" : "results"}`;
    $("pageInfo").textContent = total ? `Showing ${cf.format(off + 1)}–${cf.format(Math.min(off + items.length, total))} of ${cf.format(total)} · page ${Math.floor(off / lim) + 1} of ${Math.max(1, Math.ceil(total / lim))}` : "";
    $("prev").disabled = off <= 0;
    $("next").disabled = off + lim >= total;
  }
  function renderRecent() {
    const d = state.recent, table = $("recentTable");
    if (!d) { skeletonRows(table, 5, TX_SKEL); return; }
    const items = d.items || [];
    renderTable(table, txColumns(items, false), items, "recent",
      [h("h3", {}, "No transactions yet"), h("p", {}, "Payout instructions submitted by partners will appear here.")]);
  }
  function renderQueue() {
    const d = state.queue, table = $("queueTable");
    if (!d) { skeletonRows(table, 6, [["Queued", 120], ["Payout", 120], ["Queue status", 80], ["Lease until", 120], ["Worker", 90], ["Recipient", 100], ["Amount", 80, "num"], ["Actions", 64, "actions"]]); $("queueCount").textContent = ""; return; }
    const items = d.items || [];
    const cols = [
      { label: "Queued", cls: "date", cell: (r) => dateCell(r.queue_created) },
      { label: "Payout", cell: (r, i) => refCell(r.payout_id, "payout ID", `queue-copy-id-${i}`) },
      { label: "Queue status", cell: (r) => badge(r.queue_status, "queue") },
      { label: "Lease until", cls: "date", cell: (r) => r.lease_until
        ? h("span", {}, fmtDate(r.lease_until), isPast(r.lease_until) && /progress/i.test(r.queue_status || "") ? h("span", { class: "leaseExp" }, "Lease expired") : null)
        : dash() },
      { label: "Worker", cell: (r) => (r.worker_id ? h("span", { class: "mono trunc", title: r.worker_id }, r.worker_id) : dash()) },
      { label: "Recipient", cell: (r) => text(r.recipient) },
      { label: "Amount", cls: "num", cell: (r) => text(fmtMoney(r.amount, r.currency)) },
      { label: "Actions", cls: "actions", cell: (r, i) => detailsBtn(r.payout_id, r, `queue-details-btn-${i}`) },
    ];
    const sl = $("queueWrap").scrollLeft;
    renderTable(table, cols, items, "queue", [h("h3", {}, "Queue is empty"), h("p", {}, "There are no queue jobs to show right now.")]);
    $("queueWrap").scrollLeft = sl;
    $("queueCount").textContent = `${cf.format(items.length)} ${items.length === 1 ? "job" : "jobs"} shown${items.length >= QUEUE_LIMIT ? ` (latest ${QUEUE_LIMIT})` : ""}`;
  }

  function renderChips() {
    const box = $("activeFilters");
    const chips = [];
    const chip = (label, onRemove, testid) => h("span", { class: "chip", "data-testid": testid }, label,
      h("button", { type: "button", "aria-label": `Remove filter: ${label}`, onclick: onRemove }, icon("x")));
    if (state.q) chips.push(chip(`Search: “${state.q}”`, () => { state.q = ""; $("search").value = ""; applyFilters(); }, "chip-search"));
    if (state.status) chips.push(chip(`Payout status: ${PAYOUT_LABEL[state.status] || state.status}`, () => { state.status = ""; $("status").value = ""; applyFilters(); }, "chip-status"));
    if (chips.length) chips.push(h("button", { type: "button", class: "linkBtn", "data-testid": "clear-all-filters", onclick: clearFilters }, "Clear all"));
    box.replaceChildren(...chips);
    box.hidden = !chips.length;
  }
  function clearFilters() {
    state.q = ""; state.status = ""; $("search").value = ""; $("status").value = "";
    applyFilters();
  }
  function applyFilters() {
    state.offset = 0;
    writeHash();
    renderChips();
    refresh(["payouts"]);
  }

  // ---------- views / routing ----------
  function parseHash() {
    const [path, qs] = location.hash.replace(/^#\/?/, "").split("?");
    const p = new URLSearchParams(qs || "");
    state.view = VIEWS[path] ? path : "overview";
    state.q = p.get("q") || "";
    state.status = PAYOUT_TONE[p.get("status")] ? p.get("status") : "";
    state.offset = Math.max(0, parseInt(p.get("offset"), 10) || 0);
    state.tech = p.get("tech") === "1";
    business.parseHash(state.view, p);
  }
  function writeHash() {
    const p = new URLSearchParams();
    if (state.view === "transactions") {
      if (state.q) p.set("q", state.q);
      if (state.status) p.set("status", state.status);
      if (state.offset) p.set("offset", state.offset);
      if (state.tech) p.set("tech", "1");
    }
    if (state.view !== "transactions") business.hashParams(state.view).forEach((v, k) => p.set(k, v));
    const s = p.toString();
    history.replaceState(null, "", `#/${state.view}${s ? `?${s}` : ""}`);
  }
  function showView() {
    const v = state.view, cfg = VIEWS[v], has = !!hasSession();
    $("pageTitle").textContent = cfg.title;
    document.title = `${cfg.title} · Hubaal`;
    document.querySelectorAll(".nav a").forEach((a) => (a.dataset.view === v ? a.setAttribute("aria-current", "page") : a.removeAttribute("aria-current")));
    const needsData = cfg.parts.length > 0;
    $("connectPrompt").hidden = has || !needsData;
    document.querySelectorAll("[data-views]").forEach((el) => {
      const inView = el.dataset.views.split(" ").includes(v);
      el.hidden = !inView || (needsData && !has);
    });
    $("search").value = state.q; $("status").value = state.status; $("techToggle").checked = state.tech;
    closeNav();
    renderAll(); renderBusy(); renderStale(); renderConn();
    if (state.stale && !currentParts().some((p) => state.stale[p])) hideBanner();
  }
  function renderAll() { renderSummary(); renderRecent(); renderPayouts(); renderQueue(); business.renderAll(); }
  function onRoute() {
    const prevView = state.view;
    parseHash();
    showView();
    refresh(currentParts());
  }

  // ---------- nav (mobile) ----------
  function openNav() { document.querySelector(".main").inert = true; document.body.style.overflow = "hidden"; $("sidebar").classList.add("open"); $("navScrim").classList.add("open"); $("navScrim").hidden = false; $("menuBtn").setAttribute("aria-expanded", "true"); $("sidebar").querySelector("a").focus(); }
  function closeNav() { if (!$("sidebar").classList.contains("open")) return; $("sidebar").classList.remove("open"); $("navScrim").classList.remove("open"); $("navScrim").hidden = true; $("menuBtn").setAttribute("aria-expanded", "false"); document.querySelector(".main").inert = false; document.body.style.overflow = ""; }

  // ---------- dialogs ----------
  let activeDialog = null;
  function openDialog(rootId, panelId, trigger) {
    activeDialog = { root: $(rootId), panel: $(panelId), trigger: trigger || document.activeElement };
    activeDialog.root.hidden = false;
    document.querySelector(".app").inert = true;
    document.body.style.overflow = "hidden";
  }
  function closeDialog() {
    if (!activeDialog) return;
    const { root, trigger } = activeDialog;
    root.hidden = true; activeDialog = null; drawerReq++;
    business.onDialogClose();
    document.querySelector(".app").inert = false;
    document.body.style.overflow = "";
    if (trigger && document.contains(trigger)) trigger.focus();
  }
  function trapFocus(e) {
    const panel = activeDialog?.panel || ($("sidebar").classList.contains("open") ? $("sidebar") : null);
    if (!panel || e.key !== "Tab") return;
    const f = [...panel.querySelectorAll("button, [href], input, select, summary, [tabindex]:not([tabindex='-1'])")].filter((el) => !el.disabled && el.offsetParent !== null);
    if (!f.length) return;
    const first = f[0], last = f[f.length - 1];
    if (e.shiftKey && (document.activeElement === first || document.activeElement === panel)) { e.preventDefault(); last.focus(); }
    else if (!e.shiftKey && document.activeElement === last) { e.preventDefault(); first.focus(); }
  }

  // ---------- transaction drawer ----------
  let drawerReq = 0;
  async function openDrawer(id, row, trigger) {
    const req = ++drawerReq;
    openDialog("drawerRoot", "drawer", trigger);
    renderDetail(null, row, id);
    $("closeDrawer").focus();
    try {
      const detail = await api(`/admin/api/payouts/${encodeURIComponent(id)}`);
      if (req === drawerReq) renderDetail(detail, row, id);
    } catch (err) {
      if (req !== drawerReq) return;
      renderDetail(null, row, id, err);
    }
  }

  function kv(pairs) {
    return h("dl", { class: "kv" }, pairs.flatMap(([k, v, testid]) => [h("dt", {}, k), h("dd", { "data-testid": testid || null }, v == null || v === "" ? missing() : v)]));
  }
  function section(title, ...kids) { return h("section", { class: "dSection", "aria-label": title }, h("h3", {}, title), ...kids); }

  function renderDetail(detail, row, id, err) {
    const L = makeLookup(detail, row);
    const status = L("status");
    const ref = L("partner_tx_id", "partner_reference", "reference");
    $("drawerSub").replaceChildren(ref ? h("span", { class: "mono" }, ref) : "No transaction reference recorded");
    const body = $("drawerBody");
    const loading = !detail && !err;
    const top = [];
    if (err) top.push(h("div", { class: "callout failure", role: "alert", "data-testid": "drawer-error" },
      h("b", {}, "Couldn't load full details."), `${err.message} Showing the fields from the table row.`,
      h("div", {}, h("button", { type: "button", class: "btn secondary sm", "data-testid": "drawer-retry", onclick: () => openDrawer(id, row, activeDialog && activeDialog.trigger) }, "Retry"))));
    if (loading) top.push(h("p", { class: "caption", "aria-live": "polite" }, h("span", { class: "skel", style: "width:120px" }), " Loading full record…"));

    const err1 = L("failure_reason", "error_message", "last_error", "error", "provider_error");
    const lease = L("lease_until");
    const qStatus = L("queue_status");
    const callouts = [];
    if (status === "FAILED") callouts.push(h("div", { class: "callout failure", "data-testid": "drawer-failure" },
      h("b", {}, "Payout recorded as failed"), err1 ? `Recorded reason: ${typeof err1 === "string" ? err1 : JSON.stringify(redact(err1))}` : "No failure reason is recorded by the backend."));
    if (status === "PROCESSING" && lease && isPast(lease)) callouts.push(h("div", { class: "callout pending", "data-testid": "drawer-uncertain" },
      h("b", {}, "Outcome not confirmed"), `Still PROCESSING and the worker lease ended at ${fmtDate(lease)}. The backend has not recorded a final outcome.`));

    const overview = section("Payout overview",
      ...callouts,
      kv([
        ["Transaction reference", ref ? h("span", { class: "ref" }, h("span", { class: "mono trunc", title: ref }, ref), copyBtn(ref, "transaction reference", "drawer-copy-ref")) : null, "drawer-ref"],
        ["Partner", partnerOf({ partner_name: L("partner_name"), partner: L("partner"), partner_id: L("partner_id") }), "drawer-partner"],
        ["Amount", fmtMoney(L("amount"), L("currency")) && h("span", { class: "tnum", style: "font-weight:600" }, fmtMoney(L("amount"), L("currency"))), "drawer-amount"],
        ["Recipient", L("recipient", "recipient_name", "recipient_msisdn", "recipient_account"), "drawer-recipient"],
        ["Receiving channel", L("receiving_channel", "channel", "wallet", "bank", "provider", "method"), "drawer-channel"],
        ["Payout status", status ? h("span", {}, badge(status), h("span", { class: "sub", style: "margin-top:4px" }, `${PAYOUT_MEANING[status] || ""}${status === "SENT" ? " Not a confirmation of recipient delivery." : ""}`)) : null, "drawer-status"],
        ["Created", fmtDate(L("created_at")), "drawer-created"],
        ["Payout ID", id ? h("span", { class: "ref" }, h("span", { class: "mono trunc", title: id }, id), copyBtn(id, "payout ID", "drawer-copy-id")) : null, "drawer-id"],
      ]));

    const events = L("events", "history", "status_history", "activity", "audit_log");
    let activity;
    if (Array.isArray(events) && events.length) {
      activity = h("ol", { class: "timeline", "data-testid": "drawer-activity" }, events.map((ev) => {
        const e = ev && typeof ev === "object" ? ev : { message: String(ev) };
        const when = e.at || e.created_at || e.timestamp || e.ts || e.time;
        const what = e.status || e.type || e.event || e.action || "Event";
        const msg = e.message || e.detail || e.note;
        return h("li", {}, h("div", {}, h("div", { style: "font-weight:600" }, String(what)), msg ? h("div", {}, String(msg)) : null, h("div", { class: "when" }, fmtDate(when) || "Time not recorded")));
      }));
    } else {
      const stamps = [["Created", L("created_at")], ["Queued", L("queue_created")], ["Updated", L("updated_at")], ["Sent", L("sent_at")], ["Failed", L("failed_at")], ["Completed", L("completed_at")]].filter(([, v]) => v);
      activity = h("div", { "data-testid": "drawer-activity" },
        h("p", { class: "hint" }, "No event history is returned by the admin API. Recorded timestamps only:"),
        stamps.length ? h("ol", { class: "timeline" }, stamps.map(([k, v]) => h("li", {}, h("div", {}, h("div", { style: "font-weight:600" }, k), h("div", { class: "when" }, fmtDate(v)))))) : missing("No timestamps recorded"));
    }

    const attempts = L("attempt_count", "attempt", "tries", "retries");
    const execution = section("Execution details",
      h("p", { class: "hint" }, "Queue state describes the worker job, not the payout outcome."),
      kv([
        ["Queue status", qStatus ? badge(qStatus, "queue") : null, "drawer-queue-status"],
        ["Assigned worker", L("worker_id") ? h("span", { class: "mono" }, L("worker_id")) : null, "drawer-worker"],
        ["Lease until", lease ? `${fmtDate(lease)}${isPast(lease) ? " (ended)" : ""}` : null, "drawer-lease"],
        ["Attempts", attempts != null ? h("span", { class: "tnum" }, String(attempts)) : null, "drawer-attempts"],
        ["Provider reference", L("provider_ref", "provider_reference") ? h("span", { class: "ref" }, h("span", { class: "mono trunc", title: L("provider_ref", "provider_reference") }, L("provider_ref", "provider_reference")), copyBtn(L("provider_ref", "provider_reference"), "provider reference", "drawer-copy-provider")) : null, "drawer-provider-ref"],
        ["Recorded error", err1 ? (typeof err1 === "string" ? err1 : JSON.stringify(redact(err1))) : null, "drawer-error-text"],
      ]));

    const cbStatus = L("webhook_status", "callback_status", "notification_status", "notify_status");
    const cbAttempts = L("webhook_attempts", "callback_attempts", "notification_attempts");
    const cbLast = L("webhook_accepted_at", "webhook_last_at", "callback_last_at", "last_callback_at", "notified_at");
    const cbResp = L("webhook_last_response", "last_callback_response", "callback_response", "webhook_response", "last_webhook_status_code");
    const hasCb = [cbStatus, cbAttempts, cbLast, cbResp].some((v) => v != null);
    const notification = section("Partner notification",
      h("p", { class: "hint" }, "Callback delivery to the partner is separate from payout execution. A failed callback does not mean the payout failed."),
      hasCb ? kv([
        ["Callback status", cbStatus ? h("span", { class: "badge neutral" }, String(cbStatus)) : null, "drawer-cb-status"],
        ["Attempts", cbAttempts != null ? String(cbAttempts) : null, "drawer-cb-attempts"],
        ["Last attempt", fmtDate(cbLast), "drawer-cb-last"],
        ["Last response", cbResp != null ? h("span", { class: "mono" }, typeof cbResp === "string" ? cbResp : JSON.stringify(redact(cbResp))) : null, "drawer-cb-response"],
      ]) : h("p", { "data-testid": "drawer-cb-none" }, missing("No partner notification data is returned by the admin API.")));

    const actions = section("Actions",
      h("p", { class: "hint", "data-testid": "drawer-actions-none" }, "No operational actions are exposed by the current admin API. Payout status can only change through authorised backend processes."));

    const raw = detail ? h("section", { class: "dSection" }, h("details", { class: "raw", "data-testid": "drawer-raw" },
      h("summary", {}, "Technical view: raw record"), h("pre", { class: "mono" }, JSON.stringify(redact(detail), null, 2)))) : null;

    body.replaceChildren(...top, overview, section("Activity", activity), execution, notification, actions, raw);
  }

  // ---------- administrator connection ----------
  function openConnection(trigger) {
    $("sessionUsername").textContent = state.session?.username || "Not signed in";
    $("connStatus").textContent = state.conn === "ok" ? "Connected to the payout API." : state.conn === "bad" ? "Sign in again to restore access." : "Ready to load authenticated data.";
    $("sessionSignIn").hidden = !!state.session;
    openDialog("connRoot", "connModal", trigger);
    $("closeConn").focus();
  }
  async function connectSession() {
    state.sessionPending = true;
    try {
      state.session = await api("/admin/api/session"); state.conn = "pending";
      state.sessionPending = false; showView(); startPolling();
      const ok = await refresh(currentParts());
      $("connStatus").textContent = ok ? "Connected to the payout API." : "Some data could not load. Retry the connection.";
      $("sessionUsername").textContent = state.session?.username || "Not signed in";
      return ok;
    } catch (err) {
      state.sessionPending = false; showBanner(err, currentParts()); showView();
      $("connStatus").textContent = err.message;
      return false;
    }
  }

  // ---------- wiring ----------
  function wireUI() {
    $("menuBtn").append(icon("menu"));
    document.querySelectorAll(".nav a[data-icon]").forEach((a) => a.prepend(icon(a.dataset.icon)));
    $("closeDrawer").append(icon("x"));
    $("closeConn").append(icon("x"));
    document.querySelector(".searchIcon").append(icon("search"));

    let deb;
    $("search").addEventListener("input", () => {
      clearTimeout(deb);
      deb = setTimeout(() => { const v = $("search").value.trim(); if (v !== state.q) { state.q = v; applyFilters(); } }, 350);
    });
    $("search").addEventListener("keydown", (e) => {
      if (e.key === "Enter") { clearTimeout(deb); const v = $("search").value.trim(); if (v !== state.q) { state.q = v; applyFilters(); } }
    });
    $("status").addEventListener("change", () => { state.status = $("status").value; applyFilters(); });
    $("techToggle").addEventListener("change", () => { state.tech = $("techToggle").checked; writeHash(); renderPayouts(); });
    $("refresh").addEventListener("click", () => refresh(currentParts()));
    $("refreshQueue").addEventListener("click", () => refresh(currentParts()));
    $("bannerRetry").addEventListener("click", () => refresh(currentParts()));
    $("prev").addEventListener("click", () => { state.offset = Math.max(0, state.offset - LIMIT); writeHash(); refresh(["payouts"]).then(() => $("txHead").scrollIntoView({ block: "nearest" })); });
    $("next").addEventListener("click", () => { state.offset += LIMIT; writeHash(); refresh(["payouts"]).then(() => $("txHead").scrollIntoView({ block: "nearest" })); });

    $("menuBtn").addEventListener("click", openNav);
    $("navScrim").addEventListener("click", closeNav);
    $("openConnection").addEventListener("click", (e) => { closeNav(); openConnection(e.currentTarget); });
    $("connectPromptBtn").addEventListener("click", (e) => openConnection(e.currentTarget));
    $("reconnectSession").addEventListener("click", async () => { if (await connectSession()) { closeDialog(); toast("Connected. Dashboard refreshed."); } });
    $("logoutSession").addEventListener("click", async () => {
      $("logoutSession").disabled = true;
      try {
        const response = await fetch("/logout", { method: "POST", credentials: "same-origin", headers: { "X-CSRF-Token": csrfToken() }, redirect: "manual" });
        if (!response.ok && response.type !== "opaqueredirect" && response.status !== 303) throw Error("Sign out failed. Please retry.");
        expireSession(); location.assign("/login");
      } catch (error) { $("connStatus").textContent = error.message; $("logoutSession").disabled = false; }
    });
    $("closeBusiness").append(icon("x"));
    $("closeBusiness").addEventListener("click", closeDialog);
    business.wireUI();
    $("closeDrawer").addEventListener("click", closeDialog);
    $("closeConn").addEventListener("click", closeDialog);
    document.querySelectorAll("[data-close]").forEach((el) => el.addEventListener("click", closeDialog));
    document.addEventListener("keydown", (e) => {
      if (e.key === "Escape") { if (activeDialog) closeDialog(); else { closeNav(); $("menuBtn").focus(); } }
      trapFocus(e);
    });

    window.addEventListener("hashchange", onRoute);
    document.addEventListener("visibilitychange", () => { if (!document.hidden && hasSession()) refresh(currentParts(), { silent: true }); });
    window.addEventListener("pagehide", stopPolling);
    window.addEventListener("pageshow", startPolling);
  }

  (function boot() {
    wireUI();
    parseHash();
    if (!location.hash) writeHash();
    showView();
    startPolling();
    connectSession();
  })();
})();
