from backend.extensions import db
import time

class RoomBan(db.Model):
    """Track banned users in rooms."""
    __tablename__ = "room_bans"

    id = db.Column(db.Integer, primary_key=True, autoincrement=True)
    room_id = db.Column(db.String(36), db.ForeignKey('rooms.id'), nullable=False, index=True)
    user_id = db.Column(db.Integer, db.ForeignKey('users.id'), nullable=False, index=True)
    banned_by = db.Column(db.Integer, db.ForeignKey('users.id'), nullable=False)
    banned_at = db.Column(db.Integer, nullable=False, default=lambda: int(time.time() * 1000))
    expires_at = db.Column(db.Integer, nullable=True)  # None for permanent ban, timestamp for temp ban
    reason = db.Column(db.String(500), nullable=True)
    is_active = db.Column(db.Boolean, default=True, nullable=False)

    def to_dict(self):
        return {
            'id': self.id,
            'room_id': self.room_id,
            'user_id': self.user_id,
            'banned_by': self.banned_by,
            'banned_at': self.banned_at,
            'expires_at': self.expires_at,
            'reason': self.reason,
            'is_active': self.is_active
        }

    def is_expired(self):
        """Check if temp ban has expired."""
        if self.expires_at is None:
            return False  # Permanent ban
        return int(time.time() * 1000) >= self.expires_at
