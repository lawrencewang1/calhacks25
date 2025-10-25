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
│   ├── css/             # Stylesheets
│   ├── js/              # JavaScript modules
│   └── images/          # Static images
└── templates/           # HTML pages (future: Jinja2)
```

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
3. Backend → Backend: Validate & store message
4. Backend → All Clients: Broadcast message
5. Backend → LLM API: Send message for processing
6. LLM API → Backend: Stream response chunks
7. Backend → All Clients: Stream AI response
8. Backend → Backend: Store AI response
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
- `room.snapshot`: Initial state
- `user.joined/left`: User presence
- `message.appended`: New message
- `assistant.delta`: AI streaming
- `assistant.completed`: AI finished
- `error`: Error notifications

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

### Current Limitations
- In-memory message storage (lost on restart)
- Single server instance
- No session persistence
- No caching layer

### Future Improvements
1. **Message Persistence**
   - Store messages in database
   - Implement message history pagination
   - Add message search functionality

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

## Future Enhancements

1. **User Features**
   - User profiles
   - Avatar uploads
   - User settings
   - Direct messages

2. **Chat Features**
   - Multiple chat rooms
   - Message reactions
   - File sharing
   - Message editing/deletion

3. **AI Features**
   - Multiple AI models
   - Custom AI personalities
   - AI training on chat history
   - AI moderation

4. **Admin Features**
   - Admin dashboard
   - User management
   - Content moderation
   - Analytics

## Contributing

When adding new features:
1. Follow existing patterns
2. Add tests
3. Update documentation
4. Follow PEP 8 style guide
5. Add type hints
6. Write docstrings
