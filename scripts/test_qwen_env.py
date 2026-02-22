import torch
import sys
import os

def check_env():
    with open("scripts/env_log.txt", "w") as f:
        def log(msg):
            print(msg)
            f.write(msg + "\n")

        log(f"Python version: {sys.version}")
        log(f"PyTorch version: {torch.__version__}")
        log(f"CUDA available: {torch.cuda.is_available()}")
        if torch.cuda.is_available():
            log(f"CUDA Device: {torch.cuda.get_device_name(0)}")
            log(f"VRAM: {torch.cuda.get_device_properties(0).total_memory / 1e9:.2f} GB")

        try:
            import transformers
            log(f"Transformers version: {transformers.__version__}")
        except ImportError:
            log("Transformers NOT installed")

        try:
            import qwen_vl_utils
            log(f"qwen-vl-utils installed")
        except ImportError:
            log("qwen-vl-utils NOT installed")

        try:
            import accelerate
            log(f"accelerate version: {accelerate.__version__}")
        except ImportError:
            log("accelerate NOT installed")

        try:
            import bitsandbytes
            log(f"bitsandbytes installed")
        except ImportError:
            log("bitsandbytes NOT installed")
        
        try:
            import numpy
            log(f"Numpy version: {numpy.__version__}")
        except ImportError:
            log("Numpy NOT installed")


def test_load():
    from transformers import AutoProcessor, Qwen2VLForConditionalGeneration
    model_id = "Qwen/Qwen2-VL-2B-Instruct" # Using the one in the codebase
    print(f"\nAttempting to load {model_id} (Config only)...")
    try:
        processor = AutoProcessor.from_pretrained(model_id)
        print("Processor loaded successfully")
        
        # Load with 4-bit config to see if it even starts
        from transformers import BitsAndBytesConfig
        bnb_config = BitsAndBytesConfig(
            load_in_4bit=True,
            bnb_4bit_compute_dtype=torch.float16,
            bnb_4bit_quant_type="nf4",
            bnb_4bit_use_double_quant=True,
        )
        
        # Just try to load the model class without downloading all weights if possible, 
        # but from_pretrained will download. Let's see if it errors out early.
        # We can use trust_remote_code=True if needed
        model = Qwen2VLForConditionalGeneration.from_pretrained(
            model_id,
            torch_dtype="auto",
            device_map="auto"
        )
        print("Model loaded successfully")
    except Exception as e:
        print(f"Error loading model: {e}")

if __name__ == "__main__":
    check_env()
    # test_load() # Uncomment to actually try downloading/loading
