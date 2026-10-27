# CELL 1: Install zstd + pciutils (lspci), Ollama & Pull Official Gemma Model
import os
import subprocess
import time

print("1. Installing system dependencies (zstd, pciutils, curl, wget)...")
subprocess.run("apt-get update -qq && apt-get install -y -qq zstd pciutils curl wget", shell=True, check=True)

print("2. Installing Ollama...")
subprocess.run("curl -fsSL https://ollama.com/install.sh | sh", shell=True, check=True)

# Configure Ollama environment variables for 15GB T4 GPU
os.environ["OLLAMA_HOST"] = "0.0.0.0:11434"
os.environ["OLLAMA_FLASH_ATTENTION"] = "1"
os.environ["OLLAMA_KV_CACHE_TYPE"] = "q8_0"
os.environ["OLLAMA_KEEP_ALIVE"] = "-1"

print("3. Starting Ollama server in background...")
ollama_proc = subprocess.Popen(
    ["/usr/local/bin/ollama", "serve"],
    stdout=subprocess.PIPE,
    stderr=subprocess.PIPE,
    env=os.environ.copy()
)
time.sleep(5)

# Try official Ollama library tags in order: gemma4:12b -> gemma4:e4b -> gemma3:12b
candidate_models = ["gemma4:12b", "gemma4:e4b", "gemma3:12b"]
active_model = None

for model_tag in candidate_models:
    print(f"4. Attempting to pull '{model_tag}'...")
    res = subprocess.run(["/usr/local/bin/ollama", "pull", model_tag])
    if res.returncode == 0:
        active_model = model_tag
        print(f"\n[SUCCESS] Pulled model: {active_model}")
        print(f"--> Set OLLAMA_MODEL={active_model} in your local .env file!")
        break
    else:
        print(f"[WARN] Tag '{model_tag}' unavailable on this registry mirror, trying next...")

subprocess.run(["/usr/local/bin/ollama", "list"])