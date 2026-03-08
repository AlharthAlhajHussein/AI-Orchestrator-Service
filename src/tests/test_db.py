# test_db.py
import asyncio
from models.db.database_setup import SessionLocal
from models.db.db_operations import save_chat_turn, get_recent_history
from datetime import datetime, timezone


async def run_db_test():
    agent = "agent-123"
    user = "+15551234567"

    # Open a database session
    async with SessionLocal() as session:
        print("1. Saving mock conversations...")
        await save_chat_turn(session, agent, user, "Hi, I need help.", "Hello! How can I assist you today?", datetime.now(timezone.utc))
        await save_chat_turn(session, agent, user, "What are your hours?", "We are open 24/7.", datetime.now(timezone.utc))
        await save_chat_turn(session, agent, user, "Great, thanks.", "You're welcome!", datetime.now(timezone.utc))

        print("\n2. Fetching recent history (Limit 2)...")
        history = await get_recent_history(session, agent, user, limit=2)
        
        for turn in history:
            print(f"User: {turn.user_message}")
            print(f"AI: {turn.ai_response}")
            print("-" * 20)

if __name__ == "__main__":
    # Run the async test script
    asyncio.run(run_db_test())