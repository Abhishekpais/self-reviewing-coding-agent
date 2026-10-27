# CELL 2: Ensure cloudflared Binary Exists & Start Public HTTPS Tunnel
import os
import re
import subprocess
from pathlib import Path

CLOUDFLARED_BIN = "/usr/local/bin/cloudflared"

if not Path(CLOUDFLARED_BIN).exists():
    print("Downloading cloudflared binary to /usr/local/bin/cloudflared...")
    subprocess.run(
        [
            "wget", "-q",
            "https://github.com/cloudflare/cloudflared/releases/latest/download/cloudflared-linux-amd64",
            "-O", CLOUDFLARED_BIN
        ],
        check=True
    )
    os.chmod(CLOUDFLARED_BIN, 0o755)
    print("cloudflared installed successfully!")

print("Starting Cloudflare Quick Tunnel to http://127.0.0.1:11434 ...")
tunnel_proc = subprocess.Popen(
    [CLOUDFLARED_BIN, "tunnel", "--url", "http://127.0.0.1:11434", "--no-autoupdate"],
    stdout=subprocess.PIPE,
    stderr=subprocess.STDOUT,
    text=True
)

public_url = None
for line in tunnel_proc.stdout:
    match = re.search(r"https://[a-zA-Z0-9-]+\.trycloudflare\.com", line)
    if match:
        public_url = match.group(0)
        print("\n========================================================")
        print("COPY THESE TWO LINES INTO YOUR LOCAL .env FILE:")
        print(f"COLAB_OLLAMA_URL={public_url}")
        print(f"OLLAMA_MODEL={globals().get('active_model', 'gemma4:e4b')}")
        print("========================================================\n")
        break