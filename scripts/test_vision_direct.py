"""
Standalone test script to debug Qwen2-VL inference directly.
Run this from the project root: python scripts/test_vision_direct.py
"""

import asyncio
import sys
import os

# Add project root to path
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from PIL import Image

async def test_vision():
    print("=" * 60)
    print("QWEN2-VL DIRECT TEST")
    print("=" * 60)
    
    # 1. Check for test image
    test_image_path = "data/uploads/default/images/cat.jpg"
    if not os.path.exists(test_image_path):
        print(f"[ERROR] Test image not found at: {test_image_path}")
        print("Please provide a test image path as argument, or place an image there.")
        if len(sys.argv) > 1:
            test_image_path = sys.argv[1]
            print(f"Using provided path: {test_image_path}")
        else:
            return
    
    if not os.path.exists(test_image_path):
        print(f"[ERROR] Image still not found: {test_image_path}")
        return
    
    print(f"[OK] Found image: {test_image_path}")
    
    # 2. Load image
    try:
        img = Image.open(test_image_path).convert("RGB")
        print(f"[OK] Loaded image: {img.size}")
    except Exception as e:
        print(f"[ERROR] Failed to load image: {e}")
        return
    
    # 3. Import the vision agent
    try:
        from src.vision.qwen_agent import get_vision_agent
        print("[OK] Imported QwenVisionAgent")
    except Exception as e:
        print(f"[ERROR] Failed to import agent: {e}")
        import traceback
        traceback.print_exc()
        return
    
    # 4. Get the agent (this triggers lazy loading)
    try:
        agent = get_vision_agent()
        print("[OK] Got vision agent singleton")
    except Exception as e:
        print(f"[ERROR] Failed to get agent: {e}")
        import traceback
        traceback.print_exc()
        return
    
    # 5. Run describe_image
    print("\n[INFO] Running describe_image...")
    print("-" * 40)
    
    try:
        result = await agent.describe_image(img)
        print("-" * 40)
        print("RESULT:")
        print(result)
    except Exception as e:
        print(f"[ERROR] describe_image failed: {e}")
        import traceback
        traceback.print_exc()

if __name__ == "__main__":
    asyncio.run(test_vision())
