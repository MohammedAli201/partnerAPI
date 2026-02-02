const $ = (id) => document.getElementById(id);

const LS_KEY = "admin_executor_token";
let offset = 0;
const limit = 50;
const HARDCODED_TOKEN = "7f9c2b8b7d1e4c7c9d1a0f3e8c5b1a9f";


function getToken() {
    return localStorage.getItem(LS_KEY) || "";
}


function getToken() {
    // Prefer hardcoded token; fallback to localStorage if you remove hardcode later
    return HARDCODED_TOKEN || localStorage.getItem(LS_KEY) || "";
}


// function setToken(v) {
//     localStorage.setItem(LS_KEY, v);
// }

function authHeaders() {
    const t = getToken();
    if (!t) return {};
    return { "X-Executor-Token": t };
}

async function api(url) {
    const res = await fetch(url, { headers: authHeaders() });
    if (!res.ok) {
        const msg = await res.text();
        throw new Error(`HTTP ${res.status}: ${msg}`);
    }
    return await res.json();
}

function fmtDate(x) {
    if (!x) return "";
    try { return new Date(x).toLocaleString(); } catch { return String(x); }
}

function badge(status) {
    return `<span class="badge ${status}">${status}</span>`;
}

async function loadSummary() {
    const s = await api("/admin/api/summary");
    $("s_received").textContent = s.payouts.received;
    $("s_processing").textContent = s.payouts.processing;
    $("s_sent").textContent = s.payouts.sent;
    $("s_failed").textContent = s.payouts.failed;

    $("q_pending").textContent = s.queue.pending;
    $("q_inprogress").textContent = s.queue.in_progress;
    $("q_expired").textContent = s.queue.expired;
}

async function loadPayouts() {
    const q = encodeURIComponent($("search").value.trim());
    const st = encodeURIComponent($("status").value.trim());

    const url = `/admin/api/payouts?limit=${limit}&offset=${offset}` +
        (q ? `&q=${q}` : "") +
        (st ? `&status=${st}` : "");

    const data = await api(url);
    const tbody = $("payouts").querySelector("tbody");
    tbody.innerHTML = "";

    data.items.forEach((r) => {
        const tr = document.createElement("tr");
        tr.innerHTML = `
      <td>${fmtDate(r.created_at)}</td>
      <td>${r.recipient || ""}</td>
      <td>${r.amount} ${r.currency || ""}</td>
      <td>${badge(r.status)}</td>
      <td>${r.queue_status ? badge(r.queue_status) : ""}</td>
      <td>${r.worker_id || ""}</td>
      <td>${r.partner_tx_id || ""}</td>
      <td><button class="ghost" data-id="${r.id}">View</button></td>
    `;
        tbody.appendChild(tr);
    });

    // View details button handlers
    tbody.querySelectorAll("button[data-id]").forEach((btn) => {
        btn.addEventListener("click", async () => {
            const id = btn.getAttribute("data-id");
            const details = await api(`/admin/api/payouts/${id}`);
            $("details").textContent = JSON.stringify(details, null, 2);
            $("drawer").style.display = "flex";
        });
    });

    const page = Math.floor(data.offset / data.limit) + 1;
    const pages = Math.max(1, Math.ceil(data.total / data.limit));
    $("pageInfo").textContent = `Page ${page} / ${pages} — Total ${data.total}`;
}

async function loadQueue() {
    const data = await api("/admin/api/queue?limit=200");
    const tbody = $("queue").querySelector("tbody");
    tbody.innerHTML = "";

    data.items.forEach((r) => {
        const tr = document.createElement("tr");
        tr.innerHTML = `
      <td>${fmtDate(r.queue_created)}</td>
      <td>${r.payout_id}</td>
      <td>${r.queue_status ? badge(r.queue_status) : ""}</td>
      <td>${fmtDate(r.lease_until)}</td>
      <td>${r.worker_id || ""}</td>
      <td>${r.recipient || ""}</td>
      <td>${r.amount} ${r.currency || ""}</td>
    `;
        tbody.appendChild(tr);
    });
}

async function refreshAll() {
    await loadSummary();
    await loadPayouts();
    await loadQueue();
}

function wireUI() {
    // init token input
    $("token").value = getToken();

    $("saveToken").addEventListener("click", async () => {
        setToken($("token").value.trim());
        try {
            await refreshAll();
            alert("Token saved. Dashboard loaded.");
        } catch (e) {
            alert("Token saved, but auth failed. Check token.\n\n" + e.message);
        }
    });

    $("clearToken").addEventListener("click", () => {
        setToken("");
        $("token").value = "";
        alert("Token cleared.");
    });

    $("refresh").addEventListener("click", async () => {
        offset = 0;
        await loadPayouts();
        await loadSummary();
    });

    $("refreshQueue").addEventListener("click", loadQueue);

    $("prev").addEventListener("click", async () => {
        offset = Math.max(0, offset - limit);
        await loadPayouts();
    });

    $("next").addEventListener("click", async () => {
        offset = offset + limit;
        await loadPayouts();
    });

    $("closeDrawer").addEventListener("click", () => {
        $("drawer").style.display = "none";
    });

    // auto refresh every 10 seconds (optional)
    setInterval(async () => {
        try { await loadSummary(); } catch { }
    }, 10000);
}

(async function boot() {
    wireUI();
    if (getToken()) {
        try { await refreshAll(); }
        catch (e) { console.log(e); }
    }
})();
