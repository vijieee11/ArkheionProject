// Turns raw usernames like "osca_staff2" into a friendly "Staff 2" display name.
// If role is 'head_staff', always shows "Head Staff" regardless of the username used to log in
// (so switching between the Head Staff and Staff views stays consistent).
function formatStaffName(username, role, firstName, lastName) {
  const actualName = [firstName, lastName].filter(Boolean).join(' ').trim();
  if (actualName) return actualName;
  if (role === 'head_staff') return 'Head Staff';
  if (!username) return 'Staff';
  const staffMatch = username.match(/^osca_staff(\d+)$/i);
  if (staffMatch) return 'Staff ' + staffMatch[1];
  if (/^osca_head$/i.test(username)) return 'Head Staff';
  return username
    .replace(/[_\.]+/g, ' ')
    .replace(/@.*/, '')
    .split(' ')
    .filter(Boolean)
    .map(w => w[0].toUpperCase() + w.slice(1))
    .join(' ');
}

let staffIdentityPromise = null;
function getStaffIdentity() {
  if (staffIdentityPromise) return staffIdentityPromise;
  staffIdentityPromise = new Promise((resolve, reject) => {
    const loadIdentity = () => {
      if (!window.ArkheionAPI) return reject(new Error('Staff profile API is unavailable.'));
      window.ArkheionAPI.getCurrentUser().then(resolve, reject);
    };
    if (window.ArkheionAPI) return loadIdentity();
    let script = document.querySelector('script[data-arkheion-api]');
    if (!script) {
      script = document.createElement('script');
      script.src = '../api.js';
      script.dataset.arkheionApi = 'true';
      document.head.appendChild(script);
    }
    script.addEventListener('load', loadIdentity, { once: true });
    script.addEventListener('error', () => reject(new Error('Could not load the staff profile API.')), { once: true });
  }).catch(error => {
    staffIdentityPromise = null;
    throw error;
  });
  return staffIdentityPromise;
}

function renderSidebar(activePage) {
  const role = localStorage.getItem('ark_role') || 'regular_staff';
  const currentPath = window.location.pathname.toLowerCase();
  if (role === 'head_staff' && currentPath.includes('/staff/')) {
    const headStaffTargets = {
      dashboard: '../Headstaff/hs-dashboard.html',
      members: '../Headstaff/member-records.html',
      deaths: '../Headstaff/deaths.html',
      pension: '../Headstaff/analytics.html',
      upload: '../Headstaff/hs-pending-approval.html',
      search: '../Headstaff/member-records.html',
      map: '../Headstaff/member-records.html',
      reports: '../Headstaff/hs-reports.html',
      genaccounts: '../Headstaff/staff-mgmt.html',
      settings: '../Headstaff/settings.html',
      grocery: '../Headstaff/hs-reports.html',
      medicine: '../Headstaff/hs-reports.html',
      'booklet-summary': '../Headstaff/hs-dashboard.html',
    };
    window.location.replace(new URL(headStaffTargets[activePage] || '../Headstaff/hs-dashboard.html', window.location.href).href);
    return;
  }
  const rawUsername = localStorage.getItem('ark_username') || 'Staff';
  const displayName = formatStaffName(rawUsername, role);
  const initials = role === 'head_staff' ? 'HS' : 'S';
  const roleLabel = role === 'head_staff' ? 'OSCA Head Staff' : 'Regular Staff';

  const navGroups = [
    { section: 'Main', items: [
      { id: 'dashboard', label: 'Dashboard', icon: 'ti-layout-dashboard', href: 'dashboard.html' },
      { id: 'members',   label: 'Members',   icon: 'ti-users',            href: 'members.html' },
      { id: 'deaths',    label: 'Death records', icon: 'ti-heart-x',       href: 'deaths.html' },
    ]},
    { section: 'Services', items: [
      { id: 'pension',  label: 'Pension',   icon: 'ti-cash',          href: 'pension.html' },
      ...(role === 'regular_staff' && (localStorage.getItem('ark_barangay') || '').trim().toLowerCase() === 'ising'
        ? [{ id: 'booklet-summary', label: 'Booklet returns', icon: 'ti-notes', href: 'booklet-summary.html' }]
        : []),
    ]},
    { section: 'Documents', items: [
      { id: 'upload', label: 'Upload docs',    icon: 'ti-upload',   href: 'upload.html' },
      { id: 'search', label: 'Search records', icon: 'ti-search',   href: 'search.html' },
      { id: 'map',    label: 'Map view',       icon: 'ti-map-pin',  href: 'map.html' },
    ]},
    { section: 'System', items: [
      { id: 'reports',     label: 'Reports',            icon: 'ti-chart-bar', href: 'reports.html' },
      { id: 'genaccounts', label: 'Generate accounts',  icon: 'ti-key',        href: 'generate-accounts.html' },
      { id: 'settings',    label: 'Settings',           icon: 'ti-settings',   href: 'settings.html' },
    ]}
  ];

  let html = `<nav class="sidebar">
    <div class="sb-logo">
      <div class="sb-logo-icon"><i class="ti ti-archive"></i></div>
      <span class="sb-logo-text">Arkheion</span>
    </div>`;

  navGroups.forEach(group => {
    html += `<span class="sb-section">${group.section}</span>`;
    group.items.forEach(item => {
      const isActive = item.id === activePage;
      html += `
        <a class="nav-item ${isActive ? 'active' : ''}" href="${item.href}">
          <i class="ti ${item.icon}"></i>
          ${item.label}
        </a>`;
    });
  });

  html += `
    <div class="sb-spacer"></div>
    <a class="nav-item" href="#" onclick="logout(event)">
      <i class="ti ti-logout"></i>Logout
    </a>
    <div class="sb-user">
      <div class="sb-avatar">${initials}</div>
      <div>
        <div class="sb-uname" id="staffSidebarName">${displayName}</div>
        <div class="sb-urole">${roleLabel}</div>
      </div>
    </div>
  </nav>`;

  document.body.insertAdjacentHTML('afterbegin', html);
  ensureLogoutModal();
  getStaffIdentity().then(account => {
    const name = formatStaffName(account.username, account.role, account.first_name, account.last_name);
    const nameElement = document.getElementById('staffSidebarName');
    if (nameElement) nameElement.textContent = name;
    document.dispatchEvent(new CustomEvent('arkheion:staff-identity-loaded', { detail: { account, displayName: name } }));
  }).catch(() => {});
}

// Injects the "Confirm logout" modal once per page, reusing the same
// modal-overlay/.modal markup pattern used across the rest of the app
// (pension, grocery, register, etc.) instead of the native confirm() box.
function ensureLogoutModal() {
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
          <button class="btn btn-navy" onclick="confirmLogout()"><i class="ti ti-logout"></i> Logout</button>
        </div>
      </div>
    </div>`;
  document.body.insertAdjacentHTML('beforeend', html);
}

function logout(e) {
  e && e.preventDefault();
  ensureLogoutModal();
  openModal('modal-logout-confirm');
}

function confirmLogout() {
  localStorage.clear();
  sessionStorage.clear();
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
