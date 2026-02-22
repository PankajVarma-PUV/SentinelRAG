
import asyncio
import json
import os
import sys

# Add project root to path
sys.path.append(os.getcwd())

from src.data.database import get_database
from src.agents.metacognitive_brain import MetacognitiveBrain, SentinelRAGState
from src.agents.fusion_extractor import UniversalFusionExtractor

async def verify_unified_architecture():
    print("Starting Unified Architecture Verification...")
    db = get_database()
    print(f"DEBUG: db type is {type(db)}")
    import inspect
    print(f"DEBUG: add_scraped_content signature: {inspect.signature(db.add_scraped_content)}")
    
    db.connect()
    # 1. Setup Test Data
    conversation_id = "test_unified_conv_001"
    file_id = "test_file_unified_001"
    file_name = "test_document.png"
    
    # Cleanup if exists
    with db.backend.get_cursor() as cursor:
        cursor.execute("DELETE FROM enriched_content WHERE file_id = ?", (file_id,))
        cursor.execute("DELETE FROM scraped_content WHERE file_id = ?", (file_id,))
        cursor.execute("DELETE FROM document_registry WHERE file_id = ?", (file_id,))
    
    # Register document
    file_id = db.register_document(
        file_name,
        "fake_hash_unified",
        "image",
        conversation_id,
        "/fake/path/test.png"
    )
    
    # Add MULTIPLE legacy items (This usually caused duplicate cards)
    db.add_scraped_content(file_id, "Legacy Vision: A blue car.", "vision", metadata={"type": "vision"})
    db.add_scraped_content(file_id, "TEXT FROM IMAGE: SECURED AREA", "ocr", metadata={"type": "ocr"})
    
    # Add ONE unified enriched item
    enriched_content = "This is a high-fidelity enriched description of the blue car in the secured area. It consolidates vision and OCR data."
    db.add_enriched_content(
        file_id,
        conversation_id,
        "Legacy Vision: A blue car.\nTEXT FROM IMAGE: SECURED AREA",
        enriched_content,
        "image",
        file_name
    )
    
    print("✅ Test data populated with legacy duplicates and one enriched SOTA entry.")

    # 2. Verify MetacognitiveBrain Perception Pass
    from src.core.database import SentinelRAGDatabase
    from src.core.memory import MemoryManager
    
    rag_db = SentinelRAGDatabase()
    memory = MemoryManager(rag_db)
    brain = MetacognitiveBrain(rag_db, memory, sqlite_db=db)
    state = {"conversation_id": conversation_id, "query": "What is in the image?", "history": []}
    
    perception_data = await brain.process_perception(state)
    perceived_media = perception_data.get("perceived_media", [])
    
    print(f"Perception Result: Found {len(perceived_media)} media items.")
    for item in perceived_media:
        print(f"  - [{item.get('type')}] {item.get('file_name')}: {item.get('content')[:50]}...")

    if len(perceived_media) == 1 and perceived_media[0]['content'] == enriched_content:
        print("✅ SUCCESS: MetacognitiveBrain correctly prioritized enriched content over legacy duplicates.")
    else:
        print("❌ FAILURE: MetacognitiveBrain found duplicates or incorrect content.")

    # 3. Verify FusionExtractor
    extractor = UniversalFusionExtractor(db=db)
    fused_state = await extractor.extract_and_fuse(conversation_id)
    
    print(f"Fusion Result: {len(fused_state.visual_evidence)} visual items.")
    if len(fused_state.visual_evidence) == 1:
        print("✅ SUCCESS: FusionExtractor consolidated evidence using the unified source.")
    else:
        print("❌ FAILURE: FusionExtractor still has duplicate evidence items.")

    # 4. Cleanup
    with db.backend.get_cursor() as cursor:
        cursor.execute("DELETE FROM enriched_content WHERE file_id = ?", (file_id,))
        cursor.execute("DELETE FROM scraped_content WHERE file_id = ?", (file_id,))
        cursor.execute("DELETE FROM document_registry WHERE file_id = ?", (file_id,))
    
    print("Verification complete.")

if __name__ == "__main__":
    asyncio.run(verify_unified_architecture())
