# Multiplayer AI Chat Application

A real-time multiplayer chat application with AI assistant integration, built with Flask, Socket.IO, and modern web technologies.

## Features

- 🔐 **User Authentication** - Secure registration and login with JWT tokens
- 💬 **Real-time Chat** - WebSocket-based instant messaging with modern chat bubbles
- 🤖 **AI Assistant (Midori)** - Intelligent LLM-powered chatbot with context-aware responses
- 🧠 **Smart Response Detection** - AI decides when to respond based on conversation context
- 💾 **Persistent Messages** - Chat history saved to database and restored on server restart
- 👥 **Multi-user Support** - Multiple users can chat simultaneously with distinct visual styles
- 📱 **Responsive Design** - Works on desktop and mobile devices
- 🎨 **Modern UI** - Clean, dark-themed interface with gradient chat bubbles
- 🎯 **Intelligent Chunking** - Long AI responses broken into readable chunks at natural boundaries
- 💡 **Contextual Awareness** - AI responds to follow-ups, emotional content, and direct questions

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
   - Midori's responses appear as **green bubbles** on the left

4. **Interacting with Midori (AI Assistant)**
   - **Direct mention**: `@Midori` or `Midori, can you help?`
   - **Questions**: Ask questions naturally - Midori responds intelligently
   - **Follow-ups**: Continue conversations without mentioning her name
   - **Requests**: Use phrases like "could you", "can you", "please help"
   - **Smart responses**: Midori decides when to respond based on context
   - **Emotional awareness**: Midori responds to emotional statements

5. **Chat Features**
   - **Message History**: Previous conversations are saved and restored
   - **Character Counter**: See remaining characters as you type
   - **Smooth Animations**: Messages slide in with elegant transitions
   - **Stop Generation**: Click Stop to interrupt long AI responses

## API Endpoints

### Authentication

- `POST /api/auth/register` - Register a new user
- `POST /api/auth/login` - Login and receive JWT token

### WebSocket Events

**Client → Server:**
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

**Server → Client:**
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
- **SYSTEM_PROMPT**: Custom system prompt for Midori (see `config.py` for default)
- **CHAT_CONTEXT_MESSAGES**: Number of recent messages sent to AI for context (default: 50)
- **MESSAGE_HISTORY_LIMIT**: Maximum messages stored in memory (default: 200)
- **ALLOW_GUESTS**: Allow unauthenticated connections (default: false)

### AI Assistant (Midori) Behavior

Midori uses intelligent decision-making to determine when to respond:

**Will Respond To:**
- Direct mentions: `@Midori`, `Midori, ...`
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

**Midori not responding**
- Check if LLM API credentials are set correctly
- Review console logs for decision-making details
- Ensure `LLM_API_URL` is correct
- Try mentioning Midori directly with `@Midori`

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
