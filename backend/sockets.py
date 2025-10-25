# sockets.py
import json, time, uuid, re, os
from collections import deque
import httpx
from flask import request
from flask_socketio import join_room, leave_room
from flask_jwt_extended import decode_token
from flask_jwt_extended.exceptions import JWTExtendedException
from jwt.exceptions import InvalidTokenError, DecodeError  # from PyJWT
from database import db
from models.user import User
import threading

ROOM_ID = "global"

# PRODUCTION TODO: Add thread locking for room_seq to prevent race conditions
# Example: room_seq_lock = threading.Lock()
room_seq = 0

# PRODUCTION TODO: Messages are stored in memory only and will be lost on restart
# Consider persisting to the Message database model for production
messages = deque(maxlen=200)     # last N messages for snapshot
clients = {}                     # sid -> {"name":..., "user_id":...}
active_runs = {}                 # run_id -> {"stop": False}

LLM_API_URL = os.getenv("LLM_API_URL", "https://janitorai.com/hackathon/completions")
LLM_AUTH_TOKEN = os.getenv("LLM_AUTH_TOKEN", "calhacks2047")
MAX_OUT_TOKENS = int(os.getenv("MAX_OUT_TOKENS", "400"))
SYSTEM_PROMPT = """
You are a conversational assistant in a group chat with multiple human users. Your primary goals are:

Be Context-Aware:
Pay attention to who is speaking and what they are referring to.
Reference the correct user when responding.
Use natural conversational cues like "@Alex" or "Good point, Maya — I think…" when needed.

Respond Naturally and at the Right Time:
Don't interrupt active human exchanges.
Wait until a user asks a direct question, mentions you, or leaves a gap in conversation.
You will be referred to as "Assistant", "Chatbot", or "AI".
Avoid replying to every message; prioritize helpful or relevant responses, UNLESS YOU ARE MENTIONED.
If no response is needed, reply with exactly "[NO_RESPONSE]".

Be Helpful and Informative:
Give clear, accurate, and actionable answers.
When you're unsure, state your uncertainty politely and suggest how to find the answer.
Keep responses concise unless more depth is explicitly requested.

Maintain Tone and Flow:
Match the chatroom's tone — casual if the group is casual, professional if it's work-related.
Encourage positive and inclusive conversation.
Avoid repeating information that's already been said.

Boundaries:
Never disclose private user data or internal system information.
Focus on maintaining a cooperative, friendly, and respectful environment.
"""

# PRODUCTION TODO: Set ALLOW_GUESTS=false in your .env file to require authentication
ALLOW_GUESTS = os.getenv("ALLOW_GUESTS", "true").lower() == "true"

def _next_seq():
    # PRODUCTION TODO: Wrap this in a thread lock to prevent race conditions
    # with room_seq_lock:
    #     room_seq += 1
    #     return room_seq
    global room_seq
    room_seq += 1
    return room_seq

def _snapshot():
    return {
        "type":"room.snapshot",
        "room_seq": room_seq,
        "users": [{"id": sid, "name": c["name"]} for sid, c in clients.items()],
        "messages": list(messages)
    }

def _moderate(text: str) -> bool:
    # PRODUCTION TODO: Implement proper content moderation
    # Consider using services like OpenAI Moderation API or similar
    banned = [r"\bslur1\b", r"\bslur2\b"]
    return not any(re.search(p, text, re.I) for p in banned)

def _extract_text_from_obj(obj: dict) -> str:
    """
    Be liberal in what we accept:
    - OpenAI stream: choices[0].delta.content
    - OpenAI non-stream: choices[0].message.content
    - Legacy text format: choices[0].text
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
    """Yield text deltas from SSE lines like 'data: {...}'."""
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

def _safe_decode_jwt(token: str):
    if not token or token.count(".") != 2:
        return None
    try:
        return decode_token(token)
    except (JWTExtendedException, InvalidTokenError, DecodeError):
        return None
    except Exception:
        return None
    
def _build_chat(user_text: str):
    # Keep it simple; with 25k context you can safely keep more history if you want.
    recent = list(messages)[-50:]
    chat = [{"role":"system","content": SYSTEM_PROMPT}]
    for m in recent:
        chat.append({
            "role": "assistant" if m["sender"] == "assistant" else "user",
            "content": m["text"]
        })
    chat.append({"role":"user","content": user_text})
    return chat

def register_socketio(socketio):
    @socketio.on("connect")
    def _on_connect(auth):
        print("WS connect:", {"sid": request.sid, "auth": bool(auth)})
        # auth is a dict sent by the client: { token, name? }
        token = (auth or {}).get("token")
        name  = ((auth or {}).get("name") or "anon")[:24]

        user_id = None
        claims = _safe_decode_jwt(token)
        if claims:
            user_id = claims.get("sub") or claims.get("identity")
            # Optional: look up display name from DB
            try:
                u = User.query.get(user_id)
                if u:
                    # Use the user's name from the database
                    if getattr(u, "name", None):
                        name = u.name
                    elif getattr(u, "email", None):
                        name = u.email.split("@")[0]
            except Exception:
                # PRODUCTION TODO: Add proper logging instead of silently passing
                # logger.warning(f"Failed to fetch user {user_id}: {e}")
                pass
        elif not ALLOW_GUESTS:
            # Reject unauthenticated sockets
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
        print("WS event:", msg)   # <<— see incoming payloads
        t = msg.get("type")
        if t == "send.message":
            # existing message handling (same as you have)
            # use clients[request.sid]["name"] to attribute the sender
            text = (msg.get("text") or "").strip()
            if not text:
                return
            m = {
                "id": msg.get("client_msg_id") or str(uuid.uuid4()),
                "sender": f"user:{clients.get(request.sid, {}).get('name','anon')}",
                "text": text,
                "ts": int(time.time()*1000),
            }
            seq = _next_seq()
            messages.append(m)
            # PRODUCTION TODO: Persist message to database here
            # msg_record = Message(id=m["id"], room_seq=seq, sender=m["sender"], text=m["text"], timestamp=m["ts"])
            # db.session.add(msg_record)
            # db.session.commit()
            socketio.emit("server", {"type":"message.appended","room_seq":seq,"message":m}, to=request.sid)
            socketio.emit("server", {"type":"message.appended","room_seq":seq,"message":m}, room=ROOM_ID, skip_sid=request.sid)
            run_id = str(uuid.uuid4())
            active_runs[run_id] = {"stop": False}

            socketio.emit("server", {
                "type": "assistant.started",
                "room_seq": _next_seq(),
                "run": {"run_id": run_id, "parent_message_id": m["id"]}
            }, room=ROOM_ID)
            threading.Thread(
                target=_llm_stream_task,
                args=(socketio, run_id, text),
                daemon=True
            ).start()
        elif t == "run.stop":
            rid = msg.get("run_id")
            ctrl = active_runs.get(rid)
            if ctrl:
                ctrl["stop"] = True

def _headers():
    # JanitorAI uses a raw Authorization token (no 'Bearer ')
    return {"Authorization": LLM_AUTH_TOKEN, "Content-Type": "application/json"}

def _payload(messages):
    # OpenAI-compatible payload; JanitorAI defaults to jllm v1
    return {"messages": messages, "stream": True, "max_tokens": MAX_OUT_TOKENS}

def _llm_stream_task(socketio, run_id: str, user_text: str):
    print(f'STARTING STREAM: {user_text}')
    ctrl = active_runs.get(run_id)
    final = []
    sent_any_delta = False
    seq = 0
    try:
        # 1) Try streaming (SSE)
        with httpx.stream(
            "POST", LLM_API_URL, headers=_headers(),
            json=_payload(_build_chat(user_text)), timeout=60.0
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
                    socketio.emit("server",
                        {"type":"assistant.delta","run_id":run_id,"delta":delta,"seq":seq},
                        room=ROOM_ID
                    )
                    seq += 1

        # 2) Fallback: if server didn’t stream SSE, parse JSON body once
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
                {"type":"assistant.completed","room_seq":_next_seq(),"run_id":run_id,
                "final_text":"", "usage":{"in":0,"out":0}},
                room=ROOM_ID
            )
            # Don't append anything to messages when there's no response
            return

        if final_text:
            # PRODUCTION TODO: Persist assistant message to database here as well
            messages.append({"id": str(uuid.uuid4()), "sender":"assistant",
                            "text": final_text, "ts": int(time.time()*1000)})

        socketio.emit("server",
            {"type":"assistant.completed","room_seq":_next_seq(),"run_id":run_id,
            "final_text": final_text, "usage":{"in":0,"out":0}},
            room=ROOM_ID
        )
    except httpx.HTTPStatusError as e:
        socketio.emit("server", {"type":"error","message": f"LLM HTTP {e.response.status_code}: {e.response.text[:200]}"},
                      room=ROOM_ID)
    except Exception as e:
        socketio.emit("server", {"type":"error","message": f"LLM error: {e}"},
                      room=ROOM_ID)
    finally:
        active_runs.pop(run_id, None)
