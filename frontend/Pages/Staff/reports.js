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
  let isIsingOffice = false;
  function selectedBarangay(reportKey) {
    if (isIsingOffice && ['grocery','booklet'].includes(reportKey)) return document.getElementById('officeReportBarangay').value;
    return document.getElementById('reportBarangay').value;
  }
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
  function crc32(bytes) {
    let crc = -1;
    for (const byte of bytes) {
      crc ^= byte;
      for (let bit = 0; bit < 8; bit++) crc = (crc >>> 1) ^ (crc & 1 ? 0xedb88320 : 0);
    }
    return (crc ^ -1) >>> 0;
  }
  function zipStore(files) {
    const encoder = new TextEncoder();
    const localParts = [];
    const centralParts = [];
    let offset = 0;
    const now = new Date();
    const dosTime = (now.getHours() << 11) | (now.getMinutes() << 5) | Math.floor(now.getSeconds() / 2);
    const dosDate = ((Math.max(now.getFullYear(), 1980) - 1980) << 9) | ((now.getMonth() + 1) << 5) | now.getDate();

    for (const file of files) {
      const name = encoder.encode(file.name);
      const data = encoder.encode(file.content);
      const checksum = crc32(data);
      const local = new Uint8Array(30 + name.length);
      const localView = new DataView(local.buffer);
      localView.setUint32(0, 0x04034b50, true);
      localView.setUint16(4, 20, true);
      localView.setUint16(6, 0x0800, true);
      localView.setUint16(8, 0, true);
      localView.setUint16(10, dosTime, true);
      localView.setUint16(12, dosDate, true);
      localView.setUint32(14, checksum, true);
      localView.setUint32(18, data.length, true);
      localView.setUint32(22, data.length, true);
      localView.setUint16(26, name.length, true);
      localView.setUint16(28, 0, true);
      local.set(name, 30);
      localParts.push(local, data);

      const central = new Uint8Array(46 + name.length);
      const centralView = new DataView(central.buffer);
      centralView.setUint32(0, 0x02014b50, true);
      centralView.setUint16(4, 20, true);
      centralView.setUint16(6, 20, true);
      centralView.setUint16(8, 0x0800, true);
      centralView.setUint16(10, 0, true);
      centralView.setUint16(12, dosTime, true);
      centralView.setUint16(14, dosDate, true);
      centralView.setUint32(16, checksum, true);
      centralView.setUint32(20, data.length, true);
      centralView.setUint32(24, data.length, true);
      centralView.setUint16(28, name.length, true);
      centralView.setUint16(30, 0, true);
      centralView.setUint16(32, 0, true);
      centralView.setUint16(34, 0, true);
      centralView.setUint16(36, 0, true);
      centralView.setUint32(38, 0, true);
      centralView.setUint32(42, offset, true);
      central.set(name, 46);
      centralParts.push(central);
      offset += local.length + data.length;
    }

    const centralSize = centralParts.reduce((total, part) => total + part.length, 0);
    const end = new Uint8Array(22);
    const endView = new DataView(end.buffer);
    endView.setUint32(0, 0x06054b50, true);
    endView.setUint16(4, 0, true);
    endView.setUint16(6, 0, true);
    endView.setUint16(8, files.length, true);
    endView.setUint16(10, files.length, true);
    endView.setUint32(12, centralSize, true);
    endView.setUint32(16, offset, true);
    endView.setUint16(20, 0, true);
    return new Blob([...localParts, ...centralParts, end], {
      type: 'application/vnd.openxmlformats-officedocument.spreadsheetml.sheet',
    });
  }
  function downloadXlsx(definition, reportRows, scopeLabel) {
    const xmlEscape = value => String(value ?? '').replace(/[&<>"']/g, char => ({
      '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;', "'": '&apos;',
    })[char]).replace(/[\u0000-\u0008\u000B\u000C\u000E-\u001F]/g, '');
    const columnName = number => {
      let name = '';
      for (let value = number + 1; value; value = Math.floor((value - 1) / 26)) {
        name = String.fromCharCode(65 + (value - 1) % 26) + name;
      }
      return name;
    };
    const rows = [definition.headers, ...reportRows];
    const sheetRows = rows.map((row, rowIndex) => {
      const cells = row.map((value, columnIndex) => {
        const reference = `${columnName(columnIndex)}${rowIndex + 1}`;
        if (typeof value === 'number' && Number.isFinite(value)) {
          return `<c r="${reference}" t="n"><v>${value}</v></c>`;
        }
        return `<c r="${reference}" t="inlineStr"><is><t xml:space="preserve">${xmlEscape(value === null || value === undefined || value === '' ? '—' : value)}</t></is></c>`;
      }).join('');
      return `<row r="${rowIndex + 1}">${cells}</row>`;
    }).join('');
    const worksheet = `<?xml version="1.0" encoding="UTF-8" standalone="yes"?><worksheet xmlns="http://schemas.openxmlformats.org/spreadsheetml/2006/main"><sheetData>${sheetRows}</sheetData></worksheet>`;
    const files = [
      { name: '[Content_Types].xml', content: '<?xml version="1.0" encoding="UTF-8" standalone="yes"?><Types xmlns="http://schemas.openxmlformats.org/package/2006/content-types"><Default Extension="rels" ContentType="application/vnd.openxmlformats-package.relationships+xml"/><Default Extension="xml" ContentType="application/xml"/><Override PartName="/xl/workbook.xml" ContentType="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet.main+xml"/><Override PartName="/xl/worksheets/sheet1.xml" ContentType="application/vnd.openxmlformats-officedocument.spreadsheetml.worksheet+xml"/></Types>' },
      { name: '_rels/.rels', content: '<?xml version="1.0" encoding="UTF-8" standalone="yes"?><Relationships xmlns="http://schemas.openxmlformats.org/package/2006/relationships"><Relationship Id="rId1" Type="http://schemas.openxmlformats.org/officeDocument/2006/relationships/officeDocument" Target="xl/workbook.xml"/></Relationships>' },
      { name: 'xl/workbook.xml', content: '<?xml version="1.0" encoding="UTF-8" standalone="yes"?><workbook xmlns="http://schemas.openxmlformats.org/spreadsheetml/2006/main" xmlns:r="http://schemas.openxmlformats.org/officeDocument/2006/relationships"><sheets><sheet name="Report" sheetId="1" r:id="rId1"/></sheets></workbook>' },
      { name: 'xl/_rels/workbook.xml.rels', content: '<?xml version="1.0" encoding="UTF-8" standalone="yes"?><Relationships xmlns="http://schemas.openxmlformats.org/package/2006/relationships"><Relationship Id="rId1" Type="http://schemas.openxmlformats.org/officeDocument/2006/relationships/worksheet" Target="worksheets/sheet1.xml"/></Relationships>' },
      { name: 'xl/worksheets/sheet1.xml', content: worksheet },
    ];
    const blob = zipStore(files);
    const safeScope = String(scopeLabel).replace(/[\\/:*?"<>|]/g, '-');
    const url = URL.createObjectURL(blob);
    const link = document.createElement('a');
    link.href = url;
    link.download = `${definition.file}-${safeScope}.xlsx`;
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
    const barangay = selectedBarangay(key);
    const selectedMonth = monthInput.value;
    const scopeLabel = key === 'masterlist'
      ? (barangay || 'All barangays')
      : `${monthName(selectedMonth)} · ${barangay || 'All barangays'}`;
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
      const fileScope = `${key === 'masterlist' ? 'all-periods' : (monthInput.value || 'all-periods')}-${selectedBarangay(key) || 'all-barangays'}`;
      if (format === 'xlsx') downloadXlsx(report.definition,report.rows,fileScope);
      else if (format === 'csv') downloadCsv(report.definition,report.rows,fileScope);
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
      const [account, context] = await Promise.all([ArkheionAPI.getCurrentUser(), ArkheionAPI.populateBarangaySelects()]);
      isIsingOffice = account.role === 'regular_staff' && String(account.barangay?.name || '').trim().toLowerCase() === 'ising';
      if (isIsingOffice) {
        const officeFilter = document.getElementById('officeReportBarangay');
        (context?.availableBarangays || []).forEach(row => officeFilter.add(new Option(row.name,row.name)));
        officeFilter.value = '';
        document.getElementById('officeReportScope').hidden = false;
      } else {
        document.getElementById('groceryReportCard').hidden = true;
        document.getElementById('bookletReportCard').hidden = true;
      }
    }
    catch (error) { showReportStatus(error.message || 'Could not load your staff account and barangays.','error'); }
  }
  initReports();
