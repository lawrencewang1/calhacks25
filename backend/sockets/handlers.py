"""
WebSocket handlers for real-time chat functionality with multi-room support.

This module handles all Socket.IO events including:
- User connections and authentication
- Multi-room support (create, join, leave, switch rooms)
- Message sending and broadcasting per room
- AI assistant (Assistant) response generation with smart decision-making
- Message persistence to database
- Message chunking for better readability

Key Features:
- Multiple chatroom support
- LLM-based decision system for when AI should respond
- Automatic message chunking at natural boundaries
- Message history persistence across server restarts
- Context-aware AI responses per room
"""

import json
import time
import uuid
import re
import threading
from collections import deque

import httpx
from flask import request
from flask_socketio import join_room, leave_room
from flask_jwt_extended import decode_token
from flask_jwt_extended.exceptions import JWTExtendedException
from jwt.exceptions import InvalidTokenError, DecodeError

from backend.extensions import db
from backend.models.user import User
from backend.models.room import Room
from backend.models.message import Message
from backend.models.room_ban import RoomBan
from backend.models.saved_room import SavedRoom

class RoomState:
    """Manages state for a single chatroom with thread-safe operations."""
    def __init__(self, room_id: str):
        self.room_id = room_id
        self.room_seq = 0
        self.messages = deque(maxlen=200)
        self.clients = {}  # sid -> {"name": ..., "user_id": ...}
        self.active_runs = {}  # run_id -> {"stop": False}
        self.messages_loaded = False
        self._seq_lock = threading.Lock()  # Thread lock for room_seq

    def next_seq(self):
        """Generate the next sequence number for room events (thread-safe)."""
        with self._seq_lock:
            self.room_seq += 1
            return self.room_seq

    def snapshot(self, owner_id=None):
        """Generate a snapshot of the current room state.

        Args:
            owner_id: Optional room owner ID to include in snapshot
        """
        snapshot_data = {
            "type": "room.snapshot",
            "room_id": self.room_id,
            "room_seq": self.room_seq,
            "users": [{"id": sid, "name": c["name"], "user_id": c.get("user_id")} for sid, c in self.clients.items()],
            "messages": list(self.messages)
        }
        if owner_id is not None:
            snapshot_data["owner_id"] = owner_id
        return snapshot_data

# Global dictionary mapping room_id -> RoomState
rooms = {}
rooms_lock = threading.Lock()  # Thread lock for rooms dictionary

# Track which room each client is currently in: sid -> room_id
client_rooms = {}
client_rooms_lock = threading.Lock()  # Thread lock for client_rooms dictionary

# Track user info for each connected client: sid -> {"name": ..., "user_id": ...}
client_info = {}
client_info_lock = threading.Lock()  # Thread lock for client_info dictionary

def get_room_state(room_id: str) -> RoomState:
    """
    Get or create room state for the given room_id (thread-safe).

    Args:
        room_id: The room ID

    Returns:
        RoomState: The room state object
    """
    with rooms_lock:
        if room_id not in rooms:
            rooms[room_id] = RoomState(room_id)
        return rooms[room_id]


def _is_user_banned(app, room_id: str, user_id: int) -> tuple[bool, str]:
    """
    Check if a user is banned from a room.

    Args:
        app: Flask application instance
        room_id: The room ID
        user_id: The user ID to check

    Returns:
        tuple: (is_banned, reason) - True if banned with reason, False with empty string otherwise
    """
    try:
        with app.app_context():
            current_time = int(time.time() * 1000)

            # Check for active bans (permanent or not yet expired)
            ban = RoomBan.query.filter_by(
                room_id=room_id,
                user_id=user_id,
                is_active=True
            ).first()

            if not ban:
                return False, ""

            # Check if temp ban has expired
            if ban.expires_at and ban.expires_at < current_time:
                # Ban has expired, deactivate it
                ban.is_active = False
                db.session.commit()
                return False, ""

            # User is banned
            if ban.expires_at:
                # Temp ban
                time_left = (ban.expires_at - current_time) // 1000 // 60  # minutes
                return True, f"You are temporarily banned from this room ({time_left} minutes remaining)"
            else:
                # Permanent ban
                return True, "You are permanently banned from this room"
    except Exception as e:
        print(f"Error checking ban status: {e}")
        import traceback
        traceback.print_exc()
        return False, ""


def _load_messages_from_db(app, room_id: str):
    """
    Load recent messages from the database for a specific room.

    Loads the most recent messages (up to maxlen) from the database
    and restores the room_seq to continue from where it left off.

    Args:
        app: Flask application instance (for database access)
        room_id: The room ID to load messages for
    """
    room_state = get_room_state(room_id)

    if room_state.messages_loaded:
        return  # Already loaded

    try:
        with app.app_context():
            # Get the most recent messages for this room (limit to deque maxlen)
            recent_messages = Message.query.filter_by(
                room_id=room_id
            ).order_by(
                Message.room_seq.desc()
            ).limit(room_state.messages.maxlen).all()

            # Reverse to get chronological order
            recent_messages.reverse()

            # Load into memory
            for msg_record in recent_messages:
                room_state.messages.append({
                    "id": msg_record.id,
                    "sender": msg_record.sender,
                    "text": msg_record.text,
                    "ts": msg_record.timestamp
                })

            # Restore room_seq to the highest value
            if recent_messages:
                room_state.room_seq = max(msg.room_seq for msg in recent_messages)
                print(f"Loaded {len(recent_messages)} messages from database for room {room_id}. room_seq restored to {room_state.room_seq}")
            else:
                print(f"No messages found in database for room {room_id}")

            room_state.messages_loaded = True

    except Exception as e:
        print(f"Error loading messages from database for room {room_id}: {e}")
        import traceback
        traceback.print_exc()


def _moderate(text: str) -> bool:
    """
    Check if text contains banned content.

    PRODUCTION TODO: Implement proper content moderation.
    Consider using services like OpenAI Moderation API or similar.

    Args:
        text: The text to moderate

    Returns:
        bool: True if content is acceptable, False otherwise
    """
    banned = [r"\bslur1\b", r"\bslur2\b"]
    return not any(re.search(p, text, re.I) for p in banned)


def _extract_text_from_obj(obj: dict) -> str:
    """
    Extract text content from LLM API response.

    Be liberal in what we accept:
    - OpenAI stream: choices[0].delta.content
    - OpenAI non-stream: choices[0].message.content
    - Legacy text format: choices[0].text

    Args:
        obj: The response object from LLM API

    Returns:
        str: Extracted text or empty string
    """
    ch0 = (obj.get("choices") or [{}])[0]
    delta = (ch0.get("delta") or {}).get("content")
    if delta:
        return delta
    msg = (ch0.get("message") or {}).get("content")
    if msg:
        return msg
    txt = ch0.get("text")
    return txt or ""


def _parse_sse_chunk(raw: str):
    """
    Parse Server-Sent Events (SSE) chunks from LLM API.

    Yields text deltas from SSE lines like 'data: {...}'.

    Args:
        raw: Raw SSE response text

    Yields:
        str: Text delta from each SSE event
    """
    for line in raw.splitlines():
        if not line.startswith("data:"):
            continue
        data = line[5:].strip()
        if not data or data == "[DONE]":
            continue
        try:
            yield _extract_text_from_obj(json.loads(data))
        except json.JSONDecodeError:
            continue


def _chunk_text(text: str, max_length: int = 300) -> list[str]:
    """
    Break text into smaller chunks at natural boundaries.

    Tries to break at:
    1. Paragraph boundaries (double newlines)
    2. Sentence boundaries (. ! ?)
    3. Comma boundaries
    4. Word boundaries

    Args:
        text: The text to chunk
        max_length: Maximum length of each chunk

    Returns:
        list: List of text chunks
    """
    if len(text) <= max_length:
        return [text]

    chunks = []
    remaining = text

    while remaining:
        if len(remaining) <= max_length:
            chunks.append(remaining)
            break

        # Try to find a good break point
        chunk = remaining[:max_length]
        break_point = max_length

        # Try paragraph break first
        last_para = chunk.rfind('\n\n')
        if last_para > max_length * 0.3:  # At least 30% through
            break_point = last_para + 2
        else:
            # Try sentence break
            for punct in ['. ', '! ', '? ']:
                last_punct = chunk.rfind(punct)
                if last_punct > max_length * 0.5:  # At least 50% through
                    break_point = last_punct + 2
                    break
            else:
                # Try comma break
                last_comma = chunk.rfind(', ')
                if last_comma > max_length * 0.6:  # At least 60% through
                    break_point = last_comma + 2
                else:
                    # Try word boundary
                    last_space = chunk.rfind(' ')
                    if last_space > 0:
                        break_point = last_space + 1

        chunks.append(remaining[:break_point].rstrip())
        remaining = remaining[break_point:].lstrip()

    return chunks


def _safe_decode_jwt_with_app(token: str, app):
    """
    Safely decode a JWT token with proper app context.

    Args:
        token: The JWT token string
        app: Flask application instance

    Returns:
        dict: JWT claims if valid, None otherwise
    """
    if not token:
        print("No token provided")
        return None
    if token.count(".") != 2:
        print(f"Invalid token format (expected 2 dots, got {token.count('.')})")
        return None

    try:
        # Ensure we're in the app context for JWT decoding
        with app.app_context():
            print(f"Attempting to decode token...")
            claims = decode_token(token)
            print(f"Successfully decoded token. Claims: {claims}")
            return claims
    except (JWTExtendedException, InvalidTokenError, DecodeError) as e:
        print(f"JWT decode error: {type(e).__name__}: {e}")
        import traceback
        traceback.print_exc()
        return None
    except Exception as e:
        print(f"Unexpected JWT decode error: {type(e).__name__}: {e}")
        import traceback
        traceback.print_exc()
        return None


def _build_chat(user_text: str, room_state: RoomState, app):
    """
    Build chat context for LLM API request.

    Args:
        user_text: The user's message
        room_state: The room state object
        app: Flask application instance (for config)

    Returns:
        list: Chat messages formatted for LLM API
    """
    # Get configuration from app
    system_prompt = app.config.get("SYSTEM_PROMPT", "You are a helpful assistant.")
    context_messages = app.config.get("CHAT_CONTEXT_MESSAGES", 50)

    recent = list(room_state.messages)[-context_messages:]
    chat = [{"role": "system", "content": system_prompt}]

    for m in recent:
        chat.append({
            "role": "assistant" if m["sender"] == "assistant" else "user",
            "content": m["text"]
        })

    chat.append({"role": "user", "content": user_text})
    return chat


def _headers(app):
    """
    Generate headers for LLM API request.

    Args:
        app: Flask application instance (for config)

    Returns:
        dict: HTTP headers
    """
    auth_token = app.config.get("LLM_AUTH_TOKEN", "")
    return {"Authorization": auth_token, "Content-Type": "application/json"}


def _payload(messages, app):
    """
    Generate payload for LLM API request.

    Args:
        messages: Chat messages
        app: Flask application instance (for config)

    Returns:
        dict: Request payload
    """
    max_tokens = app.config.get("MAX_OUT_TOKENS", 400)
    return {"messages": messages, "stream": True, "max_tokens": max_tokens}


def _should_bot_respond(user_text: str, user_name: str, room_state: RoomState, app) -> bool:
    """
    Determine if the bot should respond to a message.

    Uses LLM API call with conversation context to intelligently decide
    if Assistant should respond. Considers recent conversation history and
    whether Assistant was recently active.

    Args:
        user_text: The user's message text
        user_name: The name of the user who sent the message
        room_state: The room state object
        app: Flask application instance

    Returns:
        bool: True if bot should respond, False otherwise
    """
    text_lower = user_text.lower()

    # Fast path: Always respond if directly mentioned by name or tag
    # Check for @mentions first
    if '@assistant' in text_lower or '@ai' in text_lower:
        print(f"Bot responding: directly mentioned with @")
        return True

    # Check for word-boundary mentions (assistant/ai as separate words)
    if re.search(r'\bassistant\b', text_lower) or re.search(r'\bai\b', text_lower):
        print(f"Bot responding: directly mentioned by name")
        return True

    # Check for indirect mentions/references to the bot
    indirect_mentions = [
        r'\bbot\b',
        r'\bhelp\s+me\b',
        r'\banyone\s+know\b',
        r'\bcan\s+someone\b',
        r'\bdoes\s+anyone\b',
        r'\bwhat\s+(do|does|should)\s+(you|we|i)\b'
    ]
    if any(re.search(pattern, text_lower) for pattern in indirect_mentions):
        print(f"Bot responding: indirect mention detected")
        return True

    # Build conversation context for LLM
    recent = list(room_state.messages)[-6:]  # Last 6 messages for context
    conversation_history = []

    for msg in recent:
        sender = msg.get('sender', 'unknown')
        # Format sender nicely
        if sender == 'assistant':
            formatted_sender = 'Assistant (AI assistant)'
        elif sender.startswith('user:'):
            formatted_sender = sender[5:]  # Remove 'user:' prefix
        else:
            formatted_sender = sender

        conversation_history.append(f"{formatted_sender}: {msg.get('text', '')}")

    # Check if Assistant just asked a question
    Assistant_just_asked = False
    if recent and recent[-1].get('sender') == 'assistant':
        last_bot_msg = recent[-1].get('text', '')
        Assistant_just_asked = '?' in last_bot_msg

    context_str = '\n'.join(conversation_history) if conversation_history else '(No recent messages)'

    # Use LLM to make decision
    try:
        # Build adaptive guidelines based on context
        guidelines = [
            "- RESPOND if someone references the bot indirectly (like 'what does the bot think?')",
            "- RESPOND if someone asks for help or information that Assistant can provide",
            "- RESPOND if someone asks 'can anyone help?' or 'does anyone know?' when no one else has answered",
            "- RESPOND if it's clearly a follow-up/reply to something Assistant specifically said or asked",
            "- RESPOND to genuine emotional expressions that seem like they want support (loneliness, sadness, anxiety)"
        ]

        if Assistant_just_asked:
            guidelines.insert(0, "- CRITICAL: Assistant just asked a question, and this is the user's response → DEFINITELY RESPOND")

        guidelines.extend([
            "- DON'T respond to greetings between specific users (like 'hey John')",
            "- DON'T respond to generic greetings unless it seems like they're welcoming Assistant",
            "- DON'T respond to small talk between users (like 'what are u up to', 'doing alright')",
            "- DON'T respond to users clearly having a 1-on-1 conversation about personal matters",
            "- DON'T respond to rhetorical questions or statements not looking for an answer",
            "- When uncertain, lean slightly towards NOT responding to avoid interrupting"
        ])

        decision_prompt = f"""You are deciding if Assistant (an AI assistant) should respond in a group chat.

CURRENT MESSAGE:
{user_name}: "{user_text}"

RECENT CONVERSATION:
{context_str}

GUIDELINES:
{chr(10).join(guidelines)}

Should Assistant respond?
Reply with ONLY: YES or NO"""

        with httpx.Client() as client:
            resp = client.post(
                app.config.get("LLM_API_URL", ""),
                headers=_headers(app),
                json={
                    "messages": [{"role": "user", "content": decision_prompt}],
                    "max_tokens": 100,
                    "stream": False,
                    "temperature": 0.2  # Lower temperature for more consistent decisions
                },
                timeout=5.0
            )
            resp.raise_for_status()

            # Get response text and try to parse as JSON
            response_text = resp.text.strip()
            if not response_text:
                print("Warning: Empty response from LLM decision API, defaulting to respond")
                return True

            try:
                body = resp.json()
                decision = _extract_text_from_obj(body).strip().upper()
            except json.JSONDecodeError:
                # Response is not JSON, treat it as plain text
                print(f"Non-JSON response from decision API: {response_text[:100]}")
                decision = response_text.upper()

            should_respond = "YES" in decision
            print(f"Bot decision for '{user_text[:50]}...': {decision} -> {should_respond}")
            return should_respond

    except httpx.HTTPStatusError as e:
        print(f"HTTP error in response decision: {e.response.status_code}, defaulting to lenient response")
        # More lenient default: respond to most things except very short messages
        if len(user_text.split()) <= 2 and '?' not in user_text:
            return False
        return True  # Default to responding
    except Exception as e:
        print(f"Error in response decision: {e}, defaulting to lenient response")
        import traceback
        traceback.print_exc()
        # More lenient default: respond to most things except very short messages
        if len(user_text.split()) <= 2 and '?' not in user_text:
            return False
        return True  # Default to responding


def _llm_stream_task(socketio, run_id: str, user_text: str, room_id: str, app):
    """
    Collect full LLM response and emit as complete message chunks.

    Collects the full response from the LLM API, breaks it into chunks at
    natural boundaries (paragraphs, sentences), and emits each chunk as a
    complete message with a small delay between chunks for better UX.

    Args:
        socketio: SocketIO instance
        run_id: Unique ID for this LLM run
        user_text: User's message text
        room_id: The room ID
        app: Flask application instance
    """
    print(f'STARTING STREAM in room {room_id}: {user_text}')
    room_state = get_room_state(room_id)
    ctrl = room_state.active_runs.get(run_id)
    final = []
    sent_any_delta = False

    llm_api_url = app.config.get("LLM_API_URL", "")

    try:
        # Collect the full response without emitting deltas
        with httpx.stream(
            "POST", llm_api_url, headers=_headers(app),
            json=_payload(_build_chat(user_text, room_state, app), app), timeout=60.0
        ) as resp:
            resp.raise_for_status()
            collected_raw = []
            for chunk in resp.iter_text():
                if ctrl and ctrl.get("stop"):
                    break
                collected_raw.append(chunk)
                for delta in _parse_sse_chunk(chunk):
                    sent_any_delta = True
                    final.append(delta)

        # Fallback: if server didn't stream SSE, parse JSON body once
        if not sent_any_delta:
            try:
                # Combine the whole response and parse as JSON
                body = "".join(collected_raw).strip()
                obj = json.loads(body)
                text_once = _extract_text_from_obj(obj)
                if text_once:
                    final.append(text_once)
            except Exception:
                pass

        # Finalize
        final_text = "".join(final).strip()

        # If the policy told the model to not respond, just complete without appending
        if final_text == "[NO_RESPONSE]":
            socketio.emit("server",
                {"type": "assistant.completed", "room_seq": room_state.next_seq(), "run_id": run_id,
                 "final_text": "", "usage": {"in": 0, "out": 0}},
                room=room_id
            )
            return

        if final_text:
            # Break the response into chunks at natural boundaries
            chunks = _chunk_text(final_text, max_length=300)

            # Emit each chunk as a complete message
            for i, chunk in enumerate(chunks):
                msg = {
                    "id": str(uuid.uuid4()),
                    "sender": "assistant",
                    "text": chunk,
                    "ts": int(time.time() * 1000)
                }

                # Persist assistant message to database
                seq = room_state.next_seq()
                room_state.messages.append(msg)

                try:
                    # Use app context since we're in a background thread
                    with app.app_context():
                        msg_record = Message(
                            id=msg["id"],
                            room_id=room_id,
                            room_seq=seq,
                            sender=msg["sender"],
                            text=msg["text"],
                            timestamp=msg["ts"]
                        )
                        db.session.add(msg_record)
                        db.session.commit()
                except Exception as e:
                    print(f"Error persisting assistant message to database: {e}")
                    try:
                        with app.app_context():
                            db.session.rollback()
                    except:
                        pass

                # Emit the chunk as a complete message
                socketio.emit("server",
                    {"type": "message.appended", "room_seq": seq, "message": msg},
                    room=room_id
                )

                # Small delay between chunks for better UX (0.3 seconds)
                if i < len(chunks) - 1:
                    time.sleep(0.3)

        socketio.emit("server",
            {"type": "assistant.completed", "room_seq": room_state.next_seq(), "run_id": run_id,
             "final_text": final_text, "usage": {"in": 0, "out": 0}},
            room=room_id
        )
    except httpx.HTTPStatusError as e:
        socketio.emit("server",
            {"type": "error", "message": f"LLM HTTP {e.response.status_code}: {e.response.text[:200]}"},
            room=room_id)
    except Exception as e:
        socketio.emit("server", {"type": "error", "message": f"LLM error: {e}"},
            room=room_id)
    finally:
        room_state.active_runs.pop(run_id, None)


def _llm_stream_task_dm(socketio, run_id: str, user_text: str, room_id: str, app, target_sid: str):
    """
    LLM stream task for DMs - sends messages only to a specific user.

    Args:
        socketio: SocketIO instance
        run_id: Unique ID for this LLM run
        user_text: User's message text
        room_id: The DM room ID
        app: Flask application instance
        target_sid: Socket ID of the user to send messages to
    """
    print(f'STARTING DM STREAM for {target_sid} in room {room_id}: {user_text}')
    room_state = get_room_state(room_id)
    ctrl = room_state.active_runs.get(run_id)
    final = []
    sent_any_delta = False

    llm_api_url = app.config.get("LLM_API_URL", "")

    try:
        # Collect the full response without emitting deltas
        with httpx.stream(
            "POST", llm_api_url, headers=_headers(app),
            json=_payload(_build_chat(user_text, room_state, app), app), timeout=60.0
        ) as resp:
            resp.raise_for_status()
            collected_raw = []
            for chunk in resp.iter_text():
                if ctrl and ctrl.get("stop"):
                    break
                collected_raw.append(chunk)
                for delta in _parse_sse_chunk(chunk):
                    sent_any_delta = True
                    final.append(delta)

        # Fallback: if server didn't stream SSE, parse JSON body once
        if not sent_any_delta:
            try:
                body = "".join(collected_raw).strip()
                obj = json.loads(body)
                text_once = _extract_text_from_obj(obj)
                if text_once:
                    final.append(text_once)
            except Exception:
                pass

        # Finalize
        final_text = "".join(final).strip()

        if final_text == "[NO_RESPONSE]":
            socketio.emit("server",
                {"type": "assistant.completed", "room_seq": room_state.next_seq(), "run_id": run_id,
                 "final_text": "", "usage": {"in": 0, "out": 0}},
                to=target_sid
            )
            return

        if final_text:
            # Break the response into chunks at natural boundaries
            chunks = _chunk_text(final_text, max_length=300)

            # Emit each chunk as a complete message (only to the target user)
            for i, chunk in enumerate(chunks):
                msg = {
                    "id": str(uuid.uuid4()),
                    "sender": "assistant",
                    "text": chunk,
                    "ts": int(time.time() * 1000)
                }

                # Persist assistant message to database
                seq = room_state.next_seq()
                room_state.messages.append(msg)

                try:
                    with app.app_context():
                        msg_record = Message(
                            id=msg["id"],
                            room_id=room_id,
                            room_seq=seq,
                            sender=msg["sender"],
                            text=msg["text"],
                            timestamp=msg["ts"]
                        )
                        db.session.add(msg_record)
                        db.session.commit()
                except Exception as e:
                    print(f"Error persisting DM assistant message to database: {e}")
                    try:
                        with app.app_context():
                            db.session.rollback()
                    except:
                        pass

                # Emit the chunk only to the specific user
                socketio.emit("server",
                    {"type": "dm.message", "room_seq": seq, "message": msg},
                    to=target_sid
                )

                # Small delay between chunks for better UX (0.3 seconds)
                if i < len(chunks) - 1:
                    time.sleep(0.3)

        socketio.emit("server",
            {"type": "assistant.completed", "room_seq": room_state.next_seq(), "run_id": run_id,
             "final_text": final_text, "usage": {"in": 0, "out": 0}},
            to=target_sid
        )
    except httpx.HTTPStatusError as e:
        socketio.emit("server",
            {"type": "error", "message": f"LLM HTTP {e.response.status_code}: {e.response.text[:200]}"},
            to=target_sid)
    except Exception as e:
        socketio.emit("server", {"type": "error", "message": f"LLM error: {e}"},
            to=target_sid)
    finally:
        room_state.active_runs.pop(run_id, None)


def register_socketio(socketio, app):
    """
    Register Socket.IO event handlers with multi-room support.

    Args:
        socketio: SocketIO instance
        app: Flask application instance
    """
    allow_guests = app.config.get("ALLOW_GUESTS", False)

    @socketio.on("connect")
    def _on_connect(auth):
        """Handle client connection."""
        print("WS connect:", {"sid": request.sid, "auth": auth})

        # auth is a dict sent by the client: { token, name? }
        token = (auth or {}).get("token")
        name = ((auth or {}).get("name") or "anon")[:24]

        print(f"Token present: {bool(token)}, Token value: {token[:20] if token else 'None'}...")

        user_id = None
        claims = _safe_decode_jwt_with_app(token, app)
        print(f"JWT claims decoded: {claims}")

        if claims:
            user_id = claims.get("sub") or claims.get("identity")
            print(f"User ID from JWT: {user_id}")

            # Look up display name from DB
            try:
                # Convert user_id to int for database query
                user_id_int = int(user_id) if user_id else None
                u = User.query.get(user_id_int)
                if u:
                    # Use the user's name from the database
                    if getattr(u, "name", None):
                        name = u.name
                    elif getattr(u, "email", None):
                        name = u.email.split("@")[0]
                    print(f"User found in DB: {name}")
                else:
                    print(f"User ID {user_id} not found in database")
            except ValueError as e:
                print(f"Invalid user ID format: {user_id} - {e}")
            except Exception as e:
                print(f"Error fetching user from DB: {e}")

        elif not allow_guests:
            # Reject unauthenticated sockets
            print(f"Connection rejected: ALLOW_GUESTS={allow_guests}, claims={claims}")
            return False  # tells Socket.IO to refuse the connection

        # Store client info (not yet in any room)
        client_rooms[request.sid] = None
        client_info[request.sid] = {"name": name, "user_id": user_id}

        # Send list of available rooms (official, public community, user's own rooms, and saved rooms)
        try:
            with app.app_context():
                official_rooms = Room.query.filter_by(is_active=True, is_official=True).all()
                community_rooms = Room.query.filter_by(is_active=True, is_official=False, is_public=True).all()

                # Get user's own rooms (both public and private)
                my_rooms = []
                saved_rooms = []
                if user_id:
                    my_rooms = Room.query.filter_by(is_active=True, created_by=int(user_id)).all()

                    # Get saved rooms (rooms user has joined but didn't create)
                    saved_room_entries = SavedRoom.query.filter_by(user_id=int(user_id)).all()
                    saved_room_ids = [sr.room_id for sr in saved_room_entries]
                    if saved_room_ids:
                        # Get the actual room objects, excluding rooms the user created
                        saved_rooms = Room.query.filter(
                            Room.id.in_(saved_room_ids),
                            Room.is_active == True,
                            Room.created_by != int(user_id)
                        ).all()

                official_list = [r.to_dict() for r in official_rooms]
                community_list = [r.to_dict() for r in community_rooms]
                my_rooms_list = [r.to_dict() for r in my_rooms]
                saved_rooms_list = [r.to_dict() for r in saved_rooms]

                socketio.emit("server", {
                    "type": "rooms.list",
                    "official_rooms": official_list,
                    "community_rooms": community_list,
                    "my_rooms": my_rooms_list,
                    "saved_rooms": saved_rooms_list,
                    "user_info": {"name": name, "user_id": user_id}
                }, to=request.sid)
        except Exception as e:
            print(f"Error fetching rooms: {e}")
            socketio.emit("server", {
                "type": "rooms.list",
                "official_rooms": [],
                "community_rooms": [],
                "my_rooms": [],
                "saved_rooms": [],
                "user_info": {"name": name, "user_id": user_id}
            }, to=request.sid)

    @socketio.on("disconnect")
    def _on_disconnect():
        """Handle client disconnection."""
        print("WS disconnect:", request.sid)

        # Leave current room if in one
        current_room = client_rooms.get(request.sid)
        if current_room and current_room in rooms:
            room_state = rooms[current_room]
            if request.sid in room_state.clients:
                room_state.clients.pop(request.sid, None)
                seq = room_state.next_seq()
                socketio.emit("server", {
                    "type": "user.left",
                    "room_seq": seq,
                    "user_id": request.sid,
                    "count": len(room_state.clients)
                }, room=current_room)

        client_rooms.pop(request.sid, None)
        client_info.pop(request.sid, None)

    @socketio.on("client")
    def _on_client(msg):
        """Handle client messages."""
        print("WS event:", msg)
        t = msg.get("type")

        if t == "room.join":
            # Handle room join request
            room_id = msg.get("room_id")
            if not room_id:
                socketio.emit("server", {
                    "type": "error",
                    "message": "No room_id provided"
                }, to=request.sid)
                return

            # Get user info and check for bans
            user_info = client_info.get(request.sid, {"name": "anon", "user_id": None})
            user_id = user_info["user_id"]

            # Check if user is banned from this room
            if user_id:
                is_banned, ban_reason = _is_user_banned(app, room_id, int(user_id))
                if is_banned:
                    socketio.emit("server", {
                        "type": "error",
                        "message": ban_reason
                    }, to=request.sid)
                    return

            # Get or create room state
            room_state = get_room_state(room_id)

            # Load messages for this room if not loaded yet
            _load_messages_from_db(app, room_id)

            # Leave current room if in one
            current_room = client_rooms.get(request.sid)
            if current_room:
                if current_room in rooms:
                    old_room_state = rooms[current_room]
                    old_room_state.clients.pop(request.sid, None)
                    socketio.emit("server", {
                        "type": "user.left",
                        "room_seq": old_room_state.next_seq(),
                        "user_id": request.sid,
                        "count": len(old_room_state.clients)
                    }, room=current_room)
                leave_room(current_room)

            # Join new room
            join_room(room_id)
            client_rooms[request.sid] = room_id

            # Get user info from stored client info (set during connection)
            user_info = client_info.get(request.sid, {"name": "anon", "user_id": None})
            user_name = user_info["name"]
            user_id = user_info["user_id"]

            room_state.clients[request.sid] = {"name": user_name, "user_id": user_id}

            # Query room from database to get owner ID and auto-save private rooms
            room_owner_id = None
            try:
                with app.app_context():
                    room = Room.query.get(room_id)
                    if room:
                        room_owner_id = room.created_by

                        # Auto-save private rooms when a user joins (if not the owner)
                        if user_id and not room.is_public and room.created_by != int(user_id):
                            # Check if already saved
                            existing_save = SavedRoom.query.filter_by(
                                user_id=int(user_id),
                                room_id=room_id
                            ).first()

                            if not existing_save:
                                # Save the room for this user
                                saved_room = SavedRoom(
                                    user_id=int(user_id),
                                    room_id=room_id
                                )
                                db.session.add(saved_room)
                                db.session.commit()
                                print(f"Auto-saved private room {room_id} for user {user_id}")

                                # Notify the user that the room was saved
                                socketio.emit("server", {
                                    "type": "room.saved",
                                    "room": room.to_dict(),
                                    "message": "Room saved to your list"
                                }, to=request.sid)
            except Exception as e:
                print(f"Error fetching room owner or saving room: {e}")

            # Send snapshot to this client
            socketio.emit("server", room_state.snapshot(owner_id=room_owner_id), to=request.sid)

            # Notify the room
            seq = room_state.next_seq()
            socketio.emit("server", {
                "type": "user.joined",
                "room_seq": seq,
                "user": {"id": request.sid, "name": user_name, "user_id": user_id},
                "count": len(room_state.clients)
            }, room=room_id)

        elif t == "room.create":
            # Handle room creation
            room_name = msg.get("room_name", "").strip()
            is_public = msg.get("is_public", True)  # Default to public

            if not room_name:
                socketio.emit("server", {
                    "type": "error",
                    "message": "Room name is required"
                }, to=request.sid)
                return

            # Get user ID from stored client info
            user_info = client_info.get(request.sid, {"name": "anon", "user_id": None})
            user_id = user_info["user_id"]

            if not user_id:
                socketio.emit("server", {
                    "type": "error",
                    "message": "Must be logged in to create a room"
                }, to=request.sid)
                return

            # Create room in database
            try:
                with app.app_context():
                    new_room = Room(
                        name=room_name,
                        created_by=int(user_id),
                        is_official=False,  # User-created rooms are never official
                        is_public=is_public
                    )
                    db.session.add(new_room)
                    db.session.commit()

                    # Get official and public community rooms
                    official_rooms = Room.query.filter_by(is_active=True, is_official=True).all()
                    community_rooms = Room.query.filter_by(is_active=True, is_official=False, is_public=True).all()

                    official_list = [r.to_dict() for r in official_rooms]
                    community_list = [r.to_dict() for r in community_rooms]

                    socketio.emit("server", {
                        "type": "room.created",
                        "room": new_room.to_dict()
                    }, to=request.sid)

                    # Broadcast updated room lists to all connected clients
                    # Note: my_rooms will be calculated per-client when they connect
                    socketio.emit("server", {
                        "type": "rooms.list.update",
                        "official_rooms": official_list,
                        "community_rooms": community_list
                    })

            except Exception as e:
                print(f"Error creating room: {e}")
                import traceback
                traceback.print_exc()
                with app.app_context():
                    db.session.rollback()
                socketio.emit("server", {
                    "type": "error",
                    "message": "Failed to create room"
                }, to=request.sid)

        elif t == "room.delete":
            # Handle room deletion
            room_id = msg.get("room_id")
            if not room_id:
                socketio.emit("server", {
                    "type": "error",
                    "message": "Room ID is required"
                }, to=request.sid)
                return

            # Get user ID from stored client info
            user_info = client_info.get(request.sid, {"name": "anon", "user_id": None})
            user_id = user_info["user_id"]

            if not user_id:
                socketio.emit("server", {
                    "type": "error",
                    "message": "Must be logged in to delete a room"
                }, to=request.sid)
                return

            # Delete room in database
            try:
                with app.app_context():
                    room = Room.query.get(room_id)
                    if not room:
                        socketio.emit("server", {
                            "type": "error",
                            "message": "Room not found"
                        }, to=request.sid)
                        return

                    # Check if user is the owner
                    if room.created_by != int(user_id):
                        socketio.emit("server", {
                            "type": "error",
                            "message": "You can only delete rooms you created"
                        }, to=request.sid)
                        return

                    # Don't allow deleting official rooms
                    if room.is_official:
                        socketio.emit("server", {
                            "type": "error",
                            "message": "Cannot delete official rooms"
                        }, to=request.sid)
                        return

                    # Soft delete (mark as inactive)
                    room.is_active = False
                    db.session.commit()

                    # Get updated room lists
                    official_rooms = Room.query.filter_by(is_active=True, is_official=True).all()
                    community_rooms = Room.query.filter_by(is_active=True, is_official=False, is_public=True).all()

                    official_list = [r.to_dict() for r in official_rooms]
                    community_list = [r.to_dict() for r in community_rooms]

                    # Notify the user
                    socketio.emit("server", {
                        "type": "room.deleted",
                        "room_id": room_id
                    }, to=request.sid)

                    # Broadcast updated room lists to all connected clients
                    socketio.emit("server", {
                        "type": "rooms.list.update",
                        "official_rooms": official_list,
                        "community_rooms": community_list
                    })

                    # Kick all users from the deleted room
                    if room_id in rooms:
                        room_state = rooms[room_id]
                        for sid in list(room_state.clients.keys()):
                            socketio.emit("server", {
                                "type": "room.closed",
                                "message": "This room has been deleted by the owner"
                            }, to=sid)

            except Exception as e:
                print(f"Error deleting room: {e}")
                import traceback
                traceback.print_exc()
                with app.app_context():
                    db.session.rollback()
                socketio.emit("server", {
                    "type": "error",
                    "message": "Failed to delete room"
                }, to=request.sid)

        elif t == "user.kick":
            # Handle kicking a user from a room
            room_id = msg.get("room_id")
            target_user_id = msg.get("target_user_id")

            if not room_id or not target_user_id:
                socketio.emit("server", {
                    "type": "error",
                    "message": "Room ID and target user ID are required"
                }, to=request.sid)
                return

            # Get user ID from stored client info
            user_info = client_info.get(request.sid, {"name": "anon", "user_id": None})
            user_id = user_info["user_id"]

            if not user_id:
                socketio.emit("server", {
                    "type": "error",
                    "message": "Must be logged in to kick users"
                }, to=request.sid)
                return

            try:
                with app.app_context():
                    room = Room.query.get(room_id)
                    if not room:
                        socketio.emit("server", {
                            "type": "error",
                            "message": "Room not found"
                        }, to=request.sid)
                        return

                    # Check if user is the room owner
                    if room.created_by != int(user_id):
                        socketio.emit("server", {
                            "type": "error",
                            "message": "Only the room owner can kick users"
                        }, to=request.sid)
                        return

                    # Find the target user's socket ID
                    target_sid = None
                    if room_id in rooms:
                        room_state = rooms[room_id]
                        for sid, info in room_state.clients.items():
                            if info.get("user_id") == target_user_id:
                                target_sid = sid
                                break

                    if target_sid:
                        # Remove from room state
                        room_state.clients.pop(target_sid, None)

                        # Send kick notification to the kicked user
                        socketio.emit("server", {
                            "type": "user.kicked",
                            "message": "You have been kicked from the room by the owner"
                        }, to=target_sid)

                        # Leave the room
                        leave_room(room_id, sid=target_sid)
                        client_rooms[target_sid] = None

                        # Notify others in the room
                        socketio.emit("server", {
                            "type": "user.left",
                            "room_seq": room_state.next_seq(),
                            "user_id": target_sid,
                            "count": len(room_state.clients)
                        }, room=room_id)

                    # Confirm to the requester
                    socketio.emit("server", {
                        "type": "user.kick.success",
                        "message": "User has been kicked"
                    }, to=request.sid)

            except Exception as e:
                print(f"Error kicking user: {e}")
                import traceback
                traceback.print_exc()
                socketio.emit("server", {
                    "type": "error",
                    "message": "Failed to kick user"
                }, to=request.sid)

        elif t == "user.tempban":
            # Handle temporarily banning a user (24 hours)
            room_id = msg.get("room_id")
            target_user_id = msg.get("target_user_id")

            if not room_id or not target_user_id:
                socketio.emit("server", {
                    "type": "error",
                    "message": "Room ID and target user ID are required"
                }, to=request.sid)
                return

            # Get user ID from stored client info
            user_info = client_info.get(request.sid, {"name": "anon", "user_id": None})
            user_id = user_info["user_id"]

            if not user_id:
                socketio.emit("server", {
                    "type": "error",
                    "message": "Must be logged in to ban users"
                }, to=request.sid)
                return

            try:
                with app.app_context():
                    room = Room.query.get(room_id)
                    if not room:
                        socketio.emit("server", {
                            "type": "error",
                            "message": "Room not found"
                        }, to=request.sid)
                        return

                    # Check if user is the room owner
                    if room.created_by != int(user_id):
                        socketio.emit("server", {
                            "type": "error",
                            "message": "Only the room owner can ban users"
                        }, to=request.sid)
                        return

                    # Check if user is trying to ban themselves
                    if int(target_user_id) == int(user_id):
                        socketio.emit("server", {
                            "type": "error",
                            "message": "You cannot ban yourself"
                        }, to=request.sid)
                        return

                    # Get custom duration or default to 24 hours
                    duration_ms = msg.get("duration")
                    if not duration_ms or duration_ms <= 0:
                        duration_ms = 24 * 60 * 60 * 1000  # Default: 24 hours in milliseconds

                    # Create temp ban
                    current_time = int(time.time() * 1000)
                    expires_at = current_time + duration_ms

                    # Deactivate any existing bans
                    existing_bans = RoomBan.query.filter_by(
                        room_id=room_id,
                        user_id=int(target_user_id),
                        is_active=True
                    ).all()
                    for ban in existing_bans:
                        ban.is_active = False

                    # Create new ban
                    new_ban = RoomBan(
                        room_id=room_id,
                        user_id=int(target_user_id),
                        banned_by=int(user_id),
                        expires_at=expires_at,
                        reason="Temporarily banned by room owner"
                    )
                    db.session.add(new_ban)
                    db.session.commit()

                    # Find the target user's socket ID and kick them
                    target_sid = None
                    if room_id in rooms:
                        room_state = rooms[room_id]
                        for sid, info in room_state.clients.items():
                            if info.get("user_id") == target_user_id:
                                target_sid = sid
                                break

                        if target_sid:
                            # Remove from room state
                            room_state.clients.pop(target_sid, None)

                            # Send ban notification to the banned user
                            socketio.emit("server", {
                                "type": "user.banned",
                                "message": "You have been temporarily banned from this room for 24 hours"
                            }, to=target_sid)

                            # Leave the room
                            leave_room(room_id, sid=target_sid)
                            client_rooms[target_sid] = None

                            # Notify others in the room
                            socketio.emit("server", {
                                "type": "user.left",
                                "room_seq": room_state.next_seq(),
                                "user_id": target_sid,
                                "count": len(room_state.clients)
                            }, room=room_id)

                    # Confirm to the requester
                    socketio.emit("server", {
                        "type": "user.tempban.success",
                        "message": "User has been temporarily banned for 24 hours"
                    }, to=request.sid)

            except Exception as e:
                print(f"Error temp banning user: {e}")
                import traceback
                traceback.print_exc()
                with app.app_context():
                    db.session.rollback()
                socketio.emit("server", {
                    "type": "error",
                    "message": "Failed to temp ban user"
                }, to=request.sid)

        elif t == "user.ban":
            # Handle permanently banning a user
            room_id = msg.get("room_id")
            target_user_id = msg.get("target_user_id")

            if not room_id or not target_user_id:
                socketio.emit("server", {
                    "type": "error",
                    "message": "Room ID and target user ID are required"
                }, to=request.sid)
                return

            # Get user ID from stored client info
            user_info = client_info.get(request.sid, {"name": "anon", "user_id": None})
            user_id = user_info["user_id"]

            if not user_id:
                socketio.emit("server", {
                    "type": "error",
                    "message": "Must be logged in to ban users"
                }, to=request.sid)
                return

            try:
                with app.app_context():
                    room = Room.query.get(room_id)
                    if not room:
                        socketio.emit("server", {
                            "type": "error",
                            "message": "Room not found"
                        }, to=request.sid)
                        return

                    # Check if user is the room owner
                    if room.created_by != int(user_id):
                        socketio.emit("server", {
                            "type": "error",
                            "message": "Only the room owner can ban users"
                        }, to=request.sid)
                        return

                    # Check if user is trying to ban themselves
                    if int(target_user_id) == int(user_id):
                        socketio.emit("server", {
                            "type": "error",
                            "message": "You cannot ban yourself"
                        }, to=request.sid)
                        return

                    # Deactivate any existing bans
                    existing_bans = RoomBan.query.filter_by(
                        room_id=room_id,
                        user_id=int(target_user_id),
                        is_active=True
                    ).all()
                    for ban in existing_bans:
                        ban.is_active = False

                    # Create permanent ban (expires_at = None)
                    new_ban = RoomBan(
                        room_id=room_id,
                        user_id=int(target_user_id),
                        banned_by=int(user_id),
                        expires_at=None,
                        reason="Permanently banned by room owner"
                    )
                    db.session.add(new_ban)
                    db.session.commit()

                    # Find the target user's socket ID and kick them
                    target_sid = None
                    if room_id in rooms:
                        room_state = rooms[room_id]
                        for sid, info in room_state.clients.items():
                            if info.get("user_id") == target_user_id:
                                target_sid = sid
                                break

                        if target_sid:
                            # Remove from room state
                            room_state.clients.pop(target_sid, None)

                            # Send ban notification to the banned user
                            socketio.emit("server", {
                                "type": "user.banned",
                                "message": "You have been permanently banned from this room"
                            }, to=target_sid)

                            # Leave the room
                            leave_room(room_id, sid=target_sid)
                            client_rooms[target_sid] = None

                            # Notify others in the room
                            socketio.emit("server", {
                                "type": "user.left",
                                "room_seq": room_state.next_seq(),
                                "user_id": target_sid,
                                "count": len(room_state.clients)
                            }, room=room_id)

                    # Confirm to the requester
                    socketio.emit("server", {
                        "type": "user.ban.success",
                        "message": "User has been permanently banned"
                    }, to=request.sid)

            except Exception as e:
                print(f"Error permanently banning user: {e}")
                import traceback
                traceback.print_exc()
                with app.app_context():
                    db.session.rollback()
                socketio.emit("server", {
                    "type": "error",
                    "message": "Failed to ban user"
                }, to=request.sid)

        elif t == "user.bans.list":
            # Handle fetching ban list for a room
            room_id = msg.get("room_id")

            if not room_id:
                socketio.emit("server", {
                    "type": "error",
                    "message": "Room ID is required"
                }, to=request.sid)
                return

            # Get user ID from stored client info
            user_info = client_info.get(request.sid, {"name": "anon", "user_id": None})
            user_id = user_info["user_id"]

            if not user_id:
                socketio.emit("server", {
                    "type": "error",
                    "message": "Must be logged in to view ban list"
                }, to=request.sid)
                return

            try:
                with app.app_context():
                    room = Room.query.get(room_id)
                    if not room:
                        socketio.emit("server", {
                            "type": "error",
                            "message": "Room not found"
                        }, to=request.sid)
                        return

                    # Check if user is the room owner
                    if room.created_by != int(user_id):
                        socketio.emit("server", {
                            "type": "error",
                            "message": "Only the room owner can view ban list"
                        }, to=request.sid)
                        return

                    # Get all active bans for this room
                    bans = RoomBan.query.filter_by(room_id=room_id, is_active=True).all()

                    # Build ban list with user info
                    ban_list = []
                    for ban in bans:
                        # Check if temp ban has expired
                        if ban.is_expired():
                            ban.is_active = False
                            db.session.commit()
                            continue

                        # Get user info
                        banned_user = User.query.get(ban.user_id)
                        banned_by_user = User.query.get(ban.banned_by)

                        ban_info = ban.to_dict()
                        if banned_user:
                            ban_info['banned_user_name'] = getattr(banned_user, 'name', None) or getattr(banned_user, 'email', '').split('@')[0]
                        if banned_by_user:
                            ban_info['banned_by_name'] = getattr(banned_by_user, 'name', None) or getattr(banned_by_user, 'email', '').split('@')[0]

                        ban_list.append(ban_info)

                    socketio.emit("server", {
                        "type": "user.bans.list",
                        "room_id": room_id,
                        "bans": ban_list
                    }, to=request.sid)

            except Exception as e:
                print(f"Error fetching ban list: {e}")
                import traceback
                traceback.print_exc()
                socketio.emit("server", {
                    "type": "error",
                    "message": "Failed to fetch ban list"
                }, to=request.sid)

        elif t == "user.unban":
            # Handle unbanning a user
            room_id = msg.get("room_id")
            ban_id = msg.get("ban_id")
            target_user_id = msg.get("target_user_id")

            if not room_id or not (ban_id or target_user_id):
                socketio.emit("server", {
                    "type": "error",
                    "message": "Room ID and ban ID or target user ID are required"
                }, to=request.sid)
                return

            # Get user ID from stored client info
            user_info = client_info.get(request.sid, {"name": "anon", "user_id": None})
            user_id = user_info["user_id"]

            if not user_id:
                socketio.emit("server", {
                    "type": "error",
                    "message": "Must be logged in to unban users"
                }, to=request.sid)
                return

            try:
                with app.app_context():
                    room = Room.query.get(room_id)
                    if not room:
                        socketio.emit("server", {
                            "type": "error",
                            "message": "Room not found"
                        }, to=request.sid)
                        return

                    # Check if user is the room owner
                    if room.created_by != int(user_id):
                        socketio.emit("server", {
                            "type": "error",
                            "message": "Only the room owner can unban users"
                        }, to=request.sid)
                        return

                    # Find and deactivate the ban
                    if ban_id:
                        ban = RoomBan.query.get(ban_id)
                        if ban and ban.room_id == room_id:
                            ban.is_active = False
                            db.session.commit()

                            socketio.emit("server", {
                                "type": "user.unban.success",
                                "message": "User has been unbanned",
                                "ban_id": ban_id
                            }, to=request.sid)
                        else:
                            socketio.emit("server", {
                                "type": "error",
                                "message": "Ban not found"
                            }, to=request.sid)
                    elif target_user_id:
                        # Deactivate all active bans for this user in this room
                        bans = RoomBan.query.filter_by(
                            room_id=room_id,
                            user_id=int(target_user_id),
                            is_active=True
                        ).all()

                        for ban in bans:
                            ban.is_active = False

                        db.session.commit()

                        socketio.emit("server", {
                            "type": "user.unban.success",
                            "message": "User has been unbanned",
                            "target_user_id": target_user_id
                        }, to=request.sid)

            except Exception as e:
                print(f"Error unbanning user: {e}")
                import traceback
                traceback.print_exc()
                with app.app_context():
                    db.session.rollback()
                socketio.emit("server", {
                    "type": "error",
                    "message": "Failed to unban user"
                }, to=request.sid)

        elif t == "room.save":
            # Handle saving/bookmarking a room
            room_id = msg.get("room_id")

            if not room_id:
                socketio.emit("server", {
                    "type": "error",
                    "message": "Room ID is required"
                }, to=request.sid)
                return

            # Get user ID from stored client info
            user_info = client_info.get(request.sid, {"name": "anon", "user_id": None})
            user_id = user_info["user_id"]

            if not user_id:
                socketio.emit("server", {
                    "type": "error",
                    "message": "Must be logged in to save rooms"
                }, to=request.sid)
                return

            try:
                with app.app_context():
                    room = Room.query.get(room_id)
                    if not room:
                        socketio.emit("server", {
                            "type": "error",
                            "message": "Room not found"
                        }, to=request.sid)
                        return

                    # Check if already saved
                    existing_save = SavedRoom.query.filter_by(
                        user_id=int(user_id),
                        room_id=room_id
                    ).first()

                    if existing_save:
                        socketio.emit("server", {
                            "type": "room.save.success",
                            "message": "Room already saved",
                            "room_id": room_id
                        }, to=request.sid)
                        return

                    # Save the room
                    saved_room = SavedRoom(
                        user_id=int(user_id),
                        room_id=room_id
                    )
                    db.session.add(saved_room)
                    db.session.commit()

                    socketio.emit("server", {
                        "type": "room.save.success",
                        "message": "Room saved successfully",
                        "room_id": room_id
                    }, to=request.sid)

            except Exception as e:
                print(f"Error saving room: {e}")
                import traceback
                traceback.print_exc()
                with app.app_context():
                    db.session.rollback()
                socketio.emit("server", {
                    "type": "error",
                    "message": "Failed to save room"
                }, to=request.sid)

        elif t == "room.unsave":
            # Handle unsaving/removing a saved room
            room_id = msg.get("room_id")

            if not room_id:
                socketio.emit("server", {
                    "type": "error",
                    "message": "Room ID is required"
                }, to=request.sid)
                return

            # Get user ID from stored client info
            user_info = client_info.get(request.sid, {"name": "anon", "user_id": None})
            user_id = user_info["user_id"]

            if not user_id:
                socketio.emit("server", {
                    "type": "error",
                    "message": "Must be logged in to unsave rooms"
                }, to=request.sid)
                return

            try:
                with app.app_context():
                    # Find the saved room entry
                    saved_room = SavedRoom.query.filter_by(
                        user_id=int(user_id),
                        room_id=room_id
                    ).first()

                    if not saved_room:
                        socketio.emit("server", {
                            "type": "error",
                            "message": "Room not in saved list"
                        }, to=request.sid)
                        return

                    # Delete the saved room entry
                    db.session.delete(saved_room)
                    db.session.commit()

                    socketio.emit("server", {
                        "type": "room.unsave.success",
                        "message": "Room removed from saved list",
                        "room_id": room_id
                    }, to=request.sid)

            except Exception as e:
                print(f"Error unsaving room: {e}")
                import traceback
                traceback.print_exc()
                with app.app_context():
                    db.session.rollback()
                socketio.emit("server", {
                    "type": "error",
                    "message": "Failed to unsave room"
                }, to=request.sid)

        elif t == "send.message":
            # Handle user message
            current_room = client_rooms.get(request.sid)
            if not current_room:
                socketio.emit("server", {
                    "type": "error",
                    "message": "Not in a room"
                }, to=request.sid)
                return

            room_state = get_room_state(current_room)

            text = (msg.get("text") or "").strip()
            if not text or text == '[NO_RESPONSE]':
                return

            m = {
                "id": msg.get("client_msg_id") or str(uuid.uuid4()),
                "sender": f"user:{room_state.clients.get(request.sid, {}).get('name', 'anon')}",
                "text": text,
                "ts": int(time.time() * 1000),
            }
            seq = room_state.next_seq()
            room_state.messages.append(m)

            # Persist message to database
            try:
                with app.app_context():
                    msg_record = Message(
                        id=m["id"],
                        room_id=current_room,
                        room_seq=seq,
                        sender=m["sender"],
                        text=m["text"],
                        timestamp=m["ts"]
                    )
                    db.session.add(msg_record)
                    db.session.commit()
            except Exception as e:
                print(f"Error persisting user message to database: {e}")
                try:
                    with app.app_context():
                        db.session.rollback()
                except:
                    pass

            # Broadcast message
            socketio.emit("server",
                {"type": "message.appended", "room_seq": seq, "message": m},
                to=request.sid)
            socketio.emit("server",
                {"type": "message.appended", "room_seq": seq, "message": m},
                room=current_room, skip_sid=request.sid)

            # Check if bot should respond
            user_name = room_state.clients.get(request.sid, {}).get('name', 'anon')
            if not _should_bot_respond(text, user_name, room_state, app):
                print(f"Bot decided not to respond to: {text[:50]}...")
                return

            # Start AI assistant
            run_id = str(uuid.uuid4())
            room_state.active_runs[run_id] = {"stop": False}

            socketio.emit("server", {
                "type": "assistant.started",
                "room_seq": room_state.next_seq(),
                "run": {"run_id": run_id, "parent_message_id": m["id"]}
            }, room=current_room)

            # Start LLM stream in background thread
            threading.Thread(
                target=_llm_stream_task,
                args=(socketio, run_id, f"user:{user_name}, text: " + text, current_room, app),
                daemon=True
            ).start()

        elif t == "send.dm":
            # Handle direct message to bot
            text = (msg.get("text") or "").strip()
            if not text or text == '[NO_RESPONSE]':
                return

            # Get user info
            user_info = client_info.get(request.sid, {"name": "anon", "user_id": None})
            user_name = user_info["name"]
            user_id = user_info["user_id"]

            # Create a DM "room" specific to this user
            dm_room_id = f"dm:{user_id or request.sid}"
            room_state = get_room_state(dm_room_id)

            # Load messages for this DM room if not loaded yet
            _load_messages_from_db(app, dm_room_id)

            # Add user's message
            m = {
                "id": msg.get("client_msg_id") or str(uuid.uuid4()),
                "sender": f"user:{user_name}",
                "text": text,
                "ts": int(time.time() * 1000),
            }
            seq = room_state.next_seq()
            room_state.messages.append(m)

            # Persist message to database
            try:
                with app.app_context():
                    msg_record = Message(
                        id=m["id"],
                        room_id=dm_room_id,
                        room_seq=seq,
                        sender=m["sender"],
                        text=m["text"],
                        timestamp=m["ts"]
                    )
                    db.session.add(msg_record)
                    db.session.commit()
            except Exception as e:
                print(f"Error persisting DM to database: {e}")
                try:
                    with app.app_context():
                        db.session.rollback()
                except:
                    pass

            # Send confirmation back to user
            socketio.emit("server",
                {"type": "dm.sent", "message": m},
                to=request.sid)

            # Start AI assistant (always respond to DMs)
            run_id = str(uuid.uuid4())
            room_state.active_runs[run_id] = {"stop": False}

            socketio.emit("server", {
                "type": "assistant.started",
                "room_seq": room_state.next_seq(),
                "run": {"run_id": run_id, "parent_message_id": m["id"]}
            }, to=request.sid)

            # Start LLM stream in background thread, sending responses only to this user
            # Capture request.sid before starting thread (it's a context-local variable)
            target_sid = request.sid

            threading.Thread(
                target=_llm_stream_task_dm,
                args=(socketio, run_id, f"user:{user_name}, text: " + text, dm_room_id, app, target_sid),
                daemon=True
            ).start()

        elif t == "load.dm_history":
            # Load DM history for the current user
            user_info = client_info.get(request.sid, {"name": "anon", "user_id": None})
            user_id = user_info["user_id"]
            dm_room_id = f"dm:{user_id or request.sid}"

            # Load messages for this DM room
            room_state = get_room_state(dm_room_id)
            _load_messages_from_db(app, dm_room_id)

            # Send DM history to client
            socketio.emit("server", {
                "type": "dm.history",
                "messages": list(room_state.messages)
            }, to=request.sid)

        elif t == "run.stop":
            # Handle stop request
            current_room = client_rooms.get(request.sid)
            if not current_room:
                return

            room_state = get_room_state(current_room)
            rid = msg.get("run_id")
            ctrl = room_state.active_runs.get(rid)
            if ctrl:
                ctrl["stop"] = True
