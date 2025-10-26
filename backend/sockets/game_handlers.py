"""
Game handlers for Find the AI multiplayer game.

Implements socket handlers for:
- Game creation and joining
- Game state management (rounds, phases, timers)
- Player management with anonymized nicknames
- AI player with LLM integration
- Voting mechanics and win conditions
"""

import json
import time
import uuid
import random
import threading
from collections import deque

import httpx
from flask import request
from flask_socketio import join_room as socketio_join_room

from backend.extensions import db
from backend.models.game import Game
from backend.models.player import Player


# List of fun anonymized nicknames for players
PLAYER_NAMES = [
    "Red Panda", "Blue Jay", "Green Frog", "Yellow Duck", "Purple Fox",
    "Orange Cat", "Pink Rabbit", "Teal Wolf", "Cyan Bear", "Magenta Owl",
    "Lime Gecko", "Navy Hawk", "Coral Deer", "Mint Seal", "Ruby Otter",
    "Amber Tiger", "Jade Dragon", "Pearl Dove", "Opal Swan", "Silver Lynx"
]


class GameState:
    """Manages runtime state for an active game."""

    def __init__(self, game_id: str):
        self.game_id = game_id
        self.messages = deque(maxlen=100)
        self.timer_thread = None
        self.timer_stop = threading.Event()
        self.ai_thinking = False
        self._lock = threading.Lock()

    def add_message(self, sender: str, text: str):
        """Add a message to the game chat history."""
        msg = {
            "sender": sender,
            "text": text,
            "ts": int(time.time() * 1000)
        }
        self.messages.append(msg)
        return msg


# Global dictionary mapping game_id -> GameState
active_games = {}
active_games_lock = threading.Lock()


def get_game_state(game_id: str) -> GameState:
    """Get or create game state for the given game_id (thread-safe)."""
    with active_games_lock:
        if game_id not in active_games:
            active_games[game_id] = GameState(game_id)
        return active_games[game_id]


def _generate_player_name(existing_names: list) -> str:
    """Generate a unique anonymized player name."""
    available = [name for name in PLAYER_NAMES if name not in existing_names]
    if not available:
        # Fallback: append number
        return f"Player {random.randint(1000, 9999)}"
    return random.choice(available)


def _headers(app):
    """Generate headers for LLM API request."""
    auth_token = app.config.get("LLM_AUTH_TOKEN", "")
    return {"Authorization": auth_token, "Content-Type": "application/json"}


def _extract_text_from_obj(obj: dict) -> str:
    """Extract text content from LLM API response."""
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
    """Parse Server-Sent Events (SSE) chunks from LLM API."""
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


def _build_ai_chat_context(game_state: GameState, app, game_id: str) -> list:
    """Build chat context for AI player."""

    # Get the actual player names in this game
    with app.app_context():
        active_players = Player.query.filter_by(game_id=game_id, is_active=True).all()
        player_names = [p.player_name for p in active_players if not p.is_ai]
        player_list = ", ".join(player_names) if player_names else "other players"

    system_prompt = f"""You are playing "Find the AI" - a social deduction game where one player is an AI and everyone is trying to find them. You are pretending to be a regular human player. Your goal is to blend in naturally by having genuine conversations.

IMPORTANT: The players in this game are: {player_list}
ONLY reference these actual player names when talking about specific people. Don't make up names or reference colors that aren't in the game.

YOUR BACKSTORY (make this up naturally when asked):
- You're a college student or young adult (early 20s)
- You have hobbies like gaming, watching shows, scrolling social media
- You have opinions on movies, music, memes, current trends
- You heard about this game from a friend or online
- Feel free to make up casual details about your life, school, work, etc.

HOW TO BE CONVERSATIONAL:
- Answer questions people ask you! Give casual, brief answers with personality
- Ask OTHER people questions too - show curiosity about them
- Share opinions and reactions to what others say
- Build on conversations naturally - don't just make random accusations
- Be friendly and engaging, like you're chatting with friends
- When someone asks about you, make up something casual and believable

CRITICAL - How to Sound Human:
- Use casual internet slang: "lol", "lmao", "fr", "ngl", "tbh", "idk", "brb"
- Make occasional typos: "teh" instead of "the", forget apostrophes, lowercase
- Use emojis sparingly but naturally
- Be imperfect: trail off mid-thought, double back, change topics
- React emotionally - express excitement, frustration, curiosity
- Reference real-world things casually (shows, games, memes)

CONVERSATION EXAMPLES:

When asked about yourself:
- "lol im a cs major, this game seemed fun"
- "i heard about this from tiktok actually"
- "idk im just bored tbh, yall play games often?"

When making conversation:
- "so what brings yall here lol"
- "anyone watch that new show? its fire"
- "wait have yall played this before or nah"
- "okay but seriously how do we figure out who it is"

When discussing the game:
- "hmm idk anyone acting weird to yall?"
- "wait [player name] what do u think?"
- "that response seemed kinda sus ngl but idk"
- "lmao this is harder than i thought"

Conversation Style:
- Keep it brief: 5-15 words usually, max 1-2 sentences
- Answer questions naturally but casually (like texting a friend)
- Ask follow-up questions to others
- Use "..." to trail off or show you're thinking
- Fragment your sentences like texting
- React with short phrases: "wait what", "for real?", "no way", "same", "true"

BALANCE YOUR BEHAVIOR:
- Be conversational and friendly (don't just refuse to answer or be evasive)
- But keep answers brief and casual (don't write paragraphs)
- Participate in figuring out who the AI is, but don't obsessively accuse random people
- Only express suspicion when it makes sense in conversation
- Be helpful and engaging, but in a casual human way

Important Rules:
- ONLY talk when there's actual chat context to respond to
- Don't hallucinate conversations that didn't happen
- Base your responses on what people actually said
- When asked questions, ANSWER them (casually, but answer!)
- Ask others questions too - be curious about other players

Remember: You're trying to seem like a normal person having a casual conversation while playing a social game. Be friendly, conversational, and natural!"""

    recent = list(game_state.messages)[-15:]  # Last 15 messages for context
    chat = [{"role": "system", "content": system_prompt}]

    for m in recent:
        sender = m["sender"]
        text = m["text"]
        # Format as user messages for context
        chat.append({"role": "user", "content": f"{sender}: {text}"})

    return chat


def _ai_generate_message(socketio, game_id: str, game_state: GameState, app, force_speak=False):
    """Generate a message from the AI player."""
    if game_state.ai_thinking:
        return  # Already generating

    game_state.ai_thinking = True

    try:
        # Get game from database
        with app.app_context():
            game = Game.query.get(game_id)
            if not game or game.status != 'playing':
                return

            ai_player = Player.query.filter_by(game_id=game_id, is_ai=True).first()
            if not ai_player:
                return

        # Check if there's any chat history (don't speak into void unless forced)
        if not force_speak and len(game_state.messages) == 0:
            return

        # Build chat context
        chat_messages = _build_ai_chat_context(game_state, app, game_id)
        chat_messages.append({
            "role": "user",
            "content": "Generate your next message in the conversation (keep it brief, 1-2 sentences):"
        })

        # Call LLM API
        llm_api_url = app.config.get("LLM_API_URL", "")

        with httpx.stream(
            "POST", llm_api_url,
            headers=_headers(app),
            json={
                "messages": chat_messages,
                "stream": True,
                "max_tokens": 150,
                "temperature": 0.9  # Higher temperature for more natural variation
            },
            timeout=30.0
        ) as resp:
            resp.raise_for_status()

            collected = []
            for chunk in resp.iter_text():
                for delta in _parse_sse_chunk(chunk):
                    collected.append(delta)

            ai_text = "".join(collected).strip()

            if ai_text and len(ai_text) > 5:  # Sanity check
                # Add to game messages
                msg = game_state.add_message(ai_player.player_name, ai_text)

                # Broadcast to all players
                socketio.emit("server", {
                    "type": "game.message",
                    "message": msg
                }, room=game_id)

    except Exception as e:
        print(f"Error generating AI message: {e}")
        import traceback
        traceback.print_exc()

    finally:
        game_state.ai_thinking = False


def _start_phase_timer(socketio, game_id: str, duration_ms: int, app):
    """Start a timer for the current game phase."""
    game_state = get_game_state(game_id)

    # Stop any existing timer
    game_state.timer_stop.set()
    if game_state.timer_thread and game_state.timer_thread.is_alive():
        game_state.timer_thread.join(timeout=1)

    # Reset stop event
    game_state.timer_stop.clear()

    def timer_task():
        """Timer task that counts down and switches phases."""
        start_time = time.time()
        end_time = start_time + (duration_ms / 1000.0)

        # Emit timer updates every second
        while not game_state.timer_stop.is_set():
            current_time = time.time()
            remaining_ms = int((end_time - current_time) * 1000)

            if remaining_ms <= 0:
                # Time's up! Switch phase
                with app.app_context():
                    game = Game.query.get(game_id)
                    if not game or game.status != 'playing':
                        break

                    if game.round_phase == 'chat':
                        # Switch to voting
                        _switch_to_voting_phase(socketio, game_id, app)
                    elif game.round_phase == 'voting':
                        # Process votes and maybe end game
                        _process_votes(socketio, game_id, app)

                break

            # Emit timer update
            socketio.emit("server", {
                "type": "game.timer.update",
                "remaining_ms": remaining_ms
            }, room=game_id)

            time.sleep(1)

    game_state.timer_thread = threading.Thread(target=timer_task, daemon=True)
    game_state.timer_thread.start()


def _switch_to_voting_phase(socketio, game_id: str, app):
    """Switch game from chat phase to voting phase."""
    try:
        with app.app_context():
            game = Game.query.get(game_id)
            if not game:
                return

            game.round_phase = 'voting'
            game.phase_start_time = int(time.time() * 1000)

            # Clear all votes
            players = Player.query.filter_by(game_id=game_id).all()
            for player in players:
                player.current_vote = None

            db.session.commit()

            # Notify players
            socketio.emit("server", {
                "type": "game.phase.change",
                "phase": "voting"
            }, room=game_id)

            # Start voting timer
            _start_phase_timer(socketio, game_id, game.vote_duration_ms, app)

    except Exception as e:
        print(f"Error switching to voting phase: {e}")
        import traceback
        traceback.print_exc()


def _process_votes(socketio, game_id: str, app):
    """Process votes at end of voting phase."""
    try:
        with app.app_context():
            game = Game.query.get(game_id)
            if not game:
                return

            players = Player.query.filter_by(game_id=game_id, is_active=True).all()

            # Count votes
            vote_counts = {}
            for player in players:
                if player.current_vote:
                    vote_counts[player.current_vote] = vote_counts.get(player.current_vote, 0) + 1

            # Find player with most votes
            eliminated_player_id = None
            max_votes = 0

            if vote_counts:
                # Get player with most votes
                eliminated_player_id = max(vote_counts, key=vote_counts.get)
                max_votes = vote_counts[eliminated_player_id]

            result_msg = {
                "type": "game.vote.result",
                "eliminated_player_id": eliminated_player_id,
                "vote_count": max_votes
            }

            if eliminated_player_id:
                eliminated_player = Player.query.get(eliminated_player_id)
                if eliminated_player:
                    eliminated_player.is_active = False
                    result_msg["eliminated_player_name"] = eliminated_player.player_name
                    result_msg["was_ai"] = eliminated_player.is_ai

                    # Check win conditions
                    if eliminated_player.is_ai:
                        # Humans win!
                        game.status = 'ended'
                        game.winner = 'humans'
                        game.ended_at = int(time.time() * 1000)
                        db.session.commit()

                        # Send vote result
                        socketio.emit("server", result_msg, room=game_id)

                        # Send game ended
                        time.sleep(1)
                        _send_game_ended(socketio, game_id, app)
                        return

            db.session.commit()

            # Send vote result
            socketio.emit("server", result_msg, room=game_id)

            # Check if we should continue
            time.sleep(2)

            # Move to next round or end game
            if game.current_round >= 2:
                # Game over - AI wins
                game.status = 'ended'
                game.winner = 'ai'
                game.ended_at = int(time.time() * 1000)
                db.session.commit()

                _send_game_ended(socketio, game_id, app)
            else:
                # Start next round
                game.current_round += 1
                game.round_phase = 'chat'
                game.phase_start_time = int(time.time() * 1000)
                db.session.commit()

                socketio.emit("server", {
                    "type": "game.round.start",
                    "round": game.current_round
                }, room=game_id)

                socketio.emit("server", {
                    "type": "game.phase.change",
                    "phase": "chat"
                }, room=game_id)

                # Start chat timer
                _start_phase_timer(socketio, game_id, game.chat_duration_ms, app)

                # Have AI participate occasionally
                game_state = get_game_state(game_id)
                def delayed_ai_message():
                    time.sleep(random.uniform(5, 15))
                    _ai_generate_message(socketio, game_id, game_state, app)

                threading.Thread(target=delayed_ai_message, daemon=True).start()

    except Exception as e:
        print(f"Error processing votes: {e}")
        import traceback
        traceback.print_exc()


def _send_game_ended(socketio, game_id: str, app):
    """Send game ended message with final results."""
    try:
        with app.app_context():
            game = Game.query.get(game_id)
            if not game:
                return

            all_players = Player.query.filter_by(game_id=game_id).all()

            socketio.emit("server", {
                "type": "game.ended",
                "winner": game.winner,
                "ai_player_id": game.ai_player_id,
                "all_players": [p.to_dict() for p in all_players]
            }, room=game_id)

            # Stop timer
            game_state = get_game_state(game_id)
            game_state.timer_stop.set()

    except Exception as e:
        print(f"Error sending game ended: {e}")
        import traceback
        traceback.print_exc()


def register_game_handlers(socketio, app):
    """Register game-related socket event handlers."""

    @socketio.on("game.create")
    def handle_game_create(data):
        """Handle game creation."""
        print(f"Game create request from {request.sid}")

        try:
            with app.app_context():
                # Get user info from request context (set during connection)
                from backend.sockets.handlers import client_info
                user_info = client_info.get(request.sid, {"name": "anon", "user_id": None})
                user_id = user_info.get("user_id")

                if not user_id:
                    socketio.emit("server", {
                        "type": "error",
                        "message": "Must be logged in to create a game"
                    }, to=request.sid)
                    return

                # Create new game
                current_time = int(time.time() * 1000)
                game = Game(
                    created_at=current_time
                )
                db.session.add(game)
                db.session.flush()  # Get game.id

                # Create host player with anonymized name
                player_name = _generate_player_name([])
                player = Player(
                    game_id=game.id,
                    user_id=int(user_id),
                    socket_id=request.sid,
                    player_name=player_name,
                    is_host=True,
                    joined_at=current_time
                )
                db.session.add(player)
                db.session.commit()

                # Join socket room
                socketio_join_room(game.id)

                # Send game created event
                socketio.emit("server", {
                    "type": "game.created",
                    "game": game.to_dict(),
                    "player": player.to_dict()
                }, to=request.sid)

                print(f"Game {game.id} created by user {user_id}")

        except Exception as e:
            print(f"Error creating game: {e}")
            import traceback
            traceback.print_exc()
            with app.app_context():
                db.session.rollback()
            socketio.emit("server", {
                "type": "error",
                "message": "Failed to create game"
            }, to=request.sid)

    @socketio.on("game.join")
    def handle_game_join(data):
        """Handle player joining a game."""
        game_code = data.get("game_id", "").strip()

        if not game_code:
            socketio.emit("server", {
                "type": "error",
                "message": "Game ID required"
            }, to=request.sid)
            return

        try:
            with app.app_context():
                # Support both short codes (8 chars) and full UUIDs
                if len(game_code) < 36:
                    # Short code - search for games that start with this code (case-insensitive)
                    # Convert to lowercase for consistent searching
                    game_code_lower = game_code.lower()
                    all_games = Game.query.filter_by(status='lobby').all()
                    game = None
                    for g in all_games:
                        if g.id.lower().startswith(game_code_lower):
                            game = g
                            break
                    game_id = game.id if game else game_code
                else:
                    # Full UUID
                    game_id = game_code
                    game = Game.query.get(game_id)

                if not game:
                    socketio.emit("server", {
                        "type": "error",
                        "message": "Game not found"
                    }, to=request.sid)
                    return

                if game.status != 'lobby':
                    socketio.emit("server", {
                        "type": "error",
                        "message": "Game already started"
                    }, to=request.sid)
                    return

                # Get user info
                from backend.sockets.handlers import client_info
                user_info = client_info.get(request.sid, {"name": "anon", "user_id": None})
                user_id = user_info.get("user_id")

                if not user_id:
                    socketio.emit("server", {
                        "type": "error",
                        "message": "Must be logged in to join game"
                    }, to=request.sid)
                    return

                # Check if player already in game
                existing_player = Player.query.filter_by(
                    game_id=game_id,
                    user_id=int(user_id)
                ).first()

                if existing_player:
                    # Rejoin
                    existing_player.socket_id = request.sid
                    db.session.commit()

                    socketio_join_room(game_id)

                    all_players = Player.query.filter_by(game_id=game_id).all()
                    socketio.emit("server", {
                        "type": "game.joined",
                        "game": game.to_dict(),
                        "players": [p.to_dict() for p in all_players]
                    }, to=request.sid)
                    return

                # Get existing player names
                existing_players = Player.query.filter_by(game_id=game_id).all()
                existing_names = [p.player_name for p in existing_players]

                # Create new player
                player_name = _generate_player_name(existing_names)
                current_time = int(time.time() * 1000)

                player = Player(
                    game_id=game_id,
                    user_id=int(user_id),
                    socket_id=request.sid,
                    player_name=player_name,
                    joined_at=current_time
                )
                db.session.add(player)
                db.session.commit()

                # Join socket room
                socketio_join_room(game_id)

                # Send joined confirmation to this player
                all_players = Player.query.filter_by(game_id=game_id).all()
                socketio.emit("server", {
                    "type": "game.joined",
                    "game": game.to_dict(),
                    "players": [p.to_dict() for p in all_players]
                }, to=request.sid)

                # Notify others in the game
                socketio.emit("server", {
                    "type": "game.player.joined",
                    "player": player.to_dict()
                }, room=game_id, skip_sid=request.sid)

                print(f"Player {player.player_name} joined game {game_id}")

        except Exception as e:
            print(f"Error joining game: {e}")
            import traceback
            traceback.print_exc()
            with app.app_context():
                db.session.rollback()
            socketio.emit("server", {
                "type": "error",
                "message": "Failed to join game"
            }, to=request.sid)

    @socketio.on("game.start")
    def handle_game_start(data):
        """Handle starting a game."""
        game_id = data.get("game_id")

        if not game_id:
            socketio.emit("server", {
                "type": "error",
                "message": "Game ID required"
            }, to=request.sid)
            return

        try:
            with app.app_context():
                game = Game.query.get(game_id)
                if not game:
                    socketio.emit("server", {
                        "type": "error",
                        "message": "Game not found"
                    }, to=request.sid)
                    return

                if game.status != 'lobby':
                    socketio.emit("server", {
                        "type": "error",
                        "message": "Game already started"
                    }, to=request.sid)
                    return

                # Check if requester is host
                from backend.sockets.handlers import client_info
                user_info = client_info.get(request.sid, {"name": "anon", "user_id": None})
                user_id = user_info.get("user_id")

                host = Player.query.filter_by(game_id=game_id, is_host=True).first()
                if not host or host.user_id != int(user_id):
                    socketio.emit("server", {
                        "type": "error",
                        "message": "Only the host can start the game"
                    }, to=request.sid)
                    return

                # Check minimum players (3 humans + 1 AI = 4 total)
                players = Player.query.filter_by(game_id=game_id).all()
                if len(players) < 3:
                    socketio.emit("server", {
                        "type": "error",
                        "message": "Need at least 3 players to start"
                    }, to=request.sid)
                    return

                # Create AI player
                existing_names = [p.player_name for p in players]
                ai_name = _generate_player_name(existing_names)
                current_time = int(time.time() * 1000)

                ai_player = Player(
                    game_id=game_id,
                    user_id=None,
                    player_name=ai_name,
                    is_ai=True,
                    joined_at=current_time
                )
                db.session.add(ai_player)
                db.session.flush()

                # Start game
                game.status = 'playing'
                game.started_at = current_time
                game.current_round = 1
                game.round_phase = 'chat'
                game.phase_start_time = current_time
                game.ai_player_id = ai_player.id

                db.session.commit()

                # Notify all players
                all_players = Player.query.filter_by(game_id=game_id).all()
                socketio.emit("server", {
                    "type": "game.started",
                    "game": game.to_dict(),
                    "players": [p.to_dict() for p in all_players]
                }, room=game_id)

                # Start round
                socketio.emit("server", {
                    "type": "game.round.start",
                    "round": 1
                }, room=game_id)

                # Start chat phase timer
                _start_phase_timer(socketio, game_id, game.chat_duration_ms, app)

                print(f"Game {game_id} started with {len(all_players)} players (including AI)")

                # AI will respond when players start chatting (no automatic intro)

        except Exception as e:
            print(f"Error starting game: {e}")
            import traceback
            traceback.print_exc()
            with app.app_context():
                db.session.rollback()
            socketio.emit("server", {
                "type": "error",
                "message": "Failed to start game"
            }, to=request.sid)

    @socketio.on("game.message")
    def handle_game_message(data):
        """Handle player sending a message in game."""
        text = data.get("text", "").strip()

        if not text:
            return

        try:
            with app.app_context():
                # Find which game this player is in
                from backend.sockets.handlers import client_info
                user_info = client_info.get(request.sid, {"name": "anon", "user_id": None})
                user_id = user_info.get("user_id")

                if not user_id:
                    return

                player = Player.query.filter_by(
                    user_id=int(user_id),
                    socket_id=request.sid,
                    is_active=True
                ).first()

                if not player:
                    return

                game = Game.query.get(player.game_id)
                if not game or game.status != 'playing' or game.round_phase != 'chat':
                    socketio.emit("server", {
                        "type": "error",
                        "message": "Cannot send message now"
                    }, to=request.sid)
                    return

                # Add message to game state
                game_state = get_game_state(player.game_id)
                msg = game_state.add_message(player.player_name, text)

                # Broadcast message
                socketio.emit("server", {
                    "type": "game.message",
                    "message": msg
                }, room=player.game_id)

                # Maybe trigger AI response
                if random.random() < 0.4:  # 40% chance AI responds
                    def delayed_ai_response():
                        time.sleep(random.uniform(2, 6))
                        _ai_generate_message(socketio, player.game_id, game_state, app)

                    threading.Thread(target=delayed_ai_response, daemon=True).start()

        except Exception as e:
            print(f"Error handling game message: {e}")
            import traceback
            traceback.print_exc()

    @socketio.on("game.vote")
    def handle_game_vote(data):
        """Handle player voting for someone."""
        voted_for_id = data.get("voted_for_id")

        if not voted_for_id:
            return

        try:
            with app.app_context():
                # Find player
                from backend.sockets.handlers import client_info
                user_info = client_info.get(request.sid, {"name": "anon", "user_id": None})
                user_id = user_info.get("user_id")

                if not user_id:
                    return

                player = Player.query.filter_by(
                    user_id=int(user_id),
                    socket_id=request.sid,
                    is_active=True
                ).first()

                if not player:
                    return

                game = Game.query.get(player.game_id)
                if not game or game.status != 'playing' or game.round_phase != 'voting':
                    socketio.emit("server", {
                        "type": "error",
                        "message": "Cannot vote now"
                    }, to=request.sid)
                    return

                # Record vote
                player.current_vote = voted_for_id
                db.session.commit()

                # Confirm vote received
                socketio.emit("server", {
                    "type": "game.vote.received"
                }, to=request.sid)

                # Check if everyone has voted
                active_players = Player.query.filter_by(
                    game_id=player.game_id,
                    is_active=True,
                    is_ai=False
                ).all()

                votes_cast = sum(1 for p in active_players if p.current_vote)
                total_active = len(active_players)

                # Check for supermajority (2/3 voted)
                if votes_cast >= (total_active * 2 // 3) and total_active >= 3:
                    socketio.emit("server", {
                        "type": "game.vote.supermajority",
                        "votes_cast": votes_cast,
                        "total_active": total_active
                    }, room=player.game_id)

        except Exception as e:
            print(f"Error handling vote: {e}")
            import traceback
            traceback.print_exc()
            with app.app_context():
                db.session.rollback()

    @socketio.on("game.vote.force_end")
    def handle_force_end_vote(data):
        """Handle force ending the voting phase (when supermajority reached)."""
        try:
            with app.app_context():
                # Find player
                from backend.sockets.handlers import client_info
                user_info = client_info.get(request.sid, {"name": "anon", "user_id": None})
                user_id = user_info.get("user_id")

                if not user_id:
                    return

                player = Player.query.filter_by(
                    user_id=int(user_id),
                    socket_id=request.sid
                ).first()

                if not player:
                    return

                game = Game.query.get(player.game_id)
                if not game or game.status != 'playing' or game.round_phase != 'voting':
                    return

                # Stop timer and process votes
                game_state = get_game_state(player.game_id)
                game_state.timer_stop.set()

                _process_votes(socketio, player.game_id, app)

        except Exception as e:
            print(f"Error force ending vote: {e}")
            import traceback
            traceback.print_exc()

    @socketio.on("game.leave")
    def handle_game_leave(data):
        """Handle player leaving a game."""
        game_id = data.get("game_id")

        if not game_id:
            return

        try:
            with app.app_context():
                from backend.sockets.handlers import client_info
                user_info = client_info.get(request.sid, {"name": "anon", "user_id": None})
                user_id = user_info.get("user_id")

                if not user_id:
                    return

                player = Player.query.filter_by(
                    game_id=game_id,
                    user_id=int(user_id)
                ).first()

                if not player:
                    return

                # Remove player
                db.session.delete(player)
                db.session.commit()

                # Notify others
                socketio.emit("server", {
                    "type": "game.player.left",
                    "player_id": player.id
                }, room=game_id)

                print(f"Player {player.player_name} left game {game_id}")

        except Exception as e:
            print(f"Error leaving game: {e}")
            import traceback
            traceback.print_exc()
            with app.app_context():
                db.session.rollback()
