import asyncio
import sys
from unittest.mock import MagicMock

# Mocking parts of the system to test the Healer evidence gathering
class MockState(dict):
    pass

async def test_healer_evidence_fusion():
    # Simulate a state with both text and visual evidence
    state = MockState({
        "query": "What color are the cat's eyes?",
        "evidence": [
            {"file_name": "cats.txt", "text": "Cats are mammals."}
        ],
        "perceived_media": [
            {"file_name": "cat.jpg", "content": "The kitten has large, expressive blue eyes."}
        ],
        "answer": "I don't know.",
        "metadata": {"check": {"findings": ["Missing eye color information"]}}
    })

    # Logic from metacognitive_brain.py (simulated)
    evidence_parts = []
    for e in state.get("evidence", []):
        source = e.get("file_name") or "Document"
        text = e.get("text", "")
        evidence_parts.append(f"[SOURCE: {source}]: {text}")
    
    for p in state.get("perceived_media", []):
        source = p.get("file_name") or "Visual Asset"
        desc = p.get("content", "")
        evidence_parts.append(f"[VISION_CARD: {source}]: {desc}")
    
    evidence_str = "\n\n".join(evidence_parts)
    
    print("--- Healer Evidence Fusion Test ---")
    print(f"Evidence for Healer:\n{evidence_str}")
    
    has_text = "[SOURCE: cats.txt]" in evidence_str
    has_vision = "[VISION_CARD: cat.jpg]" in evidence_str
    
    if has_text and has_vision:
        print("\n✅ PASS: Both text and visual evidence fused correctly.")
    else:
        print("\n❌ FAIL: Missing evidence components.")
        if not has_text: print("- Missing text evidence")
        if not has_vision: print("- Missing visual evidence")

if __name__ == "__main__":
    asyncio.run(test_healer_evidence_fusion())
