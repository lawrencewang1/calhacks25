/**
 * Find the AI - Game Client (Figma Design)
 */

// Global state
let socket = null;
let currentGameId = null;
let currentPlayerId = null;
let currentGameState = null;
let isMuted = false;
let allPlayers = [];

// UI Elements
const lobbyView = document.getElementById('lobbyView');
const gameView = document.getElementById('gameView');
const gameEndView = document.getElementById('gameEndView');

// Lobby elements
const createGameBtn = document.getElementById('createGameBtn');
const joinGameBtn = document.getElementById('joinGameBtn');
const gameCodeSection = document.getElementById('gameCodeSection');
const gameCode = document.getElementById('gameCode');
const copyGameCode = document.getElementById('copyGameCode');
const playerList = document.getElementById('playerList');
const playerCount = document.getElementById('playerCount');
const startGameBtn = document.getElementById('startGameBtn');

// Game elements
const currentRound = document.getElementById('currentRound');
const phaseInfo = document.getElementById('phaseInfo');
const timerDisplay = document.getElementById('timerDisplay');
const leaveGameBtn = document.getElementById('leaveGameBtn');
const chatPhase = document.getElementById('chatPhase');
const votingPhase = document.getElementById('votingPhase');
const gameChatLog = document.getElementById('gameChatLog');
const gameChatInput = document.getElementById('gameChatInput');
const gameSendBtn = document.getElementById('gameSendBtn');
const gameComposer = document.getElementById('gameComposer');
const mutedMessage = document.getElementById('mutedMessage');
const votePlayerList = document.getElementById('votePlayerList');
const voteStatusText = document.getElementById('voteStatusText');
const forceEndVoteBtn = document.getElementById('forceEndVoteBtn');

// Game end elements
const gameEndTitle = document.getElementById('gameEndTitle');
const gameEndResult = document.getElementById('gameEndResult');
const gameEndPlayerList = document.getElementById('gameEndPlayerList');
const playAgainBtn = document.getElementById('playAgainBtn');
const backToChatEnd = document.getElementById('backToChatEnd');

// Join modal
const joinGameModal = document.getElementById('joinGameModal');
const joinGameCode = document.getElementById('joinGameCode');
const joinGameConfirm = document.getElementById('joinGameConfirm');
const joinGameCancel = document.getElementById('joinGameCancel');

/**
 * Initialize the game client
 */
function init() {
  console.log('Initializing game...');

  // Check for game ID in URL
  const urlParams = new URLSearchParams(window.location.search);
  const gameId = urlParams.get('game');

  // Get JWT token
  const token = localStorage.getItem('access_token');
  if (!token) {
    window.location.href = '/login.html';
    return;
  }

  // Initialize Socket.IO
  initSocket(token);

  // Setup event listeners
  setupEventListeners();

  // If game ID in URL, show join modal
  if (gameId) {
    joinGameCode.value = gameId;
    joinGameModal.classList.remove('hidden');
  }
}

/**
 * Initialize Socket.IO connection
 */
function initSocket(token) {
  socket = io({
    auth: { token }
  });

  socket.on('connect', () => {
    console.log('Connected to server');
  });

  socket.on('disconnect', () => {
    console.log('Disconnected from server');
  });

  socket.on('server', handleServerMessage);
}

/**
 * Setup UI event listeners
 */
function setupEventListeners() {
  if (createGameBtn) {
    createGameBtn.addEventListener('click', createGame);
  }

  if (joinGameBtn) {
    joinGameBtn.addEventListener('click', () => {
      joinGameModal.classList.remove('hidden');
    });
  }

  if (copyGameCode) {
    copyGameCode.addEventListener('click', () => copyToClipboard(gameCode.textContent));
  }

  if (startGameBtn) {
    startGameBtn.addEventListener('click', startGame);
  }

  if (leaveGameBtn) {
    leaveGameBtn.addEventListener('click', leaveGame);
  }

  if (gameSendBtn) {
    gameSendBtn.addEventListener('click', sendGameMessage);
  }

  if (gameChatInput) {
    gameChatInput.addEventListener('keypress', (e) => {
      if (e.key === 'Enter') sendGameMessage();
    });
  }

  if (forceEndVoteBtn) {
    forceEndVoteBtn.addEventListener('click', forceEndVoting);
  }

  if (playAgainBtn) {
    playAgainBtn.addEventListener('click', createGame);
  }

  if (backToChatEnd) {
    backToChatEnd.addEventListener('click', () => window.location.href = '/chat.html');
  }

  if (joinGameConfirm) {
    joinGameConfirm.addEventListener('click', () => {
      const code = joinGameCode.value.trim();
      if (code) {
        joinGame(code);
        joinGameModal.classList.add('hidden');
      }
    });
  }

  if (joinGameCancel) {
    joinGameCancel.addEventListener('click', () => {
      joinGameModal.classList.add('hidden');
    });
  }
}

/**
 * Handle server messages
 */
function handleServerMessage(msg) {
  console.log('Server message:', msg);

  switch (msg.type) {
    case 'game.created':
      handleGameCreated(msg);
      break;
    case 'game.joined':
      handleGameJoined(msg);
      break;
    case 'game.player.joined':
      handlePlayerJoined(msg);
      break;
    case 'game.started':
      handleGameStarted(msg);
      break;
    case 'game.round.start':
      handleRoundStart(msg);
      break;
    case 'game.phase.change':
      handlePhaseChange(msg);
      break;
    case 'game.timer.update':
      handleTimerUpdate(msg);
      break;
    case 'game.message':
      handleGameMessage(msg);
      break;
    case 'game.vote.received':
      handleVoteReceived(msg);
      break;
    case 'game.vote.supermajority':
      handleSupermajority(msg);
      break;
    case 'game.vote.result':
      handleVoteResult(msg);
      break;
    case 'game.ended':
      handleGameEnded(msg);
      break;
    case 'game.player.left':
      handlePlayerLeft(msg);
      break;
    case 'error':
      showError(msg.message);
      break;
  }
}

/**
 * Create a new game
 */
function createGame() {
  console.log('Creating game...');
  socket.emit('game.create', {});
}

/**
 * Join an existing game
 */
function joinGame(gameId) {
  console.log('Joining game:', gameId);
  socket.emit('game.join', { game_id: gameId });
}

/**
 * Start the game
 */
function startGame() {
  if (currentGameId) {
    console.log('Starting game:', currentGameId);
    socket.emit('game.start', { game_id: currentGameId });
  }
}

/**
 * Leave the game
 */
function leaveGame() {
  if (confirm('Are you sure you want to leave the game?')) {
    socket.emit('game.leave', { game_id: currentGameId });
    window.location.href = '/chat.html';
  }
}

/**
 * Send a chat message
 */
function sendGameMessage() {
  const text = gameChatInput.value.trim();
  if (!text || isMuted) return;

  socket.emit('game.message', { text });
  gameChatInput.value = '';
}

/**
 * Vote for a player
 */
function voteForPlayer(playerId) {
  console.log('Voting for:', playerId);
  socket.emit('game.vote', { voted_for_id: playerId });
}

/**
 * Force end voting phase
 */
function forceEndVoting() {
  socket.emit('game.vote.force_end', {});
}

/**
 * Handle game created
 */
function handleGameCreated(msg) {
  console.log('Game created:', msg);
  currentGameId = msg.game.id;
  currentGameState = msg.game;
  currentPlayerId = msg.player.id;

  // Show game code
  gameCode.textContent = currentGameId.substring(0, 8).toUpperCase();
  gameCodeSection.classList.remove('hidden');
  startGameBtn.classList.remove('hidden');

  // Update player list
  allPlayers = [msg.player];
  updatePlayerList(allPlayers);
}

/**
 * Handle game joined
 */
function handleGameJoined(msg) {
  console.log('Game joined:', msg);
  currentGameId = msg.game.id;
  currentGameState = msg.game;

  // Find current player
  const myUserId = getUserIdFromToken();
  const myPlayer = msg.players.find(p => p.user_id === myUserId);
  if (myPlayer) {
    currentPlayerId = myPlayer.id;
  }

  // Show game code
  gameCode.textContent = currentGameId.substring(0, 8).toUpperCase();
  gameCodeSection.classList.remove('hidden');

  // Update player list
  allPlayers = msg.players;
  updatePlayerList(allPlayers);

  // If game already started, switch to game view
  if (msg.game.status !== 'lobby') {
    switchToGameView();
    updateGameState(msg.game);
  }
}

/**
 * Handle player joined
 */
function handlePlayerJoined(msg) {
  console.log('Player joined:', msg);
  allPlayers.push(msg.player);
  updatePlayerList(allPlayers);
}

/**
 * Handle game started
 */
function handleGameStarted(msg) {
  console.log('Game started:', msg);
  currentGameState = msg.game;
  allPlayers = msg.players;
  switchToGameView();
  updateGameState(msg.game);
}

/**
 * Handle round start
 */
function handleRoundStart(msg) {
  currentRound.textContent = msg.round;
  switchToChatPhase();
}

/**
 * Handle phase change
 */
function handlePhaseChange(msg) {
  if (msg.phase === 'voting') {
    switchToVotingPhase();
  } else if (msg.phase === 'chat') {
    switchToChatPhase();
  }
}

/**
 * Handle timer update
 */
function handleTimerUpdate(msg) {
  const remaining = msg.remaining_ms;
  const minutes = Math.floor(remaining / 60000);
  const seconds = Math.floor((remaining % 60000) / 1000);
  timerDisplay.textContent = minutes + ':' + (seconds < 10 ? '0' : '') + seconds;

  // Warn if less than 30 seconds
  if (remaining < 30000) {
    timerDisplay.classList.add('warning');
  } else {
    timerDisplay.classList.remove('warning');
  }
}

/**
 * Handle game message
 */
function handleGameMessage(msg) {
  const message = msg.message;
  const messageEl = document.createElement('div');
  messageEl.className = 'game-message';

  const senderEl = document.createElement('div');
  senderEl.className = 'game-message-sender';
  senderEl.textContent = message.sender.replace('user:', '');

  const textEl = document.createElement('div');
  textEl.className = 'game-message-text';
  textEl.textContent = message.text;

  const timeEl = document.createElement('div');
  timeEl.className = 'game-message-time';
  timeEl.textContent = new Date(message.ts).toLocaleTimeString();

  messageEl.appendChild(senderEl);
  messageEl.appendChild(textEl);
  messageEl.appendChild(timeEl);

  gameChatLog.appendChild(messageEl);
  gameChatLog.scrollTop = gameChatLog.scrollHeight;
}

/**
 * Handle vote received
 */
function handleVoteReceived(msg) {
  voteStatusText.textContent = 'Vote recorded!';
}

/**
 * Handle supermajority
 */
function handleSupermajority(msg) {
  forceEndVoteBtn.classList.remove('hidden');
  voteStatusText.textContent = 'Supermajority reached (' + msg.votes_cast + '/' + msg.total_active + '). You can force end voting.';
}

/**
 * Handle vote result
 */
function handleVoteResult(msg) {
  // Hide voting phase
  votingPhase.classList.add('view-hidden');

  // Show alert with result
  if (!msg.eliminated_player_id) {
    alert('No player was eliminated this round.');
  } else {
    let resultMsg = msg.eliminated_player_name + ' was eliminated with ' + msg.vote_count + ' votes.';
    if (msg.was_ai) {
      resultMsg += '\n\nThey were the AI! Humans win!';
    } else {
      resultMsg += '\n\nThey were human. The game continues...';
    }
    alert(resultMsg);
  }

  // Update muted status
  if (msg.eliminated_player_id === currentPlayerId) {
    isMuted = true;
  }
}

/**
 * Handle game ended
 */
function handleGameEnded(msg) {
  console.log('Game ended:', msg);
  switchToGameEndView();

  gameEndTitle.textContent = msg.winner === 'humans' ? 'HUMANS WIN!' : 'AI WINS!';
  gameEndTitle.className = 'game-end-title ' + (msg.winner === 'humans' ? 'humans-win' : 'ai-wins');

  let resultHTML = '<h3>Game Over</h3>';
  if (msg.winner === 'humans') {
    resultHTML += '<p>The humans successfully found the AI imposter!</p>';
  } else {
    resultHTML += '<p>The AI survived both rounds. Everyone loses!</p>';
  }
  resultHTML += '<p>The AI was: <strong>' + getPlayerNameById(msg.ai_player_id, msg.all_players) + '</strong></p>';

  gameEndResult.innerHTML = resultHTML;

  // Show all players
  updateGameEndPlayerList(msg.all_players, msg.ai_player_id);
}

/**
 * Handle player left
 */
function handlePlayerLeft(msg) {
  allPlayers = allPlayers.filter(p => p.id !== msg.player_id);
  updatePlayerList(allPlayers);
}

/**
 * Update player list in lobby
 */
function updatePlayerList(players) {
  if (players.length === 0) {
    playerList.innerHTML = '<div style="grid-column: 1 / -1; text-align: center; color: var(--game-text-gray); padding: 2rem;">Waiting for players...</div>';
    playerCount.textContent = '0';
    return;
  }

  playerList.innerHTML = '';
  let playerIndex = 1;
  players.forEach(player => {
    if (player.is_ai) return; // Don't show AI in lobby

    const card = document.createElement('div');
    card.className = 'player-card';

    const avatar = document.createElement('div');
    avatar.className = 'player-avatar';
    avatar.textContent = '?';  // Hide identity in lobby

    const info = document.createElement('div');
    const name = document.createElement('div');
    name.className = 'player-name';
    name.textContent = `Player ${playerIndex}`;  // Generic name in lobby

    info.appendChild(name);
    card.appendChild(avatar);
    card.appendChild(info);
    playerList.appendChild(card);
    playerIndex++;
  });

  playerCount.textContent = players.filter(p => !p.is_ai).length;
}

/**
 * Update voting player list
 */
function updateVotingPlayerList(players) {
  votePlayerList.innerHTML = '';
  players.filter(p => p.is_active && p.id !== currentPlayerId).forEach(player => {
    const card = document.createElement('div');
    card.className = 'vote-player-card';

    card.innerHTML = '<div class="player-avatar">' + player.player_name.charAt(0).toUpperCase() + '</div><div><div class="player-name">' + player.player_name + '</div></div>';

    card.addEventListener('click', () => {
      document.querySelectorAll('.vote-player-card').forEach(c => c.classList.remove('selected'));
      card.classList.add('selected');
      voteForPlayer(player.id);
    });

    votePlayerList.appendChild(card);
  });
}

/**
 * Update game end player list
 */
function updateGameEndPlayerList(players, aiPlayerId) {
  gameEndPlayerList.innerHTML = '';
  players.forEach(player => {
    const card = document.createElement('div');
    card.className = 'player-card';

    const avatar = document.createElement('div');
    avatar.className = 'player-avatar';
    avatar.textContent = player.player_name.charAt(0).toUpperCase();

    const info = document.createElement('div');
    const name = document.createElement('div');
    name.className = 'player-name';
    name.textContent = player.player_name;

    const status = document.createElement('div');
    status.className = 'player-status';
    if (player.id === aiPlayerId) {
      status.textContent = '🤖 AI';
      status.style.color = 'var(--game-red)';
    } else if (!player.is_active) {
      status.textContent = 'Voted Out';
      status.classList.add('voted-out');
    } else {
      status.textContent = 'Survived';
    }

    info.appendChild(name);
    info.appendChild(status);
    card.appendChild(avatar);
    card.appendChild(info);
    gameEndPlayerList.appendChild(card);
  });
}

/**
 * Switch to game view
 */
function switchToGameView() {
  lobbyView.classList.add('view-hidden');
  gameView.classList.remove('view-hidden');
  gameEndView.classList.add('view-hidden');
}

/**
 * Switch to game end view
 */
function switchToGameEndView() {
  lobbyView.classList.add('view-hidden');
  gameView.classList.add('view-hidden');
  gameEndView.classList.remove('view-hidden');
}

/**
 * Switch to chat phase
 */
function switchToChatPhase() {
  phaseInfo.textContent = 'Chat Phase';
  chatPhase.classList.remove('view-hidden');
  votingPhase.classList.add('view-hidden');

  if (isMuted) {
    gameComposer.classList.add('hidden');
    mutedMessage.classList.remove('hidden');
  } else {
    gameComposer.classList.remove('hidden');
    mutedMessage.classList.add('hidden');
  }
}

/**
 * Switch to voting phase
 */
function switchToVotingPhase() {
  phaseInfo.textContent = 'Voting Phase';
  chatPhase.classList.add('view-hidden');
  votingPhase.classList.remove('view-hidden');

  // Update voting list
  updateVotingPlayerList(allPlayers);
}

/**
 * Update game state
 */
function updateGameState(game) {
  currentRound.textContent = game.current_round;

  if (game.round_phase === 'chat') {
    switchToChatPhase();
  } else if (game.round_phase === 'voting') {
    switchToVotingPhase();
  }
}

/**
 * Show error message
 */
function showError(message) {
  alert(message);
}

/**
 * Copy text to clipboard
 */
function copyToClipboard(text) {
  navigator.clipboard.writeText(text).then(() => {
    alert('Copied to clipboard!');
  });
}

/**
 * Get user ID from JWT token
 */
function getUserIdFromToken() {
  const token = localStorage.getItem('access_token');
  if (!token) return null;

  try {
    const payload = JSON.parse(atob(token.split('.')[1]));
    return payload.sub || payload.identity;
  } catch (e) {
    return null;
  }
}

/**
 * Get player name by ID
 */
function getPlayerNameById(playerId, players) {
  const player = players.find(p => p.id === playerId);
  return player ? player.player_name : 'Unknown';
}

// Initialize on page load
document.addEventListener('DOMContentLoaded', init);
