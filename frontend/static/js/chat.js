/**
 * Multi-room chat interface logic and WebSocket handling.
 */

let socket = null;
let currentRun = null;
let mySocketId = null; // Track current user's socket ID
let myMessageIds = new Set(); // Track IDs of messages we sent
let currentRoomId = null; // Track current room
let officialRooms = []; // List of official rooms
let communityRooms = []; // List of community rooms
let myRooms = []; // List of user's own rooms
let savedRooms = []; // List of saved rooms
let currentUserId = null; // Current user's ID
let lastShownTimestamp = null; // Track last timestamp that was shown
let lastMessageSender = null; // Track last message sender
let lastMessageTimestamp = null; // Track last message timestamp
const TIMESTAMP_THRESHOLD = 5 * 60 * 1000; // 5 minutes in milliseconds
let dmMessages = []; // Store DM messages
let dmLastSender = null; // Track last sender in DM
let dmLastTimestamp = null; // Track last timestamp in DM
let roomIdFromUrl = null; // Room ID from URL parameter
let currentMembers = []; // Current room members
let currentRoomOwnerId = null; // Current room owner ID
let selectedUserId = null; // Selected user for modal
let selectedUserName = null; // Selected user name for modal
let contextMenuRoom = null; // Room data for context menu
let contextMenuType = null; // Type of room list (my/saved/etc)

// Connection retry state
let retryAttempt = 0; // Current retry attempt
let maxRetries = 10; // Maximum retry attempts
let retryTimeout = null; // Retry timeout handle
let isManualDisconnect = false; // Flag for intentional disconnects

/**
 * Get URL parameter by name.
 * @param {string} name - Parameter name
 * @returns {string|null} - Parameter value or null
 */
function getUrlParameter(name) {
  const urlParams = new URLSearchParams(window.location.search);
  return urlParams.get(name);
}

/**
 * Update URL with room parameter without reloading page.
 * @param {string} roomId - The room ID
 */
function updateUrlWithRoom(roomId) {
  const url = new URL(window.location);
  if (roomId) {
    url.searchParams.set('room', roomId);
  } else {
    url.searchParams.delete('room');
  }
  window.history.pushState({}, '', url);
}

/**
 * Toggle member list sidebar.
 */
function toggleMemberList() {
  const sidebar = $('memberSidebar');
  sidebar.classList.toggle('hidden');
}

/**
 * Update member list display.
 * @param {Array} members - Array of member objects {id, name}
 * @param {string} ownerId - Room owner's user ID
 */
function updateMemberList(members, ownerId) {
  currentMembers = members || [];
  currentRoomOwnerId = ownerId;

  // Show/hide view bans button based on ownership
  const viewBansBtn = $('viewBansBtn');
  if (currentUserId && ownerId && String(currentUserId) === String(ownerId)) {
    viewBansBtn.style.display = 'flex';
  } else {
    viewBansBtn.style.display = 'none';
  }

  const memberList = $('memberList');
  const memberCount = $('memberCount');

  memberList.innerHTML = '';
  memberCount.textContent = members.length;

  if (members.length === 0) {
    const empty = document.createElement('div');
    empty.className = 'member-list-empty';
    empty.textContent = 'No members';
    memberList.appendChild(empty);
    return;
  }

  members.forEach(member => {
    const memberEl = document.createElement('div');
    memberEl.className = 'member-item';

    // Check if this member is the room owner
    const isOwner = member.user_id && ownerId && String(member.user_id) === String(ownerId);
    if (isOwner) {
      memberEl.classList.add('is-owner');
    }

    // Avatar
    const avatar = document.createElement('div');
    avatar.className = 'member-avatar';
    avatar.textContent = (member.name || 'U').charAt(0).toUpperCase();
    memberEl.appendChild(avatar);

    // Info
    const info = document.createElement('div');
    info.className = 'member-info';

    const nameEl = document.createElement('div');
    nameEl.className = 'member-name';
    nameEl.textContent = member.name || 'Anonymous';

    if (isOwner) {
      const badge = document.createElement('span');
      badge.className = 'member-badge';
      badge.textContent = 'OWNER';
      nameEl.appendChild(document.createTextNode(' '));
      nameEl.appendChild(badge);
    }

    info.appendChild(nameEl);
    memberEl.appendChild(info);

    // Click to show user modal (only if not yourself and you're the owner)
    if (member.user_id && currentUserId && String(member.user_id) !== String(currentUserId) &&
        String(currentUserId) === String(currentRoomOwnerId)) {
      memberEl.classList.add('clickable');
      memberEl.addEventListener('click', () => {
        showUserModal(member.user_id, member.name);
      });
    }

    memberList.appendChild(memberEl);
  });
}

/**
 * Show user management modal.
 * @param {string} userId - User ID
 * @param {string} userName - User name
 */
function showUserModal(userId, userName) {
  selectedUserId = userId;
  selectedUserName = userName;
  $('userModalName').textContent = userName;
  $('userModal').classList.remove('hidden');
}

/**
 * Hide user management modal.
 */
function hideUserModal() {
  $('userModal').classList.add('hidden');
  selectedUserId = null;
  selectedUserName = null;
}

/**
 * Kick user from room.
 */
function kickUser() {
  if (!selectedUserId || !currentRoomId) return;

  if (!confirm(`Kick ${selectedUserName} from this room?`)) {
    return;
  }

  socket.emit('client', {
    type: 'user.kick',
    room_id: currentRoomId,
    target_user_id: selectedUserId
  });

  hideUserModal();
}

/**
 * Temporarily ban user from room (24 hours).
 */
function tempBanUser() {
  if (!selectedUserId || !currentRoomId) return;

  // Get custom duration from the picker
  const durationValue = parseInt($('banDuration').value) || 24;
  const durationUnit = $('banDurationUnit').value;

  // Convert to milliseconds
  let durationMs;
  if (durationUnit === 'days') {
    durationMs = durationValue * 24 * 60 * 60 * 1000;
  } else {
    durationMs = durationValue * 60 * 60 * 1000;
  }

  // Create readable duration string
  const durationStr = `${durationValue} ${durationUnit}`;

  if (!confirm(`Temporarily ban ${selectedUserName} for ${durationStr}?`)) {
    return;
  }

  socket.emit('client', {
    type: 'user.tempban',
    room_id: currentRoomId,
    target_user_id: selectedUserId,
    duration: durationMs
  });

  hideUserModal();
}

/**
 * Permanently ban user from room.
 */
function banUser() {
  if (!selectedUserId || !currentRoomId) return;

  if (!confirm(`Permanently ban ${selectedUserName} from this room?`)) {
    return;
  }

  socket.emit('client', {
    type: 'user.ban',
    room_id: currentRoomId,
    target_user_id: selectedUserId
  });

  hideUserModal();
}

/**
 * Show ban list modal.
 */
function showBanList() {
  if (!currentRoomId) return;

  // Request ban list from server
  socket.emit('client', {
    type: 'user.bans.list',
    room_id: currentRoomId
  });

  // Show modal
  $('banListModal').classList.remove('hidden');
}

/**
 * Hide ban list modal.
 */
function hideBanList() {
  $('banListModal').classList.add('hidden');
}

/**
 * Update ban list display.
 * @param {Array} bans - Array of ban objects
 */
function updateBanList(bans) {
  const banListContent = $('banListContent');

  if (!bans || bans.length === 0) {
    banListContent.innerHTML = '<div class="ban-list-empty">No active bans</div>';
    return;
  }

  banListContent.innerHTML = '';

  bans.forEach(ban => {
    const banItem = document.createElement('div');
    banItem.className = 'ban-item';

    // Ban info section
    const infoDiv = document.createElement('div');
    infoDiv.className = 'ban-item-info';

    const userDiv = document.createElement('div');
    userDiv.className = 'ban-item-user';
    userDiv.textContent = ban.banned_user_name || `User ${ban.user_id}`;

    const detailsDiv = document.createElement('div');
    detailsDiv.className = 'ban-item-details';

    // Format ban type and expiration
    let banTypeText;
    if (ban.expires_at) {
      const expiresDate = new Date(ban.expires_at);
      const now = new Date();
      const hoursLeft = Math.ceil((expiresDate - now) / (1000 * 60 * 60));
      banTypeText = `<span class="temporary">Temporary ban</span> - expires in ${hoursLeft}h`;
    } else {
      banTypeText = '<span class="permanent">Permanent ban</span>';
    }

    const bannedBy = ban.banned_by_name || `User ${ban.banned_by}`;
    const bannedAt = new Date(ban.banned_at).toLocaleString();

    detailsDiv.innerHTML = `
      ${banTypeText}<br>
      Banned by: ${bannedBy}<br>
      Banned at: ${bannedAt}
    `;

    infoDiv.appendChild(userDiv);
    infoDiv.appendChild(detailsDiv);

    // Actions section
    const actionsDiv = document.createElement('div');
    actionsDiv.className = 'ban-item-actions';

    const unbanBtn = document.createElement('button');
    unbanBtn.className = 'unban-btn';
    unbanBtn.textContent = 'Unban';
    unbanBtn.onclick = () => unbanUser(ban.id, ban.user_id, ban.banned_user_name);

    actionsDiv.appendChild(unbanBtn);

    banItem.appendChild(infoDiv);
    banItem.appendChild(actionsDiv);

    banListContent.appendChild(banItem);
  });
}

/**
 * Unban a user.
 * @param {number} banId - Ban ID
 * @param {number} userId - User ID
 * @param {string} userName - User name
 */
function unbanUser(banId, userId, userName) {
  if (!currentRoomId) return;

  if (!confirm(`Unban ${userName || `User ${userId}`}?`)) {
    return;
  }

  socket.emit('client', {
    type: 'user.unban',
    room_id: currentRoomId,
    ban_id: banId,
    target_user_id: userId
  });
}

/**
 * Copy room link to clipboard.
 * @param {string} roomId - The room ID
 * @param {string} roomName - The room name
 */
function copyRoomLink(roomId, roomName) {
  const url = new URL(window.location.origin + window.location.pathname);
  url.searchParams.set('room', roomId);

  navigator.clipboard.writeText(url.toString()).then(() => {
    log(`✓ Link copied for "${roomName}"`, 'meta');

    // Visual feedback - could add a toast notification here
    console.log('Room link copied:', url.toString());
  }).catch(err => {
    console.error('Failed to copy link:', err);
    log('! Failed to copy link', 'meta');
  });
}

/**
 * Show context menu for a room.
 * @param {Event} e - The mouse event
 * @param {Object} room - Room object
 * @param {string} roomType - Type of room list ('my', 'saved', etc.)
 */
function showRoomContextMenu(e, room, roomType) {
  e.preventDefault();
  e.stopPropagation();

  const menu = $('roomContextMenu');
  const deleteItem = menu.querySelector('[data-action="delete"]');
  const unsaveItem = menu.querySelector('[data-action="unsave"]');

  // Store room data for later use
  contextMenuRoom = room;
  contextMenuType = roomType;

  // Show/hide options based on room type
  deleteItem.style.display = roomType === 'my' ? 'block' : 'none';
  unsaveItem.style.display = roomType === 'saved' ? 'block' : 'none';

  // Position the menu at mouse cursor
  menu.style.left = e.pageX + 'px';
  menu.style.top = e.pageY + 'px';
  menu.classList.add('visible');

  // Adjust position if menu goes off screen
  setTimeout(() => {
    const rect = menu.getBoundingClientRect();
    if (rect.right > window.innerWidth) {
      menu.style.left = (e.pageX - rect.width) + 'px';
    }
    if (rect.bottom > window.innerHeight) {
      menu.style.top = (e.pageY - rect.height) + 'px';
    }
  }, 0);
}

/**
 * Hide the context menu.
 */
function hideRoomContextMenu() {
  const menu = $('roomContextMenu');
  menu.classList.remove('visible');
  contextMenuRoom = null;
  contextMenuType = null;
}

/**
 * Handle context menu item clicks.
 * @param {string} action - The action to perform
 */
function handleContextMenuAction(action) {
  if (!contextMenuRoom) return;

  switch (action) {
    case 'copy':
      copyRoomLink(contextMenuRoom.id, contextMenuRoom.name);
      break;
    case 'delete':
      deleteRoom(contextMenuRoom.id, contextMenuRoom.name);
      break;
    case 'unsave':
      unsaveRoom(contextMenuRoom.id, contextMenuRoom.name);
      break;
  }

  hideRoomContextMenu();
}

/**
 * Format timestamp to a readable format.
 * @param {number} ts - Timestamp in milliseconds
 * @returns {string} - Formatted time string
 */
function formatTimestamp(ts) {
  const date = new Date(ts);
  const now = new Date();
  const isToday = date.toDateString() === now.toDateString();

  const timeStr = date.toLocaleTimeString('en-US', {
    hour: 'numeric',
    minute: '2-digit',
    hour12: true
  });

  if (isToday) {
    return timeStr;
  } else {
    const dateStr = date.toLocaleDateString('en-US', {
      month: 'short',
      day: 'numeric'
    });
    return `${dateStr} ${timeStr}`;
  }
}

/**
 * Log a message to the chat.
 * @param {string} line - The message text
 * @param {string} cls - CSS class for styling (user/other/assistant/meta)
 * @param {string} sender - Optional sender name to display above the bubble
 * @param {number} ts - Optional timestamp in milliseconds
 */
function log(line, cls = '', sender = null, ts = null) {
  const wrapper = document.createElement('div');
  wrapper.className = 'msg-wrapper ' + cls;

  // Determine if we should show the sender label
  // Show if: sender is provided AND (different sender OR 5+ minutes since last message OR first message)
  let shouldShowSender = false;
  if (sender && cls !== 'meta') {
    const senderKey = `${cls}:${sender}`; // Include class to differentiate user/other/assistant

    // Check if sender changed
    const senderChanged = lastMessageSender !== senderKey;

    // Check if 5+ minutes passed since last message
    const timeSinceLastMessage = (lastMessageTimestamp && ts) ? (ts - lastMessageTimestamp) : Infinity;
    const timeThresholdPassed = timeSinceLastMessage >= TIMESTAMP_THRESHOLD;

    // Show sender if: no previous sender, sender changed, or time threshold passed
    if (!lastMessageSender || senderChanged || timeThresholdPassed) {
      shouldShowSender = true;
    }

    lastMessageSender = senderKey;
  }

  // Add sender label with timestamp whenever we show the sender
  if (shouldShowSender && sender) {
    const label = document.createElement('div');
    label.className = 'msg-label';

    const senderName = document.createElement('span');
    senderName.className = 'msg-sender-name';
    // Display "Assistant" for assistant, otherwise show sender name
    senderName.textContent = cls === 'assistant' ? 'Assistant' : sender;
    label.appendChild(senderName);

    // Always add timestamp when showing sender name
    if (ts) {
      const timestampSpan = document.createElement('span');
      timestampSpan.className = 'msg-label-timestamp';
      timestampSpan.textContent = formatTimestamp(ts);
      label.appendChild(timestampSpan);
    }

    wrapper.appendChild(label);
  }

  // Create message bubble
  const el = document.createElement('div');
  el.className = 'msg ' + cls;
  el.textContent = line;

  // Store timestamp on the element for hover display
  if (ts && cls !== 'meta') {
    el.setAttribute('data-timestamp', ts);

    // Create custom tooltip
    const tooltip = document.createElement('div');
    tooltip.className = 'msg-tooltip';
    tooltip.textContent = formatTimestamp(ts);
    wrapper.appendChild(tooltip);

    // Show/hide tooltip on hover
    el.addEventListener('mouseenter', (e) => {
      tooltip.classList.add('visible');
    });
    el.addEventListener('mouseleave', (e) => {
      tooltip.classList.remove('visible');
    });
  }

  wrapper.appendChild(el);

  // Update last message timestamp AFTER processing
  if (ts && cls !== 'meta') {
    lastMessageTimestamp = ts;
  }

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
 * Update DM character count display.
 */
function updateDmCharCount() {
  const text = $('dmText').value;
  const count = text.length;
  const max = 500;
  const counter = $('dmCharCount');
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
 * Log a message to the DM window.
 * @param {string} line - The message text
 * @param {string} cls - CSS class for styling (user/assistant)
 * @param {string} sender - Sender name
 * @param {number} ts - Timestamp in milliseconds
 */
function logDm(line, cls = '', sender = null, ts = null) {
  const wrapper = document.createElement('div');
  wrapper.className = 'msg-wrapper ' + cls;

  // Determine if we should show the sender label
  let shouldShowSender = false;
  if (sender && cls !== 'meta') {
    const senderKey = `${cls}:${sender}`;
    const senderChanged = dmLastSender !== senderKey;
    const timeSinceLastMessage = (dmLastTimestamp && ts) ? (ts - dmLastTimestamp) : Infinity;
    const timeThresholdPassed = timeSinceLastMessage >= TIMESTAMP_THRESHOLD;

    if (!dmLastSender || senderChanged || timeThresholdPassed) {
      shouldShowSender = true;
    }

    dmLastSender = senderKey;
  }

  // Add sender label with timestamp
  if (shouldShowSender && sender) {
    const label = document.createElement('div');
    label.className = 'msg-label';

    const senderName = document.createElement('span');
    senderName.className = 'msg-sender-name';
    senderName.textContent = cls === 'assistant' ? 'Assistant' : sender;
    label.appendChild(senderName);

    if (ts) {
      const timestampSpan = document.createElement('span');
      timestampSpan.className = 'msg-label-timestamp';
      timestampSpan.textContent = formatTimestamp(ts);
      label.appendChild(timestampSpan);
    }

    wrapper.appendChild(label);
  }

  // Create message bubble
  const el = document.createElement('div');
  el.className = 'msg ' + cls;
  el.textContent = line;

  // Store timestamp for hover display
  if (ts && cls !== 'meta') {
    el.setAttribute('data-timestamp', ts);

    const tooltip = document.createElement('div');
    tooltip.className = 'msg-tooltip';
    tooltip.textContent = formatTimestamp(ts);
    wrapper.appendChild(tooltip);

    el.addEventListener('mouseenter', () => {
      tooltip.classList.add('visible');
    });
    el.addEventListener('mouseleave', () => {
      tooltip.classList.remove('visible');
    });
  }

  wrapper.appendChild(el);

  // Update last message timestamp
  if (ts && cls !== 'meta') {
    dmLastTimestamp = ts;
  }

  $('dmLog').appendChild(wrapper);
  $('dmLog').scrollTop = $('dmLog').scrollHeight;
}

/**
 * Show the DM modal and load history.
 */
function showDmModal() {
  $('dmModal').classList.remove('hidden');
  $('dmText').value = '';
  updateDmCharCount();

  // Request DM history from server
  if (socket && !socket.disconnected) {
    socket.emit('client', { type: 'load.dm_history' });
  }

  // Focus on input
  setTimeout(() => $('dmText').focus(), 100);
}

/**
 * Hide the DM modal.
 */
function hideDmModal() {
  $('dmModal').classList.add('hidden');
}

/**
 * Send a DM to the bot.
 */
function sendDm() {
  if (!socket || socket.disconnected) {
    logDm('! Not connected to server', 'meta');
    return;
  }

  const t = $('dmText').value.trim();
  if (!t) return;

  const msgId = crypto.randomUUID();

  socket.emit('client', {
    type: 'send.dm',
    client_msg_id: msgId,
    text: t
  });

  $('dmText').value = '';
  updateDmCharCount();
  $('dmText').focus();
}

/**
 * Update the room list display.
 * @param {Array} official - List of official room objects
 * @param {Array} community - List of community room objects
 * @param {Array} my - List of user's own room objects
 */
function updateRoomList(official, community, my, saved) {
  officialRooms = official || [];
  communityRooms = community || [];
  myRooms = my || [];
  savedRooms = saved || [];

  // Update official rooms
  const officialList = $('officialRoomList');
  officialList.innerHTML = '';

  if (officialRooms.length === 0) {
    const empty = document.createElement('div');
    empty.className = 'room-list-empty';
    empty.textContent = 'No official rooms';
    officialList.appendChild(empty);
  } else {
    officialRooms.forEach(room => {
      const roomEl = createRoomElement(room, 'official');
      officialList.appendChild(roomEl);
    });
  }

  // Update community rooms
  const communityList = $('communityRoomList');
  communityList.innerHTML = '';

  if (communityRooms.length === 0) {
    const empty = document.createElement('div');
    empty.className = 'room-list-empty';
    empty.textContent = 'No community rooms';
    communityList.appendChild(empty);
  } else {
    communityRooms.forEach(room => {
      const roomEl = createRoomElement(room, 'community');
      communityList.appendChild(roomEl);
    });
  }

  // Update my rooms
  const myRoomsList = $('myRoomList');
  myRoomsList.innerHTML = '';

  if (myRooms.length === 0) {
    const empty = document.createElement('div');
    empty.className = 'room-list-empty';
    empty.textContent = 'No rooms created yet';
    myRoomsList.appendChild(empty);
  } else {
    myRooms.forEach(room => {
      const roomEl = createRoomElement(room, 'my');
      myRoomsList.appendChild(roomEl);
    });
  }

  // Update saved rooms
  const savedRoomsList = $('savedRoomList');
  savedRoomsList.innerHTML = '';

  if (savedRooms.length === 0) {
    const empty = document.createElement('div');
    empty.className = 'room-list-empty';
    empty.textContent = 'No saved rooms yet';
    savedRoomsList.appendChild(empty);
  } else {
    savedRooms.forEach(room => {
      const roomEl = createRoomElement(room, 'saved');
      savedRoomsList.appendChild(roomEl);
    });
  }
}

/**
 * Create a room element for the sidebar.
 * @param {Object} room - Room object
 * @param {string} roomType - Type of room list ('official', 'community', 'my', 'saved')
 * @returns {HTMLElement} - Room element
 */
function createRoomElement(room, roomType = 'community') {
  const roomEl = document.createElement('div');
  roomEl.className = 'room-item';
  if (room.id === currentRoomId) {
    roomEl.classList.add('active');
  }

  const roomContent = document.createElement('div');
  roomContent.className = 'room-content';

  const roomName = document.createElement('div');
  roomName.className = 'room-name';
  roomName.textContent = room.name;

  // Add badge for official rooms
  if (room.is_official) {
    const badge = document.createElement('span');
    badge.className = 'room-badge official';
    badge.textContent = 'OFFICIAL';
    roomName.appendChild(badge);
  }

  // Add badge for private rooms
  if (!room.is_public && !room.is_official) {
    const badge = document.createElement('span');
    badge.className = 'room-badge private';
    badge.textContent = 'PRIVATE';
    roomName.appendChild(badge);
  }

  roomContent.appendChild(roomName);
  roomEl.appendChild(roomContent);

  // Add click handler for joining room
  roomEl.addEventListener('click', () => joinRoom(room.id, room.name));

  // Add right-click handler for context menu
  roomEl.addEventListener('contextmenu', (e) => showRoomContextMenu(e, room, roomType));

  return roomEl;
}

/**
 * Delete a room.
 * @param {string} roomId - The room ID to delete
 * @param {string} roomName - The room name
 */
function deleteRoom(roomId, roomName) {
  if (!confirm(`Are you sure you want to delete the room "${roomName}"?`)) {
    return;
  }

  if (!socket || socket.disconnected) {
    log('! Not connected to server', 'meta');
    return;
  }

  console.log('Deleting room:', roomId);
  socket.emit('client', {
    type: 'room.delete',
    room_id: roomId
  });
}

/**
 * Remove a room from saved list.
 * @param {string} roomId - The room ID
 * @param {string} roomName - The room name
 */
function unsaveRoom(roomId, roomName) {
  if (!confirm(`Remove "${roomName}" from saved rooms?`)) {
    return;
  }

  if (!socket || socket.disconnected) {
    log('! Not connected to server', 'meta');
    return;
  }

  console.log('Unsaving room:', roomId);
  socket.emit('client', {
    type: 'room.unsave',
    room_id: roomId
  });
}

/**
 * Join a specific room.
 * @param {string} roomId - The room ID to join
 * @param {string} roomName - The room name
 */
function joinRoom(roomId, roomName) {
  if (!socket || socket.disconnected) {
    log('! Not connected to server', 'meta');
    return;
  }

  if (currentRoomId === roomId) {
    return; // Already in this room
  }

  console.log('Joining room:', roomId, roomName);
  currentRoomId = roomId;
  $('currentRoomName').textContent = roomName;

  // Update URL with room parameter
  updateUrlWithRoom(roomId);

  // Clear current messages
  $('log').innerHTML = '';

  // Send join request
  socket.emit('client', {
    type: 'room.join',
    room_id: roomId
  });

  // Update room list display
  updateRoomList(officialRooms, communityRooms, myRooms, savedRooms);
}

/**
 * Show the create room modal.
 */
function showCreateRoomModal() {
  $('roomModal').classList.remove('hidden');
  $('roomNameInput').value = '';
  $('roomNameInput').focus();
}

/**
 * Hide the create room modal.
 */
function hideCreateRoomModal() {
  $('roomModal').classList.add('hidden');
}

/**
 * Create a new room.
 */
function createRoom() {
  const roomName = $('roomNameInput').value.trim();
  const isPublic = $('roomPublicCheckbox').checked;

  if (!roomName) {
    return;
  }

  if (!socket || socket.disconnected) {
    log('! Not connected to server', 'meta');
    return;
  }

  console.log('Creating room:', roomName, 'Public:', isPublic);
  socket.emit('client', {
    type: 'room.create',
    room_name: roomName,
    is_public: isPublic
  });

  hideCreateRoomModal();
}

/**
 * Send a message to the chat.
 */
function sendMessage() {
  if (!socket || socket.disconnected) return;
  if (!currentRoomId) {
    log('! Please join a room first', 'meta');
    return;
  }

  const t = $('text').value.trim();
  if (!t) return;

  const msgId = crypto.randomUUID();
  myMessageIds.add(msgId); // Track this as our message

  socket.emit('client', {
    type: 'send.message',
    client_msg_id: msgId,
    text: t
  });

  $('text').value = '';
  updateCharCount();
  $('text').focus();
}

/**
 * Calculate retry delay with exponential backoff.
 * @param {number} attempt - Current retry attempt number
 * @returns {number} - Delay in milliseconds
 */
function getRetryDelay(attempt) {
  // Exponential backoff: 1s, 2s, 4s, 8s, 16s, max 30s
  return Math.min(1000 * Math.pow(2, attempt), 30000);
}

/**
 * Attempt to reconnect with exponential backoff.
 */
function attemptReconnect() {
  if (retryAttempt >= maxRetries) {
    console.error('Max reconnection attempts reached');
    setStatus('connection failed');
    log('! Unable to connect. Please check your connection and refresh the page.', 'meta');
    return;
  }

  const delay = getRetryDelay(retryAttempt);
  retryAttempt++;

  console.log(`Reconnection attempt ${retryAttempt}/${maxRetries} in ${delay}ms`);
  setStatus(`reconnecting (${retryAttempt}/${maxRetries})`);
  log(`! Reconnecting in ${delay / 1000}s (attempt ${retryAttempt}/${maxRetries})...`, 'meta');

  retryTimeout = setTimeout(() => {
    console.log('Attempting reconnection...');
    connectSocket();
  }, delay);
}

/**
 * Reset retry state after successful connection.
 */
function resetRetryState() {
  retryAttempt = 0;
  if (retryTimeout) {
    clearTimeout(retryTimeout);
    retryTimeout = null;
  }
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
    // Redirect to login with current page as redirect parameter
    setTimeout(() => {
      const redirectUrl = encodeURIComponent(window.location.pathname + window.location.search);
      window.location.href = `login.html?redirect=${redirectUrl}`;
    }, 2000);
    return;
  }

  // If we already have a socket, disconnect it first
  if (socket) {
    socket.removeAllListeners();
    socket.disconnect();
  }

  // Configure Socket.IO for Cloudflare Tunnel compatibility
  socket = io(BACKEND_DEFAULT, {
    auth: {token},
    // Use polling first, then upgrade to WebSocket if possible
    // This works better with Cloudflare tunnels
    transports: ['polling', 'websocket'],
    upgrade: true,  // Allow upgrade from polling to WebSocket
    reconnection: false, // We'll handle reconnection manually
    // Additional options for tunnel compatibility
    forceNew: true,  // Force new connection
    timeout: 10000,  // 10 second timeout
    // Add path if needed
    path: '/socket.io/'
  });

  socket.on('connect', () => {
    console.log('Socket connected successfully');
    mySocketId = socket.id; // Store our socket ID
    setStatus('connected');
    resetRetryState(); // Reset retry counter on successful connection

    // Clear any "reconnecting" messages
    const metaMessages = document.querySelectorAll('.chat-log .meta');
    metaMessages.forEach(msg => {
      if (msg.textContent.includes('Reconnecting') || msg.textContent.includes('Connection error')) {
        msg.remove();
      }
    });

    log('✓ Connected to server', 'meta');
  });

  socket.on('disconnect', (reason) => {
    console.log('Socket disconnected:', reason);
    setStatus('disconnected');
    setUsers(0);

    // Don't clear room info immediately - we might reconnect
    if (!isManualDisconnect) {
      log('! Disconnected from server. Attempting to reconnect...', 'meta');
      attemptReconnect();
    }
  });

  socket.on('connect_error', (err) => {
    console.error('Socket connection error:', err);
    console.error('Error details:', {
      message: err.message,
      description: err.description,
      context: err.context,
      type: err.type
    });
    setStatus('connection error');

    // Check if it's an authentication error
    if (err.message && (err.message.includes('authentication') || err.message.includes('jwt') || err.message.includes('token'))) {
      console.error('Authentication error - token may be invalid or expired');
      log('! Authentication failed. Your session may have expired. Redirecting to login...', 'meta');

      // Clear invalid token
      saveToken(null);

      // Redirect to login with current page as redirect parameter
      setTimeout(() => {
        const redirectUrl = encodeURIComponent(window.location.pathname + window.location.search);
        window.location.href = `login.html?redirect=${redirectUrl}`;
      }, 2000);
    } else {
      // Network error - attempt reconnection
      const errorMsg = err.message || 'Unknown error';
      log(`! Connection error: ${errorMsg}. Retrying with different transport...`, 'meta');
      attemptReconnect();
    }
  });

  socket.on('server', m => {
    console.log('Server message:', m);

    switch (m.type) {
      case 'rooms.list':
        // Received list of available rooms
        console.log('Received rooms list:', m);
        if (m.user_info && m.user_info.user_id) {
          currentUserId = m.user_info.user_id;
        }
        updateRoomList(m.official_rooms, m.community_rooms, m.my_rooms, m.saved_rooms);

        // Check if room ID is in URL
        if (!roomIdFromUrl) {
          roomIdFromUrl = getUrlParameter('room');
        }

        // Auto-join room from URL if available
        if (roomIdFromUrl && !currentRoomId) {
          // Try to find the room in any of the lists
          const allRooms = [
            ...(m.official_rooms || []),
            ...(m.community_rooms || []),
            ...(m.my_rooms || [])
          ];
          const targetRoom = allRooms.find(r => r.id === roomIdFromUrl);

          if (targetRoom) {
            console.log('Auto-joining room from URL:', targetRoom.name);
            joinRoom(targetRoom.id, targetRoom.name);
          } else {
            // Room not found, try joining anyway (might be a private room we have access to)
            console.log('Attempting to join room from URL:', roomIdFromUrl);
            socket.emit('client', {
              type: 'room.join',
              room_id: roomIdFromUrl
            });
            currentRoomId = roomIdFromUrl;
            $('currentRoomName').textContent = 'Loading room...';
          }
        } else if (!currentRoomId && m.official_rooms && m.official_rooms.length > 0) {
          // Auto-join first official room if no URL parameter and not already in a room
          const firstRoom = m.official_rooms[0];
          joinRoom(firstRoom.id, firstRoom.name);
        }
        break;

      case 'rooms.list.update':
        // Received updated room list (after room creation/deletion)
        console.log('Received room list update:', m);
        // Keep current myRooms and savedRooms, but update official and community
        updateRoomList(m.official_rooms, m.community_rooms, myRooms, savedRooms);
        break;

      case 'room.created':
        // Room was successfully created
        console.log('Room created:', m.room);
        log(`Room "${m.room.name}" created successfully`, 'meta');
        // Add to myRooms and update display
        myRooms.push(m.room);
        updateRoomList(officialRooms, communityRooms, myRooms, savedRooms);
        break;

      case 'room.deleted':
        // Room was deleted
        console.log('Room deleted:', m.room_id);
        log('Room deleted successfully', 'meta');
        // Remove from myRooms
        myRooms = myRooms.filter(r => r.id !== m.room_id);
        updateRoomList(officialRooms, communityRooms, myRooms, savedRooms);
        // If we're in the deleted room, clear the chat
        if (currentRoomId === m.room_id) {
          currentRoomId = null;
          $('currentRoomName').textContent = '';
          $('log').innerHTML = '';
        }
        break;

      case 'room.closed':
        // Room was closed (deleted by owner while we were in it)
        log(`! ${m.message}`, 'meta');
        currentRoomId = null;
        $('currentRoomName').textContent = '';
        break;

      case 'room.snapshot':
        // Joined a room, received initial state
        console.log('Room snapshot:', m);
        setUsers(m.users.length);
        $('log').innerHTML = '';

        // Set room owner ID from snapshot
        if (m.owner_id) {
          currentRoomOwnerId = String(m.owner_id);
        }

        // Update room name if it was "Loading room..."
        if ($('currentRoomName').textContent === 'Loading room...') {
          // Try to find the room name from our lists
          const allRooms = [
            ...(officialRooms || []),
            ...(communityRooms || []),
            ...(myRooms || [])
          ];
          const room = allRooms.find(r => r.id === m.room_id);
          if (room) {
            $('currentRoomName').textContent = room.name;
          } else {
            $('currentRoomName').textContent = `Room ${m.room_id.slice(0, 8)}`;
          }
        }

        // Update member list
        updateMemberList(m.users || [], currentRoomOwnerId);

        // Reset tracking for new room
        lastShownTimestamp = null;
        lastMessageSender = null;
        lastMessageTimestamp = null;
        m.messages.forEach(x => {
          let cls, sender;
          if (x.sender === 'assistant') {
            cls = 'assistant';
            sender = 'Assistant';
          } else if (myMessageIds.has(x.id)) {
            cls = 'user';
            sender = null; // Don't show our own name
          } else {
            cls = 'other';
            sender = formatSender(x.sender);
          }
          log(x.text, cls, sender, x.ts);
        });
        break;

      case 'user.joined':
        setUsers(m.count);
        log(`${m.user.name} joined`, 'meta');
        // Add user to member list (only if not already present)
        if (m.user) {
          const exists = currentMembers.some(u => u.id === m.user.id);
          if (!exists) {
            currentMembers.push(m.user);
            updateMemberList(currentMembers, currentRoomOwnerId);
          }
        }
        break;

      case 'user.left':
        setUsers(m.count);
        // Find the user's name before removing them from the list
        let leavingUserName = 'User';
        if (m.user_id) {
          const user = currentMembers.find(u => u.id === m.user_id);
          if (user && user.name) {
            leavingUserName = user.name;
          }
          // Remove user from member list
          currentMembers = currentMembers.filter(u => u.id !== m.user_id);
          updateMemberList(currentMembers, currentRoomOwnerId);
        }
        log(`${leavingUserName} left`, 'meta');
        break;

      case 'message.appended':
        let cls, sender;
        if (m.message.sender === 'assistant') {
          cls = 'assistant';
          sender = 'Assistant';
        } else if (myMessageIds.has(m.message.id)) {
          cls = 'user';
          sender = null; // Don't show our own name
        } else {
          cls = 'other';
          sender = formatSender(m.message.sender);
        }
        log(m.message.text, cls, sender, m.message.ts);
        break;

      case 'assistant.started':
        currentRun = m.run.run_id;
        break;

      case 'assistant.completed':
        currentRun = null;
        break;

      case 'dm.sent':
        // User's DM was sent
        logDm(m.message.text, 'user', 'You', m.message.ts);
        break;

      case 'dm.message':
        // Received DM response from bot
        logDm(m.message.text, 'assistant', 'Assistant', m.message.ts);
        break;

      case 'dm.history':
        // Received DM history
        $('dmLog').innerHTML = '';
        dmLastSender = null;
        dmLastTimestamp = null;
        m.messages.forEach(msg => {
          let cls, sender;
          if (msg.sender === 'assistant') {
            cls = 'assistant';
            sender = 'Assistant';
          } else {
            cls = 'user';
            sender = 'You';
          }
          logDm(msg.text, cls, sender, msg.ts);
        });
        break;

      case 'user.kicked':
        log(`! ${m.message}`, 'meta');
        // Clear current room
        currentRoomId = null;
        updateUrlWithRoom(null);
        break;

      case 'user.banned':
        log(`! ${m.message}`, 'meta');
        // Clear current room
        currentRoomId = null;
        updateUrlWithRoom(null);
        break;

      case 'user.bans.list':
        // Received ban list for the room
        updateBanList(m.bans);
        break;

      case 'user.unban.success':
        log(`✓ ${m.message}`, 'meta');
        // Refresh the ban list if modal is open
        if (!$('banListModal').classList.contains('hidden')) {
          showBanList();
        }
        break;

      case 'user.ban.success':
      case 'user.tempban.success':
        log(`✓ ${m.message}`, 'meta');
        break;

      case 'room.saved':
        log(`✓ ${m.message}`, 'meta');
        // Add room to saved list if not already there
        if (!savedRooms.find(r => r.id === m.room.id)) {
          savedRooms.push(m.room);
          updateRoomList(officialRooms, communityRooms, myRooms, savedRooms);
        }
        break;

      case 'room.unsave.success':
        log(`✓ ${m.message}`, 'meta');
        // Remove room from saved list
        savedRooms = savedRooms.filter(r => r.id !== m.room_id);
        updateRoomList(officialRooms, communityRooms, myRooms, savedRooms);
        break;

      case 'error':
        log(`! error: ${m.message}`, 'meta');
        break;
    }
  });
}

/**
 * Show settings message.
 * @param {string} elementId - Message element ID
 * @param {string} message - Message text
 * @param {string} type - Message type (success/error)
 */
function showSettingsMessage(elementId, message, type) {
  const el = $(elementId);
  el.textContent = message;
  el.className = `message ${type}`;
  setTimeout(() => {
    el.textContent = '';
    el.className = 'message';
  }, 5000);
}

/**
 * Show the settings modal and load current user info.
 */
async function showSettingsModal() {
  const token = getToken();
  if (!token) {
    return;
  }

  try {
    const response = await postJSON(BACKEND_DEFAULT + '/api/auth/profile', null, 'GET');
    if (response.user) {
      $('settingsUsername').value = response.user.name || '';
      $('settingsEmail').value = response.user.email || '';
    }
  } catch (err) {
    console.error('Failed to load profile:', err);
  }

  // Clear password fields
  $('currentPassword').value = '';
  $('newPassword').value = '';
  $('confirmPassword').value = '';

  // Clear messages
  $('profileMessage').textContent = '';
  $('passwordMessage').textContent = '';

  $('settingsModal').classList.remove('hidden');
}

/**
 * Hide the settings modal.
 */
function hideSettingsModal() {
  $('settingsModal').classList.add('hidden');
}

/**
 * Save profile changes.
 */
async function saveProfile() {
  const username = $('settingsUsername').value.trim();
  const email = $('settingsEmail').value.trim();

  if (!username || !email) {
    showSettingsMessage('profileMessage', 'Username and email are required', 'error');
    return;
  }

  try {
    const response = await postJSON(BACKEND_DEFAULT + '/api/auth/profile', {
      name: username,
      email: email
    }, 'PUT');

    if (response.msg) {
      showSettingsMessage('profileMessage', response.msg, 'success');
    }
  } catch (err) {
    const message = err.msg || 'Failed to update profile';
    showSettingsMessage('profileMessage', message, 'error');
  }
}

/**
 * Change password.
 */
async function changePassword() {
  const currentPassword = $('currentPassword').value;
  const newPassword = $('newPassword').value;
  const confirmPassword = $('confirmPassword').value;

  if (!currentPassword || !newPassword || !confirmPassword) {
    showSettingsMessage('passwordMessage', 'All password fields are required', 'error');
    return;
  }

  if (newPassword !== confirmPassword) {
    showSettingsMessage('passwordMessage', 'New passwords do not match', 'error');
    return;
  }

  if (newPassword.length < 6) {
    showSettingsMessage('passwordMessage', 'Password must be at least 6 characters', 'error');
    return;
  }

  try {
    const response = await postJSON(BACKEND_DEFAULT + '/api/auth/password', {
      current_password: currentPassword,
      new_password: newPassword
    }, 'PUT');

    if (response.msg) {
      showSettingsMessage('passwordMessage', response.msg, 'success');
      // Clear password fields on success
      $('currentPassword').value = '';
      $('newPassword').value = '';
      $('confirmPassword').value = '';
    }
  } catch (err) {
    const message = err.msg || 'Failed to change password';
    showSettingsMessage('passwordMessage', message, 'error');
  }
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

  // Room creation modal
  $('createRoomBtn').onclick = showCreateRoomModal;
  $('createRoomCancel').onclick = hideCreateRoomModal;
  $('createRoomConfirm').onclick = createRoom;

  $('roomNameInput').addEventListener('keydown', (e) => {
    if (e.key === 'Enter') {
      e.preventDefault();
      createRoom();
    } else if (e.key === 'Escape') {
      hideCreateRoomModal();
    }
  });

  // Click outside modal to close
  $('roomModal').addEventListener('click', (e) => {
    if (e.target === $('roomModal')) {
      hideCreateRoomModal();
    }
  });

  // DM modal
  $('dmBtn').onclick = showDmModal;
  $('dmClose').onclick = hideDmModal;
  $('dmSend').onclick = sendDm;

  $('dmText').addEventListener('keydown', (e) => {
    if (e.key === 'Enter' && !e.shiftKey) {
      e.preventDefault();
      sendDm();
    }
  });

  $('dmText').addEventListener('input', updateDmCharCount);

  $('dmModal').addEventListener('click', (e) => {
    if (e.target === $('dmModal')) {
      hideDmModal();
    }
  });

  // Settings modal
  $('settingsBtn').onclick = showSettingsModal;
  $('settingsClose').onclick = hideSettingsModal;
  $('saveProfile').onclick = saveProfile;
  $('savePassword').onclick = changePassword;
  $('logoutBtnSettings').onclick = logout;

  $('settingsModal').addEventListener('click', (e) => {
    if (e.target === $('settingsModal')) {
      hideSettingsModal();
    }
  });

  // Logout button (header)
  $('logoutBtn').onclick = logout;

  // Play game button
  $('playGameBtn').onclick = () => {
    window.location.href = '/game.html';
  };

  // Member list toggle
  $('toggleMembersBtn').onclick = toggleMemberList;

  // User modal
  $('userModalClose').onclick = hideUserModal;
  $('kickUserBtn').onclick = kickUser;
  $('tempBanUserBtn').onclick = tempBanUser;
  $('banUserBtn').onclick = banUser;

  $('userModal').addEventListener('click', (e) => {
    if (e.target === $('userModal')) {
      hideUserModal();
    }
  });

  // Ban list modal
  $('viewBansBtn').onclick = showBanList;
  $('banListModalClose').onclick = hideBanList;

  $('banListModal').addEventListener('click', (e) => {
    if (e.target === $('banListModal')) {
      hideBanList();
    }
  });

  // Context menu handlers
  const contextMenuItems = document.querySelectorAll('.context-menu-item');
  contextMenuItems.forEach(item => {
    item.addEventListener('click', () => {
      const action = item.getAttribute('data-action');
      handleContextMenuAction(action);
    });
  });

  // Hide context menu when clicking elsewhere
  document.addEventListener('click', (e) => {
    if (!e.target.closest('.room-context-menu')) {
      hideRoomContextMenu();
    }
  });

  // Hide context menu on scroll
  document.addEventListener('scroll', hideRoomContextMenu, true);

  // Initialize
  connectSocket();
  updateCharCount();
  updateDmCharCount();
}

// Initialize on page load
window.addEventListener('load', initChat);
