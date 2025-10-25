/**
 * Utility functions shared across the application.
 */

// DOM helper
const $ = id => document.getElementById(id);

// Backend URL
const BACKEND_DEFAULT = window.location.origin;

/**
 * Make a POST request with JSON payload.
 * @param {string} url - The URL to post to
 * @param {object} body - The JSON body
 * @returns {Promise<object>} - The response data
 */
async function postJSON(url, body) {
  const r = await fetch(url, {
    method: 'POST',
    headers: {'Content-Type': 'application/json'},
    body: JSON.stringify(body)
  });
  const text = await r.text();
  let data;
  try {
    data = JSON.parse(text);
  } catch {
    throw new Error(text);
  }
  if (!r.ok) throw new Error(data.msg || `HTTP ${r.status}`);
  return data;
}

/**
 * Save JWT token to localStorage.
 * @param {string|null} t - The token to save, or null to remove
 */
function saveToken(t) {
  if (t) {
    localStorage.setItem('access_token', t);
  } else {
    localStorage.removeItem('access_token');
  }
}

/**
 * Get JWT token from localStorage.
 * @returns {string|null} - The token or null
 */
function getToken() {
  return localStorage.getItem('access_token');
}
