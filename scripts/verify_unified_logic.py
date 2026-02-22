
import asyncio
import json
import os
import sys
import traceback

# Add project root to path
sys.path.append(os.getcwd())

from src.data.database import get_database

async def verify_unified_logic():
    print("--- STARTING LIGHTWEIGHT LOGIC VERIFICATION ---")
    db = get_database()
    try:
        db.connect()
        
        # 1. Setup Test Data
        conv_id = db.create_conversation(title="Verification Chat")
        file_hash = "hash_logic_verification_vfinal"
        
        # Cleanup if exists
        doc = db.get_document_by_hash(file_hash)
        if doc:
            db.delete_document_by_hash(file_hash)
            print(f"Deleted existing doc with hash {file_hash}")

        # Register document
        file_id = db.register_document(
            file_name="test.png",
            file_hash=file_hash,
            file_type="image",
            conversation_id=conv_id,
            file_path="/fake/path/test.png"
        )
        print(f"✅ Document registered: {file_id}")

        # Add Legacy Scraped Content (2 items)
        db.add_scraped_content(file_id, "Legacy Vision 1", "vision")
        db.add_scraped_content(file_id, "Legacy OCR 1", "ocr")
        
        # Add Unified Enriched Content (1 item)
        enriched_text = "Unified high-fidelity description."
        db.add_enriched_content(
            file_id=file_id,
            conversation_id=conv_id,
            original_content="Legacy 1 + Legacy 2",
            enriched_content=enriched_text,
            content_type="image",
            file_name="test.png"
        )
        
        print("✅ Database populated.")

        # 2. Test get_enriched_content_by_chat
        enriched_results = db.get_enriched_content_by_chat(conv_id)
        print(f"get_enriched_content_by_chat: Found {len(enriched_results)} items.")
        for res in enriched_results:
            print(f"  - Content: {res.get('enriched_content')}")
        
        if len(enriched_results) == 1 and enriched_results[0]['enriched_content'] == enriched_text:
            print("✅ SUCCESS: Found single enriched item for chat.")
        else:
            print("❌ FAILURE: Enriched retrieval failed.")

        # 3. Test deduplication in perception logic (simulated)
        scraped = db.get_enriched_content_by_chat(conv_id)
        if not scraped:
            scraped = db.get_scraped_content_by_chat(conv_id)
        
        assets = []
        seen = set()
        for item in scraped:
            content = item.get('enriched_content') or item.get('content', '')
            key = content[:200].strip().lower()
            if key not in seen:
                seen.add(key)
                assets.append(item)
        
        print(f"Simulated Perception Deduplication: {len(assets)} items.")
        if len(assets) == 1:
            print("✅ SUCCESS: Deduplication logic works by preferring enriched content.")
        else:
            print("❌ FAILURE: Deduplication logic failed.")

        # 4. Test @mention query
        mention_results = db.get_enriched_content_by_filenames(conv_id, ["test.png"])
        print(f"get_enriched_content_by_filenames: Found {len(mention_results)} items.")
        if len(mention_results) == 1:
            print("✅ SUCCESS: @mention targeting works on enriched_content.")
        else:
            print("❌ FAILURE: @mention targeting failed.")

    except Exception as e:
        print(f"❌ CRITICAL ERROR DURING VERIFICATION: {e}")
        traceback.print_exc()
    finally:
        # 5. Cleanup
        try:
            with db.get_cursor() as cursor:
                cursor.execute("DELETE FROM enriched_content WHERE file_name = 'test.png'")
                cursor.execute("DELETE FROM document_registry WHERE file_name = 'test.png'")
            print("--- CLEANUP COMPLETE ---")
        except: pass
        print("--- VERIFICATION COMPLETE ---")

if __name__ == "__main__":
    asyncio.run(verify_unified_logic())
