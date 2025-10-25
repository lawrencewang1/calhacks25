# sockets.py
import json, time, uuid, re, os
from collections import deque
import httpx
from flask import request
from flask_socketio import join_room, leave_room
from flask_jwt_extended import decode_token
from database import db
from models.user import User
# (optional) from models.message import Message

ROOM_ID = "global"
room_seq = 0
messages = deque(maxlen=200)     # last N messages for snapshot
clients = {}                     # sid -> {"name":..., "user_id":...}
active_runs = {}                 # run_id -> {"stop": False}

LLM_API_URL = os.getenv("LLM_API_URL", "https://janitorai.com/hackathon/completions")
LLM_AUTH_TOKEN = os.getenv("LLM_AUTH_TOKEN", "calhacks2047")
SYSTEM_PROMPT = """
You are a conversational assistant in a group chat with multiple human users. Your primary goals are:

Be Context-Aware:
Pay attention to who is speaking and what they are referring to.
Reference the correct user when responding.
Use natural conversational cues like “@Alex” or “Good point, Maya — I think…” when needed.

Respond Naturally and at the Right Time:
Don’t interrupt active human exchanges.
Wait until a user asks a direct question, mentions you, or leaves a gap in conversation.
Avoid replying to every message; prioritize helpful or relevant responses.

Be Helpful and Informative:
Give clear, accurate, and actionable answers.
When you’re unsure, state your uncertainty politely and suggest how to find the answer.
Keep responses concise unless more depth is explicitly requested.

Maintain Tone and Flow:
Match the chatroom’s tone — casual if the group is casual, professional if it’s work-related.
Encourage positive and inclusive conversation.
Avoid repeating information that’s already been said.

Boundaries:
Never disclose private user data or internal system information.
Focus on maintaining a cooperative, friendly, and respectful environment.
"""
MAX_OUT_TOKENS = int(os.getenv("MAX_OUT_TOKENS", "400"))

def _next_seq():
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

def _build_chat(user_text: str):
    # Keep it simple; with 25k context you can safely keep more history if you want.
    recent = list(messages)[-30:]
    chat = [{"role":"system","content": SYSTEM_PROMPT}]
    for m in recent:
        chat.append({
            "role": "assistant" if m["sender"] == "assistant" else "user",
            "content": m["text"]
        })
    chat.append({"role":"user","content": user_text})
    return chat

def register_socketio(socketio):
    from flask_jwt_extended.exceptions import JWTExtendedException

    @socketio.on("connect")
    def _on_connect():
        # Client will immediately send a 'client' event with type='join'
        pass

    @socketio.on("disconnect")
    def _on_disconnect():
        if request.sid in clients:
            clients.pop(request.sid, None)
            seq = _next_seq()
            socketio.emit("server", {"type":"user.left","room_seq":seq,"user_id":request.sid,"count":len(clients)}, room=ROOM_ID)

    @socketio.on("client")
    def _on_client(msg):
        t = msg.get("type")

        if t == "join":
            # Expect either a token or a name. Token is best; name is fallback for demo.
            token = msg.get("token")
            name = (msg.get("name") or "anon")[:24]
            user_id = None
            if token:
                try:
                    data = decode_token(token)  # validates signature with your JWT setup
                    user_id = data.get("sub")
                    # Optional: lookup user to display email/name
                    u = User.query.get(user_id)
                    if u and u.email:
                        name = u.email.split("@")[0]
                except JWTExtendedException:
                    pass  # treat as anon for demo

            clients[request.sid] = {"name": name, "user_id": user_id}
            join_room(ROOM_ID)
            # Send snapshot only to the joiner
            socketio.emit("server", _snapshot(), to=request.sid)
            # Notify room
            seq = _next_seq()
            socketio.emit("server", {"type":"user.joined","room_seq":seq,"user":{"id":request.sid,"name":name},"count":len(clients)}, room=ROOM_ID)

        elif t == "send.message":
            text = (msg.get("text") or "").strip()
            client_msg_id = msg.get("client_msg_id") or str(uuid.uuid4())
            if not text:
                return
            if not _moderate(text):
                socketio.emit("server", {"type":"error","message":"Message blocked by moderation"}, to=request.sid)
                return

            # Append user message
            m = {"id": client_msg_id, "sender": f"user:{clients.get(request.sid,{}).get('name','anon')}", "text": text, "ts": int(time.time()*1000)}
            seq = _next_seq()
            messages.append(m)
            socketio.emit("server", {"type":"message.appended","room_seq":seq,"message":m}, room=ROOM_ID)
            # (optional) persist:
            # db.session.add(Message(room_seq=seq, sender=m["sender"], text=text)); db.session.commit()

            # Start LLM run
            run_id = str(uuid.uuid4())
            seq2 = _next_seq()
            socketio.emit("server", {"type":"assistant.started","room_seq":seq2,"run":{"run_id":run_id,"parent_message_id":m["id"]}}, room=ROOM_ID)
            active_runs[run_id] = {"stop": False}
            socketio.start_background_task(target=_llm_stream_task, socketio=socketio, run_id=run_id, user_text=text)

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
        text = "".join(final).strip()
        if text:
            messages.append({"id": str(uuid.uuid4()), "sender":"assistant",
                             "text": text, "ts": int(time.time()*1000)})

        seq_room = _next_seq()
        socketio.emit("server",
            {"type":"assistant.completed","room_seq":seq_room,"run_id":run_id,
             "final_text": text, "usage":{"in":0,"out":0}},
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
