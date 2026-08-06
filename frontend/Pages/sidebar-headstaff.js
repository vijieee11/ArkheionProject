// sidebar-headstaff.js — Dedicated sidebar for Head Staff-only pages
// Usage: <script src="sidebar-headstaff.js"></script>
// Then call: renderHeadStaffSidebar('hs-dashboard') at bottom of body

function renderHeadStaffSidebar(activePage) {
  const username = localStorage.getItem('ark_username') || 'Head Staff';
  const initials = username.split('_').map(w => w[0]?.toUpperCase() || '').join('').slice(0,2) || 'HS';

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
        { id: 'requests',  label: 'Staff requests',    icon: 'ti-inbox',       href: 'requests.html' },
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
    <a class="nav-item" href="dashboard.html">
      <i class="ti ti-arrow-back-up"></i>Switch to Staff view
    </a>
    <a class="nav-item" href="login.html" onclick="logoutHS(event)">
      <i class="ti ti-logout"></i>Logout
    </a>
    <div class="sb-user">
      <div class="sb-avatar" style="background:var(--gold);color:var(--navy);">${initials}</div>
      <div>
        <div class="sb-uname">${username}</div>
        <div class="sb-urole" style="color:var(white);font-weight:600;">Head Staff</div>
      </div>
    </div>
  </nav>`;

  document.body.insertAdjacentHTML('afterbegin', html);
}

function logoutHS(e) {
  e && e.preventDefault();
  if (confirm('Are you sure you want to logout?')) {
    localStorage.clear();
    window.location.href = 'login.html';
  }
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