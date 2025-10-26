from backend.extensions import db
import uuid, time

class Room(db.Model):
    __tablename__ = "rooms"

    id = db.Column(db.String(36), primary_key=True, default=lambda: str(uuid.uuid4()))
    name = db.Column(db.String(100), nullable=False)
    created_by = db.Column(db.Integer, db.ForeignKey('users.id'), nullable=False, index=True)
    created_at = db.Column(db.Integer, nullable=False, default=lambda: int(time.time() * 1000))
    is_active = db.Column(db.Boolean, default=True, nullable=False, index=True)
    is_official = db.Column(db.Boolean, default=False, nullable=False, index=True)
    is_public = db.Column(db.Boolean, default=True, nullable=False, index=True)

    # Relationship to messages
    messages = db.relationship('Message', backref='room', lazy=True, cascade='all, delete-orphan')

    def to_dict(self):
        return {
            'id': self.id,
            'name': self.name,
            'created_by': self.created_by,
            'created_at': self.created_at,
            'is_active': self.is_active,
            'is_official': self.is_official,
            'is_public': self.is_public
        }
