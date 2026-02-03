async function loadHealth() {
    const dot = document.getElementById("healthDot");
    const text = document.getElementById("healthText");
    const details = document.getElementById("healthDetails");

    try {
        const r = await fetch("/health", { cache: "no-store" });
        if (!r.ok) throw new Error("health not ok");
        const data = await r.json();

        dot.style.background = "#16a34a";
        dot.style.boxShadow = "0 0 0 4px rgba(22,163,74,.18)";
        text.textContent = "System healthy";
        details.textContent = `DB: ${data.database} • Queue: ${data.queue_health.total_queued} • Expired: ${data.queue_health.expired_tasks}`;
    } catch (e) {
        dot.style.background = "#ef4444";
        dot.style.boxShadow = "0 0 0 4px rgba(239,68,68,.18)";
        text.textContent = "System unavailable";
        details.textContent = "";
    }
}

document.getElementById("year").textContent = String(new Date().getFullYear());
loadHealth();
setInterval(loadHealth, 15000);
