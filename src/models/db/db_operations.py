# models/db/db_operations.py
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select
from models.db.chat import ChatTurn
import datetime

async def save_chat_turn(
    session: AsyncSession, 
    agent_id: str, 
    platform: str, 
    sender_info: dict, 
    user_message: str, 
    ai_response: str, 
    user_message_timestamp: datetime
) -> ChatTurn:
    """Saves a single turn of conversation to the database."""
    new_turn = ChatTurn(
        agent_id=agent_id,
        platform=platform, 
        sender_id=sender_info["username"],
        user_message=user_message,
        ai_response=ai_response,
        user_message_timestamp=user_message_timestamp
    )
    session.add(new_turn)
    await session.commit()
    await session.refresh(new_turn)
    return new_turn

async def get_recent_history(
    session: AsyncSession, 
    agent_id: str, 
    platform: str, 
    sender_info: dict, 
    limit: int = 10
) -> list[ChatTurn]:
    """Fetches the last N messages, utilizing the pre-sorted composite index."""
    
    query = select(ChatTurn)\
        .where(
            ChatTurn.agent_id == agent_id, 
            ChatTurn.platform == platform, 
            ChatTurn.sender_id == sender_info["username"]
        )\
        .order_by(ChatTurn.timestamp.desc())\
        .limit(limit)
    
    result = await session.execute(query)
    turns = result.scalars().all()
    
    return list(reversed(turns))
