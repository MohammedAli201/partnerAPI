let offset = 0;
let limit = 25;
let total = 0;

function fmtDate(x) {
    if (!x) return "";
    const d = new Date(x);
    return d.toISOString().slice(0, 19).replace("T", " ");
}

function badge(status) {
    return `<span class="badge ${status}">${status}</span>`;
}

async function loadSummary() {
    const r = await fetch("/partner/api/summary");
    if (!r.ok) throw new Error("Failed to load summary");
    const data = await r.json();

    document.getElementById("c-received").textContent = data.payouts.received;
    document.getElementById("c-processing").textContent = data.payouts.processing;
    document.getElementById("c-sent").textContent = data.payouts.sent;
    document.getElementById("c-failed").textContent = data.payouts.failed;
}

async function loadPayouts() {
    const q = document.getElementById("q").value.trim();
    const status = document.getElementById("status").value;

    const params = new URLSearchParams({
        limit: String(limit),
        offset: String(offset),
    });
    if (q) params.set("q", q);
    if (status) params.set("status", status);

    const r = await fetch(`/partner/api/payouts?${params.toString()}`);
    if (!r.ok) throw new Error("Failed to load payouts");
    const data = await r.json();

    total = data.total;

    const tbody = document.getElementById("rows");
    if (!data.items.length) {
        tbody.innerHTML = `<tr><td colspan="6" class="muted">No payouts found</td></tr>`;
    } else {
        tbody.innerHTML = data.items.map(p => `
      <tr>
        <td>${fmtDate(p.created_at)}</td>
        <td>${p.partner_tx_id ?? ""}</td>
        <td>${p.recipient ?? ""}</td>
        <td>${p.amount} ${p.currency}</td>
        <td>${p.provider ?? ""}</td>
        <td>${badge(p.status)}</td>
      </tr>
    `).join("");
    }

    const page = Math.floor(offset / limit) + 1;
    const pages = Math.max(1, Math.ceil(total / limit));
    document.getElementById("page").textContent = `Page ${page} / ${pages} (Total ${total})`;

    document.getElementById("prev").disabled = offset === 0;
    document.getElementById("next").disabled = offset + limit >= total;
}

async function refreshAll(resetOffset = false) {
    try {
        if (resetOffset) offset = 0;
        await loadSummary();
        await loadPayouts();
    } catch (e) {
        const tbody = document.getElementById("rows");
        tbody.innerHTML = `<tr><td colspan="6" class="muted">Error: ${e.message}</td></tr>`;
    }
}

document.getElementById("btn-refresh").addEventListener("click", () => refreshAll(true));
document.getElementById("prev").addEventListener("click", () => { offset = Math.max(0, offset - limit); refreshAll(false); });
document.getElementById("next").addEventListener("click", () => { offset = offset + limit; refreshAll(false); });

document.getElementById("q").addEventListener("keydown", (e) => {
    if (e.key === "Enter") refreshAll(true);
});
document.getElementById("status").addEventListener("change", () => refreshAll(true));

refreshAll(true);
