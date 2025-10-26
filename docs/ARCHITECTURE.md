# Architecture Documentation

This document describes the architecture and design decisions for the Multiplayer AI Chat application.

## Overview

The application follows a modern client-server architecture with real-time communication capabilities. It's built using Flask for the backend and vanilla JavaScript for the frontend, with Socket.IO enabling real-time bidirectional communication.

## System Architecture

```
┌─────────────┐
│   Browser   │
│  (Client)   │
└─────┬───────┘
      │ HTTP/WebSocket
      │
┌─────▼───────────────────────┐
│     Nginx (Production)       │
│   Reverse Proxy & SSL        │
└─────┬───────────────────────┘
      │
┌─────▼──────────────────────────────┐
│      Flask Application              │
│  ┌──────────────────────────────┐  │
│  │    Gunicorn + Eventlet       │  │
│  │   (WSGI + WebSocket Server)  │  │
│  └──────────────────────────────┘  │
│                                     │
│  ┌───────────┐  ┌──────────────┐  │
│  │   Routes  │  │   Sockets    │  │
│  │  (REST)   │  │ (WebSocket)  │  │
│  └─────┬─────┘  └──────┬───────┘  │
│        │                │           │
│  ┌─────▼────────────────▼──────┐  │
│  │      Services Layer         │  │
│  │  (Business Logic)           │  │
│  └─────┬───────────────────────┘  │
│        │                            │
│  ┌─────▼────────┐  ┌──────────┐  │
│  │   Database   │  │  LLM API  │  │
│  │   (SQLite/   │  │ (External)│  │
│  │  PostgreSQL) │  │           │  │
│  └──────────────┘  └──────────┘  │
└─────────────────────────────────┘
```

## Component Architecture

### Backend Structure

```
backend/
├── __init__.py           # Application factory
├── extensions.py         # Flask extensions initialization
├── config/               # Configuration classes
├── models/               # Database models (ORM)
├── routes/               # REST API endpoints
├── services/             # Business logic layer
├── sockets/              # WebSocket handlers
└── utils/                # Helper functions
```

### Frontend Structure

```
frontend/
├── static/
│   ├── css/
│   │   ├── main.css      # Global styles
│   │   ├── auth.css      # Authentication pages
│   │   └── chat.css      # Chat interface & bubbles
│   ├── js/
│   │   ├── utils.js      # Utility functions
│   │   ├── auth.js       # Authentication logic
│   │   └── chat.js       # Chat & WebSocket logic
│   └── images/           # Static images
└── templates/            # Static HTML pages
```

### Frontend Chat UI Architecture

**Message Display System:**
- **Current User**: Blue gradient bubbles aligned right
- **Other Users**: Purple gradient bubbles aligned left with name labels
- **AI Assistant (Midori)**: Green gradient bubbles aligned left with "Midori" label
- **System Messages**: Centered, transparent, italic text

**CSS Architecture:**
```css
.msg-wrapper (flexbox container)
  ├── .msg-label (sender name, optional)
  └── .msg (the bubble)
      ├── .user (blue, right-aligned)
      ├── .other (purple, left-aligned)
      ├── .assistant (green, left-aligned)
      └── .meta (transparent, centered)
```

**JavaScript Message Tracking:**
- `myMessageIds` Set: Tracks IDs of messages sent by current user
- Used to distinguish own messages from others
- Enables proper bubble color/positioning

## Design Patterns

### 1. Application Factory Pattern

The backend uses the Application Factory pattern to create Flask instances:

```python
def create_app(config_name=None):
    app = Flask(__name__)
    # Load configuration
    # Initialize extensions
    # Register blueprints
    # Register routes
    return app
```

**Benefits:**
- Easy testing with different configurations
- Multiple app instances possible
- Clean separation of concerns
- Better for larger applications

### 2. Blueprint Pattern

Routes are organized into blueprints for modularity:

```python
auth_bp = Blueprint("auth", __name__)

@auth_bp.post("/register")
def register():
    # Registration logic
```

**Benefits:**
- Modular route organization
- Easy to add/remove features
- Clear URL namespacing
- Better code organization

### 3. Repository Pattern (Implicit)

SQLAlchemy models act as repositories:

```python
class User(db.Model):
    # Model definition

# Usage
user = User.query.filter_by(email=email).first()
```

**Benefits:**
- Abstraction over database access
- Easy to test with mocking
- Consistent data access patterns

### 4. Service Layer Pattern

Business logic is separated into service functions:

```python
# services/auth_service.py
def authenticate_user(email, password):
    # Authentication logic
```

**Benefits:**
- Separation of concerns
- Reusable business logic
- Easier to test
- Cleaner controllers

## Data Flow

### Authentication Flow

```
1. User → Frontend: Enter credentials
2. Frontend → Backend: POST /api/auth/login
3. Backend → Database: Query user
4. Backend → Backend: Verify password
5. Backend → Frontend: Return JWT token
6. Frontend → LocalStorage: Store token
7. Frontend → Backend: Connect WebSocket with token
8. Backend → Database: Verify token & get user
9. Backend → Frontend: Connection accepted
```

### Message Flow

```
1. User → Frontend: Type message
2. Frontend → Backend: WebSocket emit "send.message"
3. Backend → Database: Persist user message
4. Backend → All Clients: Broadcast message
5. Backend → LLM API: Check if AI should respond (decision API call)
6. If yes:
   a. Backend → LLM API: Send message for processing with context
   b. LLM API → Backend: Stream response
   c. Backend → Backend: Collect full response
   d. Backend → Backend: Chunk response at natural boundaries
   e. Backend → Database: Persist each chunk as separate message
   f. Backend → All Clients: Emit complete chunks with delays
```

### AI Response Decision Flow

```
1. User sends message
2. Check for direct mention (@Midori/@ai) → Respond
3. If not direct mention:
   a. Build conversation context (last 6 messages)
   b. Check if Midori was recently active
   c. Call LLM decision API with context
   d. LLM returns YES or NO
   e. If YES: proceed with response
   f. If NO: skip response
4. On error: default to responding for questions/requests
```

## Database Design

### Entity Relationship

```
┌──────────┐          ┌───────────┐
│  User    │          │  Message  │
├──────────┤          ├───────────┤
│ id (PK)  │          │ id (PK)   │
│ name     │          │ room_seq  │
│ email    │◄────────┤│ sender    │
│ password │ owns     │ text      │
│          │          │ timestamp │
└──────────┘          └───────────┘
```

### User Model
- Stores user credentials
- Hashes passwords with Werkzeug
- Unique constraints on email and username

### Message Model
- Stores chat messages
- Links to users via sender field
- Includes timestamps for ordering

## Real-Time Communication

### Socket.IO Events

**Client → Server:**
- `connect`: Establish connection with JWT
- `send.message`: Send chat message
- `run.stop`: Stop AI response

**Server → Client:**
- `room.snapshot`: Initial state (includes last 200 messages from database)
- `user.joined/left`: User presence updates
- `message.appended`: New message from user or AI
  - Used for both user messages and AI response chunks
  - Messages are complete (not character-by-character streaming)
- `assistant.started`: AI assistant started processing
- `assistant.completed`: AI finished responding
- `error`: Error notifications

**Note:** The `assistant.delta` event was removed in favor of complete message chunks sent via `message.appended`.

## AI Assistant Architecture

### Response Decision System

The AI assistant ("Midori") uses an intelligent decision-making system to determine when to respond:

**Components:**
1. **Fast Path**: Direct mentions bypass decision logic
2. **Context Building**: Gather last 6 messages for context
3. **Activity Detection**: Check if Midori was recently active
4. **LLM Decision**: Call LLM API to decide YES/NO
5. **Fallback Logic**: Default to responding on API errors

**Decision Factors:**
- Direct mentions (@Midori, Midori)
- Recent conversational context
- Whether Midori just asked a question
- Message content (questions, requests, emotional statements)
- User interaction patterns

### Response Chunking System

Long AI responses are automatically split into manageable chunks:

**Algorithm:**
1. Collect full response from LLM
2. Break into chunks at natural boundaries:
   - Paragraph breaks (double newlines)
   - Sentence endings (. ! ?)
   - Comma breaks (for very long sentences)
   - Word boundaries (last resort)
3. Maximum chunk size: ~300 characters
4. Emit each chunk as separate message
5. Add 0.3s delay between chunks for readability

**Benefits:**
- More conversational feel
- Easier to read on mobile
- Natural conversation pacing
- Better message grouping

### Connection Management

```javascript
// Client-side
socket = io(url, {
  auth: { token: jwtToken },
  transports: ['websocket', 'polling']
});

// Server-side
@socketio.on("connect")
def handle_connect(auth):
    token = auth.get("token")
    # Validate JWT
    # Store client info
    # Send snapshot
```

## Security Architecture

### Authentication
- JWT tokens for stateless authentication
- Tokens include user ID claim
- Tokens expire after 1 hour
- Refresh tokens not yet implemented

### Authorization
- WebSocket connections require valid JWT
- Guest access disabled by default
- CORS configured for specific origins
- Input validation on all endpoints

### Data Protection
- Passwords hashed with Werkzeug
- SQL injection prevented by ORM
- XSS prevented by proper escaping
- HTTPS enforced in production

## Scalability Considerations

### Current Implementation
- ✅ Messages persisted to database
- ✅ Message history loaded on startup
- ✅ Last 200 messages kept in memory for performance
- ❌ Single server instance
- ❌ No session persistence across servers
- ❌ No caching layer

### Current Limitations
- Single server instance (no horizontal scaling)
- No distributed session management
- No caching layer for frequently accessed data
- LLM API calls are blocking (no queue system)

### Future Improvements
1. **Message Management** ✅ (Implemented)
   - ✅ Store messages in database
   - Add message history pagination
   - Add message search functionality
   - Implement message editing/deletion

2. **Session Management**
   - Use Redis for session storage
   - Enable multi-server deployment
   - Implement sticky sessions

3. **Caching**
   - Cache user data
   - Cache recent messages
   - Use Redis for distributed cache

4. **Load Balancing**
   - Multiple app instances
   - Nginx load balancing
   - WebSocket sticky sessions

5. **Database Optimization**
   - Use PostgreSQL in production
   - Add database indexes
   - Implement connection pooling
   - Set up read replicas

6. **Background Processing**
   - Use Celery for async tasks
   - Queue LLM requests
   - Implement retry logic

## Error Handling

### Strategy
- Try-except blocks around critical code
- Specific error messages for debugging
- Generic messages for users
- Logging at appropriate levels

### HTTP Errors
- `400`: Bad request (validation errors)
- `401`: Unauthorized (auth failures)
- `404`: Not found
- `500`: Internal server error

### WebSocket Errors
- Sent as `error` events
- Include descriptive messages
- Log on server side
- Don't expose internal details

## Testing Strategy

### Unit Tests
- Test individual functions
- Mock external dependencies
- Use pytest fixtures
- Aim for >80% coverage

### Integration Tests
- Test API endpoints
- Test database operations
- Test authentication flow
- Use test database

### Manual Testing
- Test WebSocket connections
- Test real-time features
- Test across browsers
- Test on mobile devices

## Configuration Management

### Environment-Based Config
```python
config = {
    "development": DevelopmentConfig,
    "production": ProductionConfig,
    "testing": TestingConfig
}
```

### Settings Priority
1. Environment variables (.env)
2. Config class defaults
3. Application defaults

## Logging

### Log Levels
- **DEBUG**: Detailed information
- **INFO**: General information
- **WARNING**: Warning messages
- **ERROR**: Error messages
- **CRITICAL**: Critical failures

### Log Destinations
- Development: Console
- Production: Files + monitoring service

## Monitoring (Future)

### Metrics to Track
- Request rate and response times
- WebSocket connections
- LLM API latency
- Error rates
- User activity

### Tools to Consider
- Prometheus for metrics
- Grafana for visualization
- Sentry for error tracking
- ELK stack for log aggregation

## Technology Choices

### Why Flask?
- Lightweight and flexible
- Excellent for APIs
- Good ecosystem
- Easy to learn

### Why Socket.IO?
- Reliable WebSocket implementation
- Automatic fallback to polling
- Room support
- Wide browser support

### Why SQLAlchemy?
- Powerful ORM
- Database agnostic
- Great tooling
- Active community

### Why SQLite (dev) / PostgreSQL (prod)?
- SQLite: Simple, zero-config, file-based
- PostgreSQL: Production-ready, scalable, features

## Implemented Features ✅

1. **Message Persistence**
   - ✅ Messages saved to database
   - ✅ Message history loaded on startup
   - ✅ Last 200 messages kept in memory

2. **Smart AI Assistant**
   - ✅ Context-aware response decisions
   - ✅ LLM-based decision making
   - ✅ Intelligent message chunking
   - ✅ Named assistant (Midori)
   - ✅ Emotional awareness

3. **Modern Chat UI**
   - ✅ Chat bubbles for messages
   - ✅ Visual distinction between users
   - ✅ Gradient styling
   - ✅ Smooth animations
   - ✅ Character counter

## Future Enhancements

1. **User Features**
   - User profiles with avatars
   - User settings/preferences
   - Direct messages
   - User status (online/away/offline)
   - Read receipts

2. **Chat Features**
   - Multiple chat rooms
   - Message reactions/emojis
   - File sharing
   - Message editing/deletion
   - Message search
   - Mention notifications
   - Typing indicators

3. **AI Features**
   - Multiple AI models to choose from
   - Custom AI personalities
   - AI training on chat history
   - AI content moderation
   - Voice input/output
   - Image generation

4. **Admin Features**
   - Admin dashboard
   - User management
   - Content moderation tools
   - Analytics and metrics
   - Rate limiting
   - Ban/mute capabilities

5. **Performance**
   - Message pagination
   - Infinite scroll
   - Image lazy loading
   - WebP image format
   - Service workers for offline support

## Contributing

When adding new features:
1. Follow existing patterns
2. Add tests
3. Update documentation
4. Follow PEP 8 style guide
5. Add type hints
6. Write docstrings
