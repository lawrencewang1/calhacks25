/**
 * Authentication logic for login and registration.
 */

/**
 * Set authentication message.
 * @param {string} t - The message text
 * @param {boolean} isError - Whether this is an error message
 */
function setAuthMsg(t, isError = false) {
  const el = $('authMsg');
  el.textContent = t || '';
  el.className = isError ? 'meta error' : 'meta';
}

/**
 * Perform login.
 * @returns {Promise<void>}
 */
async function doLogin() {
  const email = $('email').value.trim();
  const password = $('password').value;
  const rememberMe = $('rememberMe') ? $('rememberMe').checked : true;

  if (!email || !password) {
    return setAuthMsg('Email & password required.', true);
  }

  try {
    const j = await postJSON(`${BACKEND_DEFAULT}/api/auth/login`, {email, password});
    const token = j.access_token || j.token;

    if (!token) {
      throw new Error('No access_token');
    }

    // Save token with appropriate duration based on "remember me"
    if (rememberMe) {
      // Save to cookie for 30 days
      setCookie('access_token', token, 30);
      localStorage.setItem('access_token', token);
    } else {
      // Save only to localStorage (session only - will be cleared when browser closes)
      localStorage.setItem('access_token', token);
    }

    setAuthMsg('Logged in. Redirecting...');

    // Redirect to the requested page or default to chat
    setTimeout(() => {
      const urlParams = new URLSearchParams(window.location.search);
      const redirect = urlParams.get('redirect');
      window.location.href = redirect ? decodeURIComponent(redirect) : 'chat.html';
    }, 500);
  } catch (e) {
    setAuthMsg('Login error: ' + e.message, true);
  }
}

/**
 * Perform registration.
 * @returns {Promise<void>}
 */
async function doRegister() {
  const username = $('username').value.trim();
  const email = $('email').value.trim();
  const password = $('password').value;
  const confirmPassword = $('confirmPassword').value;

  if (!username || !email || !password || !confirmPassword) {
    return setAuthMsg('All fields are required.', true);
  }

  if (password !== confirmPassword) {
    return setAuthMsg('Passwords do not match.', true);
  }

  if (password.length < 6) {
    return setAuthMsg('Password must be at least 6 characters with uppercase, lowercase, digit, and special character.', true);
  }

  try {
    console.log('Registering user...');
    const response = await postJSON(`${BACKEND_DEFAULT}/api/auth/register`, {
      name: username,
      email: email,
      password: password
    });

    console.log('Registration response:', response);

    // Automatically log in after successful registration
    const token = response.access_token || response.token;
    console.log('Token from registration:', token ? token.substring(0, 20) + '...' : 'null');

    if (token) {
      saveToken(token);
      console.log('Token saved to localStorage');
      console.log('Verification - token in localStorage:', localStorage.getItem('access_token') ? 'present' : 'missing');
      setAuthMsg('Account created! Redirecting...');
      setTimeout(() => {
        const urlParams = new URLSearchParams(window.location.search);
        const redirect = urlParams.get('redirect');
        window.location.href = redirect ? decodeURIComponent(redirect) : 'chat.html';
      }, 1000);
    } else {
      console.warn('No token received from registration!');
      setAuthMsg('Account created! Redirecting to login...');
      setTimeout(() => {
        const urlParams = new URLSearchParams(window.location.search);
        const redirect = urlParams.get('redirect');
        const loginUrl = redirect ? `login.html?redirect=${encodeURIComponent(redirect)}` : 'login.html';
        window.location.href = loginUrl;
      }, 1000);
    }
  } catch (e) {
    console.error('Registration error:', e);
    setAuthMsg('Registration error: ' + e.message, true);
  }
}
