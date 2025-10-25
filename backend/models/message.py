from backend.extensions import db
import uuid, time

class Message(db.Model):
    __tablename__ = "messages"
    id = db.Column(db.String(36), primary_key=True, default=lambda: str(uuid.uuid4()))
    room_seq = db.Column(db.Integer, nullable=False, index=True)
    sender = db.Column(db.String(64), nullable=False)  # "user:<name>" or "assistant"
    text = db.Column(db.Text, nullable=False)
    timestamp = db.Column(db.Integer, nullable=False, default=lambda: int(time.time() * 1000))