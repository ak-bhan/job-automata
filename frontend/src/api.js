/**
 * api.js — All fetch calls to the JobAutomata backend.
 *
 * Every function throws an Error with a human-readable message on non-ok
 * responses, extracting the `detail` field from the JSON body when available.
 */

const BASE = 'http://localhost:8000';

/**
 * Parses a non-ok response and throws a descriptive Error.
 * @param {Response} res
 */
async function handleError(res) {
  let message = `HTTP ${res.status}`;
  try {
    const body = await res.json();
    if (body.detail) {
      message = typeof body.detail === 'string'
        ? body.detail
        : JSON.stringify(body.detail);
    }
  } catch {
    // Could not parse JSON — use status text
    message = res.statusText || message;
  }
  throw new Error(message);
}

/**
 * Fetch the currently saved profile.
 * @returns {Promise<Object>} Profile data object
 */
export async function getProfile() {
  const res = await fetch(`${BASE}/profile`);
  if (!res.ok) await handleError(res);
  return res.json();
}

/**
 * Save or update the user profile.
 * @param {Object} data - Profile fields to save
 * @returns {Promise<Object>} Saved profile data
 */
export async function saveProfile(data) {
  const res = await fetch(`${BASE}/profile`, {
    method: 'PUT',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify(data),
  });
  if (!res.ok) await handleError(res);
  return res.json();
}

/**
 * Upload a resume PDF file.
 * @param {File} file - The PDF file to upload
 * @returns {Promise<{resume_path: string}>} Object containing the saved path
 */
export async function uploadResume(file) {
  const formData = new FormData();
  formData.append('file', file);
  const res = await fetch(`${BASE}/upload-resume`, {
    method: 'POST',
    body: formData,
  });
  if (!res.ok) await handleError(res);
  return res.json();
}

/**
 * Trigger a form fill for the given URL.
 * @param {string} url - The job application URL
 * @returns {Promise<Object>} Fill summary with detected/filled/skipped counts and field details
 */
export async function fillForm(url) {
  const res = await fetch(`${BASE}/fill`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ url }),
  });
  if (!res.ok) await handleError(res);
  return res.json();
}

/**
 * Retrieve fill history logs.
 * @param {number} [limit=20] - Maximum number of log entries to return
 * @returns {Promise<Array>} Array of fill log objects
 */
export async function getLogs(limit = 20) {
  const res = await fetch(`${BASE}/logs?limit=${limit}`);
  if (!res.ok) await handleError(res);
  return res.json();
}
