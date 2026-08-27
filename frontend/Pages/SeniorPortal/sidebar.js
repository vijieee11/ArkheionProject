// Turns raw usernames like "osca_staff2" into a friendly "Staff 2" display name.
// If role is 'head_staff', always shows "Head Staff" regardless of the username used to log in
// (so switching between the Head Staff and Staff views stays consistent).
function formatStaffName(username, role) {
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

function renderSidebar(activePage) {
  const role     = localStorage.getItem('ark_role') || 'regular_staff';
  const rawUsername = localStorage.getItem('ark_username') || 'Staff';
  const displayName = formatStaffName(rawUsername, role);
  const initials = role === 'head_staff' ? 'HS' : 'S';
  const roleLabel = role === 'head_staff' ? 'Head Staff' : 'Regular Staff';

  const navGroups = [
    { section: 'Main', items: [
      { id: 'dashboard', label: 'Dashboard', icon: 'ti-layout-dashboard', href: 'dashboard.html' },
      { id: 'members',   label: 'Members',   icon: 'ti-users',            href: 'members.html' },
    ]},
    { section: 'Services', items: [
      { id: 'grocery',  label: 'Groceries', icon: 'ti-shopping-cart', href: 'grocery.html' },
      { id: 'medicine', label: 'Medicine',  icon: 'ti-pill',          href: 'medicine.html' },
      { id: 'pension',  label: 'Pension',   icon: 'ti-cash',          href: 'pension.html' },
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
        <div class="sb-uname">${displayName}</div>
        <div class="sb-urole">${roleLabel}</div>
      </div>
    </div>
  </nav>`;

  document.body.insertAdjacentHTML('afterbegin', html);
}

function logout(e) {
  e && e.preventDefault();
  if (confirm('Are you sure you want to logout?')) {
    localStorage.clear();
    window.location.href = '../login.html';
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