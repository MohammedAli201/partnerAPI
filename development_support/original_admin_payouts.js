/* Add explicit synthetic terminal actions to the original Transactions table. */
(() => {
  const signedPayouts = new Map();
  const originalApi = api;
  const originalStatusSelect = statusSelect;
  const originalUpdate = updatePayoutStatus;

  api = async function (url, options = {}) {
    const result = await originalApi(url, options);
    if (new URL(url, location.origin).pathname === '/admin/api/payouts' && !options.method) {
      signedPayouts.clear();
      for (const payout of result.items || []) {
        if (payout.is_development_simulation) signedPayouts.set(payout.id, payout.status);
      }
    }
    return result;
  };

  statusSelect = function (id, status) {
    if (!signedPayouts.has(id)) return originalStatusSelect(id, status);
    const current = signedPayouts.get(id);
    if (!['RECEIVED', 'PROCESSING'].includes(current)) {
      return `<span class="badge ${current}">${current}</span><small>Test payout</small>`;
    }
    const options = [current, 'SENT', 'FAILED', 'REJECTED'];
    return `<select class="statusSelect" data-id="${id}" data-current="${current}">${options.map(value =>
      `<option value="${value}" ${value === current ? 'selected' : ''}>${value}</option>`).join('')}</select><small>Test payout</small>`;
  };

  updatePayoutStatus = async function (id, status) {
    if (!signedPayouts.has(id)) return originalUpdate(id, status);
    const reason = prompt('Reason for this terminal test result:');
    if (reason === null) return { cancelled: true };
    if (!reason.trim() || reason.length > 500) throw Error('Enter a reason of 1 to 500 characters.');
    const response = await fetch(`/admin/api/development-payouts/${encodeURIComponent(id)}/terminal`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json', 'X-Simulator-Action': 'terminal' },
      body: JSON.stringify({ status, reason }),
    });
    const result = await response.json();
    if (!response.ok) throw Error(result.detail || 'Terminal test result failed.');
    return result;
  };

  // The original script starts an asynchronous load before this extension runs.
  // Refresh once through the wrapped reader so first-load rows have their source.
  loadPayouts().catch(() => {
    document.getElementById('pageInfo').textContent = 'Unable to load payouts. Please refresh.';
  });
})();
