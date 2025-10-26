/**
 * Chat interface logic and WebSocket handling.
 */

let socket = null;
let currentRun = null;
let mySocketId = null; // Track current user's socket ID

/**
 * Log a message to the chat.
 * @param {string} line - The message text
 * @param {string} cls - CSS class for styling
 * @param {string} sender - Optional sender name to display above the bubble
 */
function log(line, cls = '', sender = null) {
  const wrapper = document.createElement('div');
  wrapper.className = 'msg-wrapper ' + cls;

  // Add sender label for user messages
  if (sender && cls === 'user') {
    const label = document.createElement('div');
    label.className = 'msg-label';
    label.textContent = sender;
    wrapper.appendChild(label);
  }

  // Create message bubble
  const el = document.createElement('div');
  el.className = 'msg ' + cls;
  el.textContent = line;
  wrapper.appendChild(el);

  $('log').appendChild(wrapper);
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
        m.messages.forEach(x => {
          const cls = x.sender === 'assistant' ? 'assistant' : 'user';
          const sender = cls === 'user' ? formatSender(x.sender) : null;
          log(x.text, cls, sender);
        });
        break;

      case 'user.joined':
        setUsers(m.count);
        log(`${m.user.name} joined`, 'meta');
        break;

      case 'user.left':
        setUsers(m.count);
        log('user left', 'meta');
        break;

      case 'message.appended':
        const cls = m.message.sender === 'assistant' ? 'assistant' : 'user';
        const sender = cls === 'user' ? formatSender(m.message.sender) : null;
        log(m.message.text, cls, sender);
        break;

      case 'assistant.started':
        currentRun = m.run.run_id;
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
