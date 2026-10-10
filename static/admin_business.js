/** Live business views for the supplied operations dashboard. */
export function createBusinessViews(ui) {
  const { $, state, api, h, fmtMoney, dateCell, fmtDate, text, badge, refCell,
    renderTable, skeletonRows, kv, section, toast, openDialog, closeDialog,
    refresh, writeHash, openDrawer } = ui;
  const PAGE = 50, PARTNERS_PAGE = 100;
  const defaults = () => ({ preset: "month", currency: "USD", activity: "live", partner_id: "", start: "", end: "" });
  let earningsFilter = defaults(), feeOffset = 0, partnerOffset = 0, feeState = "", feeSort = "accepted_desc";
  let fundsFilter = { search: "", status: "", sort: "balance_desc", page: 1 };
  let enquiriesFilter = { q: "", offset: 0 };
  const requests = new Map();
  const choice = (value, values, fallback) => values.includes(value) ? value : fallback;
  const positive = value => /^\d+$/.test(value || "") && Number(value) > 0 && Number(value) <= 2147483647 ? value : "";
  const offset = value => Math.max(0, Math.min(100000000, Number.parseInt(value, 10) || 0));
  const empty = message => [h("h3", {}, message)];
  const loading = table => skeletonRows($(table), 4, [["Loading records", 150], ["", 110], ["", 90]]);
  const money = (value, currency) => text(fmtMoney(value, currency));

  function earningsParams() {
    const p = new URLSearchParams({ preset: earningsFilter.preset, currency: earningsFilter.currency, activity: earningsFilter.activity });
    if (earningsFilter.partner_id) p.set("partner_id", earningsFilter.partner_id);
    if (earningsFilter.preset === "custom") { p.set("start", earningsFilter.start); p.set("end", earningsFilter.end); }
    return p;
  }
  function detailParams() {
    const p = earningsParams();
    p.set("sort", feeSort); if (feeState) p.set("state", feeState);
    return p;
  }
  async function latest(part, url, render) {
    const prior = requests.get(part);
    if (prior?.url === url) return prior.promise;
    prior?.controller.abort();
    const request = { url, controller: new AbortController() };
    requests.set(part, request);
    request.promise = (async () => {
      try {
        const data = await api(url, request.controller.signal);
        if (requests.get(part) !== request) throw new DOMException("Superseded request", "AbortError");
        state[part] = data; render();
      } finally {
        if (requests.get(part) === request) requests.delete(part);
      }
    })();
    return request.promise;
  }
  const loaders = {
    earnings: () => latest("earnings", `/admin/api/earnings?${earningsParams()}`, renderEarnings),
    earningsPartners: () => latest("earningsPartners", `/admin/api/earnings/partners?${earningsParams()}&limit=${PARTNERS_PAGE}&offset=${partnerOffset}`, renderEarningsPartners),
    feeDetails: () => latest("feeDetails", `/admin/api/earnings/details?${detailParams()}&limit=${PAGE}&offset=${feeOffset}`, renderFees),
    funds: () => latest("funds", `/admin/api/funds/partners?${new URLSearchParams({ ...fundsFilter, limit: PAGE })}`, renderFunds),
    enquiries: () => latest("enquiries", `/admin/api/partnerships?${new URLSearchParams({ ...enquiriesFilter, limit: PAGE })}`, renderEnquiries),
  };
  function pager(prefix, data) {
    const total = Number(data?.total) || 0, limit = Number(data?.limit) || PAGE;
    const off = data?.offset ?? ((data?.page || 1) - 1) * limit;
    const rows = data?.items || data?.partners || [];
    $(`${prefix}PageInfo`).textContent = !data ? "" : total && rows.length
      ? `Showing ${off + 1}–${Math.min(off + rows.length, total)} of ${total}` : `No records on this page · ${total} total`;
    $(`${prefix}Prev`).disabled = !data || off <= 0;
    $(`${prefix}Next`).disabled = !data || off + limit >= total;
  }

  function renderEarnings() {
    const report = state.earnings, s = report?.summary;
    const cards = [["net", "Net fee revenue", "Gross earned fees minus fee reversals"],
      ["gross", "Gross earned fees", "Recognitions posted in the selected period"],
      ["pending", "Pending fees", "Current holds; included in reserved funds"],
      ["reversals", "Fee reversals", "Compensating entries posted in the selected period"]];
    $("earningsCards").replaceChildren(...cards.map(([key, title, hint]) => h("div", { class: "card", "data-testid": `earnings-${key}` },
      h("div", { class: "cardTop" }, title), s ? h("div", { class: "metric", "data-testid": `earnings-${key}-amount` }, money(s[key], s.currency)) : h("span", { class: "skel lg" }), h("p", {}, hint))));
    $("earningsScope").textContent = s ? `${s.start_date} through ${s.end_date} · ${s.timezone} · ${s.currency} · ${s.activity}. Snapshot ${fmtDate(s.snapshot_at)}. ${s.reconciliation_required} payouts require fee reconciliation.` : "";
    const trend = report?.trend || [];
    $("earningsTrend").replaceChildren(!s ? h("span", { class: "skel lg" }) : !trend.length ? h("p", { class: "caption" }, "No financial postings in this period.")
      : h("ol", { class: "trendRows" }, trend.map(row => h("li", {}, h("span", {}, row.day), h("strong", { class: "tnum" }, money(row.net, s.currency))))));
    $("earningsExport").href = `/admin/api/earnings/export.csv?${detailParams()}`;
  }
  function renderEarningsPartners() {
    const data = state.earningsPartners;
    if (!data) { loading("earningsPartners"); $("prevEarningsPartners").disabled = $("moreEarningsPartners").disabled = true; return; }
    renderTable($("earningsPartners"), [
      { label: "Partner", cell: r => h("button", { type: "button", class: "link", onclick: () => choosePartner(r.id) }, r.name) },
      ...["gross", "reversals", "net", "pending"].map(key => ({ label: { gross: "Gross earned", reversals: "Reversals", net: "Net revenue", pending: "Pending now" }[key], cls: "num", cell: r => money(r[key], earningsFilter.currency) })),
      { label: "Payouts", cls: "num", cell: r => text(r.payout_count) },
    ], data.items || [], "earnings-partner", empty("No fee activity in this scope."));
    $("earningsPartnersInfo").textContent = data.items?.length ? `Showing partners ${partnerOffset + 1}–${partnerOffset + data.items.length}` : "No partners on this page";
    $("prevEarningsPartners").disabled = partnerOffset === 0;
    $("moreEarningsPartners").disabled = (data.items?.length || 0) < PARTNERS_PAGE;
  }
  function choosePartner(id) {
    earningsFilter.partner_id = String(id); $("earningsPartner").value = String(id);
    feeOffset = partnerOffset = 0; clearEarnings(); writeHash(); refresh(["earnings", "earningsPartners", "feeDetails"]);
  }
  function renderFees() {
    const data = state.feeDetails;
    if (!data) { loading("feeTable"); pager("fee", null); return; }
    renderTable($("feeTable"), [
      { label: "Partner / payout", cell: r => h("div", {}, h("strong", {}, r.partner), refCell(r.external_reference || r.payout_id, "transaction reference")) },
      { label: "Principal", cls: "num", cell: r => money(r.principal, r.currency) },
      { label: "Original fee", cls: "num", cell: r => money(r.original_fee, r.currency) },
      { label: "Payout / fee state", cell: r => h("div", {}, badge(r.payout_state), h("span", { class: "sub" }, r.fee_state)) },
      { label: "Recognized", cls: "num", cell: r => money(r.gross_earned, r.currency) },
      { label: "Reversed", cls: "num", cell: r => money(r.reversed, r.currency) },
      { label: "Net lifetime fees", cls: "num", cell: r => money(r.net, r.currency) },
      { label: "Actions", cell: r => h("button", { class: "link", type: "button", onclick: e => showFeeAudit(r, e.currentTarget) }, "Ledger audit") },
    ], data.items || [], "fee", empty("No fee records in this scope."));
    pager("fee", data);
  }
  function dialog(title, trigger, ...children) {
    historyRequest++;
    $("businessTitle").textContent = title; $("businessBody").replaceChildren(...children);
    openDialog("businessRoot", "businessDialog", trigger); $("closeBusiness").focus();
  }
  function showFeeAudit(row, trigger) {
    const events = Array.isArray(row.financial_events) ? row.financial_events : [];
    dialog("Transaction fee audit", trigger, kv([
      ["Partner", row.partner], ["Transaction reference", row.external_reference], ["Payout ID", row.payout_id],
      ["Principal", money(row.principal, row.currency)], ["Original fee", money(row.original_fee, row.currency)],
      ["Policy version", row.policy_version], ["Activity", row.activity], ["Fee state", row.fee_state],
      ["Period net revenue", money(row.period_net, row.currency)], ["Lifetime net revenue", money(row.net, row.currency)],
      ["Recognized", fmtDate(row.recognized_at)], ["Evidence state", row.evidence_state],
    ]), section("Ledger postings", events.length ? h("ol", { class: "timeline" }, events.map(event => h("li", {}, h("div", {},
      h("strong", {}, event.event_type), h("p", { class: "mono" }, event.journal_id), h("p", {}, `Minor units: ${event.amount_minor}`),
      h("p", {}, event.reason || ""), h("p", {}, event.evidence_ref || ""), h("p", { class: "when" }, fmtDate(event.posted_at))))))
      : h("p", { class: "caption" }, "No recognized fee postings for this payout.")),
      h("button", { class: "btn secondary", type: "button", onclick: e => { closeDialog(); openDrawer(row.payout_id, { partner_tx_id: row.external_reference }, trigger); } }, "View payout details"));
  }

  function renderFunds() {
    const data = state.funds;
    if (!data) { loading("fundsTable"); pager("funds", null); return; }
    renderTable($("fundsTable"), [
      { label: "Partner", cell: r => h("div", {}, h("strong", {}, r.name), h("span", { class: "sub" }, `Partner ${r.id}`)) },
      { label: "Status", cell: r => h("span", { class: `badge ${r.is_active ? "success" : "neutral"}` }, r.is_active ? "Active" : "Inactive") },
      { label: "Available", cls: "num", cell: r => money(r.balance_available, r.funding_currency) },
      { label: "Reserved", cls: "num", cell: r => money(r.balance_reserved, r.funding_currency) },
      { label: "Total", cls: "num", cell: r => money(r.balance_total, r.funding_currency) },
      { label: "Updated", cls: "date", cell: r => dateCell(r.updated_at) },
      { label: "Actions", cell: r => h("div", { class: "rowActions" },
        h("button", { class: "link", type: "button", onclick: e => showFundingHistory(r, e.currentTarget) }, "Funding history"),
        h("button", { class: "btn secondary sm", type: "button", disabled: !r.is_active || !r.ledger_enabled, onclick: e => showDeposit(r, e.currentTarget), title: !r.ledger_enabled ? "Opening funding must be reconciled first" : "Record received partner funding" }, "Record deposit")) },
    ], data.partners || [], "funds", empty("No partners match these filters."));
    pager("funds", data);
  }
  let historyRequest = 0;
  async function showFundingHistory(partner, trigger) {
    dialog(`${partner.name} · Funding history`, trigger, h("p", { class: "caption" }, "Loading received funding…"));
    const request = historyRequest;
    try {
      const data = await api(`/admin/api/funds/history/${partner.id}?limit=50`);
      if (request !== historyRequest || $("businessRoot").hidden) return;
      const table = h("table", {}, h("thead"), h("tbody"));
      renderTable(table, [
        { label: "Recorded", cls: "date", cell: r => dateCell(r.created_at) },
        { label: "Type", cell: r => text(r.type) },
        { label: "Amount", cell: r => money(r.amount, partner.funding_currency) },
        { label: "Reference", cell: r => refCell(r.reference, "funding reference") },
        { label: "Recorded by", cell: r => text(r.admin_user) },
      ], data.history || [], "funding-history", empty("No funding deposits recorded."));
      $("businessBody").replaceChildren(h("p", { class: "caption" }, "Funding history records partner deposits; payout movements are reflected in available and reserved balances."), h("div", { class: "tableWrap" }, table));
    } catch (error) { if (request === historyRequest && !$("businessRoot").hidden) $("businessBody").replaceChildren(h("p", { role: "alert" }, error.message), h("button", { type: "button", class: "btn secondary", onclick: () => showFundingHistory(partner, trigger) }, "Retry")); }
  }
  function showDeposit(partner, trigger) {
    const form = h("form", { class: "depositForm", "data-testid": "deposit-form" });
    const input = (label, name, attrs) => {
      const control = h("input", { name, id: `deposit-${name}`, required: true, ...attrs });
      form.append(h("label", { for: `deposit-${name}`, class: "fieldLabel" }, label), control); return control;
    };
    form.append(h("p", { class: "caption" }, `Record funding already received from ${partner.name}. Currency: ${partner.funding_currency}.`));
    const amount = input("Amount received", "amount", { type: "number", min: "0.01", max: "9999999999999.99", step: "0.01", inputmode: "decimal" });
    const reference = input("Unique funding reference", "reference", { type: "text", maxlength: 128 });
    const evidence = input("Bank or funding evidence reference", "evidence", { type: "text", maxlength: 512 });
    const notice = h("p", { role: "status", "aria-live": "polite", "data-testid": "deposit-status" });
    const review = h("div", { class: "depositReview", hidden: true });
    const edit = h("button", { type: "button", class: "btn secondary", hidden: true }, "Edit details");
    const submit = h("button", { type: "submit", class: "btn primary", "data-testid": "deposit-submit" }, "Review deposit");
    form.append(review, notice, h("div", { class: "formBtns" }, edit, submit));
    let approved = null, submitting = false;
    edit.addEventListener("click", () => { approved = null; review.hidden = edit.hidden = true; [amount, reference, evidence].forEach(e => e.readOnly = false); submit.textContent = "Review deposit"; amount.focus(); });
    form.addEventListener("submit", async event => {
      event.preventDefault(); if (submitting) return;
      if (!approved) {
        approved = { partner_id: partner.id, amount: amount.value, reference: reference.value.trim(), note: evidence.value.trim() };
        if (!approved.reference || !approved.note) { approved = null; notice.textContent = "Enter a funding reference and evidence reference."; return; }
        review.replaceChildren(kv([["Partner", partner.name], ["Amount", money(approved.amount, partner.funding_currency)], ["Funding reference", approved.reference], ["Evidence", approved.note]]));
        review.hidden = edit.hidden = false; [amount, reference, evidence].forEach(e => e.readOnly = true); submit.textContent = "Confirm received deposit"; submit.focus(); return;
      }
      submitting = true; submit.disabled = edit.disabled = true; notice.textContent = "Recording deposit…";
      try {
        const result = await api("/admin/api/funds/deposit", undefined, { method: "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify(approved) });
        closeDialog(); toast(`Deposit recorded · ${result.journal_id}`); state.funds = null; refresh(["funds"]);
      } catch (error) {
        notice.textContent = `${error.message} Keep the same funding reference when retrying.`;
      } finally { submitting = false; submit.disabled = edit.disabled = false; }
    });
    dialog("Record received funding", trigger, form); amount.focus();
  }
  function renderEnquiries() {
    const data = state.enquiries;
    if (!data) { loading("enquiriesTable"); pager("enquiries", null); return; }
    renderTable($("enquiriesTable"), [
      { label: "Received", cls: "date", cell: r => dateCell(r.created_at) },
      { label: "Reference", cell: r => refCell(r.reference, "enquiry reference") },
      { label: "Company", cell: r => text(r.company_name) },
      { label: "Country", cell: r => text(r.country) },
      { label: "Contact", cell: r => h("div", {}, text(r.contact_name), h("span", { class: "sub" }, r.email)) },
      { label: "Monthly volume", cell: r => text(r.monthly_volume) },
      { label: "Channels", cell: r => text(r.channels) },
    ], data.items || [], "enquiry", empty("No partnership enquiries match these filters."));
    pager("enquiries", data);
  }

  function clearEarnings() { state.earnings = state.earningsPartners = state.feeDetails = null; }
  function syncFilters() {
    Object.entries({ earningsPeriod: earningsFilter.preset, earningsCurrency: earningsFilter.currency, earningsActivity: earningsFilter.activity,
      earningsPartner: earningsFilter.partner_id, earningsStart: earningsFilter.start, earningsEnd: earningsFilter.end,
      feeState, feeSort, fundsSearch: fundsFilter.search, fundsStatus: fundsFilter.status, fundsSort: fundsFilter.sort, enquiriesSearch: enquiriesFilter.q,
    }).forEach(([id, value]) => $(id).value = value);
    $("earningsStart").disabled = $("earningsEnd").disabled = earningsFilter.preset !== "custom";
    $("earningsStart").required = $("earningsEnd").required = earningsFilter.preset === "custom";
  }
  function parseHash(view, p) {
    if (view === "earnings") {
      const next = { preset: choice(p.get("preset"), ["today", "7days", "month", "custom"], "month"),
        currency: choice(p.get("currency"), ["USD", "EUR", "GBP"], "USD"),
        activity: choice(p.get("activity"), ["live", "simulation", "unclassified"], "live"),
        partner_id: positive(p.get("partner_id")), start: p.get("start") || "", end: p.get("end") || "" };
      if (next.preset === "custom" && (!/^\d{4}-\d{2}-\d{2}$/.test(next.start) || !/^\d{4}-\d{2}-\d{2}$/.test(next.end) || next.start > next.end)) next.preset = "month";
      if (JSON.stringify(next) !== JSON.stringify(earningsFilter)) clearEarnings();
      earningsFilter = next; feeOffset = offset(p.get("fee_offset")); partnerOffset = offset(p.get("partner_offset"));
      feeState = choice(p.get("fee_state"), ["PENDING", "EARNED", "PARTIALLY_REVERSED", "REVERSED", "RELEASED", "RECONCILIATION_REQUIRED", "ZERO_FEE"], "");
      feeSort = choice(p.get("fee_sort"), ["accepted_desc", "accepted_asc", "fee_desc", "recognized_desc"], "accepted_desc");
    } else if (view === "funds") {
      const next = { search: (p.get("search") || "").slice(0, 160), status: choice(p.get("status"), ["active", "inactive"], ""),
        sort: choice(p.get("sort"), ["balance_desc", "balance_asc", "name_asc", "name_desc", "id_desc"], "balance_desc"), page: Math.max(1, offset(p.get("page"))) };
      if (JSON.stringify(next) !== JSON.stringify(fundsFilter)) state.funds = null;
      fundsFilter = next;
    } else if (view === "enquiries") {
      const next = { q: (p.get("q") || "").slice(0, 160), offset: offset(p.get("offset")) };
      if (JSON.stringify(next) !== JSON.stringify(enquiriesFilter)) state.enquiries = null;
      enquiriesFilter = next;
    }
    syncFilters();
  }
  function hashParams(view) {
    if (view === "earnings") {
      const p = earningsParams(); if (feeOffset) p.set("fee_offset", feeOffset); if (partnerOffset) p.set("partner_offset", partnerOffset);
      if (feeState) p.set("fee_state", feeState); if (feeSort !== "accepted_desc") p.set("fee_sort", feeSort); return p;
    }
    if (view === "funds") return new URLSearchParams(fundsFilter);
    if (view === "enquiries") return new URLSearchParams(enquiriesFilter);
    return new URLSearchParams();
  }
  function wireUI() {
    $("earningsPeriod").addEventListener("change", () => {
      const custom = $("earningsPeriod").value === "custom";
      $("earningsStart").disabled = $("earningsEnd").disabled = !custom;
      $("earningsStart").required = $("earningsEnd").required = custom;
    });
    $("earningsFilters").addEventListener("submit", event => {
      event.preventDefault();
      if ($("earningsPeriod").value === "custom" && $("earningsStart").value > $("earningsEnd").value) { toast("The end date must be on or after the start date."); return; }
      earningsFilter = { preset: $("earningsPeriod").value, currency: $("earningsCurrency").value, activity: $("earningsActivity").value,
        partner_id: positive($("earningsPartner").value), start: $("earningsStart").value, end: $("earningsEnd").value };
      feeOffset = partnerOffset = 0; clearEarnings(); writeHash(); refresh(["earnings", "earningsPartners", "feeDetails"]);
    });
    for (const id of ["feeState", "feeSort"]) $(id).addEventListener("change", () => { feeState = $("feeState").value; feeSort = $("feeSort").value; feeOffset = 0; state.feeDetails = null; writeHash(); refresh(["feeDetails"]); });
    for (const [id, delta] of [["feePrev", -PAGE], ["feeNext", PAGE]]) $(id).addEventListener("click", () => { feeOffset = Math.max(0, feeOffset + delta); state.feeDetails = null; writeHash(); refresh(["feeDetails"]); });
    for (const [id, delta] of [["prevEarningsPartners", -PARTNERS_PAGE], ["moreEarningsPartners", PARTNERS_PAGE]]) $(id).addEventListener("click", () => { partnerOffset = Math.max(0, partnerOffset + delta); state.earningsPartners = null; writeHash(); refresh(["earningsPartners"]); });
    $("fundsFilters").addEventListener("submit", event => { event.preventDefault(); fundsFilter = { search: $("fundsSearch").value.trim(), status: $("fundsStatus").value, sort: $("fundsSort").value, page: 1 }; state.funds = null; writeHash(); refresh(["funds"]); });
    for (const [id, delta] of [["fundsPrev", -1], ["fundsNext", 1]]) $(id).addEventListener("click", () => { fundsFilter.page = Math.max(1, fundsFilter.page + delta); state.funds = null; writeHash(); refresh(["funds"]); });
    let enquiryTimer;
    function searchEnquiries() { clearTimeout(enquiryTimer); enquiriesFilter = { q: $("enquiriesSearch").value.trim(), offset: 0 }; state.enquiries = null; writeHash(); refresh(["enquiries"]); }
    $("enquiriesFilters").addEventListener("submit", event => { event.preventDefault(); searchEnquiries(); });
    $("enquiriesSearch").addEventListener("input", () => { clearTimeout(enquiryTimer); enquiryTimer = setTimeout(searchEnquiries, 350); });
    for (const [id, delta] of [["enquiriesPrev", -PAGE], ["enquiriesNext", PAGE]]) $(id).addEventListener("click", () => { enquiriesFilter.offset = Math.max(0, enquiriesFilter.offset + delta); state.enquiries = null; writeHash(); refresh(["enquiries"]); });
    $("refreshFunds").addEventListener("click", () => refresh(["funds"]));
    $("refreshEnquiries").addEventListener("click", () => refresh(["enquiries"]));
  }
  return { loaders, parseHash, hashParams, wireUI,
    onDialogClose() { historyRequest++; },
    renderAll() { renderEarnings(); renderEarningsPartners(); renderFees(); renderFunds(); renderEnquiries();
      $("scopeChip").textContent = `Partner scope: ${state.view === "earnings" && earningsFilter.partner_id ? `Partner ${earningsFilter.partner_id}` : "All partners"}`; },
    clear() { requests.forEach(request => request.controller.abort()); requests.clear(); state.earningsPartners = null; historyRequest++; $("businessBody").replaceChildren(); },
  };
}
