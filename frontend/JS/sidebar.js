// sidebar.js — Shared sidebar for all staff pages
// Usage: <script src="sidebar.js"></script>
// Then call: renderSidebar('dashboard') at bottom of body

function renderSidebar(activePage) {
  const role     = localStorage.getItem('ark_role') || 'regular_staff';
  const username = localStorage.getItem('ark_username') || 'Staff';
  const initials = username.split('_').map(w => w[0]?.toUpperCase() || '').join('').slice(0,2) || 'ST';
  const roleLabel = role === 'head_staff' ? 'Head Staff' : 'Regular Staff';

  const navGroups = [
    {
      section: 'Main',
      items: [
        { id: 'dashboard', label: 'Dashboard',     icon: 'ti-layout-dashboard', href: 'dashboard.html' },
        { id: 'members',   label: 'Members',       icon: 'ti-users',            href: 'members.html' },
      ]
    },
    {
      section: 'Services',
      items: [
        { id: 'grocery',  label: 'Groceries', icon: 'ti-shopping-cart', href: 'grocery.html' },
        { id: 'medicine', label: 'Medicine',  icon: 'ti-pill',          href: 'medicine.html' },
        { id: 'pension',  label: 'Pension',   icon: 'ti-cash',          href: 'pension.html' },
      ]
    },
    {
      section: 'Documents',
      items: [
        { id: 'upload', label: 'Upload docs',    icon: 'ti-upload',   href: 'upload.html' },
        { id: 'search', label: 'Search records', icon: 'ti-search',   href: 'search.html' },
        { id: 'map',    label: 'Map view',       icon: 'ti-map-pin',  href: 'map.html' },
      ]
    },
    {
      section: 'System',
      items: [
        { id: 'reports',  label: 'Reports',  icon: 'ti-chart-bar',    href: 'reports.html' },
        { id: 'audit',    label: 'Audit log',icon: 'ti-shield-check', href: 'audit.html', badge: '9' },
        ...(role === 'head_staff' ? [
          { id: 'staffmgmt', label: 'Staff mgmt', icon: 'ti-users-group', href: 'staff-mgmt.html', badgeGold: 'HEAD' }
        ] : [])
      ]
    }
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
      const badge     = item.badge     ? `<span class="nav-badge">${item.badge}</span>` : '';
      const badgeGold = item.badgeGold ? `<span class="nav-badge-gold">${item.badgeGold}</span>` : '';
      html += `
        <a class="nav-item ${isActive ? 'active' : ''}" href="${item.href}"
           style="${item.badgeGold ? 'color:#FAC775' : ''}">
          <i class="ti ${item.icon}"></i>
          ${item.label}${badge}${badgeGold}
        </a>`;
    });
  });

  html += `
    <div class="sb-spacer"></div>
    <a class="nav-item" href="login.html" onclick="logout(event)">
      <i class="ti ti-settings"></i>Settings
    </a>
    <div class="sb-user">
      <div class="sb-avatar">${initials}</div>
      <div>
        <div class="sb-uname">${username}</div>
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