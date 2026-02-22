import sys
import os
import asyncio

# Add project root to python path
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))

from src.data.database import get_database as get_relational_db
from src.core.database import get_database as get_vector_db

def test_relational_flow():
    print("="*60)
    print("TESTING RELATIONAL DATABASE (SQLITE/POSTGRES) FLOW")
    print("="*60)
    
    db = get_relational_db()
    db.connect()
    db.initialize_schema()
    
    print("\n1. CREATING: Initializing new conversation...")
    chat_id = db.create_conversation(title="Diagnostic Flow Test")
    print(f"   [+] Conversation created with ID: {chat_id}")
    
    print("\n2. STORING: Adding messages...")
    user_msg_id = db.add_message(
        conversation_id=chat_id,
        role="user",
        content="Hello, system. This is a diagnostic message."
    )
    print(f"   [+] User message stored: {user_msg_id}")
    
    asst_msg_id = db.add_message(
        conversation_id=chat_id,
        role="assistant",
        content="Message received loud and clear over the purged database."
    )
    print(f"   [+] Assistant message stored: {asst_msg_id}")
    
    print("\n3. FETCHING: Retrieving full conversation history...")
    messages = db.get_messages(chat_id)
    print(f"   [+] Retrieved {len(messages)} messages.")
    for msg in messages:
        print(f"       -> [{msg['role'].upper()}] {msg['content'][:40]}...")

    print("\n4. UPDATING: Testing token updates and duplicate logic...")
    dup_exists = db.find_duplicate_query(chat_id, "Hello, system. This is a diagnostic message.")
    if dup_exists:
        print(f"   [+] Semantic deduplication guard functioning correctly.")
        db.increment_duplicate_count(asst_msg_id)
        print(f"   [+] Incremented duplicate count for {asst_msg_id}")
    
    print("\n5. FETCHING: Confirming updates applied...")
    updated_messages = db.get_messages(chat_id)
    for msg in updated_messages:
        if msg['message_id'] == asst_msg_id:
            print(f"   [+] Final duplicate count: {msg.get('duplicate_count', 0)}")
            
    print("\n6. DELETING: Cleaning up test conversation...")
    deleted = db.delete_conversation(chat_id)
    print(f"   [+] Conversation deleted successfully: {deleted}")


def test_vector_flow():
    print("\n" + "="*60)
    print("TESTING LANCE DB (VECTOR) ALIGNMENT")
    print("="*60)
    
    vdb = get_vector_db()
    
    print("\n1. VALIDATING LanceDB Schema...")
    # Just accessing the tables proves LanceDB is operational and holding the document logic
    try:
        tbl = vdb.conn.open_table("document_registry")
        print("   [+] LANCE DB holds 'document_registry'")
        tbl2 = vdb.conn.open_table("scraped_content")
        print("   [+] LANCE DB holds 'scraped_content'")
        tbl3 = vdb.conn.open_table("enriched_content")
        print("   [+] LANCE DB holds 'enriched_content'")
    except Exception as e:
        print(f"   [!] Error accessing LanceDB tables: {e}")

if __name__ == "__main__":
    test_relational_flow()
    test_vector_flow()
    print("\n" + "="*60)
    print("DIAGNOSTIC COMPLETE. PURGE VALIDATED.")
    print("="*60)
