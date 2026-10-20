/* Fill Senior Portal identity labels from the authenticated account, not demo text. */
(async function loadSeniorPortalIdentity() {
  const api = window.ArkheionAPI;
  if (!api) return;

  try {
    const currentUser = await api.getCurrentUser();
    const senior = currentUser.senior_citizen || {};
    if (!['senior', 'family'].includes(currentUser.role) || !senior.id) return;

    let record = senior;
    if (currentUser.role === 'senior') {
      record = Object.assign({}, senior, await api.get(`/api/seniors/${senior.id}/`));
    }
    const name = [record.first_name, record.middle_name, record.last_name]
      .filter(Boolean).join(' ') || currentUser.username || 'Senior citizen';
    const initials = name.split(/\s+/).filter(Boolean).slice(0, 2)
      .map((part) => part.charAt(0)).join('').toUpperCase() || 'SC';

    document.querySelectorAll('.portal-uname, [data-senior-name], #portal-greeting-name')
      .forEach((element) => { element.textContent = name; });
    document.querySelectorAll('.portal-avatar, [data-senior-initials]')
      .forEach((element) => { element.textContent = initials; });

    const fields = {
      full_name: name,
      osca_id: record.osca_id,
      registration_cert_no: record.registration_cert_no,
      date_of_registration: record.date_of_registration,
      date_of_birth: record.date_of_birth,
      age: record.age == null ? null : `${record.age} years old`,
      sex: record.sex === 'M' ? 'Male' : record.sex === 'F' ? 'Female' : record.sex,
      civil_status: record.civil_status,
      address: record.address,
      barangay_name: record.barangay_name,
      milestone_age: record.milestone_age,
    };
    document.querySelectorAll('[data-senior-field]').forEach((element) => {
      const value = fields[element.dataset.seniorField];
      element.textContent = value == null || value === '' ? '—' : value;
    });
    document.querySelectorAll('[data-senior-input]').forEach((element) => {
      const value = fields[element.dataset.seniorInput];
      element.value = value == null ? '' : value;
    });

    const oscaLabel = document.getElementById('portal-osca-id');
    if (oscaLabel) oscaLabel.textContent = record.osca_id || '—';
    const barangayLabel = document.getElementById('portal-barangay');
    if (barangayLabel) barangayLabel.textContent = record.barangay_name || 'Barangay not set';
    document.dispatchEvent(new CustomEvent('arkheion:senior-identity-loaded', { detail: { user: currentUser, senior: record, name } }));
  } catch (error) {
    console.warn('Could not load Senior Portal identity:', error);
  }
})();
