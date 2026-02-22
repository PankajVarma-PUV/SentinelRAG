
import asyncio
import sys
import os
from datetime import datetime

# Add src to path
sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))

from src.core.database import SentinelRAGDatabase
from src.agents.metacognitive_brain import MetacognitiveBrain
from src.core.memory import MemoryManager

async def verify_attribution():
    print("Initializing components...")
    db = SentinelRAGDatabase()
    memory = MemoryManager(db)
    brain = MetacognitiveBrain(db, memory)
    
    # 1. Setup Conversation
    conv_id = f"test_attr_{int(datetime.now().timestamp())}"
    db.create_conversation(conversation_id=conv_id, name="Attribution Test")
    print(f"Created conversation: {conv_id}")

    # 2. Add 'cats.txt' (Text Asset)
    print("Injecting cats.txt...")
    file_id_txt = db.register_document(
        file_name="cats.txt",
        file_hash="hash_cats_txt",
        file_type="document",
        conversation_id=conv_id,
        file_path="cats.txt"
    )
    db.add_knowledge([{
        "text": "Domestic cats (Felis catus) are small carnivorous mammals.",
        "vector": [0.1]*1024, # Dummy vector matching schema
        "file_name": "cats.txt",
        "conversation_id": conv_id,
        "metadata": {"file_name": "cats.txt", "type": "document"}
    }])
    # Also inject into enriched_content for the new RAG logic
    db.add_enriched_content(
        file_id=file_id_txt,
        conversation_id=conv_id,
        original_content="Domestic cats (Felis catus) are small carnivorous mammals.",
        enriched_content="Domestic cats (Felis catus) are small carnivorous mammals.",
        content_type="text",
        file_name="cats.txt"
    )

    # 3. Add 'cat.jpg' (Visual Asset)
    print("Injecting cat.jpg...")
    file_id_jpg = db.register_document(
        file_name="cat.jpg",
        file_hash="hash_cat_jpg",
        file_type="image",
        conversation_id=conv_id,
        file_path="cat.jpg"
    )
    db.add_scraped_content(
        file_id=file_id_jpg,
        content="The image shows a small kitten with blue eyes and cream fur.",
        sub_type="vision",
        metadata={"file_name": "cat.jpg", "type": "image"}
    )
    db.add_enriched_content(
        file_id=file_id_jpg,
        conversation_id=conv_id,
        original_content="[Image Binary]",
        enriched_content="The image shows a small kitten with blue eyes and cream fur.",
        content_type="image",
        file_name="cat.jpg"
    )

    # 4. Test Case 1: Loose match @cat -> Should match cat.jpg (base name)
    print("\n--- Test Case 1: @cat (Targeting cat.jpg) ---")
    state_1 = {
        "query": "what color of eyes?",
        "conversation_id": conv_id,
        "mentioned_files": ["cat"], # The ambiguous tag
        "intent": "rag"
    }
    
    # Manually run execute_rag based on the new logic
    # We need to simulate the Extractor first because execute_rag now relies on unified_evidence
    print("Running Extractor...")
    extractor_out = await brain.run_extractor(state_1)
    state_1["unified_evidence"] = extractor_out["unified_evidence"]
    
    # Now run RAG
    print("Running RAG...")
    rag_out = await brain.execute_rag(state_1)
    
    evidence = rag_out.get("evidence", [])
    print(f"Result Evidence Count: {len(evidence)}")
    
    found_jpg = False
    found_txt = False
    for e in evidence:
        print(f" - Found evidence from: {e['file_name']}")
        if e['file_name'] == 'cat.jpg': found_jpg = True
        if e['file_name'] == 'cats.txt': found_txt = True
        
    if found_jpg and not found_txt:
        print("PASS: Correctly identified cat.jpg and ignored cats.txt for '@cat'")
    else:
        print(f"FAIL: Expected/Actual mismatch. Jpg={found_jpg}, Txt={found_txt}")

    # 5. Test Case 2: Exact match @cats.txt
    print("\n--- Test Case 2: @cats.txt ---")
    state_2 = {
        "query": "tell me about it",
        "conversation_id": conv_id,
        "mentioned_files": ["cats.txt"],
        "intent": "rag"
    }
    extractor_out_2 = await brain.run_extractor(state_2)
    state_2["unified_evidence"] = extractor_out_2["unified_evidence"]
    rag_out_2 = await brain.execute_rag(state_2)
    
    evidence_2 = rag_out_2.get("evidence", [])
    found_txt_2 = any(e['file_name'] == 'cats.txt' for e in evidence_2)
    
    if found_txt_2:
         print("PASS: Correctly identified cats.txt")
    else:
         print("FAIL: Could not find cats.txt")


if __name__ == "__main__":
    asyncio.run(verify_attribution())
