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

export const adminGetStats = () => adminRequest('/admin/stats');
export const adminGetFiles = () => adminRequest('/admin/files');
export const adminGetUsers = () => adminRequest('/admin/users');
export const adminGetProjects = () => adminRequest('/admin/projects');
export const adminGetImages = () => adminRequest('/admin/images');
export const adminGetAgents = () => adminRequest('/admin/agents');
export const adminGetLogs = (limit = 100) => adminRequest(`/admin/logs?limit=${limit}`);

export const adminUpdateUserStatus = (userId, isActive) =>
  adminRequest(`/admin/users/${userId}/status`, {
    method: 'PATCH',
    body: { is_active: isActive },
  });

export const adminDeleteProject = (projectId) =>
  adminRequest(`/admin/projects/${projectId}`, { method: 'DELETE' });

export const adminDeleteImage = (imageId) =>
  adminRequest(`/admin/images/${imageId}`, { method: 'DELETE' });
