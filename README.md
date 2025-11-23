# Multiplayer AI Chat + Find the AI Game

A real-time multiplayer chat platform with an integrated social deduction mini-game ("Find the AI" / AI MPOSTER) where one hidden LLM tries to blend in while everyone else chats and votes it out. Built with Flask, Socket.IO, and modern web technologies.

## Features

- 🔐 **User Authentication** - Secure registration and login with JWT tokens
- 💬 **Real-time Chat** - Multi-room WebSocket chat with modern UI and persisted history
- 🤖 **AI Assistant & Imposter** - Context-aware assistant in chat plus a hidden LLM player during games
- 🕵️ **Find the AI Game** - Host/join lobbies via codes, anonymized nicknames, and a secret AI that tries to pass as human
- ⏱️ **Timed Rounds & Voting** - 2-round structure with chat (3m) and voting (1m), supermajority fast-forward, and mute-on-elimination
- 📱 **Responsive Design** - Works on desktop and mobile devices
- 🎨 **Modern UI** - Clean, dark-themed interface with gradient chat bubbles
- 🎯 **Intelligent Chunking** - Long AI responses broken into readable chunks at natural boundaries
- 💡 **Contextual Awareness** - AI responds to follow-ups, emotional content, and direct questions

## Find the AI: Game Overview

- **Goal:** Spot the LLM imposter that is injected when the host starts the game.
- **Lobby:** Create a lobby from `/game.html`, share the 8-character code (full UUID also works), and wait in the "searching for players" view. Names stay generic until the game begins.
- **Start conditions:** Host-only start, minimum of 3 human players; an anonymized AI player is auto-added on start.
- **Round structure:** Two rounds total. Each round has a chat phase (~3 minutes) followed by a voting phase (~1 minute). Timer updates stream to all players; supermajority (>=2/3 of active humans) unlocks a "force end voting" option.
- **Chat phase:** Everyone talks in real time; the AI occasionally replies (40% chance per human message, with a natural delay) using the last 15 messages for context and casual, slangy tone.
- **Voting phase:** Players vote on who to eliminate. The player with the most votes is knocked out and muted for the rest of the game; if the AI is eliminated, humans win immediately.
- **Win/lose:** Humans win by ejecting the AI; if the AI survives through the end of round 2, the AI wins. The end screen reveals the imposter and each player's status, with quick options to play again or return to chat.

## Tech Stack

### Backend
- **Flask** - Python web framework
- **Flask-SocketIO** - WebSocket support
- **Flask-JWT-Extended** - JWT authentication
- **Flask-SQLAlchemy** - Database ORM
- **SQLite** - Database
- **httpx** - HTTP client for LLM API

### Frontend
- **HTML5/CSS3** - Modern web standards
- **Socket.IO Client** - Real-time communication
- **Vanilla JavaScript** - No framework dependencies

## Project Structure

```
calhacks25/
├── backend/          # Backend application
│   ├── config/      # Configuration files
│   ├── models/      # Database models
│   ├── routes/      # API endpoints
│   ├── services/    # Business logic
│   ├── sockets/     # WebSocket handlers
│   └── utils/       # Helper functions
├── frontend/        # Frontend files
│   ├── static/      # CSS, JS, images
│   └── templates/   # HTML templates
├── instance/        # Instance-specific files (DB)
├── tests/           # Test suite
└── docs/            # Documentation
```

## Getting Started

### Prerequisites

- Python 3.8 or higher
- pip (Python package manager)
- Virtual environment (recommended)

### Installation

1. **Clone the repository**
   ```bash
   git clone <repository-url>
   cd calhacks25
   ```

2. **Create and activate virtual environment**
   ```bash
   python -m venv .venv
   source .venv/bin/activate  # On Windows: .venv\Scripts\activate
   ```

3. **Install dependencies**
   ```bash
   pip install -r requirements.txt
   ```

4. **Set up environment variables**
   ```bash
   cp .env.example .env
   # Edit .env and set your configuration
   ```

5. **Initialize the database**
   ```bash
   python run.py
   # Database will be created automatically on first run
   ```

### Running the Application

**Development Mode:**
```bash
python run.py
```

The application will be available at `http://localhost:5000`

**Production Mode:**
```bash
# Set environment variable
export FLASK_ENV=production

# Use a production WSGI server (e.g., gunicorn)
gunicorn --worker-class eventlet -w 1 run:app
```

## Usage

### Chat

1. **Register an Account**
   - Navigate to `http://localhost:5000/register.html`
   - Enter username, email, and password
   - Confirm password and create account

2. **Login**
   - Go to `http://localhost:5000/login.html`
   - Enter your credentials
   - You'll be redirected to the chat

3. **Chat**
   - Type messages in the input box (max 500 characters)
   - Press Enter or click Send
   - Your messages appear as **blue bubbles** on the right
   - Other users' messages appear as **purple bubbles** on the left
   - Assistant's responses appear as **green bubbles** on the left

4. **Interacting with Assistant (AI Assistant)**
   - **Direct mention**: `@Assistant` or `Assistant, can you help?`
   - **Questions**: Ask questions naturally - Assistant responds intelligently
   - **Follow-ups**: Continue conversations without mentioning her name
   - **Requests**: Use phrases like "could you", "can you", "please help"
   - **Smart responses**: Assistant decides when to respond based on context
   - **Emotional awareness**: Assistant responds to emotional statements

5. **Chat Features**
   - **Message History**: Previous conversations are saved and restored
   - **Character Counter**: See remaining characters as you type
   - **Smooth Animations**: Messages slide in with elegant transitions
   - **Stop Generation**: Click Stop to interrupt long AI responses

### Play "Find the AI"

1. **Open the game lobby**  
   - Log in, then visit `http://localhost:5000/game.html` (or share a link like `/game.html?game=ABCD1234` to pre-fill the join modal).
2. **Create or join**  
   - Click **CREATE GAME** to host and get an 8-character code (first 8 of the UUID). Share the code with friends.  
   - Or click **JOIN GAME** and enter a code to enter an existing lobby.
3. **Start the match**  
   - Only the host can start. You need at least 3 human players; an anonymized AI player is automatically added on start. Lobby names stay generic until the game begins.
4. **Play the rounds**  
   - Each round: ~3 minutes of open chat, then ~1 minute of voting. Timer updates appear at the top; a supermajority (>=2/3 of active humans) enables **FORCE END VOTING**.  
   - The AI occasionally replies during chat with casual, human-like messages based on the last 15 messages.
5. **Vote and finish**  
   - Select who you think is the AI. Eliminated players are muted for the rest of the game.  
   - Humans win as soon as the AI is voted out; if the AI survives through round 2, the AI wins. The end screen reveals the imposter with options to **PLAY AGAIN** or return to chat.

## API Endpoints

### Authentication

- `POST /api/auth/register` - Register a new user
- `POST /api/auth/login` - Login and receive JWT token

### WebSocket Events

**Client → Server (Chat):**
- `connect` - Establish WebSocket connection with JWT auth
- `send.message` - Send a chat message
  ```json
  {
    "type": "send.message",
    "client_msg_id": "uuid",
    "text": "message content"
  }
  ```
- `run.stop` - Stop the AI assistant generation
  ```json
  {
    "type": "run.stop",
    "run_id": "uuid"
  }
  ```

**Server → Client (Chat):**
- `room.snapshot` - Initial state with message history (on connect)
  - Includes last 200 messages from database
  - Current user list
  - Room sequence number
- `user.joined` - User joined notification
- `user.left` - User left notification
- `message.appended` - New message from user or assistant
  - Used for both user messages and AI response chunks
  - Messages are complete (not streamed character-by-character)
- `assistant.started` - AI assistant started processing
- `assistant.completed` - AI assistant finished
- `error` - Error notification

**Client → Server (Game):**
- `game.create` - Create a new lobby and become host
- `game.join` - Join a lobby by ID or short code
  ```json
  { "game_id": "ABCD1234" }
  ```
- `game.start` - Host-only; starts the match and injects the AI player
  ```json
  { "game_id": "uuid" }
  ```
- `game.message` - Send a message during the chat phase
  ```json
  { "text": "message content" }
  ```
- `game.vote` - Vote for a player during the voting phase
  ```json
  { "voted_for_id": "player-uuid" }
  ```
- `game.vote.force_end` - Force-end voting after supermajority is reached
- `game.leave` - Leave the lobby/game
  ```json
  { "game_id": "uuid" }
  ```

**Server → Client (Game):**
- `game.created` - Sent to host with the new `game` and `player`
- `game.joined` - Sent to joiner with `game` plus all `players`
- `game.player.joined` / `game.player.left` - Lobby roster updates
- `game.started` - Game transitions to playing and AI is added
- `game.round.start` - Announces current round number (1 or 2)
- `game.phase.change` - Switches between `chat` and `voting`
- `game.timer.update` - Remaining ms in the current phase
- `game.message` - Chat message from any player (human or AI)
- `game.vote.received` - Confirmation that your vote was recorded
- `game.vote.supermajority` - Supermajority reached (>=2/3 votes cast) and force-end is allowed
- `game.vote.result` - Voting outcome with `eliminated_player_id`, `eliminated_player_name`, `was_ai`, `vote_count`
- `game.ended` - Final results with `winner`, `ai_player_id`, and `all_players`
- `error` - Error notification

## Configuration

### Environment Variables

Create a `.env` file in the root directory:

```env
# Flask Configuration
JWT_SECRET_KEY=your-secret-key-here
PORT=5000

# Database Configuration
SQLALCHEMY_DATABASE_URI=sqlite:///chatbot.db

# LLM API Configuration
LLM_API_URL=https://janitorai.com/hackathon/completions
LLM_AUTH_TOKEN=your-llm-token-here
MAX_OUT_TOKENS=400

# AI Assistant Configuration
SYSTEM_PROMPT=Your custom system prompt (optional)
CHAT_CONTEXT_MESSAGES=50
MESSAGE_HISTORY_LIMIT=200
MAX_MESSAGE_LENGTH=500

# Feature Flags
ALLOW_GUESTS=false
```

### Configuration Details

- **JWT_SECRET_KEY**: Secret key for JWT token signing (required in production)
- **LLM_API_URL**: URL for the LLM API endpoint
- **LLM_AUTH_TOKEN**: Authentication token for LLM API
- **MAX_OUT_TOKENS**: Maximum tokens per AI response (default: 400)
- **SYSTEM_PROMPT**: Custom system prompt for Assistant (see `config.py` for default)
- **CHAT_CONTEXT_MESSAGES**: Number of recent messages sent to AI for context (default: 50)
- **MESSAGE_HISTORY_LIMIT**: Maximum messages stored in memory (default: 200)
- **ALLOW_GUESTS**: Allow unauthenticated connections (default: false)

### AI Assistant (Assistant) Behavior

Assistant uses intelligent decision-making to determine when to respond:

**Will Respond To:**
- Direct mentions: `@Assistant`, `Assistant, ...`
- Questions following her recent activity (follow-ups)
- Direct requests: "could you", "can you", "help me"
- Emotional statements when no one else is responding
- General questions directed at the group

**Will NOT Respond To:**
- User-to-user greetings: "hey John!"
- Short exchanges between specific users
- Messages clearly directed at another user
- Small talk when users are conversing with each other

**Response Format:**
- Long responses are automatically chunked at natural boundaries (paragraphs, sentences)
- Each chunk appears as a separate message with a 0.3s delay
- Maximum chunk size: ~300 characters

### Security Notes

⚠️ **PRODUCTION REQUIREMENTS:**
- Generate a strong `JWT_SECRET_KEY` (use `openssl rand -hex 32`)
- Never commit `.env` file to version control
- Use HTTPS in production
- Restrict CORS origins
- Implement rate limiting
- Add proper logging
- Use a production WSGI server
- Regularly backup the SQLite database

## Development

### Running Tests

```bash
# Run all tests
pytest

# Run with coverage
pytest --cov=backend tests/

# Run specific test file
pytest tests/test_auth.py
```

### Code Style

This project follows PEP 8 style guidelines. Use tools like:

```bash
# Format code
black backend/

# Lint code
flake8 backend/

# Type checking
mypy backend/
```

## Troubleshooting

### Common Issues

**"Connection rejected by server"**
- Check if JWT token is valid
- Ensure `ALLOW_GUESTS=false` is set correctly
- Clear browser localStorage and re-login

**"Can't start the Find the AI game"**
- Only the host can start; make sure you're the host of the lobby
- You need at least 3 human players before start (AI is added automatically)
- Games can only be started from the lobby state (not after already starting/ending)

**"No module named 'flask'"**
- Activate virtual environment
- Run `pip install -r requirements.txt`

**Database errors**
- Delete `instance/chatbot.db`
- Restart the application to recreate database
- Check database permissions

**"Working outside of application context"**
- This usually happens in background threads
- The code should use `with app.app_context():` for database operations
- Already handled in the current implementation

**Assistant not responding**
- Check if LLM API credentials are set correctly
- Review console logs for decision-making details
- Ensure `LLM_API_URL` is correct
- Try mentioning Assistant directly with `@Assistant`

**Messages not persisting after restart**
- Check that database migrations ran successfully
- Verify `SQLALCHEMY_DATABASE_URI` is set correctly
- Check write permissions for database file

**Chat bubbles not displaying correctly**
- Clear browser cache
- Check browser console for JavaScript errors
- Ensure all CSS files are loaded correctly

## Contributing

1. Fork the repository
2. Create a feature branch (`git checkout -b feature/amazing-feature`)
3. Commit your changes (`git commit -m 'Add amazing feature'`)
4. Push to the branch (`git push origin feature/amazing-feature`)
5. Open a Pull Request

## License

This project was created for CalHacks 2025.

## Acknowledgments

- CalHacks 2025 Hackathon
- JanitorAI for LLM API access
- Flask and Socket.IO communities

## Contact

For questions or support, please open an issue on GitHub.
