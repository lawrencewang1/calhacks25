# API Documentation

This document describes the REST and WebSocket APIs for the Multiplayer AI Chat application.

## REST API Endpoints

### Base URL
```
http://localhost:5000/api
```

### Authentication

All authenticated endpoints require a JWT token in the Authorization header:
```
Authorization: Bearer <token>
```

---

## Auth Endpoints

### POST /auth/register

Register a new user account.

**Request Body:**
```json
{
  "name": "username",      // Optional - will be generated from email if not provided
  "email": "user@example.com",
  "password": "securepassword"
}
```

**Response (201 Created):**
```json
{
  "access_token": "eyJhbGci...",
  "user": {
    "id": 1,
    "name": "username",
    "email": "user@example.com"
  }
}
```

**Error Responses:**
- `400 Bad Request`: Missing required fields or user already exists
- `500 Internal Server Error`: Database error

---

### POST /auth/login

Login with existing credentials.

**Request Body:**
```json
{
  "email": "user@example.com",
  "password": "securepassword"
}
```

**Response (200 OK):**
```json
{
  "access_token": "eyJhbGci...",
  "user": {
    "id": 1,
    "name": "username",
    "email": "user@example.com"
  }
}
```

**Error Responses:**
- `401 Unauthorized`: Invalid credentials
- `400 Bad Request`: Missing required fields

---

## WebSocket API

### Connection

Connect to WebSocket at:
```
ws://localhost:5000/socket.io/
```

**Connection Parameters:**
```javascript
socket = io(url, {
  auth: {
    token: "eyJhbGci..."  // JWT token from login/register
  },
  transports: ['websocket', 'polling']
});
```

---

## Client → Server Events

### send.message

Send a chat message.

**Payload:**
```json
{
  "type": "send.message",
  "client_msg_id": "uuid-v4",
  "text": "Hello, world!"
}
```

---

### run.stop

Stop the AI assistant's current response.

**Payload:**
```json
{
  "type": "run.stop",
  "run_id": "uuid-v4"
}
```

---

## Server → Client Events

All server events are sent under the `"server"` event name.

### room.snapshot

Initial state sent upon connection.

**Payload:**
```json
{
  "type": "room.snapshot",
  "room_seq": 42,
  "users": [
    {"id": "socket-id", "name": "username"}
  ],
  "messages": [
    {
      "id": "msg-uuid",
      "sender": "user:username",
      "text": "Message text",
      "ts": 1234567890000
    }
  ]
}
```

---

### user.joined

A user joined the chat.

**Payload:**
```json
{
  "type": "user.joined",
  "room_seq": 43,
  "user": {
    "id": "socket-id",
    "name": "username"
  },
  "count": 5
}
```

---

### user.left

A user left the chat.

**Payload:**
```json
{
  "type": "user.left",
  "room_seq": 44,
  "user_id": "socket-id",
  "count": 4
}
```

---

### message.appended

A new message was sent.

**Payload:**
```json
{
  "type": "message.appended",
  "room_seq": 45,
  "message": {
    "id": "msg-uuid",
    "sender": "user:username",
    "text": "Message text",
    "ts": 1234567890000
  }
}
```

---

### assistant.started

The AI assistant started processing.

**Payload:**
```json
{
  "type": "assistant.started",
  "room_seq": 46,
  "run": {
    "run_id": "run-uuid",
    "parent_message_id": "msg-uuid"
  }
}
```

---

### assistant.delta

Streaming response from AI assistant.

**Payload:**
```json
{
  "type": "assistant.delta",
  "run_id": "run-uuid",
  "delta": "text chunk",
  "seq": 0
}
```

---

### assistant.completed

AI assistant finished responding.

**Payload:**
```json
{
  "type": "assistant.completed",
  "room_seq": 47,
  "run_id": "run-uuid",
  "final_text": "Complete response",
  "usage": {
    "in": 100,
    "out": 50
  }
}
```

---

### error

An error occurred.

**Payload:**
```json
{
  "type": "error",
  "message": "Error description"
}
```

---

## Message Format

### User Messages
- Sender format: `"user:<username>"`
- Example: `"user:alice"`

### Assistant Messages
- Sender format: `"assistant"`

### Timestamps
- Unix timestamp in milliseconds
- Example: `1234567890000`

---

## Rate Limiting

Currently no rate limiting is implemented.

**TODO for Production:**
- Add rate limiting to prevent abuse
- Implement per-user quotas
- Add CAPTCHA for registration

---

## Error Handling

### HTTP Status Codes
- `200`: Success
- `201`: Created
- `400`: Bad Request
- `401`: Unauthorized
- `404`: Not Found
- `500`: Internal Server Error

### WebSocket Errors
Errors are sent as `error` events with descriptive messages.

---

## Security Notes

**Current Implementation:**
- JWT tokens expire after 1 hour
- Passwords are hashed using Werkzeug
- Guest access is disabled by default

**Production Requirements:**
- Enable HTTPS
- Restrict CORS origins
- Implement rate limiting
- Add input validation
- Add content moderation
- Use secure JWT secrets
- Implement refresh tokens
