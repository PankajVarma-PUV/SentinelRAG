import asyncio
import uuid
import sys
import os
from datetime import datetime

# Add src to path
sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))

from src.core.database import SentinelRAGDatabase
from src.core.memory import MemoryManager
from src.agents.metacognitive_brain import MetacognitiveBrain
from src.core.utils import logger

async def test_memory_v2():
    db = SentinelRAGDatabase()
    memory = MemoryManager(db)
    brain = MetacognitiveBrain(db, memory)
    
    conv_id = f"test_v2_{uuid.uuid4()}"
    logger.info(f"Starting Memory 2.0 Stress Test: {conv_id}")

    # 1. Setup multi-topic history
    history_turns = [
        ("user", "I want to talk about Space. I love the James Webb telescope."),
        ("assistant", "The James Webb Space Telescope is a marvel of engineering! Its gold-plated mirrors capture infrared light from the earliest stars."),
        ("user", "Actually, let's switch to Cooking. My favorite color is Blue so maybe I should make Blue Pasta?"),
        ("assistant", "Blue pasta! You could use butterfly pea flower or red cabbage to get a natural blue hue. It would look quite avant-garde."),
        ("user", "Anyway, tell me about the telescope again."), # This should be reformulated to JWST
        ("assistant", "The JWST is currently orbiting the L2 point, peering back billions of years into cosmic history."),
    ]

    for role, content in history_turns:
        # Mocking persistence manually for setup
        brain._persist_message(conv_id, role, content)
        await asyncio.sleep(0.1) # Ensure separate timestamps

    logger.info("History seeded. Running Memory 2.0 Queries...")

    # --- Test 1: Ambiguity Resolution (Reformulation) ---
    query1 = "What color was the pasta we discussed?"
    logger.info(f"Test 1 (Ambiguity): {query1}")
    
    final_answer1 = ""
    generator1 = await brain.run(query=query1, conversation_id=conv_id)
    async for event in generator1:
        if event["type"] == "token":
            final_answer1 += event["token"]
        elif event["type"] == "status":
            logger.info(f"[{event['agent']}] {event['stage']}")
    
    print(f"\nQUERY 1: {query1}")
    print(f"RESPONSE 1: {final_answer1}")
    assert "blue" in final_answer1.lower(), "Should remember the blue pasta color."

    # --- Test 2: Semantic Topic Recall ---
    query2 = "Summarize just our discussion about Space."
    logger.info(f"Test 2 (Semantic Topic): {query2}")

    final_answer2 = ""
    generator2 = await brain.run(query=query2, conversation_id=conv_id)
    async for event in generator2:
        if event["type"] == "token":
            final_answer2 += event["token"]
        elif event["type"] == "status":
            logger.info(f"[{event['agent']}] {event['stage']}")

    print(f"\nQUERY 2: {query2}")
    print(f"RESPONSE 2: {final_answer2}")
    # Should mention telescope, not cooking.
    assert "telescope" in final_answer2.lower() or "space" in final_answer2.lower(), "Should recall Space facts."
    assert "cooking" not in final_answer2.lower(), "Should NOT include cooking in a space-specific summary."

    # --- Test 3: Reasoning Check ---
    # Since 'final' yield includes metadata, let's check it
    logger.info("Verifying Reason Trace in final yield...")
    generator3 = await brain.run(query="What did we say about blue?", conversation_id=conv_id)
    async for event in generator3:
        if event["type"] == "final":
            reasoning = event["result"].get("metadata", {}).get("reasoning")
            print(f"REASONING TRACE: {reasoning}")
            assert reasoning is not None, "Reasoning trace should be present in metadata."

    logger.info("Memory 2.0 Verification SUCCESS!")

if __name__ == "__main__":
    asyncio.run(test_memory_v2())
