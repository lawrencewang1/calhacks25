"""
Game model for Find the AI game.

Tracks game state, rounds, phases, and timing.
"""

import uuid
from backend.extensions import db


class Game(db.Model):
    """Game model for tracking Find the AI game sessions."""

    __tablename__ = 'games'

    id = db.Column(db.String(36), primary_key=True, default=lambda: str(uuid.uuid4()))
    status = db.Column(db.String(20), nullable=False, default='lobby')  # lobby, playing, ended
    current_round = db.Column(db.Integer, nullable=False, default=1)
    round_phase = db.Column(db.String(20), nullable=False, default='chat')  # chat, voting
    phase_start_time = db.Column(db.BigInteger)  # Timestamp in milliseconds
    chat_duration_ms = db.Column(db.Integer, default=180000)  # 3 minutes default
    vote_duration_ms = db.Column(db.Integer, default=60000)   # 1 minute default
    winner = db.Column(db.String(20))  # humans, ai, or None
    ai_player_id = db.Column(db.String(36))  # ID of the AI player
    created_at = db.Column(db.BigInteger, nullable=False)  # Timestamp in milliseconds
    started_at = db.Column(db.BigInteger)  # Timestamp in milliseconds when game started
    ended_at = db.Column(db.BigInteger)  # Timestamp in milliseconds when game ended

    # Relationships
    players = db.relationship('Player', back_populates='game', cascade='all, delete-orphan')

    def to_dict(self):
        """Convert game to dictionary representation."""
        return {
            'id': self.id,
            'status': self.status,
            'current_round': self.current_round,
            'round_phase': self.round_phase,
            'phase_start_time': self.phase_start_time,
            'chat_duration_ms': self.chat_duration_ms,
            'vote_duration_ms': self.vote_duration_ms,
            'winner': self.winner,
            'ai_player_id': self.ai_player_id,
            'created_at': self.created_at,
            'started_at': self.started_at,
            'ended_at': self.ended_at
        }
