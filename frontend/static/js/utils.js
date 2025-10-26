/**
 * Utility functions shared across the application.
 */

// DOM helper
const $ = id => document.getElementById(id);

// Backend URL
const BACKEND_DEFAULT = window.location.origin;

/**
 * Make an HTTP request with JSON payload.
 * @param {string} url - The URL to request
 * @param {object} body - The JSON body (optional for GET)
 * @param {string} method - HTTP method (default: POST)
 * @returns {Promise<object>} - The response data
 */
async function postJSON(url, body, method = 'POST') {
  const headers = {'Content-Type': 'application/json'};

  // Add auth token if available
  const token = getToken();
  if (token) {
    headers['Authorization'] = `Bearer ${token}`;
  }

  const options = {
    method: method,
    headers: headers
  };

  // Only add body for non-GET requests
  if (method !== 'GET' && body !== null) {
    options.body = JSON.stringify(body);
  }

  const r = await fetch(url, options);
  const text = await r.text();
  let data;
  try {
    data = JSON.parse(text);
  } catch {
    throw new Error(text);
  }
  if (!r.ok) throw data;
  return data;
}

/**
 * Set a cookie.
 * @param {string} name - Cookie name
 * @param {string} value - Cookie value
 * @param {number} days - Days until expiration (default: 30)
 */
function setCookie(name, value, days = 30) {
  const date = new Date();
  date.setTime(date.getTime() + (days * 24 * 60 * 60 * 1000));
  const expires = `expires=${date.toUTCString()}`;
  // Set cookie with SameSite=Lax for security
  document.cookie = `${name}=${value};${expires};path=/;SameSite=Lax`;
}

/**
 * Get a cookie by name.
 * @param {string} name - Cookie name
 * @returns {string|null} - Cookie value or null
 */
function getCookie(name) {
  const nameEQ = name + "=";
  const ca = document.cookie.split(';');
  for (let i = 0; i < ca.length; i++) {
    let c = ca[i];
    while (c.charAt(0) === ' ') c = c.substring(1, c.length);
    if (c.indexOf(nameEQ) === 0) return c.substring(nameEQ.length, c.length);
  }
  return null;
}

/**
 * Delete a cookie.
 * @param {string} name - Cookie name
 */
function deleteCookie(name) {
  document.cookie = `${name}=;expires=Thu, 01 Jan 1970 00:00:00 UTC;path=/;`;
}

/**
 * Save JWT token to cookie (persistent login).
 * @param {string|null} t - The token to save, or null to remove
 */
function saveToken(t) {
  if (t) {
    // Save to cookie with 30 day expiration
    setCookie('access_token', t, 30);
    // Also keep in localStorage as backup
    localStorage.setItem('access_token', t);
  } else {
    // Remove from both cookie and localStorage
    deleteCookie('access_token');
    localStorage.removeItem('access_token');
  }
}

/**
 * Get JWT token from cookie or localStorage.
 * @returns {string|null} - The token or null
 */
function getToken() {
  // Try cookie first (persistent)
  let token = getCookie('access_token');

  // Fall back to localStorage
  if (!token) {
    token = localStorage.getItem('access_token');
    // If found in localStorage, migrate to cookie
    if (token) {
      setCookie('access_token', token, 30);
    }
  }

  return token;
}

/**
 * Logout user by clearing token and redirecting to login.
 */
function logout() {
  saveToken(null);
  window.location.href = '/login.html';
}
