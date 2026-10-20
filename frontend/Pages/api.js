(function (window) {
  'use strict';

  const DEFAULT_API_BASE_URL = 'http://127.0.0.1:8000';
  const API_BASE_URL = String(window.ARKHEION_API_URL || DEFAULT_API_BASE_URL).replace(/\/+$/, '');
  let refreshInProgress = null;
  let staffContextInProgress = null;

  function buildUrl(path) {
    if (/^https?:\/\//i.test(path)) return path;
    return API_BASE_URL + (path.charAt(0) === '/' ? path : `/${path}`);
  }

  function toMessage(data, fallback) {
    if (!data) return fallback;
    if (typeof data === 'string') return data;
    if (typeof data.detail === 'string') return data.detail;
    const messages = [];
    Object.keys(data).forEach((key) => {
      const value = data[key];
      const values = Array.isArray(value) ? value : [value];
      values.forEach((item) => {
        if (typeof item === 'string') messages.push(item);
        else if (item && typeof item === 'object') messages.push(toMessage(item, ''));
      });
    });
    return messages.filter(Boolean).join(' ') || fallback;
  }

  async function readResponse(response) {
    if (response.status === 204) return null;
    const text = await response.text();
    if (!text) return null;
    try {
      return JSON.parse(text);
    } catch (_) {
      return text;
    }
  }

  function clearAuth() {
    sessionStorage.removeItem('ark_token');
    sessionStorage.removeItem('ark_refresh_token');
    localStorage.removeItem('ark_token');
    localStorage.removeItem('ark_refresh_token');
    localStorage.removeItem('ark_username');
    localStorage.removeItem('ark_role');
    localStorage.removeItem('ark_barangay');
    localStorage.removeItem('ark_barangay_id');
    localStorage.removeItem('ark_osca_id');
    localStorage.removeItem('ark_senior_profile');
  }

  function redirectToLogin() {
    if (window.location.pathname.endsWith('/login.html')) return;
    const loginPath = window.ARKHEION_LOGIN_PATH || '../login.html';
    window.location.assign(new URL(loginPath, window.location.href).href);
  }

  function expireSession() {
    clearAuth();
    redirectToLogin();
  }

  async function refreshAccessToken() {
    if (refreshInProgress) return refreshInProgress;
    const refresh = sessionStorage.getItem('ark_refresh_token');
    if (!refresh) return null;

    refreshInProgress = (async function () {
      try {
        const response = await fetch(buildUrl('/api/token/refresh/'), {
          method: 'POST',
          headers: { 'Content-Type': 'application/json', Accept: 'application/json' },
          body: JSON.stringify({ refresh }),
        });
        const result = await readResponse(response);
        if (!response.ok || !result || !result.access) return null;
        sessionStorage.setItem('ark_token', result.access);
        if (result.refresh) sessionStorage.setItem('ark_refresh_token', result.refresh);
        return result.access;
      } catch (_) {
        return null;
      } finally {
        refreshInProgress = null;
      }
    })();
    return refreshInProgress;
  }

  async function request(path, options) {
    const settings = options || {};
    const method = settings.method || 'GET';
    const headers = new Headers(settings.headers || {});
    headers.set('Accept', 'application/json');

    let body = settings.body;
    if (body !== undefined && body !== null && typeof body !== 'string' && !(body instanceof FormData)) {
      body = JSON.stringify(body);
      if (!headers.has('Content-Type')) headers.set('Content-Type', 'application/json');
    }

    const explicitToken = settings.token;
    const storedToken = settings.auth === false ? null : sessionStorage.getItem('ark_token');
    const token = explicitToken || storedToken;
    if (token) headers.set('Authorization', `Bearer ${token}`);

    const init = { method, headers, body, cache: 'no-store' };
    let response = await fetch(buildUrl(path), init);

    const canRefresh = response.status === 401 && settings.auth !== false &&
      !/\/api\/token(?:\/refresh)?\/$/.test(path);
    if (canRefresh) {
      const freshToken = await refreshAccessToken();
      if (freshToken) {
        headers.set('Authorization', `Bearer ${freshToken}`);
        response = await fetch(buildUrl(path), init);
      } else {
        expireSession();
      }
    }

    const data = await readResponse(response);
    if (!response.ok) {
      const error = new Error(toMessage(data, `Request failed (${response.status}).`));
      error.status = response.status;
      error.data = data;
      throw error;
    }
    return data;
  }

  async function download(path, filename) {
    const headers = new Headers({ Accept: "application/octet-stream" });
    const token = sessionStorage.getItem("ark_token");
    if (token) headers.set("Authorization", `Bearer ${token}`);
    let response = await fetch(buildUrl(path), { method: "GET", headers, cache: "no-store" });
    if (response.status === 401) {
      const freshToken = await refreshAccessToken();
      if (!freshToken) {
        expireSession();
        throw new Error("Your session expired. Please sign in again.");
      }
      headers.set("Authorization", `Bearer ${freshToken}`);
      response = await fetch(buildUrl(path), { method: "GET", headers, cache: "no-store" });
    }
    if (!response.ok) {
      const data = await readResponse(response);
      throw new Error(toMessage(data, `Download failed (${response.status}).`));
    }
    const objectUrl = URL.createObjectURL(await response.blob());
    const link = document.createElement("a");
    link.href = objectUrl;
    link.download = filename || "document";
    document.body.appendChild(link);
    link.click();
    link.remove();
    setTimeout(() => URL.revokeObjectURL(objectUrl), 1000);
  }

  async function getStaffContext() {
    if (staffContextInProgress) return staffContextInProgress;
    staffContextInProgress = (async function () {
      try {
        const results = await Promise.all([
          request('/api/me/'),
          request('/api/barangays/'),
        ]);
        const user = results[0];
        const barangays = Array.isArray(results[1]) ? results[1] : [];
        if (!['head_staff', 'regular_staff'].includes(user.role)) {
          throw new Error('This page is only available to OSCA staff accounts.');
        }

        if (user.role === 'head_staff') {
          return { user, barangays, availableBarangays: barangays };
        }

        if (!user.barangay || !user.barangay.id) {
          throw new Error('Your staff account has no assigned barangay. Contact the OSCA administrator.');
        }
        return {
          user,
          barangays,
          availableBarangays: barangays.filter((barangay) => barangay.id === user.barangay.id),
        };
      } catch (error) {
        staffContextInProgress = null;
        throw error;
      }
    })();
    return staffContextInProgress;
  }

  async function populateBarangaySelects(root) {
    const container = root || document;
    const selects = Array.from(container.querySelectorAll('select[data-arkheion-barangay]'));
    if (!selects.length) return null;
    selects.forEach((select) => { select.disabled = true; });
    const context = await getStaffContext();

    selects.forEach((select) => {
      const mode = select.dataset.arkheionBarangay || 'choice';
      const firstLabel = select.options[0]?.textContent.trim() ||
        (mode === 'filter' ? 'All barangays' : 'Select barangay');
      const priorValue = select.value;
      select.replaceChildren();

      if (['filter', 'filter-empty'].includes(mode) && context.user.role === 'head_staff') {
        select.add(new Option(firstLabel, mode === 'filter-empty' ? '' : 'All barangays'));
      } else if (mode !== 'filter' && context.user.role === 'head_staff') {
        select.add(new Option(firstLabel, ''));
      }

      context.availableBarangays.forEach((barangay) => {
        select.add(new Option(barangay.name, barangay.name));
      });

      if (context.user.role === 'regular_staff') {
        select.value = context.user.barangay.name;
        select.disabled = true;
      } else {
        const canKeepPrior = Array.from(select.options).some((option) => option.value === priorValue);
        select.value = canKeepPrior ? priorValue : (mode === 'filter-empty' ? '' : (mode === 'filter' ? 'All barangays' : ''));
        select.disabled = false;
      }
      select.dispatchEvent(new Event('change', { bubbles: true }));
    });
    return context;
  }

  window.ArkheionAPI = {
    baseUrl: API_BASE_URL,
    request,
    get: (path, options) => request(path, Object.assign({}, options, { method: 'GET' })),
    post: (path, body, options) => request(path, Object.assign({}, options, { method: 'POST', body })),
    download,
    patch: (path, body, options) => request(path, Object.assign({}, options, { method: 'PATCH', body })),
    delete: (path, options) => request(path, Object.assign({}, options, { method: 'DELETE' })),
    getCurrentUser: () => request('/api/me/'),
    getBarangays: () => request('/api/barangays/'),
    getStaffContext,
    populateBarangaySelects,
    clearAuth,
  };
})(window);
