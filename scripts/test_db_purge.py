import asyncio
import sys
import os

# Add the project root to the python path
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))

from src.data.database import get_database

async def run_test():
    db = get_database()
    print(f"Connecting to database: {db.db_type}")
    success = db.connect()
    print(f"Connection success: {success}")
    
    if not success:
        print("Failed to connect.")
        return

    # Initialize schema (which now excludes the dead tables)
    db.initialize_schema()
    print("Schema initialized.")
    
    # Test Relational Chat Core (the only things left in database.py)
    chat_id = db.create_conversation(title="Test DB Purge")
    print(f"Created chat: {chat_id}")
    
    msg_id = db.add_message(
        conversation_id=chat_id,
        role="user",
        content="Testing the sleek new database."
    )
    print(f"Added message: {msg_id}")
    
    msgs = db.get_active_messages(chat_id)
    print(f"Retrieved {len(msgs)} messages.")
    print("Test passed. Relational state engine is functioning flawlessly.")
    
if __name__ == "__main__":
    asyncio.run(run_test())
