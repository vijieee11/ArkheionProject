renderSidebar('reports');
  const asArray = data => Array.isArray(data) ? data : (data && Array.isArray(data.results) ? data.results : []);
  const htmlEscape = value => String(value ?? '').replace(/[&<>"']/g, char => ({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'}[char]));
  const textValue = value => String(value ?? '').trim();
  const reportDefinitions = {
    masterlist: { title: 'Senior Citizen Masterlist', file: 'senior-masterlist', headers: ['OSCA ID','Last name','First name','Middle name','Suffix','Barangay','Age','Sex','Civil status','Registration status'] },
    pension: { title: 'Pension Payroll', file: 'pension-payroll', headers: ['Period','OSCA ID','Senior citizen','Barangay','Amount (PHP)','Claim status','Date claimed','Claimed by'] },
    grocery: { title: 'Grocery Distribution List', file: 'grocery-distribution-list', headers: ['Period','Distribution date','Barangay','OSCA ID','Senior citizen','Claim status','Date claimed','Claimed by','Representative'] },
    booklet: { title: 'Full Booklets Returned to OSCA', file: 'full-booklet-returns', headers: ['Date returned','OSCA ID','Senior citizen','Barangay','Status','Recorded by','Note'] },
  };
  const monthInput = document.getElementById('reportMonth');
  const now = new Date();
  monthInput.value = `${now.getFullYear()}-${String(now.getMonth()+1).padStart(2,'0')}`;

  function showReportStatus(message, type='info') {
    const box = document.getElementById('reportStatus');
    box.textContent = message;
    box.className = `report-status show ${type}`;
  }
  function selectedBarangay() { return document.getElementById('reportBarangay').value; }
  function matchesBarangay(row, name) { return !name || String(row.barangay || '') === name; }
  function periodAsMonth(value) {
    const raw = String(value || '').trim();
    const numeric = raw.match(/^(\d{4})-(\d{1,2})$/);
    if (numeric) return `${numeric[1]}-${numeric[2].padStart(2,'0')}`;
    const named = raw.match(/^([A-Za-z]+)\s+(\d{4})$/);
    if (!named) return '';
    const date = new Date(`${named[1]} 1, ${named[2]}`);
    return Number.isNaN(date.getTime()) ? '' : `${date.getFullYear()}-${String(date.getMonth()+1).padStart(2,'0')}`;
  }
  function monthName(value) {
    if (!/^\d{4}-\d{2}$/.test(value || '')) return value || 'All periods';
    const [year,month] = value.split('-').map(Number);
    return new Intl.DateTimeFormat('en-PH',{month:'long',year:'numeric'}).format(new Date(year,month-1,1));
  }
  function reportPeriodLabel(value) {
    const normalized = periodAsMonth(value);
    return normalized ? monthName(normalized) : (value || 'Unspecified period');
  }
  function activeForMonth(period) {
    const selected = monthInput.value;
    return !selected || periodAsMonth(period) === selected;
  }
  function downloadCsv(definition, reportRows, scopeLabel) {
    const escapeCell = value => {
      let cell = String(value ?? '');
      if (/^[=+\-@\t\r]/.test(cell)) cell = `'${cell}`;
      return `"${cell.replace(/"/g,'""')}"`;
    };
    const table = [definition.headers, ...reportRows].map(row => row.map(escapeCell).join(',')).join('\r\n');
    const blob = new Blob(['\uFEFF', table], {type:'text/csv;charset=utf-8;'});
    const url = URL.createObjectURL(blob);
    const link = document.createElement('a');
    link.href = url;
    link.download = `${definition.file}-${scopeLabel}.csv`;
    document.body.appendChild(link); link.click(); link.remove();
    setTimeout(() => URL.revokeObjectURL(url), 1000);
  }
  function openPrintReport(printWindow, definition, reportRows, scopeLabel, sourceNote) {
    const heading = `<h1>${htmlEscape(definition.title)}</h1><p class="meta">${htmlEscape(scopeLabel)} · Generated ${htmlEscape(new Date().toLocaleString('en-PH'))}</p>`;
    const note = sourceNote ? `<p class="note">${htmlEscape(sourceNote)}</p>` : '';
    const body = reportRows.length
      ? reportRows.map(row => `<tr>${row.map(cell => `<td>${htmlEscape(cell === null || cell === undefined || cell === '' ? '—' : cell)}</td>`).join('')}</tr>`).join('')
      : `<tr><td colspan="${definition.headers.length}" class="empty">No records match the selected filters.</td></tr>`;
    printWindow.document.open();
    printWindow.document.write(`<!doctype html><html><head><meta charset="utf-8"><title>${htmlEscape(definition.title)}</title><style>body{font:12px Arial,sans-serif;color:#17212b;margin:28px}h1{font-size:20px;margin:0 0 6px}.meta,.note{color:#556575;font-size:11px;margin:0 0 16px}.note{padding:9px;background:#eff6f4}table{width:100%;border-collapse:collapse}th,td{border:1px solid #ccd5dd;padding:7px;text-align:left;vertical-align:top}th{background:#eef3f4;font-weight:700}.empty{text-align:center;color:#617080;padding:22px}@media print{body{margin:12mm}thead{display:table-header-group}tr{break-inside:avoid}}</style></head><body>${heading}${note}<table><thead><tr>${definition.headers.map(header => `<th>${htmlEscape(header)}</th>`).join('')}</tr></thead><tbody>${body}</tbody></table></body></html>`);
    printWindow.document.close();
    setTimeout(() => { if (!printWindow.closed) { printWindow.focus(); printWindow.print(); } }, 300);
  }
  function seniorName(row) { return [row.first_name,row.middle_name,row.last_name].filter(Boolean).join(' '); }
  function claimLabel(row) { return row.claimed ? 'Claimed' : 'Unclaimed'; }

  async function buildReport(key) {
    const definition = reportDefinitions[key];
    const barangay = selectedBarangay();
    const selectedMonth = monthInput.value;
    const scopeLabel = `${monthName(selectedMonth)} · ${barangay || 'All barangays'}`;
    if (key === 'booklet') {
      const returns = asArray(await ArkheionAPI.get('/api/booklet-returns/'));
      const filtered = returns.filter(row => (!selectedMonth || String(row.date_returned).startsWith(selectedMonth)) && (!barangay || row.barangay_name === barangay));
      const rows = filtered.map(row => [row.date_returned,row.senior_osca_id,row.senior_name,row.barangay_name,'Full',row.recorded_by_name||'',row.note||'']);
      return {definition, rows, scopeLabel, sourceNote:'Source: completed physical booklets recorded as returned to the OSCA office.'};
    }    if (key === 'masterlist') {
      const seniors = asArray(await ArkheionAPI.get('/api/seniors/'));
      const rows = seniors.filter(row => row.is_active && matchesBarangay({barangay:row.barangay_name}, barangay)).map(row => [row.osca_id,row.last_name,row.first_name,row.middle_name,row.suffix,row.barangay_name,row.age,row.sex === 'M' ? 'Male' : row.sex === 'F' ? 'Female' : '',row.civil_status,row.registration_status]);
      rows.sort((a,b) => String(a[5]).localeCompare(String(b[5])) || String(a[1]).localeCompare(String(b[1])) || String(a[2]).localeCompare(String(b[2])));
      return {definition, rows, scopeLabel, sourceNote:'Source: active senior records available to your authenticated staff account.'};
    }
    if (key === 'pension') {
      const [pensionResponse, seniorResponse] = await Promise.all([ArkheionAPI.get('/api/pensions/'),ArkheionAPI.get('/api/seniors/')]);
      const seniors = asArray(seniorResponse);
      const seniorById = new Map(seniors.map(row => [String(row.id),row]));
      const rows = asArray(pensionResponse).filter(record => {
        const senior = seniorById.get(String(record.senior_citizen)) || {};
        return activeForMonth(record.period) && matchesBarangay({barangay:senior.barangay_name},barangay);
      }).map(record => {
        const senior = seniorById.get(String(record.senior_citizen)) || {};
        const claimant = record.claimed ? (record.claimed_by === 'self' ? 'Self' : record.representative || 'Authorized representative') : '';
        return [reportPeriodLabel(record.period),record.senior_osca_id || senior.osca_id,record.senior_name || seniorName(senior),senior.barangay_name,Number(record.amount)||0,claimLabel(record),record.date_claimed||'',claimant];
      });
      rows.sort((a,b) => String(a[3]).localeCompare(String(b[3])) || String(a[1]).localeCompare(String(b[1])));
      return {definition, rows, scopeLabel, sourceNote:'Source: pension claim history in the backend. A payroll export lists recorded claims and is not proof of eligibility.'};
    }
    if (key === 'grocery') {
      const response = await ArkheionAPI.get('/api/grocery/claims/');
      const rows = asArray(response).filter(record => activeForMonth(record.period) && matchesBarangay(record,barangay)).map(record => [reportPeriodLabel(record.period),record.distribution_date,record.barangay,record.senior_osca_id,record.senior_name,claimLabel(record),record.date_claimed||'',record.claimed ? (record.claimed_by === 'self' ? 'Self' : 'Authorized representative') : '',record.representative||'']);
      rows.sort((a,b) => String(a[2]).localeCompare(String(b[2])) || String(a[4]).localeCompare(String(b[4])));
      return {definition, rows, scopeLabel, sourceNote:'Source: grocery claims saved in the backend and visible to your staff account.'};
    }
    throw new Error('Unknown report type.');
  }

  async function generateReport(button,key,format) {
    const original = button.innerHTML;
    let printWindow = null;
    if (format === 'pdf') {
      printWindow = window.open('', '_blank');
      if (!printWindow) {
        showReportStatus('The browser blocked the print window. Allow pop-ups for this page and try again.','error');
        return;
      }
    }
    button.disabled = true;
    button.innerHTML = '<i class="ti ti-loader"></i> Preparing…';
    showReportStatus('Preparing report from current records…','info');
    try {
      const report = await buildReport(key);
      if (format === 'csv') downloadCsv(report.definition,report.rows,monthInput.value || 'all-periods');
      else openPrintReport(printWindow,report.definition,report.rows,report.scopeLabel,report.sourceNote);
      showReportStatus(`${report.definition.title}: prepared ${report.rows.length} row${report.rows.length === 1 ? '' : 's'}.`,'success');
    } catch (error) {
      if (printWindow && !printWindow.closed) printWindow.close();
      showReportStatus(error.message || 'Could not prepare this report.','error');
    } finally {
      button.disabled = false;
      button.innerHTML = original;
    }
  }

  async function initReports() {
    try {
      const [account] = await Promise.all([ArkheionAPI.getCurrentUser(), ArkheionAPI.populateBarangaySelects()]);
      if (account.role === 'regular_staff' && String(account.barangay?.name || '').trim().toLowerCase() !== 'ising') {
        document.getElementById('groceryReportCard').hidden = true;
      }
    }
    catch (error) { showReportStatus(error.message || 'Could not load your staff account and barangays.','error'); }
  }
  initReports();
