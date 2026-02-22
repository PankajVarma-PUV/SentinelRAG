"""
MINIMAL Qwen2-VL test - writes all output to a log file.
Run: .venv\Scripts\python.exe scripts\test_qwen_minimal.py
Check output in: scripts/qwen_test_log.txt
"""

import sys
import os

LOG_FILE = "scripts/qwen_test_log.txt"

def log(msg):
    print(msg)
    with open(LOG_FILE, "a", encoding="utf-8") as f:
        f.write(msg + "\n")

# Clear log first
with open(LOG_FILE, "w") as f:
    f.write("=== QWEN2-VL MINIMAL TEST ===\n")

try:
    import torch
    log(f"PyTorch: {torch.__version__}")
    log(f"CUDA: {torch.cuda.is_available()}")
    if torch.cuda.is_available():
        log(f"Device: {torch.cuda.get_device_name(0)}")
        log(f"VRAM: {torch.cuda.get_device_properties(0).total_memory / 1e9:.2f} GB")
except Exception as e:
    log(f"ERROR (torch): {e}")

try:
    import transformers
    log(f"Transformers: {transformers.__version__}")
except Exception as e:
    log(f"ERROR (transformers): {e}")

try:
    import qwen_vl_utils
    log("qwen_vl_utils: OK")
except Exception as e:
    log(f"ERROR (qwen_vl_utils): {e}")

try:
    import accelerate
    log(f"accelerate: {accelerate.__version__}")
except Exception as e:
    log(f"ERROR (accelerate): {e}")
    
try:
    import bitsandbytes
    log("bitsandbytes: OK")
except Exception as e:
    log(f"ERROR (bitsandbytes): {e}")

log("\n--- Loading Model ---")

try:
    from transformers import AutoProcessor, Qwen2VLForConditionalGeneration, BitsAndBytesConfig
    
    model_id = "Qwen/Qwen2-VL-2B-Instruct"
    log(f"Loading {model_id}...")
    
    bnb_config = BitsAndBytesConfig(
        load_in_4bit=True,
        bnb_4bit_compute_dtype=torch.float16,
        bnb_4bit_quant_type="nf4",
        bnb_4bit_use_double_quant=True,
    )
    
    processor = AutoProcessor.from_pretrained(model_id)
    log("Processor loaded OK")
    
    model = Qwen2VLForConditionalGeneration.from_pretrained(
        model_id,
        quantization_config=bnb_config,
        device_map="auto",
        max_memory={0: "4GiB", "cpu": "24GiB"},
        low_cpu_mem_usage=True
    )
    log("Model loaded OK")
    log(f"Model device: {next(model.parameters()).device}")
    
except Exception as e:
    log(f"ERROR (loading): {e}")
    import traceback
    log(traceback.format_exc())
    sys.exit(1)

log("\n--- Running Inference ---")

try:
    from PIL import Image
    from qwen_vl_utils import process_vision_info
    import tempfile
    
    # Create a simple test image
    test_img = Image.new("RGB", (224, 224), color=(255, 0, 0))
    log("Created test image (solid red 224x224)")
    
    with tempfile.NamedTemporaryFile(suffix=".jpg", delete=False) as tmp:
        tmp_path = tmp.name
        test_img.save(tmp_path, "JPEG")
    log(f"Saved to: {tmp_path}")
    
    prompt = "Describe this image briefly."
    messages = [{
        "role": "user",
        "content": [
            {"type": "image", "image": f"file://{tmp_path}", "min_pixels": 224*224, "max_pixels": 1024*1024},
            {"type": "text", "text": prompt},
        ]
    }]
    
    text = processor.apply_chat_template(messages, tokenize=False, add_generation_prompt=True)
    log(f"Chat template applied, len={len(text)}")
    
    image_inputs, video_inputs = process_vision_info(messages)
    log(f"Vision info: images={len(image_inputs) if image_inputs else 0}")
    
    inputs = processor(
        text=[text],
        images=image_inputs,
        videos=video_inputs,
        padding=True,
        return_tensors="pt",
    )
    log(f"Inputs prepared, keys={list(inputs.keys())}")
    
    device = next(model.parameters()).device
    inputs = {k: v.to(device) if hasattr(v, 'to') else v for k, v in inputs.items()}
    log(f"Moved to device: {device}")
    
    if torch.cuda.is_available():
        torch.cuda.empty_cache()
        log(f"CUDA memory before generation: {torch.cuda.memory_allocated()/1e9:.2f} GB")
    
    log("Starting generation...")
    with torch.no_grad():
        generated_ids = model.generate(
            **inputs, 
            max_new_tokens=128,
            do_sample=False,
            use_cache=True
        )
    log(f"Generation complete! Shape: {generated_ids.shape}")
    
    generated_ids_trimmed = [
        out_ids[len(in_ids):] for in_ids, out_ids in zip(inputs["input_ids"], generated_ids)
    ]
    output_text = processor.batch_decode(
        generated_ids_trimmed, skip_special_tokens=True, clean_up_tokenization_spaces=False
    )[0]
    
    log(f"\n=== OUTPUT ===\n{output_text}\n==============")
    
    os.remove(tmp_path)
    
except Exception as e:
    log(f"ERROR (inference): {e}")
    import traceback
    log(traceback.format_exc())

log("\n=== TEST COMPLETE ===")
