# models/db/chat.py
from sqlalchemy import Column, String, Text, DateTime, Index
from sqlalchemy.dialects.postgresql import UUID
import uuid
from datetime import datetime, timezone
from .base_model import Base

class ChatTurn(Base):
    __tablename__ = "chat_turns"

    # Use UUID for the primary key
    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    
    # Adding length limits to Strings saves RAM in PostgreSQL indexes
    agent_id = Column(String(100), nullable=False)
    platform = Column(String(50), nullable=False) 
    sender_id = Column(String(100), nullable=False)
    
    user_message = Column(Text, nullable=True)
    user_message_timestamp = Column(DateTime(timezone=True), default=lambda: datetime.now(timezone.utc))
    ai_response = Column(Text, nullable=False)
    timestamp = Column(DateTime(timezone=True), default=lambda: datetime.now(timezone.utc))

    # --- THE PERFECT COMPOSITE INDEX ---
    __table_args__ = (
        # We drop the individual indexes and create ONE index that perfectly matches our query.
        # Notice we index the timestamp in DESCENDING order.
        Index(
            'ix_chat_history_lookup', 
            'agent_id', 
            'platform', 
            'sender_id', 
            timestamp.desc()
        ),
    )