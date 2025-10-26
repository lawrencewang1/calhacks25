"""
Player model for Find the AI game.

Tracks player state, votes, and activity within a game.
"""

import uuid
from backend.extensions import db


class Player(db.Model):
    """Player model for tracking participants in Find the AI game."""

    __tablename__ = 'players'

    id = db.Column(db.String(36), primary_key=True, default=lambda: str(uuid.uuid4()))
    game_id = db.Column(db.String(36), db.ForeignKey('games.id'), nullable=False)
    user_id = db.Column(db.Integer, db.ForeignKey('users.id'))  # None for AI players
    socket_id = db.Column(db.String(100))  # Current socket connection
    player_name = db.Column(db.String(50), nullable=False)  # Anonymized display name
    is_ai = db.Column(db.Boolean, nullable=False, default=False)
    is_active = db.Column(db.Boolean, nullable=False, default=True)  # False if voted out
    is_host = db.Column(db.Boolean, nullable=False, default=False)  # First player is host
    current_vote = db.Column(db.String(36))  # ID of player they voted for
    joined_at = db.Column(db.BigInteger, nullable=False)  # Timestamp in milliseconds

    # Relationships
    game = db.relationship('Game', back_populates='players')

    def to_dict(self):
        """Convert player to dictionary representation."""
        return {
            'id': self.id,
            'game_id': self.game_id,
            'user_id': self.user_id,
            'player_name': self.player_name,
            'is_ai': self.is_ai,
            'is_active': self.is_active,
            'is_host': self.is_host,
            'joined_at': self.joined_at
        }
