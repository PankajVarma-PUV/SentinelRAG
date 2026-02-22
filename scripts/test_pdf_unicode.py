
import sys
import os
from pathlib import Path

# Add src to path
sys.path.append(str(Path(__file__).parent.parent))

from src.core.pdf_exporter import generate_conversation_pdf
from src.core.utils import logger

def test_unicode_pdf():
    logger.info("Starting Unicode PDF Verification...")
    
    conversation = {
        "title": "SentinelRAG Global Test: हिंदी | 中文 | English",
        "conversation_id": "test-session-unicode-123",
        "conversation_created_at": "2026-02-17 12:00:00"
    }
    
    messages = [
        {
            "role": "user",
            "content": "Hello, can you speak Hindi and Chinese?",
            "message_created_at": "12:00:01",
            "metadata_json": "{}"
        },
        {
            "role": "assistant",
            "content": "हाँ, मैं हिंदी बोल सकता हूँ। (Yes, I can speak Hindi.) \n\n我也可以说中文。 (I can also speak Chinese.)",
            "message_created_at": "12:00:05",
            "metadata_json": '{"intent": "translation", "confidence_score": 0.98, "processing_time_sec": 1.2, "sources": [{"file_name": "language_model.v1"}]}'
        }
    ]
    
    try:
        pdf_bytes = generate_conversation_pdf(conversation, messages)
        
        output_path = "test_unicode_export.pdf"
        with open(output_path, "wb") as f:
            f.write(pdf_bytes)
        
        logger.info(f"✅ Success! PDF generated at: {os.path.abspath(output_path)}")
        logger.info("Please manually inspect the file to ensure Hindi and Chinese characters are rendered correctly.")
        
    except Exception as e:
        logger.error(f"❌ PDF Generation FAILED: {e}")
        import traceback
        traceback.print_exc()
        sys.exit(1)

if __name__ == "__main__":
    test_unicode_pdf()
