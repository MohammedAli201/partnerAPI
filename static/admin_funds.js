// Admin Funds Management JavaScript

let currentPage = 1;
const pageSize = 20;
let totalPartners = 0;
// Bootstrap helper function - ADD THIS AT THE TOP
function getBootstrap() {
    if (typeof bootstrap !== 'undefined') {
        return bootstrap;
    }
    if (window.bootstrap) {
        return window.bootstrap;
    }
    console.error('Bootstrap not loaded! Make sure bootstrap.bundle.min.js is included.');
    return null;
}
document.addEventListener('DOMContentLoaded', function () {
    loadPartners();
    loadPartnerDropdowns();
    ['earningsPeriod','earningsCurrency','earningsActivity'].forEach(id => document.getElementById(id).addEventListener('change', loadPartners));

    // Event listeners
    document.getElementById('searchPartner').addEventListener('input', debounce(loadPartners, 300));
    document.getElementById('filterActive').addEventListener('change', loadPartners);
    document.getElementById('sortBy').addEventListener('change', loadPartners);
    document.getElementById('refreshBtn').addEventListener('click', loadPartners);

    // Add funds form
    document.getElementById('submitAddFunds').addEventListener('click', addFunds);

    // Adjust funds form
    document.getElementById('submitAdjustFunds').addEventListener('click', adjustFunds);

    // Modal show events to refresh dropdowns
    document.getElementById('addFundsModal').addEventListener('show.bs.modal', loadPartnerDropdowns);
    document.getElementById('adjustFundsModal').addEventListener('show.bs.modal', loadPartnerDropdowns);
});

function debounce(func, wait) {
    let timeout;
    return function executedFunction(...args) {
        const later = () => {
            clearTimeout(timeout);
            func(...args);
        };
        clearTimeout(timeout);
        timeout = setTimeout(later, wait);
    };
}

async function loadPartners() {
    try {
        const search = document.getElementById('searchPartner').value;
        const status = document.getElementById('filterActive').value;
        const sort = document.getElementById('sortBy').value;

        const feeFilters = new URLSearchParams({earnings_period:document.getElementById('earningsPeriod').value,earnings_currency:document.getElementById('earningsCurrency').value,earnings_activity:document.getElementById('earningsActivity').value});
        const response = await fetch(`/admin/api/funds/partners?page=${currentPage}&limit=${pageSize}&search=${encodeURIComponent(search)}&status=${status}&sort=${sort}&${feeFilters}`);
        const data = await response.json();
        if(data.earnings_period) document.getElementById('earningsScope').textContent = `${data.earnings_period.start_date} through ${data.earnings_period.end_date} · ${data.earnings_period.timezone}. Net fee revenue is separate from partner funds.`;

        if (!response.ok) throw new Error(data.detail || 'Failed to load partners');

        renderPartnersTable(data.partners);
        renderPagination(data.total, data.total_pages);
        totalPartners = data.total;

        document.getElementById('tableInfo').innerHTML =
            `Showing ${((currentPage - 1) * pageSize) + 1} to ${Math.min(currentPage * pageSize, totalPartners)} of ${totalPartners} partners`;

    } catch (error) {
        showAlert('error', error.message);
    }
}

async function loadPartnerDropdowns() {
    try {
        const response = await fetch('/admin/api/funds/partners?limit=1000&active_only=true');
        const data = await response.json();

        const addDropdown = document.getElementById('addFundsPartner');
        const adjustDropdown = document.getElementById('adjustFundsPartner');

        addDropdown.innerHTML = '<option value="">Select a partner...</option>';
        adjustDropdown.innerHTML = '<option value="">Select a partner...</option>';

        data.partners.forEach(partner => {
            const option = `<option value="${partner.id}">${partner.name} (ID: ${partner.id}) - Balance: $${partner.balance_available}</option>`;
            addDropdown.innerHTML += option;
            adjustDropdown.innerHTML += option;
        });
    } catch (error) {
        console.error('Error loading partner dropdowns:', error);
    }
}

function renderPartnersTable(partners) {
    const tbody = document.getElementById('partnersTableBody');
    tbody.innerHTML = '';

    if (partners.length === 0) {
        tbody.innerHTML = `
            <tr>
                <td colspan="8" class="text-center py-4 text-muted">
                    <i class="fas fa-users-slash fa-2x mb-2"></i><br>
                    No partners found
                </td>
            </tr>
        `;
        return;
    }

    partners.forEach(partner => {
        const row = document.createElement('tr');
        const statusBadge = partner.is_active
            ? '<span class="badge bg-success">Active</span>'
            : '<span class="badge bg-secondary">Inactive</span>';

        const lastUpdated = partner.updated_at
            ? new Date(partner.updated_at).toLocaleString()
            : 'Never';

        row.innerHTML = `
            <td>${partner.id}</td>
            <td><strong>${escapeHtml(partner.name)}</strong></td>
            <td>${statusBadge}</td>
            <td class="fw-bold text-success">$${parseFloat(partner.balance_available).toFixed(2)}</td>
            <td class="text-warning">$${parseFloat(partner.balance_reserved).toFixed(2)}</td>
            <td class="fw-bold text-primary">
                $${(parseFloat(partner.balance_available) + parseFloat(partner.balance_reserved)).toFixed(2)}
            </td>
            <td class="text-end"><strong>${escapeHtml(partner.earned_fees || '0.00')} ${escapeHtml(partner.earnings_currency || 'USD')}</strong><br><a href="/admin/earnings?${new URLSearchParams({partner_id:partner.id,preset:document.getElementById('earningsPeriod').value,currency:document.getElementById('earningsCurrency').value,activity:document.getElementById('earningsActivity').value})}">View earnings</a></td>
            <td class="text-muted small">${lastUpdated}</td>
            <td>
                <div class="btn-group btn-group-sm">
                    <button class="btn btn-outline-primary" onclick="showAddFundsModal(${partner.id})"
                            title="Add Funds">
                        <i class="fas fa-plus"></i>
                    </button>
                    <button class="btn btn-outline-warning" onclick="showAdjustModal(${partner.id})"
                            title="Adjust Balance">
                        <i class="fas fa-edit"></i>
                    </button>
                    <button class="btn btn-outline-info" onclick="showHistory(${partner.id}, '${escapeHtml(partner.name)}')"
                            title="View History">
                        <i class="fas fa-history"></i>
                    </button>
                </div>
            </td>
        `;
        tbody.appendChild(row);
    });
}

function renderPagination(total, totalPages) {
    const pagination = document.getElementById('pagination');
    pagination.innerHTML = '';

    if (totalPages <= 1) return;

    // Previous button
    const prevLi = document.createElement('li');
    prevLi.className = `page-item ${currentPage === 1 ? 'disabled' : ''}`;
    prevLi.innerHTML = `<a class="page-link" href="#" ${currentPage > 1 ? `onclick="changePage(${currentPage - 1})"` : ''}>Previous</a>`;
    pagination.appendChild(prevLi);

    // Page numbers
    for (let i = 1; i <= totalPages; i++) {
        const li = document.createElement('li');
        li.className = `page-item ${currentPage === i ? 'active' : ''}`;
        li.innerHTML = `<a class="page-link" href="#" onclick="changePage(${i})">${i}</a>`;
        pagination.appendChild(li);
    }

    // Next button
    const nextLi = document.createElement('li');
    nextLi.className = `page-item ${currentPage === totalPages ? 'disabled' : ''}`;
    nextLi.innerHTML = `<a class="page-link" href="#" ${currentPage < totalPages ? `onclick="changePage(${currentPage + 1})"` : ''}>Next</a>`;
    pagination.appendChild(nextLi);
}

function changePage(page) {
    currentPage = page;
    loadPartners();
}

// async function addFunds() {
//     const partnerId = document.getElementById('addFundsPartner').value;
//     const amount = document.getElementById('addFundsAmount').value;
//     const reference = document.getElementById('addFundsReference').value;

//     if (!partnerId || !amount || !reference.trim()) {
//         showAlert('warning', 'Please select a partner, enter an amount and a unique funding reference');
//         return;
//     }

//     try {
//         const response = await fetch(`/admin/partner/${partnerId}/deposit`, {
//             method: 'POST',
//             headers: {
//                 'Content-Type': 'application/json',
//             },
//             body: JSON.stringify({
//                 amount: amount,
//                 reference: reference || null,
//                 note: `Admin deposit via UI`
//             })
//         });

//         const data = await response.json();

//         if (!response.ok) throw new Error(data.detail || 'Failed to add funds');

//         showAlert('success', `Successfully added $${amount} to partner`);

//         // Reset form and close modal
//         document.getElementById('addFundsForm').reset();
//         bootstrap.Modal.getInstance(document.getElementById('addFundsModal')).hide();

//         // Refresh partners list
//         loadPartners();

//     } catch (error) {
//         showAlert('error', error.message);
//     }
// }

async function addFunds() {
    const partnerId = document.getElementById('addFundsPartner').value;
    const amount = document.getElementById('addFundsAmount').value;
    const reference = document.getElementById('addFundsReference').value;

    if (!partnerId || !amount || !reference.trim()) {
        showAlert('warning', 'Please select a partner, enter an amount and a unique funding reference');
        return;
    }

    try {
        const response = await fetch(`/admin/partner/${partnerId}/deposit`, {
            method: 'POST',
            headers: {
                'Content-Type': 'application/json',
            },
            body: JSON.stringify({
                amount: amount,
                reference: reference || null,
                note: `Admin deposit via UI`
            })
        });

        const data = await response.json();

        if (!response.ok) throw new Error(data.detail || 'Failed to add funds');

        showAlert('success', `Successfully added $${amount} to partner`);

        // Reset form and close modal - UPDATED
        document.getElementById('addFundsForm').reset();
        const bs = getBootstrap();
        if (bs) {
            const modalElement = document.getElementById('addFundsModal');
            if (modalElement) {
                const modalInstance = bs.Modal.getInstance(modalElement);
                if (modalInstance) {
                    modalInstance.hide();
                }
            }
        }

        // Refresh partners list
        loadPartners();

    } catch (error) {
        showAlert('error', error.message);
    }
}

async function adjustFunds() {
    const partnerId = document.getElementById('adjustFundsPartner').value;
    const amount = document.getElementById('adjustFundsAmount').value;
    const adjustmentType = document.getElementById('adjustmentType').value;

    const reason = document.getElementById('adjustFundsReason').value;

    if (!partnerId || !amount || !reason) {
        showAlert('warning', 'Please fill all required fields');
        return;
    }

    try {
        if (!/^\d+(\.\d{1,2})?$/.test(amount)) throw new Error('Use an exact amount with at most two decimals');
        const parts = amount.split('.');
        const cents = BigInt(parts[0]) * 100n + BigInt((parts[1] || '').padEnd(2, '0'));
        if (cents <= 0n || cents > 1000000000000n) throw new Error('Correction amount out of range');
        const response = await fetch(`/admin/api/funds/corrections/propose`, {
            method: 'POST',
            headers: {
                'Content-Type': 'application/json',
            },
            body: JSON.stringify({
                partner_id: parseInt(partnerId),
                delta_minor: Number(adjustmentType === 'subtract' ? -cents : cents),
                business_reference: crypto.randomUUID(),
                evidence_ref: reason
            })
        });

        const data = await response.json();

        if (!response.ok) throw new Error(data.detail || 'Failed to adjust balance');

        showAlert('success', `Correction ${data.review_id} proposed. A different administrator must review and approve it; the balance is unchanged.`);

        // Reset form and close modal
        document.getElementById('adjustFundsForm').reset();
        bootstrap.Modal.getInstance(document.getElementById('adjustFundsModal')).hide();

        // Refresh partners list
        loadPartners();

    } catch (error) {
        showAlert('error', error.message);
    }
}

function showAddFundsModal(partnerId) {
    if (partnerId) {
        document.getElementById('addFundsPartner').value = partnerId;
    }
    new bootstrap.Modal(document.getElementById('addFundsModal')).show();
}

function showAdjustModal(partnerId) {
    if (partnerId) {
        document.getElementById('adjustFundsPartner').value = partnerId;
    }
    new bootstrap.Modal(document.getElementById('adjustFundsModal')).show();
}

async function showHistory(partnerId, partnerName) {
    document.getElementById('historyPartnerName').textContent = partnerName;

    try {
        const response = await fetch(`/admin/api/funds/history/${partnerId}`);
        const data = await response.json();

        if (!response.ok) throw new Error(data.detail || 'Failed to load history');

        const tbody = document.getElementById('historyTableBody');
        tbody.innerHTML = '';

        if (data.history.length === 0) {
            tbody.innerHTML = `
                <tr>
                    <td colspan="7" class="text-center py-3 text-muted">
                        No transaction history found
                    </td>
                </tr>
            `;
        } else {
            data.history.forEach(record => {
                const row = document.createElement('tr');
                const amountClass = record.type === 'deposit' ? 'text-success' : 'text-danger';

                row.innerHTML = `
                    <td>${new Date(record.created_at).toLocaleString()}</td>
                    <td><span class="badge bg-${record.type === 'deposit' ? 'success' : 'warning'}">${record.type}</span></td>
                    <td class="${amountClass} fw-bold">$${parseFloat(record.amount).toFixed(2)}</td>
                    <td>$${parseFloat(record.previous_balance).toFixed(2)}</td>
                    <td>$${parseFloat(record.new_balance).toFixed(2)}</td>
                    <td>${escapeHtml(record.reference || '')}</td>
                    <td>${escapeHtml(record.admin_user || 'System')}</td>
                `;
                tbody.appendChild(row);
            });
        }

        new bootstrap.Modal(document.getElementById('historyModal')).show();

    } catch (error) {
        showAlert('error', error.message);
    }
}

function showAlert(type, message) {
    const alertDiv = document.createElement('div');
    alertDiv.className = `alert alert-${type} alert-dismissible fade show position-fixed`;
    alertDiv.style.cssText = 'top: 20px; right: 20px; z-index: 9999; max-width: 400px;';
    alertDiv.innerHTML = `
        ${message}
        <button type="button" class="btn-close" data-bs-dismiss="alert"></button>
    `;

    document.body.appendChild(alertDiv);

    setTimeout(() => {
        if (alertDiv.parentNode) {
            alertDiv.classList.remove('show');
            setTimeout(() => alertDiv.remove(), 150);
        }
    }, 5000);
}

function escapeHtml(text) {
    const div = document.createElement('div');
    div.textContent = text;
    return div.innerHTML;
}
