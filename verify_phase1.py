import os
import subprocess
import sys
from pathlib import Path
from dotenv import load_dotenv
import requests
from rich.console import Console
from rich.panel import Panel

console = Console()
load_dotenv()

PROJECT_ROOT = Path(__file__).resolve().parent
SANDBOX_ROOT = (PROJECT_ROOT / os.getenv("SANDBOX_ROOT", "./sandbox/workspaces")).resolve()
COLAB_URL = os.getenv("COLAB_OLLAMA_URL", "").rstrip("/")
MODEL_NAME = os.getenv("OLLAMA_MODEL", "gemma4:12b-it")


def check_virtual_environment() -> None:
    in_venv = (
        hasattr(sys, "real_prefix")
        or (hasattr(sys, "base_prefix") and sys.base_prefix != sys.prefix)
        or bool(os.environ.get("VIRTUAL_ENV"))
    )
    if not in_venv:
        console.print("[bold red][FAIL] You are NOT running inside the local virtual environment (.venv)![/bold red]")
        sys.exit(1)
    console.print(f"[bold green][PASS] Virtual Environment Active:[/bold green] {sys.executable}")


def check_in_project_sandbox() -> None:
    SANDBOX_ROOT.mkdir(parents=True, exist_ok=True)
    if not SANDBOX_ROOT.is_relative_to(PROJECT_ROOT):
        console.print(f"[bold red][FAIL] Sandbox path {SANDBOX_ROOT} escapes project root {PROJECT_ROOT}![/bold red]")
        sys.exit(1)

    # Test creating an isolated project folder & executing code inside the sandbox using .venv Python
    test_proj_dir = SANDBOX_ROOT / "phase1_sanity_check" / "src"
    test_proj_dir.mkdir(parents=True, exist_ok=True)
    test_script = test_proj_dir / "hello_sandbox.py"
    test_script.write_text('import sys; print("SANDBOX_OK:", sys.executable)\n', encoding="utf-8")

    proc = subprocess.run(
        [sys.executable, str(test_script)],
        cwd=str(test_proj_dir),
        capture_output=True,
        text=True,
        timeout=5,
    )
    if proc.returncode != 0 or "SANDBOX_OK:" not in proc.stdout:
        console.print(f"[bold red][FAIL] Sandbox subprocess execution failed:[/bold red] {proc.stderr}")
        sys.exit(1)
    console.print(f"[bold green][PASS] In-Project Sandbox Verified:[/bold green] {SANDBOX_ROOT}")


def check_colab_ollama_connection() -> None:
    if not COLAB_URL or "replace-with-your-tunnel" in COLAB_URL:
        console.print("[bold yellow][WARN] COLAB_OLLAMA_URL is not set in .env yet. Update .env after running Colab Cell 2.[/bold yellow]")
        return

    resp = requests.get(f"{COLAB_URL}/api/tags", timeout=15)
    resp.raise_for_status()
    models = [m.get("name") for m in resp.json().get("models", [])]
    console.print(f"[bold green][PASS] Connected to Colab Ollama Tunnel:[/bold green] {COLAB_URL}")
    console.print(f"[cyan]Available Colab GPU Models:[/cyan] {models}")


if __name__ == "__main__":
    console.print(Panel.fit("[bold cyan]Phase 1 Verification: .venv + In-Project Sandbox + Colab GPU[/bold cyan]"))
    check_virtual_environment()
    check_in_project_sandbox()
    check_colab_ollama_connection()