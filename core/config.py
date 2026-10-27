import os
import sys
from pathlib import Path
from dotenv import load_dotenv

load_dotenv()

PROJECT_ROOT = Path(__file__).resolve().parent.parent
SANDBOX_ROOT = (PROJECT_ROOT / os.getenv("SANDBOX_ROOT", "./sandbox/workspaces")).resolve()
COLAB_OLLAMA_URL = os.getenv("COLAB_OLLAMA_URL", "").rstrip("/")
OLLAMA_MODEL = os.getenv("OLLAMA_MODEL", "gemma4:e4b")
ENFORCE_VENV = os.getenv("ENFORCE_VENV", "true").lower() == "true"

# Always use the active virtual environment's Python interpreter for sandbox subprocesses
VENV_PYTHON = sys.executable


def verify_runtime_isolation() -> None:
    """Ensure the agent is running inside the local .venv and the sandbox stays inside PROJECT_ROOT."""
    if ENFORCE_VENV:
        in_venv = (
            hasattr(sys, "real_prefix")
            or (hasattr(sys, "base_prefix") and sys.base_prefix != sys.prefix)
            or bool(os.environ.get("VIRTUAL_ENV"))
        )
        if not in_venv:
            raise RuntimeError(
                f"Virtual environment required! Activate .venv first (current interpreter: {sys.executable})."
            )

    SANDBOX_ROOT.mkdir(parents=True, exist_ok=True)
    if not SANDBOX_ROOT.is_relative_to(PROJECT_ROOT):
        raise RuntimeError(
            f"Security violation: SANDBOX_ROOT ({SANDBOX_ROOT}) must be inside PROJECT_ROOT ({PROJECT_ROOT})."
        )


def ensure_inside_sandbox(path: Path) -> Path:
    """Resolve a path and guarantee it cannot escape SANDBOX_ROOT."""
    resolved = path.resolve()
    if not resolved.is_relative_to(SANDBOX_ROOT):
        raise PermissionError(f"Path '{resolved}' escapes the in-project sandbox '{SANDBOX_ROOT}'!")
    return resolved


verify_runtime_isolation()