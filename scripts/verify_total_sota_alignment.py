import os
import sys
from pathlib import Path

# Add project root to path
sys.path.append(str(Path(__file__).parent.parent))

from src.core.ollama_client import get_ollama_client, OllamaClient
from src.core.database import get_database
from src.agents.synthesizer import SynthesizerAgent
from src.core.config import ChunkingConfig

def test_ollama_singleton():
    print("--- [1] Testing Ollama Singleton ---")
    c1 = get_ollama_client()
    c2 = get_ollama_client()
    assert c1 is c2, "FAILED: get_ollama_client is NOT a singleton!"
    print("PASS: OllamaClient is a verified singleton.")

def test_database_indexing_methods():
    print("\n--- [2] Testing Database Indexing Methods ---")
    db = get_database()
    print(f"Database type: {type(db)}")
    print(f"Has add_knowledge_from_text: {hasattr(db, 'add_knowledge_from_text')}")
    if hasattr(db, 'add_knowledge_from_text'):
        import inspect
        sig = inspect.signature(db.add_knowledge_from_text)
        print(f"Signature: {sig}")
    
    assert hasattr(db, 'add_knowledge_from_text'), "FAILED: database missing add_knowledge_from_text"
    assert hasattr(db, 'search_knowledge'), "FAILED: database missing search_knowledge"
    print("PASS: Database indexing methods are present.")

def test_indexing_flow():
    print("\n--- [3] Testing Indexing Flow ---")
    db = get_database()
    chat_id = "test_indexing_session"
    file_name = "test_logic_check.txt"
    test_text = "The secret sequence is 9-8-7-6-5-4-3-2-1. This is unique content for indexing test."
    
    # Clean up old test data if any
    try:
        db.conn.open_table("knowledge_base").delete(f"conversation_id = '{chat_id}'")
    except:
        pass
        
    print(f"Indexing test content for {chat_id}...")
    db.add_knowledge_from_text(
        text=test_text,
        file_name=file_name,
        conversation_id=chat_id,
        project_id="default"
    )
    
    # Search for it
    from src.data.embedder import get_embedder
    embedder = get_embedder()
    query_vec = embedder.encode("what is the secret sequence?").tolist()
    
    results = db.search_knowledge(query_vec, project_id="default", conversation_id=None, limit=5)
    
    found = False
    for res in results:
        if "secret sequence" in res.get('text', ''):
            print(f"PASS: Found indexed content in RAG search! Chunk: {res['text'][:50]}...")
            found = True
            break
    
    if not found:
        print("FAILED: Indexed content not found in search results.")
        sys.exit(1)

def test_citation_matching():
    print("\n--- [4] Testing Citation Matching Logic ---")
    agent = SynthesizerAgent()
    
    # Mock chunks
    chunks = [
        {
            "source": "SentinelRAG_Architecture.pdf",
            "text": "The core engine uses LanceDB.",
            "chunk_id": "c1",
            "metadata": {"file_name": "SentinelRAG_Architecture.pdf"}
        },
        {
            "source": "cats.png",
            "text": "There is a cat in this image.",
            "chunk_id": "c2",
            "metadata": {"file_name": "cats.png"}
        }
    ]
    
    # Test 1: Full name match
    response1 = "Architectural details are found in [Source: SentinelRAG_Architecture.pdf]."
    citations1 = agent._extract_citations(response1, chunks)
    assert len(citations1) == 1 and citations1[0]['source'] == "SentinelRAG_Architecture.pdf", "FAILED: Full name citation match fail."
    
    # Test 2: Base name match (common for multimodal)
    response2 = "I see a feline here [Source: cats]."
    citations2 = agent._extract_citations(response2, chunks)
    assert len(citations2) == 1 and citations2[0]['source'] == "cats.png", "FAILED: Base name citation match fail."
    
    # Test 3: Mixed case match
    response3 = "LanceDB is used [Source: sentinelrag_architecture]."
    citations3 = agent._extract_citations(response3, chunks)
    assert len(citations3) == 1 and citations3[0]['source'] == "SentinelRAG_Architecture.pdf", "FAILED: Mixed case citation match fail."
    
    print("PASS: Citation matching logic (Full, Base, Case-Insensitive) is verified.")

if __name__ == "__main__":
    try:
        test_ollama_singleton()
        test_database_indexing_methods()
        test_indexing_flow()
        test_citation_matching()
        print("\n🏆 TOTAL SOTA ALIGNMENT VERIFIED: ALL SYSTEMS OPERATIONAL 🏆")
    except Exception as e:
        print(f"\n❌ VERIFICATION CRITICAL FAILURE: {e}")
        import traceback
        traceback.print_exc()
        sys.exit(1)
