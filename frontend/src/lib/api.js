/**
 * Single API boundary. Pages never call fetch directly.
 * Session cookies are HttpOnly; mutations echo the per-session CSRF token.
 */

export const API_BASE = import.meta.env.VITE_API_BASE || '/api/v1';

// Origin of the API (and of the public /c/<code> verification pages), resolved
// once so QR links can be built without guessing from the current route.
export const API_ORIGIN = (() => {
  try {
    return new URL(API_BASE, window.location.origin).origin;
  } catch {
    return '';
  }
})();

let csrfToken = null;
let unauthorizedHandler = null;

// Concurrent identical reads (React StrictMode double effects, several widgets on
// one screen) must share a single network request instead of racing each other.
const GET_INFLIGHT = new Map();

const DEFAULT_TIMEOUT_MS = 25000;
const UPLOAD_TIMEOUT_MS = 60000;

// Reads retry once on a transient backend answer. A cold database used to show
// "internal server error" until the user refreshed; now the page heals itself.
const RETRYABLE_STATUS = new Set([429, 502, 503, 504]);
const RETRY_DELAY_MS = 400;
const RETRY_MAX_DELAY_MS = 2000;

const sleep = (ms) => new Promise((resolve) => setTimeout(resolve, ms));

function retryDelay(res) {
  const header = Number(res.headers.get('retry-after'));
  if (Number.isFinite(header) && header > 0) return Math.min(header * 1000, RETRY_MAX_DELAY_MS);
  return RETRY_DELAY_MS;
}

export class ApiError extends Error {
  constructor(message, { status = 0, code = '', details = null } = {}) {
    super(message);
    this.name = 'ApiError';
    this.status = status;
    this.code = code;
    this.details = details;
  }
}

export function onUnauthorized(handler) {
  unauthorizedHandler = handler;
}

let stepUpHandler = null;

/**
 * Register the step-up prompt. Resolves true once a fresh authenticator code
 * has been accepted; the request that needed it is then retried once.
 */
export function onStepUpRequired(handler) {
  stepUpHandler = handler;
}

export function setCsrfToken(token) {
  csrfToken = token;
}

export async function refreshCsrf() {
  try {
    const res = await fetch(`${API_BASE}/auth/csrf`, { credentials: 'include' });
    if (!res.ok) {
      csrfToken = null;
      return null;
    }
    const body = await res.json();
    csrfToken = body?.csrfToken || null;
    return csrfToken;
  } catch {
    csrfToken = null;
    return null;
  }
}

function query(params = {}) {
  const search = new URLSearchParams();
  Object.entries(params).forEach(([key, value]) => {
    if (value !== undefined && value !== null && value !== '') search.set(key, value);
  });
  const qs = search.toString();
  return qs ? `?${qs}` : '';
}

export function api(path, options = {}) {
  const method = String(options.method || 'GET').toUpperCase();
  if (method !== 'GET' && method !== 'HEAD') {
    return runRequest(path, { ...options, method });
  }

  const key = `${method} ${path}`;
  const pending = GET_INFLIGHT.get(key);
  if (pending) return pending;

  const request = runRequest(path, { ...options, method }).finally(() => {
    if (GET_INFLIGHT.get(key) === request) GET_INFLIGHT.delete(key);
  });
  GET_INFLIGHT.set(key, request);
  return request;
}

async function runRequest(
  path,
  { method = 'GET', body, form, retry = true, steppedUp = false, timeoutMs, headers: extraHeaders } = {},
) {
  const headers = { ...(extraHeaders || {}) };
  const controller = typeof AbortController !== 'undefined' ? new AbortController() : null;
  const timeout = controller
    ? setTimeout(() => controller.abort(), timeoutMs ?? (form ? UPLOAD_TIMEOUT_MS : DEFAULT_TIMEOUT_MS))
    : null;

  const init = { method, credentials: 'include', headers };
  if (controller) init.signal = controller.signal;

  if (form) {
    init.body = form;
  } else if (body !== undefined) {
    headers['Content-Type'] = 'application/json';
    init.body = JSON.stringify(body);
  }

  if (!['GET', 'HEAD', 'OPTIONS'].includes(method) && csrfToken) {
    headers['X-CSRF-Token'] = csrfToken;
  }

  const readOnly = method === 'GET' || method === 'HEAD';
  let res;
  let text = '';
  try {
    res = await fetch(`${API_BASE}${path}`, init);
    text = await res.text();
  } catch (error) {
    if (error?.name === 'AbortError') {
      throw new ApiError('The server took too long to respond. Please try again.', {
        code: 'TIMEOUT',
      });
    }
    if (readOnly && retry) {
      await sleep(RETRY_DELAY_MS);
      return runRequest(path, { method, retry: false, timeoutMs });
    }
    throw new ApiError('Could not reach the convention service. Check your connection and retry.', {
      code: 'NETWORK',
    });
  } finally {
    if (timeout) clearTimeout(timeout);
  }

  let payload = null;
  if (text) {
    try {
      payload = JSON.parse(text);
    } catch {
      payload = text;
    }
  }

  if (!res.ok) {
    const error = payload?.error;
    if (readOnly && retry && RETRYABLE_STATUS.has(res.status)) {
      await sleep(retryDelay(res));
      return runRequest(path, { method, retry: false, timeoutMs });
    }
    if (res.status === 403 && error?.code === 'CSRF_INVALID' && retry) {
      await refreshCsrf();
      // Bypass the shared-read map: this is a retry of the same request.
      return runRequest(path, { method, body, form, retry: false, timeoutMs, headers: extraHeaders });
    }
    if (res.status === 401) unauthorizedHandler?.();
    const code = error?.code || '';
    if (code === 'STEP_UP_REQUIRED' && stepUpHandler && !steppedUp) {
      const confirmed = await stepUpHandler(error);
      if (confirmed) {
        return runRequest(path, { method, body, form, retry: false, steppedUp: true, timeoutMs, headers: extraHeaders });
      }
    }
    // A staff account that cannot complete enrolment/conversion yet gets a
    // sentence they can act on rather than a bare forbidden screen.
    const message =
      code === 'MFA_REQUIRED'
        ? 'Two-factor authentication is required. Open /manage to finish setting it up.'
        : error?.message || `Request failed (${res.status})`;
    throw new ApiError(message, {
      status: res.status,
      code,
      details: error?.details ?? null,
    });
  }

  return payload;
}

export const publicApi = {
  config: () => api('/public/config'),
  edition: () => api('/public/editions/current'),
  editionBySlug: (slug) => api(`/public/editions/${encodeURIComponent(slug)}`),
  categories: (slug) => api(`/public/editions/${encodeURIComponent(slug)}/categories`),
  registrationCategories: (slug) =>
    api(`/public/editions/${encodeURIComponent(slug)}/registration-categories`),
  events: (slug, params = {}) =>
    api(`/public/editions/${encodeURIComponent(slug)}/events${query(params)}`),
  event: (slug, eventSlug) =>
    api(`/public/editions/${encodeURIComponent(slug)}/events/${encodeURIComponent(eventSlug)}`),
  schedule: (slug) => api(`/public/editions/${encodeURIComponent(slug)}/schedule`),
  announcements: (slug, params = {}) =>
    api(`/public/editions/${encodeURIComponent(slug)}/announcements${query(params)}`),
  policy: (slug) => api(`/public/editions/${encodeURIComponent(slug)}/policy`),
  submitInquiry: (payload) =>
    api('/public/inquiries', {
      method: 'POST',
      body: payload,
    }),
  iconUrl: (iconId) => `${API_BASE}/public/icons/${iconId}`,
  teamInvite: (code) => api(`/public/teams/${encodeURIComponent(code)}`),
};

export const authApi = {
  login: (payload) => api('/auth/login', { method: 'POST', body: payload }),
  logout: () => api('/auth/logout', { method: 'POST' }),
  me: () => api('/me'),
  mfaSetup: (params) => {
    const query = params?.reset ? '?reset=true' : '';
    return api(`/auth/mfa/setup${query}`, { method: 'POST' });
  },
  mfaVerify: (payload) => api('/auth/mfa/verify', { method: 'POST', body: payload }),
  mfaChallenge: (payload) => api('/auth/mfa/challenge', { method: 'POST', body: payload }),
  mfaStepUp: (payload) => api('/auth/mfa/step-up', { method: 'POST', body: payload }),
  sessions: () => api('/me/sessions'),
  profile: () => api('/me/profile'),
  updateProfile: (payload) => api('/me/profile', { method: 'PATCH', body: payload }),
  googleLoginHref: (next = '/portal') =>
    `${API_BASE}/auth/google/login?next=${encodeURIComponent(next)}`,
};

export const portalApi = {
  pass: (editionId) => api(`/editions/${editionId}/pass`),
  worklist: (editionId) => api(`/editions/${editionId}/worklist`),
  basket: (editionId) => api(`/editions/${editionId}/basket`),
  addToBasket: (editionId, eventIds) =>
    api(`/editions/${editionId}/basket/events`, {
      method: 'POST',
      body: { eventIds },
    }),
  removeFromBasket: (editionId, eventId) =>
    api(`/editions/${editionId}/basket/events/${eventId}`, { method: 'DELETE' }),
  quote: (editionId, eventIds) =>
    api(`/editions/${editionId}/quote`, { method: 'POST', body: { eventIds } }),
  checkout: (editionId, quoteId, idempotencyKey) =>
    api(`/editions/${editionId}/checkout`, {
      method: 'POST',
      body: { quoteId },
      headers: idempotencyKey ? { 'Idempotency-Key': idempotencyKey } : undefined,
    }),
  removeEvent: (editionId, eventId) =>
    api(`/editions/${editionId}/events/${eventId}`, { method: 'DELETE' }),
  saveSelections: (editionId, eventIds) =>
    api(`/editions/${editionId}/pass/selections`, { method: 'PUT', body: { eventIds } }),
  registrations: (editionId) => api(`/editions/${editionId}/registrations`),
  registerAddons: (editionId, eventIds) =>
    api(`/editions/${editionId}/registrations`, { method: 'POST', body: { eventIds } }),
  cancelRegistration: (editionId, registrationId) =>
    api(`/editions/${editionId}/registrations/${registrationId}`, { method: 'DELETE' }),
  teams: (editionId) => api(`/editions/${editionId}/teams`),
  createTeam: (editionId, payload) =>
    api(`/editions/${editionId}/teams`, { method: 'POST', body: payload }),
  joinTeam: (editionId, inviteCode) =>
    api(`/editions/${editionId}/teams/join`, { method: 'POST', body: { inviteCode } }),
  leaveTeam: (editionId, teamId, { disband = false } = {}) =>
    api(`/editions/${editionId}/teams/${teamId}${disband ? '?disband=true' : ''}`, {
      method: 'DELETE',
    }),
  rotateInvite: (editionId, teamId) =>
    api(`/editions/${editionId}/teams/${teamId}/rotate-invite`, { method: 'POST' }),
  toggleTeamLock: (editionId, teamId) =>
    api(`/editions/${editionId}/teams/${teamId}/lock`, { method: 'POST' }),
  tickets: (editionId) => api(`/editions/${editionId}/tickets`),
  payment: (editionId, orderId) => api(`/editions/${editionId}/payments/${orderId}`),
  mockPay: (editionId, orderId) =>
    api(`/editions/${editionId}/payments/${orderId}/mock`, { method: 'POST' }),
  verifyPayment: (editionId, payload) =>
    api(`/editions/${editionId}/payments/verify`, { method: 'POST', body: payload }),
};

export const registrationApi = {
  get: (editionId) => api(`/editions/${editionId}/registration`),
  saveProfile: (editionId, payload) =>
    api(`/editions/${editionId}/registration/profile`, { method: 'PUT', body: payload }),
  uploadDocument: (editionId, docType, form) =>
    api(`/editions/${editionId}/registration/documents/${docType}`, {
      method: 'POST',
      form,
    }),
  deleteDocument: (editionId, docType) =>
    api(`/editions/${editionId}/registration/documents/${docType}`, {
      method: 'DELETE',
    }),
  submit: (editionId) =>
    api(`/editions/${editionId}/registration/submit`, { method: 'POST' }),
  verifyPayment: (editionId, payload) =>
    api(`/editions/${editionId}/registration/payment/verify`, {
      method: 'POST',
      body: payload,
    }),
  payment: (editionId, orderId) =>
    api(`/editions/${editionId}/registration/payments/${orderId}`),
  mockPay: (editionId, orderId) =>
    api(`/editions/${editionId}/registration/payments/${orderId}/mock`, {
      method: 'POST',
    }),
  resubmit: (editionId) =>
    api(`/editions/${editionId}/registration/resubmit`, { method: 'POST' }),
  requestCategoryChange: (editionId, payload) =>
    api(`/editions/${editionId}/registration/category-change`, {
      method: 'POST',
      body: payload,
    }),
  categoryChangePayment: (editionId) =>
    api(`/editions/${editionId}/registration/category-change/payment`),
  markNotificationRead: (editionId, id) =>
    api(`/editions/${editionId}/registration/notifications/${id}/read`, {
      method: 'POST',
    }),
  documentUrl: (editionId, documentId, download = false) =>
    `${API_BASE}/editions/${editionId}/registration/documents/${documentId}/content${
      download ? '?download=true' : ''
    }`,
  fetchDocumentBlob: async (editionId, documentId) => {
    const url = `${API_BASE}/editions/${editionId}/registration/documents/${documentId}/content`;
    const res = await fetch(url, { credentials: 'include' });
    if (!res.ok) throw new Error('Could not load document content');
    return res.blob();
  },
  receiptUrl: (editionId) => `${API_BASE}/editions/${editionId}/registration/receipt`,
  qrToken: (editionId) => api(`/editions/${editionId}/registration/qr-token`),
  confirmationUrl: (editionId) =>
    `${API_BASE}/editions/${editionId}/registration/confirmation`,
  passCardUrl: (editionId) => `${API_BASE}/editions/${editionId}/registration/pass-card`,
};

const adminBase = (editionId) => `/editions/${editionId}/admin`;

const registrationAdminBase = (editionId) => `${adminBase(editionId)}/registration`;

export const adminApi = {
  sync: (editionId) => api(`${adminBase(editionId)}/sync`, { method: 'POST' }),
  overview: (editionId) => api(`${adminBase(editionId)}/overview`),
  permissions: (editionId) => api(`${adminBase(editionId)}/my-permissions`),
  settings: (editionId) => api(`${adminBase(editionId)}/settings`),
  updateSettings: (editionId, payload) =>
    api(`${adminBase(editionId)}/settings`, { method: 'PATCH', body: payload }),
  policies: (editionId) => api(`${adminBase(editionId)}/policies`),
  checkPolicy: (editionId, payload) =>
    api(`${adminBase(editionId)}/policies/check`, { method: 'POST', body: payload }),
  createPolicy: (editionId, payload) =>
    api(`${adminBase(editionId)}/policies`, { method: 'POST', body: payload }),
  customCredentials: (editionId) => api(`${adminBase(editionId)}/custom-credentials`),
  createCustomCredential: (editionId, payload) =>
    api(`${adminBase(editionId)}/custom-credentials`, { method: 'POST', body: payload }),
  updateCustomCredential: (editionId, credentialId, payload) =>
    api(`${adminBase(editionId)}/custom-credentials/${credentialId}`, {
      method: 'PATCH',
      body: payload,
    }),
  revokeCustomCredential: (editionId, credentialId, payload = {}) =>
    api(`${adminBase(editionId)}/custom-credentials/${credentialId}/revoke`, {
      method: 'POST',
      body: payload,
    }),
  categories: (editionId) => api(`${adminBase(editionId)}/categories`),
  createCategory: (editionId, payload) =>
    api(`${adminBase(editionId)}/categories`, { method: 'POST', body: payload }),
  updateCategory: (editionId, categoryId, payload) =>
    api(`${adminBase(editionId)}/categories/${categoryId}`, { method: 'PATCH', body: payload }),
  events: (editionId, params = {}) => api(`${adminBase(editionId)}/events${query(params)}`),
  event: (editionId, eventId) => api(`${adminBase(editionId)}/events/${eventId}`),
  createEvent: (editionId, payload) =>
    api(`${adminBase(editionId)}/events`, { method: 'POST', body: payload }),
  updateEvent: (editionId, eventId, payload) =>
    api(`${adminBase(editionId)}/events/${eventId}`, { method: 'PATCH', body: payload }),
  icons: (editionId) => api(`${adminBase(editionId)}/icons`),
  uploadIcon: (editionId, form) =>
    api(`${adminBase(editionId)}/icons`, { method: 'POST', form }),
  uploadBanner: (editionId, form) =>
    api(`${adminBase(editionId)}/banner-upload`, { method: 'POST', form }),
  uploadCredentialPhoto: (editionId, form) =>
    api(`${adminBase(editionId)}/custom-credentials/photo`, { method: 'POST', form }),
  archiveIcon: (editionId, iconId) =>
    api(`${adminBase(editionId)}/icons/${iconId}`, { method: 'DELETE' }),
  users: (editionId, params = {}) => api(`${adminBase(editionId)}/users${query(params)}`),
  setUserStatus: (editionId, userId, payload) =>
    api(`${adminBase(editionId)}/users/${userId}/status`, { method: 'PATCH', body: payload }),
  memberships: (editionId) => api(`${adminBase(editionId)}/memberships`),
  grantMembership: (editionId, payload) =>
    api(`${adminBase(editionId)}/memberships`, { method: 'POST', body: payload }),
  inviteStaff: (editionId, payload) =>
    api(`${adminBase(editionId)}/staff-invites`, { method: 'POST', body: payload }),
  payments: (editionId, params = {}) => api(`${adminBase(editionId)}/payments${query(params)}`),
  refunds: (editionId) => api(`${adminBase(editionId)}/refunds`),
  createRefund: (editionId, payload) =>
    api(`${adminBase(editionId)}/refunds`, { method: 'POST', body: payload }),
  registrations: (editionId, params = {}) =>
    api(`${adminBase(editionId)}/registrations${query(params)}`),
  teams: (editionId, params = {}) =>
    api(`${adminBase(editionId)}/teams${query(params)}`),
  toggleTeamLock: (editionId, teamId) =>
    api(`${adminBase(editionId)}/teams/${teamId}/lock`, { method: 'POST' }),
  disbandTeam: (editionId, teamId) =>
    api(`${adminBase(editionId)}/teams/${teamId}`, { method: 'DELETE' }),
  forceCancelEventRegistration: (editionId, registrationId, payload) =>
    api(`${adminBase(editionId)}/registrations/${registrationId}/force-cancel`, {
      method: 'POST',
      body: payload,
    }),
  approveEventRegistration: (editionId, registrationId) =>
    api(`${adminBase(editionId)}/registrations/${registrationId}/approve`, {
      method: 'POST',
    }),
  refundEventRegistration: (editionId, registrationId, payload) =>
    api(`${adminBase(editionId)}/registrations/${registrationId}/refund`, {
      method: 'POST',
      body: payload,
    }),
  eventRoster: (editionId, eventId, params = {}) =>
    api(`${adminBase(editionId)}/events/${eventId}/roster${query(params)}`),
  markAttendance: (editionId, payload) =>
    api(`${adminBase(editionId)}/attendance/mark`, { method: 'POST', body: payload }),
  deleteAttendance: (editionId, attendanceId) =>
    api(`${adminBase(editionId)}/attendance/${attendanceId}`, { method: 'DELETE' }),
  announcements: (editionId) => api(`${adminBase(editionId)}/announcements`),
  createAnnouncement: (editionId, payload) =>
    api(`${adminBase(editionId)}/announcements`, { method: 'POST', body: payload }),
  updateAnnouncement: (editionId, announcementId, payload) =>
    api(`${adminBase(editionId)}/announcements/${announcementId}`, { method: 'PATCH', body: payload }),
  deleteAnnouncement: (editionId, announcementId) =>
    api(`${adminBase(editionId)}/announcements/${announcementId}`, { method: 'DELETE' }),
  audit: (editionId, params = {}) => api(`${adminBase(editionId)}/audit${query(params)}`),
  dbPlaygroundSeed: (editionId, payload) =>
    api(`${adminBase(editionId)}/db-playground/seed`, { method: 'POST', body: payload }),
  attendance: (editionId, params = {}) =>
    api(`${adminBase(editionId)}/attendance${query(params)}`),
  checkin: (editionId, payload) =>
    api(`${adminBase(editionId)}/checkin`, { method: 'POST', body: payload }),
  recentCheckins: (editionId) => api(`${adminBase(editionId)}/recent-checkins`),
  registrationConfig: (editionId) => api(`${registrationAdminBase(editionId)}/config`),
  updateRegistrationConfig: (editionId, payload) =>
    api(`${registrationAdminBase(editionId)}/config`, { method: 'PATCH', body: payload }),
  collegeRegistrations: (editionId, params = {}) =>
    api(`${registrationAdminBase(editionId)}${query(params)}`),
  collegeRegistration: (editionId, id) =>
    api(`${registrationAdminBase(editionId)}/${id}`),
  addRegistrationNote: (editionId, id, note) =>
    api(`${registrationAdminBase(editionId)}/${id}/notes`, {
      method: 'POST',
      body: { note },
    }),
  updateRegistrationDetails: (editionId, id, payload) =>
    api(`${registrationAdminBase(editionId)}/${id}/details`, {
      method: 'PATCH',
      body: payload,
    }),
  decideRegistration: (editionId, id, payload) =>
    api(`${registrationAdminBase(editionId)}/${id}/decision`, {
      method: 'POST',
      body: payload,
    }),
  requestRegistrationDocuments: (editionId, id, payload) =>
    api(`${registrationAdminBase(editionId)}/${id}/request-documents`, {
      method: 'POST',
      body: payload,
    }),
  refundRegistration: (editionId, id, payload) =>
    api(`${registrationAdminBase(editionId)}/${id}/refund`, {
      method: 'POST',
      body: payload,
    }),
  decideRegistrationCategoryChange: (editionId, id, payload) =>
    api(`${registrationAdminBase(editionId)}/${id}/category-change`, {
      method: 'POST',
      body: payload,
    }),
  registrationDocumentUrl: (editionId, registrationId, documentId, download = false) =>
    `${API_BASE}/editions/${editionId}/admin/registration/${registrationId}/documents/${documentId}/content${
      download ? '?download=true' : ''
    }`,
  fetchRegistrationDocumentBlob: async (editionId, registrationId, documentId) => {
    const url = `${API_BASE}/editions/${editionId}/admin/registration/${registrationId}/documents/${documentId}/content`;
    const res = await fetch(url, { credentials: 'include' });
    if (!res.ok) throw new Error('Could not load document content');
    return res.blob();
  },
};
