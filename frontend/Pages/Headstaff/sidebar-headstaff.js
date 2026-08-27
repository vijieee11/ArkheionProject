// sidebar-headstaff.js — Dedicated sidebar for Head Staff-only pages
// This file lives inside Pages/Headstaff/
// Usage: <script src="sidebar-headstaff.js"></script>
// Then call: renderHeadStaffSidebar('hs-dashboard') at bottom of body

function renderHeadStaffSidebar(activePage) {
  // Every account on this sidebar is Head Staff, so the badge/initials are
  // always "HS" — no need to derive them from the raw username.
  const initials = 'HS';
  const displayName = 'Head Staff';

  const navGroups = [
    {
      section: 'Overview',
      items: [
        { id: 'hs-dashboard', label: 'Head Staff Dashboard', icon: 'ti-layout-dashboard', href: 'hs-dashboard.html' },
      ]
    },
    {
      section: 'Requests',
      items: [
        { id: 'approvals', label: 'Pending approvals', icon: 'ti-checklist',   href: 'hs-pending-approval.html', badge: '5' },
        { id: 'requests',  label: 'Staff requests',    icon: 'ti-inbox',       href: 'staff_request.html' },
      ]
    },
    {
      section: 'Oversight',
      items: [
        { id: 'staffmgmt',    label: 'Manage staff',      icon: 'ti-users-group',  href: 'staff-mgmt.html' },
        { id: 'audit',        label: 'Audit log',         icon: 'ti-shield-check', href: 'audit.html' },
      ]
    },
    {
      section: 'System',
      items: [
        { id: 'settings', label: 'System settings', icon: 'ti-settings',  href: 'settings.html' },
        { id: 'reports',  label: 'Reports',          icon: 'ti-file-text', href: 'hs-reports.html' },
      ]
    }
  ];

  let html = `<nav class="sidebar">
    <div class="sb-logo">
      <div class="sb-logo-icon"><i class="ti ti-archive"></i></div>
      <span class="sb-logo-text">Arkheion</span>
    </div>
    <div style="margin:0 16px 12px;padding:6px 10px;background:var(--gold);border-radius:6px;text-align:center;">
      <span style="font-size:10px;font-weight:700;letter-spacing:.5px;color:var(--navy);">HEAD STAFF PORTAL</span>
    </div>`;

  navGroups.forEach(group => {
    html += `<span class="sb-section">${group.section}</span>`;
    group.items.forEach(item => {
      const isActive = item.id === activePage;
      const badge = item.badge ? `<span class="nav-badge">${item.badge}</span>` : '';
      html += `
        <a class="nav-item ${isActive ? 'active' : ''}" href="${item.href}">
          <i class="ti ${item.icon}"></i>
          ${item.label}${badge}
        </a>`;
    });
  });

  html += `
    <div class="sb-spacer"></div>
    <a class="nav-item" href="../Staff/dashboard.html">
      <i class="ti ti-arrow-back-up"></i>Switch to Staff view
    </a>
    <a class="nav-item" href="#" onclick="logoutHS(event)">
      <i class="ti ti-logout"></i>Logout
    </a>
    <div class="sb-user">
      <div class="sb-avatar" style="background:var(--gold);color:var(--navy);">${initials}</div>
      <div>
        <div class="sb-uname">${displayName}</div>
        <div class="sb-urole">OSCA Head Staff</div>
      </div>
    </div>
  </nav>`;

  document.body.insertAdjacentHTML('afterbegin', html);
  ensureLogoutModalHS();
}

// Same modal-overlay/.modal pattern used across the rest of the app —
// replaces the native confirm() box for logout.
function ensureLogoutModalHS() {
  if (document.getElementById('modal-logout-confirm')) return;
  const html = `
    <div class="modal-overlay" id="modal-logout-confirm" onclick="if(event.target===this)closeModal('modal-logout-confirm')">
      <div class="modal" style="width:380px;">
        <div class="modal-header">
          <span class="modal-title">Log out</span>
          <button class="modal-close" onclick="closeModal('modal-logout-confirm')"><i class="ti ti-x"></i></button>
        </div>
        <div class="modal-body">
          <p style="margin:0;font-size:14px;color:var(--gray-600,#555);">Are you sure you want to logout?</p>
        </div>
        <div class="modal-footer">
          <button class="btn btn-ghost" onclick="closeModal('modal-logout-confirm')">Cancel</button>
          <button class="btn btn-navy" onclick="confirmLogoutHS()"><i class="ti ti-logout"></i> Logout</button>
        </div>
      </div>
    </div>`;
  document.body.insertAdjacentHTML('beforeend', html);
}

function logoutHS(e) {
  e && e.preventDefault();
  ensureLogoutModalHS();
  openModal('modal-logout-confirm');
}

function confirmLogoutHS() {
  localStorage.clear();
  window.location.href = '../login.html';
}

function showToast(msg, type = 'success') {
  const toast = document.createElement('div');
  toast.className = `toast ${type}`;
  toast.innerHTML = `<i class="ti ti-${type === 'success' ? 'circle-check' : 'alert-circle'}"></i> ${msg}`;
  document.body.appendChild(toast);
  setTimeout(() => toast.classList.add('show'), 10);
  setTimeout(() => { toast.classList.remove('show'); setTimeout(() => toast.remove(), 300); }, 3000);
}

function openModal(id)  { document.getElementById(id)?.classList.add('open'); }
function closeModal(id) { document.getElementById(id)?.classList.remove('open'); }