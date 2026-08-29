const TOKEN_KEY = 'archi_access_token';

function authHeaders(json = false) {
  const token = localStorage.getItem(TOKEN_KEY);
  const h = { Authorization: `Bearer ${token}` };
  if (json) h['Content-Type'] = 'application/json';
  return h;
}

export async function uploadImage(file) {
  const form = new FormData();
  form.append('file', file);
  const res = await fetch('/upload/image', {
    method: 'POST',
    headers: authHeaders(),
    body: form,
  });
  if (!res.ok) {
    const err = await res.json().catch(() => ({}));
    throw new Error(err.detail || `Upload failed: ${res.status}`);
  }
  return res.json();
}

export async function analyzeImage(fileId) {
  const res = await fetch('/analyze/', {
    method: 'POST',
    headers: authHeaders(true),
    body: JSON.stringify({ file_id: fileId }),
  });
  if (!res.ok) {
    const err = await res.json().catch(() => ({}));
    throw new Error(err.detail || `Analysis failed: ${res.status}`);
  }
  return res.json();
}

export async function getHistory() {
  const res = await fetch('/analyze/history', {
    headers: authHeaders(),
  });
  if (!res.ok) {
    const err = await res.json().catch(() => ({}));
    throw new Error(err.detail || `History failed: ${res.status}`);
  }
  return res.json();
}

export async function getMe() {
  const res = await fetch('/auth/me', {
    headers: authHeaders(),
  });
  if (!res.ok) {
    const err = await res.json().catch(() => ({}));
    throw new Error(err.detail || `Profile failed: ${res.status}`);
  }
  return res.json();
}

export async function deleteAccount() {
  const res = await fetch('/auth/account', {
    method: 'DELETE',
    headers: authHeaders(),
  });
  if (!res.ok) {
    const err = await res.json().catch(() => ({}));
    throw new Error(err.detail || `Delete account failed: ${res.status}`);
  }
  return res.json();
}

export async function registerEmail({ email, password, name }) {
  const res = await fetch('/auth/register', {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ email, password, name }),
  });
  if (!res.ok) {
    const err = await res.json().catch(() => ({}));
    throw new Error(err.detail || `Đăng ký thất bại: ${res.status}`);
  }
  return res.json();
}

export async function verifyEmail(token) {
  const res = await fetch('/auth/verify-email', {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ token }),
  });
  if (!res.ok) {
    const err = await res.json().catch(() => ({}));
    throw new Error(err.detail || `Xác minh thất bại: ${res.status}`);
  }
  return res.json();
}

export async function loginEmail({ email, password }) {
  const res = await fetch('/auth/login', {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ email, password }),
  });
  if (!res.ok) {
    const err = await res.json().catch(() => ({}));
    throw new Error(err.detail || `Đăng nhập thất bại: ${res.status}`);
  }
  return res.json();
}

export async function forgotPassword(email) {
  const res = await fetch('/auth/forgot-password', {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ email }),
  });
  if (!res.ok) {
    const err = await res.json().catch(() => ({}));
    throw new Error(err.detail || `Yêu cầu thất bại: ${res.status}`);
  }
  return res.json();
}

export async function resetPassword(token, newPassword) {
  const res = await fetch('/auth/reset-password', {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ token, new_password: newPassword }),
  });
  if (!res.ok) {
    const err = await res.json().catch(() => ({}));
    throw new Error(err.detail || `Đặt lại mật khẩu thất bại: ${res.status}`);
  }
  return res.json();
}

export async function getHistoryDetail(imageId) {
  const res = await fetch(`/analyze/history/${imageId}`, {
    headers: authHeaders(),
  });
  if (!res.ok) {
    const err = await res.json().catch(() => ({}));
    throw new Error(err.detail || `Detail failed: ${res.status}`);
  }
  return res.json();
}

export async function getHistoryImageObjectUrl(imageId) {
  const res = await fetch(`/analyze/image/${imageId}`, {
    headers: authHeaders(),
  });
  if (!res.ok) throw new Error(`Image failed: ${res.status}`);
  const blob = await res.blob();
  return URL.createObjectURL(blob);
}

// ── Knowledge base (style cards) ──────────────────────────────────────────────

export async function getStyleKnowledge(name) {
  const res = await fetch(`/knowledge/style?name=${encodeURIComponent(name)}`, {
    headers: authHeaders(),
  });
  if (!res.ok) {
    const err = await res.json().catch(() => ({}));
    throw new Error(err.detail || `Knowledge lookup failed: ${res.status}`);
  }
  return res.json();
}

export async function getStyleKnowledgeById(styleId) {
  const res = await fetch(`/knowledge/style/${encodeURIComponent(styleId)}`, {
    headers: authHeaders(),
  });
  if (!res.ok) {
    const err = await res.json().catch(() => ({}));
    throw new Error(err.detail || `Knowledge lookup failed: ${res.status}`);
  }
  return res.json();
}

// ── Q&A about a specific analysis ─────────────────────────────────────────────

export async function askAnalysis(imageId, question, history, lang) {
  const res = await fetch(`/analyze/${encodeURIComponent(imageId)}/ask`, {
    method: 'POST',
    headers: authHeaders(true),
    body: JSON.stringify({ question, history, lang }),
  });
  if (!res.ok) {
    const err = await res.json().catch(() => ({}));
    throw new Error(err.detail || `Q&A failed: ${res.status}`);
  }
  return res.json();
}

// ── Billing / token wallet (user) ─────────────────────────────────────────────

async function billingRequest(url, { method = 'GET', body = null } = {}) {
  const opts = { method, headers: authHeaders(body != null) };
  if (body != null) opts.body = JSON.stringify(body);
  const res = await fetch(url, opts);
  if (!res.ok) {
    const err = await res.json().catch(() => ({}));
    throw new Error(err.detail || `Request failed: ${res.status}`);
  }
  return res.json();
}

export const billingGetPlans = () => billingRequest('/billing/plans');
export const billingGetWallet = () => billingRequest('/billing/wallet');
export const billingGetLedger = (limit = 50, offset = 0) =>
  billingRequest(`/billing/ledger?limit=${limit}&offset=${offset}`);
export const billingGetTransactions = (limit = 50, offset = 0) =>
  billingRequest(`/billing/transactions?limit=${limit}&offset=${offset}`);
export const billingCheckout = (planId, idempotencyKey = null) =>
  billingRequest('/billing/checkout', {
    method: 'POST',
    body: { plan_id: planId, idempotency_key: idempotencyKey },
  });
export const billingGetTransactionStatus = (orderRef) =>
  billingRequest(`/billing/transactions/${encodeURIComponent(orderRef)}/status`);

// ── Admin endpoints ─────────────────────────────────────────────────────────
// Thin wrappers over the protected /admin API. All require an admin JWT.

async function adminRequest(url, { method = 'GET', body = null } = {}) {
  const opts = { method, headers: authHeaders(body != null) };
  if (body != null) opts.body = JSON.stringify(body);
  const res = await fetch(url, opts);
  if (!res.ok) {
    const err = await res.json().catch(() => ({}));
    throw new Error(err.detail || `Request failed: ${res.status}`);
  }
  return res.json();
}

// Fetch protected binary content (image bytes) and return an object URL.
async function adminObjectUrl(url) {
  const res = await fetch(url, { headers: authHeaders() });
  if (!res.ok) throw new Error(`Image failed: ${res.status}`);
  const blob = await res.blob();
  return URL.createObjectURL(blob);
}

export const adminGetStats = () => adminRequest('/admin/stats');
export const adminGetFiles = () => adminRequest('/admin/files');
export const adminGetUsers = () => adminRequest('/admin/users');
export const adminGetProjects = () => adminRequest('/admin/projects');
export const adminGetProjectDetail = (projectId) => adminRequest(`/admin/projects/${projectId}`);
export const adminGetImages = () => adminRequest('/admin/images');
export const adminGetImageDetail = (imageId) => adminRequest(`/admin/images/${imageId}`);
export const adminGetImageRaw = (imageId) => adminObjectUrl(`/admin/images/${imageId}/raw`);
export const adminGetFileRaw = (fileId) => adminObjectUrl(`/admin/files/${fileId}/raw`);
export const adminGetAgents = () => adminRequest('/admin/agents');
export const adminGetLogs = (limit = 200, level = null) =>
  adminRequest(`/admin/logs?limit=${limit}${level ? `&level=${level}` : ''}`);

export const adminUpdateUserStatus = (userId, isActive) =>
  adminRequest(`/admin/users/${userId}/status`, {
    method: 'PATCH',
    body: { is_active: isActive },
  });

export const adminRenameProject = (projectId, projectName) =>
  adminRequest(`/admin/projects/${projectId}/name`, {
    method: 'PATCH',
    body: { project_name: projectName },
  });

export const adminDeleteProject = (projectId) =>
  adminRequest(`/admin/projects/${projectId}`, { method: 'DELETE' });

export const adminDeleteImage = (imageId) =>
  adminRequest(`/admin/images/${imageId}`, { method: 'DELETE' });

export const adminDeleteFile = (fileId) =>
  adminRequest(`/admin/files/${fileId}`, { method: 'DELETE' });

// ── Knowledge Base management (admin) ────────────────────────────────────────

export const adminKbListStyles = () => adminRequest('/admin/kb/styles');
export const adminKbGetStyle = (id) => adminRequest(`/admin/kb/styles/${id}`);
export const adminKbCreateStyle = (body) =>
  adminRequest('/admin/kb/styles', { method: 'POST', body });
export const adminKbUpdateStyle = (id, body) =>
  adminRequest(`/admin/kb/styles/${id}`, { method: 'PUT', body });
export const adminKbDeleteStyle = (id) =>
  adminRequest(`/admin/kb/styles/${id}`, { method: 'DELETE' });

export const adminKbListFamilies = () => adminRequest('/admin/kb/families');
export const adminKbCreateFamily = (id, name) =>
  adminRequest('/admin/kb/families', { method: 'POST', body: { id, name } });
export const adminKbRenameFamily = (id, name) =>
  adminRequest(`/admin/kb/families/${id}`, { method: 'PUT', body: { name } });
export const adminKbDeleteFamily = (id) =>
  adminRequest(`/admin/kb/families/${id}`, { method: 'DELETE' });

export const adminKbListSuggestions = () => adminRequest('/admin/kb/suggestions');
export const adminKbDismissSuggestion = (name) =>
  adminRequest(`/admin/kb/suggestions/${encodeURIComponent(name)}`, { method: 'DELETE' });

// ── Admin billing / revenue ───────────────────────────────────────────────────

export const adminGetRevenue = (granularity = 'day', dateFrom = null, dateTo = null) => {
  const p = new URLSearchParams({ granularity });
  if (dateFrom) p.set('date_from', dateFrom);
  if (dateTo) p.set('date_to', dateTo);
  return adminRequest(`/admin/revenue?${p.toString()}`);
};
export const adminGetRevenueByUser = (userIds = [], granularity = 'month') => {
  const p = new URLSearchParams({ granularity, user_ids: userIds.join(',') });
  return adminRequest(`/admin/revenue/by-user?${p.toString()}`);
};
export const adminGetTopSpenders = (limit = 10) =>
  adminRequest(`/admin/top-spenders?limit=${limit}`);
export const adminGetTransactions = (statusFilter = null, limit = 100) =>
  adminRequest(`/admin/transactions?limit=${limit}${statusFilter ? `&status=${statusFilter}` : ''}`);
export const adminGetBillingPlans = () => adminRequest('/admin/plans');
export const adminCreatePlan = (body) => adminRequest('/admin/plans', { method: 'POST', body });
export const adminUpdatePlan = (planId, body) =>
  adminRequest(`/admin/plans/${planId}`, { method: 'PATCH', body });
export const adminDeactivatePlan = (planId) =>
  adminRequest(`/admin/plans/${planId}`, { method: 'DELETE' });
export const adminAdjustTokens = (userId, delta, reason) =>
  adminRequest(`/admin/users/${userId}/token-adjustment`, {
    method: 'POST',
    body: { delta, reason },
  });
export const adminRefundTransaction = (transactionId, body) =>
  adminRequest(`/admin/transactions/${transactionId}/refund`, { method: 'POST', body });
export const adminReconcilePayments = () => adminRequest('/admin/reconcile', { method: 'POST' });

// ── Provider API-key management (admin) ───────────────────────────────────────

export const adminGetApiKeys = () => adminRequest('/admin/api-keys');
export const adminGetApiKeyProviders = () => adminRequest('/admin/api-keys/providers');
export const adminCreateApiKey = (body) =>
  adminRequest('/admin/api-keys', { method: 'POST', body });
export const adminUpdateApiKey = (keyId, body) =>
  adminRequest(`/admin/api-keys/${keyId}`, { method: 'PUT', body });
export const adminToggleApiKey = (keyId, isActive) =>
  adminRequest(`/admin/api-keys/${keyId}/toggle`, { method: 'PATCH', body: { is_active: isActive } });
export const adminDeleteApiKey = (keyId) =>
  adminRequest(`/admin/api-keys/${keyId}`, { method: 'DELETE' });
export const adminTestApiKey = (body) =>
  adminRequest('/admin/api-keys/test', { method: 'POST', body });
export const adminTestStoredApiKey = (keyId) =>
  adminRequest(`/admin/api-keys/${keyId}/test`, { method: 'POST' });

// ── Website CMS (admin) ───────────────────────────────────────────────────────

export const adminGetCmsDraft = (page) => adminRequest(`/admin/cms/${page}/draft`);
export const adminSaveCmsDraft = (page, content, baseRevisionNo = null) =>
  adminRequest(`/admin/cms/${page}/draft`, {
    method: 'PUT',
    body: { content, base_revision_no: baseRevisionNo },
  });
export const adminPublishCms = (page) =>
  adminRequest(`/admin/cms/${page}/publish`, { method: 'POST' });
export const adminGetCmsRevisions = (page) => adminRequest(`/admin/cms/${page}/revisions`);
export const adminRestoreCms = (page, revisionNo) =>
  adminRequest(`/admin/cms/${page}/restore/${revisionNo}`, { method: 'POST' });

// ── Public website content (no auth) ──────────────────────────────────────────

export async function getPublishedContent(page) {
  try {
    // Always revalidate so a just-published change shows up immediately.
    const res = await fetch(`/content/${page}`, { cache: 'no-cache' });
    if (!res.ok) return null;
    return res.json();
  } catch {
    return null; // best-effort: fall back to hardcoded defaults
  }
}

export async function getCmsDraftContent(page) {
  // Preview mode: fetch the admin draft (requires admin JWT). Best-effort.
  try {
    const res = await fetch(`/admin/cms/${page}/draft`, { headers: authHeaders() });
    if (!res.ok) return null;
    return res.json();
  } catch {
    return null;
  }
}
