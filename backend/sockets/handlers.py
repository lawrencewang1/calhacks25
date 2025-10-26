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

# Global chat room
ROOM_ID = "global"

# PRODUCTION TODO: Add thread locking for room_seq to prevent race conditions
room_seq = 0

# PRODUCTION TODO: Messages are stored in memory only and will be lost on restart
# Consider persisting to the Message database model for production
messages = deque(maxlen=200)     # last N messages for snapshot
clients = {}                     # sid -> {"name":..., "user_id":...}
active_runs = {}                 # run_id -> {"stop": False}


def _next_seq():
    """
    Generate the next sequence number for room events.

    PRODUCTION TODO: Wrap this in a thread lock to prevent race conditions.

    Returns:
        int: The next sequence number
    """
    global room_seq
    room_seq += 1
    return room_seq


def _snapshot():
    """
    Generate a snapshot of the current room state.

    Returns:
        dict: Room snapshot with users and messages
    """
    return {
        "type": "room.snapshot",
        "room_seq": room_seq,
        "users": [{"id": sid, "name": c["name"]} for sid, c in clients.items()],
        "messages": list(messages)
    }


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


def _build_chat(user_text: str, app):
    """
    Build chat context for LLM API request.

    Args:
        user_text: The user's message
        app: Flask application instance (for config)

    Returns:
        list: Chat messages formatted for LLM API
    """
    # Get configuration from app
    system_prompt = app.config.get("SYSTEM_PROMPT", "You are a helpful assistant.")
    context_messages = app.config.get("CHAT_CONTEXT_MESSAGES", 50)

    recent = list(messages)[-context_messages:]
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


def _should_bot_respond(user_text: str, user_name: str, app) -> bool:
    """
    Determine if the bot should respond to a message.

    Uses heuristics and conversation context to decide if Midori should respond.

    Args:
        user_text: The user's message text
        user_name: The name of the user who sent the message
        app: Flask application instance

    Returns:
        bool: True if bot should respond, False otherwise
    """
    text_lower = user_text.lower()

    # Always respond if directly mentioned
    mentions = ['@midori', '@ai', 'midori', 'hey midori', 'hi midori']
    if any(mention in text_lower for mention in mentions):
        return True

    # Check for direct request phrases
    request_phrases = ['could you', 'can you', 'would you', 'will you', 'please help', 'help me']
    if any(phrase in text_lower for phrase in request_phrases):
        return True

    # Get recent context
    recent = list(messages)[-5:]  # Look at last 5 messages for better context

    # Check if bot was recently active (last message or second-to-last was from assistant)
    bot_recently_active = False
    if recent:
        last_sender = recent[-1].get('sender', '') if len(recent) >= 1 else ''
        second_last_sender = recent[-2].get('sender', '') if len(recent) >= 2 else ''

        bot_recently_active = (last_sender == 'assistant' or second_last_sender == 'assistant')

    # If bot was recently active and user asks a question, it's likely a follow-up
    if bot_recently_active and '?' in user_text:
        print(f"Bot responding to follow-up question after recent activity")
        return True

    # Check for question patterns
    if '?' in user_text:
        # Count recent messages from users vs assistant
        recent_user_msgs = [m for m in recent[-3:] if m.get('sender', '').startswith('user:')]
        recent_assistant_msgs = [m for m in recent[-3:] if m.get('sender') == 'assistant']

        # If there are recent assistant messages, more likely to be relevant
        if len(recent_assistant_msgs) > 0:
            return True

        # If it's just users talking to each other (2+ user messages in a row), skip
        if len(recent_user_msgs) >= 2 and len(recent_assistant_msgs) == 0:
            # Check if messages are short and conversational
            avg_length = sum(len(m.get('text', '').split()) for m in recent_user_msgs) / len(recent_user_msgs)
            if avg_length <= 5:
                return False

        # Otherwise, respond to questions
        return True

    # If message is very short and conversational between users, don't respond
    if len(user_text.split()) <= 3:
        recent_user_only = [m for m in recent[-3:] if m.get('sender', '').startswith('user:')]
        if len(recent_user_only) >= 2:
            # Short messages between users, probably chatting
            return False

    # Check for conversational continuity (references to previous topic)
    if bot_recently_active and len(user_text.split()) > 5:
        # Longer message after bot was active, likely continuing the conversation
        return True

    # Default to not responding for unclear cases
    return False


def _llm_stream_task(socketio, run_id: str, user_text: str, app):
    """
    Collect full LLM response and emit as complete message chunks.

    Collects the full response from the LLM API, breaks it into chunks at
    natural boundaries (paragraphs, sentences), and emits each chunk as a
    complete message with a small delay between chunks for better UX.

    Args:
        socketio: SocketIO instance
        run_id: Unique ID for this LLM run
        user_text: User's message text
        app: Flask application instance
    """
    print(f'STARTING STREAM: {user_text}')
    ctrl = active_runs.get(run_id)
    final = []
    sent_any_delta = False

    llm_api_url = app.config.get("LLM_API_URL", "")

    try:
        # Collect the full response without emitting deltas
        with httpx.stream(
            "POST", llm_api_url, headers=_headers(app),
            json=_payload(_build_chat(user_text, app), app), timeout=60.0
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
                {"type": "assistant.completed", "room_seq": _next_seq(), "run_id": run_id,
                 "final_text": "", "usage": {"in": 0, "out": 0}},
                room=ROOM_ID
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

                # PRODUCTION TODO: Persist assistant message to database here as well
                messages.append(msg)

                # Emit the chunk as a complete message
                socketio.emit("server",
                    {"type": "message.appended", "room_seq": _next_seq(), "message": msg},
                    room=ROOM_ID
                )

                # Small delay between chunks for better UX (0.3 seconds)
                if i < len(chunks) - 1:
                    time.sleep(0.3)

        socketio.emit("server",
            {"type": "assistant.completed", "room_seq": _next_seq(), "run_id": run_id,
             "final_text": final_text, "usage": {"in": 0, "out": 0}},
            room=ROOM_ID
        )
    except httpx.HTTPStatusError as e:
        socketio.emit("server",
            {"type": "error", "message": f"LLM HTTP {e.response.status_code}: {e.response.text[:200]}"},
            room=ROOM_ID)
    except Exception as e:
        socketio.emit("server", {"type": "error", "message": f"LLM error: {e}"},
            room=ROOM_ID)
    finally:
        active_runs.pop(run_id, None)


def register_socketio(socketio, app):
    """
    Register Socket.IO event handlers.

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

        # Accept connection
        clients[request.sid] = {"name": name, "user_id": user_id}
        join_room(ROOM_ID)

        # Send snapshot to this client
        socketio.emit("server", _snapshot(), to=request.sid)

        # Notify the room
        seq = _next_seq()
        socketio.emit("server", {
            "type": "user.joined",
            "room_seq": seq,
            "user": {"id": request.sid, "name": name},
            "count": len(clients)
        }, room=ROOM_ID)

    @socketio.on("disconnect")
    def _on_disconnect():
        """Handle client disconnection."""
        print("WS disconnect:", request.sid)
        if request.sid in clients:
            clients.pop(request.sid, None)
            seq = _next_seq()
            socketio.emit("server", {
                "type": "user.left",
                "room_seq": seq,
                "user_id": request.sid,
                "count": len(clients)
            }, room=ROOM_ID)

    @socketio.on("client")
    def _on_client(msg):
        """Handle client messages."""
        print("WS event:", msg)
        t = msg.get("type")

        if t == "send.message":
            # Handle user message
            text = (msg.get("text") or "").strip()
            if not text or text == '[NO_RESPONSE]':
                return

            m = {
                "id": msg.get("client_msg_id") or str(uuid.uuid4()),
                "sender": f"user:{clients.get(request.sid, {}).get('name', 'anon')}",
                "text": text,
                "ts": int(time.time() * 1000),
            }
            seq = _next_seq()
            messages.append(m)

            # PRODUCTION TODO: Persist message to database here
            from backend.models.message import Message
            msg_record = Message(
                id=m["id"],
                room_seq=seq,
                sender=m["sender"],
                text=m["text"],
                timestamp=m["ts"]
            )
            db.session.add(msg_record)
            db.session.commit()

            # Broadcast message
            socketio.emit("server",
                {"type": "message.appended", "room_seq": seq, "message": m},
                to=request.sid)
            socketio.emit("server",
                {"type": "message.appended", "room_seq": seq, "message": m},
                room=ROOM_ID, skip_sid=request.sid)

            # Check if bot should respond
            user_name = clients.get(request.sid, {}).get('name', 'anon')
            if not _should_bot_respond(text, user_name, app):
                print(f"Bot decided not to respond to: {text[:50]}...")
                return

            # Start AI assistant
            run_id = str(uuid.uuid4())
            active_runs[run_id] = {"stop": False}

            socketio.emit("server", {
                "type": "assistant.started",
                "room_seq": _next_seq(),
                "run": {"run_id": run_id, "parent_message_id": m["id"]}
            }, room=ROOM_ID)

            # Start LLM stream in background thread
            threading.Thread(
                target=_llm_stream_task,
                args=(socketio, run_id, f"user:{user_name}, text: " + text, app),
                daemon=True
            ).start()

        elif t == "run.stop":
            # Handle stop request
            rid = msg.get("run_id")
            ctrl = active_runs.get(rid)
            if ctrl:
                ctrl["stop"] = True
