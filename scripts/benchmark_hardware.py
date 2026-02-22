"""
SentinelRAG Hardware Benchmarking Script
This script identifies the maximum context window (num_ctx) that your GPU can handle
before Ollama offloads layers to the CPU.

It performs a "Pressure Test" by iteratively increasing the context window size
and checking the VRAM allocation status via the Ollama management API.
"""

import requests
import time
import json
import os
import sys

# Configuration
OLLAMA_URL = "http://localhost:11434"
TARGET_MODEL = "gemma3:12b"
START_CTX = 512
MAX_CTX = 16384
STEP = 512

def check_cpu_offloading():
    """
    Checks if the model is currently offloaded to CPU.
    Returns (is_on_cpu, vram_usage, total_size, percentage)
    """
    try:
        response = requests.get(f"{OLLAMA_URL}/api/ps")
        if response.status_code != 200:
            return False, 0, 0, 0
        
        models = response.json().get("models", [])
        for m in models:
            if m.get("name").startswith(TARGET_MODEL.split(":")[0]):
                size = m.get("size", 0)
                vram = m.get("size_vram", 0)
                percentage = (vram / size * 100) if size > 0 else 0
                is_on_cpu = vram < size
                return is_on_cpu, vram, size, percentage
        
        return False, 0, 0, 0 # Model not loaded yet?
    except Exception as e:
        print(f"Error checking CPU status: {e}")
        return False, 0, 0, 0

def run_test(num_ctx):
    """
    Triggers a generation with a specific context window.
    """
    print(f"\n--- Testing Context Window: {num_ctx} tokens ---")
    
    # Generate a dummy prompt that fills the context window
    # approx 4 chars per token
    dummy_text = "test " * (num_ctx - 100) 
    
    payload = {
        "model": TARGET_MODEL,
        "prompt": f"Summarize this text: {dummy_text}",
        "stream": False,
        "options": {
            "num_ctx": num_ctx,
            "num_predict": 10,
            "temperature": 0
        }
    }
    
    try:
        # We use a short timeout for the check because we'll monitor 'ps' concurrently or right after
        # Actually, Ollama loads the model UNTIL the request is finished.
        start_time = time.time()
        response = requests.post(f"{OLLAMA_URL}/api/generate", json=payload, timeout=300)
        end_time = time.time()
        
        if response.status_code != 200:
            print(f"Ollama Error: {response.text}")
            return False
            
        print(f"Generation completed in {end_time - start_time:.2f}s")
        return True
    except requests.exceptions.Timeout:
        print("Request timed out (this is common when offloading to CPU)")
        return False
    except Exception as e:
        print(f"Test failed: {e}")
        return False

def main():
    print("🚀 Starting SentinelRAG Hardware Context Benchmark")
    print(f"Target Model: {TARGET_MODEL}")
    print(f"Step Increment: {STEP} tokens")
    
    stable_ctx = 0
    results = []

    for ctx in range(START_CTX, MAX_CTX + 1, STEP):
        success = run_test(ctx)
        
        # Immediate check after generation start/finish
        is_cpu, vram, size, pct = check_cpu_offloading()
        
        result = {
            "num_ctx": ctx,
            "vram_allocation_pct": pct,
            "is_on_cpu": is_cpu,
            "status": "PASS" if not is_cpu else "FAIL (Offloaded to CPU)"
        }
        results.append(result)
        
        if is_cpu:
            print(f"⚠️  CRITICAL: CPU Offloading Detected! GPU only holds {pct:.1f}% of the model.")
            print(f"The last stable GPU context window was: {stable_ctx} tokens.")
            break
        
        if not success:
            print(f"❌ Test failed at {ctx} tokens (potential crash or timeout).")
            break
            
        print(f"✅ Context {ctx} tokens passed (100% on GPU)")
        stable_ctx = ctx
        time.sleep(2) # Give hardware a breather

    # Save results
    report_path = os.path.join(os.path.dirname(__file__), "benchmark_results.json")
    with open(report_path, "w") as f:
        json.dump({
            "target_model": TARGET_MODEL,
            "stable_ctx_tokens": stable_ctx,
            "full_log": results
        }, f, indent=4)
    
    print(f"\nBenchmark Complete. Results saved to {report_path}")
    print(f"FINAL RECOMMENDED MAX_INPUT_TOKENS: {stable_ctx}")

if __name__ == "__main__":
    main()
