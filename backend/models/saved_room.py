from backend.extensions import db
import time

class SavedRoom(db.Model):
    """Track rooms that users have saved/joined."""
    __tablename__ = "saved_rooms"

    id = db.Column(db.Integer, primary_key=True, autoincrement=True)
    user_id = db.Column(db.Integer, db.ForeignKey('users.id'), nullable=False, index=True)
    room_id = db.Column(db.String(36), db.ForeignKey('rooms.id'), nullable=False, index=True)
    saved_at = db.Column(db.Integer, nullable=False, default=lambda: int(time.time() * 1000))

    # Unique constraint to prevent duplicate saves
    __table_args__ = (
        db.UniqueConstraint('user_id', 'room_id', name='unique_user_room'),
    )

    def to_dict(self):
        return {
            'id': self.id,
            'user_id': self.user_id,
            'room_id': self.room_id,
            'saved_at': self.saved_at
        }
