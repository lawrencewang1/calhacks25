/**
 * Chat interface logic and WebSocket handling.
 */

let socket = null;
let currentRun = null;

/**
 * Log a message to the chat.
 * @param {string} line - The message text
 * @param {string} cls - CSS class for styling
 */
function log(line, cls = '') {
  const el = document.createElement('div');
  el.className = 'msg ' + cls;
  el.textContent = line;
  $('log').appendChild(el);
  $('log').scrollTop = $('log').scrollHeight;
}

/**
 * Format sender name by removing "user:" prefix.
 * @param {string} sender - The sender identifier
 * @returns {string} - Formatted sender name
 */
function formatSender(sender) {
  return sender.startsWith('user:') ? sender.substring(5) : sender;
}

/**
 * Set user count display.
 * @param {number} n - Number of users
 */
function setUsers(n) {
  $('users').textContent = `users: ${n}`;
}

/**
 * Set connection status display.
 * @param {string} t - Status text
 */
function setStatus(t) {
  $('status').textContent = t;
}

/**
 * Update character count display.
 */
function updateCharCount() {
  const text = $('text').value;
  const count = text.length;
  const max = 500;
  const counter = $('charCount');
  counter.textContent = `${count}/${max}`;

  // Change color based on remaining characters
  counter.classList.remove('warning', 'error');
  if (count > max * 0.9) {
    counter.classList.add('error');
  } else if (count > max * 0.7) {
    counter.classList.add('warning');
  }
}

/**
 * Send a message to the chat.
 */
function sendMessage() {
  if (!socket || socket.disconnected) return;
  const t = $('text').value.trim();
  if (!t) return;

  socket.emit('client', {
    type: 'send.message',
    client_msg_id: crypto.randomUUID(),
    text: t
  });

  $('text').value = '';
  updateCharCount();
  $('text').focus();
}

/**
 * Connect to the WebSocket server.
 */
function connectSocket() {
  const token = getToken();
  console.log('Attempting to connect with token:', token ? token.substring(0, 20) + '...' : 'null');

  if (!token) {
    setStatus('not authenticated');
    log('! No access token found. Please login.', 'meta');
    return;
  }

  socket = io(BACKEND_DEFAULT, {
    auth: {token},
    transports: ['websocket', 'polling']
  });

  socket.on('connect', () => {
    console.log('Socket connected successfully');
    setStatus('connected');
  });

  socket.on('disconnect', () => {
    console.log('Socket disconnected');
    setStatus('disconnected');
    setUsers(0);
  });

  socket.on('connect_error', (err) => {
    console.error('Socket connection error:', err);
    setStatus('connection error');
    log(`! Connection error: ${err.message}. Check browser console for details.`, 'meta');
  });

  socket.on('server', m => {
    switch (m.type) {
      case 'room.snapshot':
        setUsers(m.users.length);
        $('log').textContent = '';
        m.messages.forEach(x => log(`${formatSender(x.sender)}> ${x.text}`, x.sender === 'assistant' ? 'assistant' : 'user'));
        break;

      case 'user.joined':
        setUsers(m.count);
        log(`* ${m.user.name} joined`, 'meta');
        break;

      case 'user.left':
        setUsers(m.count);
        log('* user left', 'meta');
        break;

      case 'message.appended':
        log(`${formatSender(m.message.sender)}> ${m.message.text}`, m.message.sender === 'assistant' ? 'assistant' : 'user');
        break;

      case 'assistant.started':
        currentRun = m.run.run_id;
        // Create an empty assistant message element for streaming deltas
        log('assistant> ', 'assistant');
        break;

      case 'assistant.delta':
        const logEl = $('log').lastElementChild;
        if (logEl && logEl.classList.contains('assistant')) {
          logEl.textContent += m.delta;
        }
        break;

      case 'assistant.completed':
        currentRun = null;
        break;

      case 'error':
        log(`! error: ${m.message}`, 'meta');
        break;
    }
  });
}

/**
 * Initialize chat interface.
 */
function initChat() {
  // Show JWT preview
  const token = getToken();
  $('jwtPreview').textContent = token || '(none)';

  // Set up event listeners
  $('send').onclick = sendMessage;
  $('stop').onclick = () => {
    if (!socket || socket.disconnected || !currentRun) return;
    socket.emit('client', {type: 'run.stop', run_id: currentRun});
  };

  $('text').addEventListener('keydown', (e) => {
    if (e.key === 'Enter' && !e.shiftKey) {
      e.preventDefault();
      sendMessage();
    }
  });

  $('text').addEventListener('input', updateCharCount);

  // Initialize
  connectSocket();
  updateCharCount();
}

// Initialize on page load
window.addEventListener('load', initChat);
