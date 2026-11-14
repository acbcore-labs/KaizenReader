"""KaizenReader Configuration & Runtime Constants.

Adheres to Mechanical Sympathy, Semantic Rigor, and Third Door Choice.
"""
from pathlib import Path
import os
import socket

ROOT_DIR = Path(__file__).resolve().parent.parent
MODELS_DIR = ROOT_DIR / "models"

# Prefer FP16 model (~163MB) for Apple Silicon M1 memory efficiency; fallback to FP32
_FP16_MODEL = MODELS_DIR / "kokoro-v1.0.fp16.onnx"
_FP32_MODEL = MODELS_DIR / "kokoro-v1.0.onnx"
MODEL_PATH = _FP16_MODEL if _FP16_MODEL.exists() else _FP32_MODEL
VOICES_PATH = MODELS_DIR / "voices-v1.0.bin"

DATA_DIR = ROOT_DIR / "data"
DATA_DIR.mkdir(parents=True, exist_ok=True)
UPLOAD_DIR = DATA_DIR / "uploads"
UPLOAD_DIR.mkdir(parents=True, exist_ok=True)
CACHE_DIR = DATA_DIR / "audio_cache"
CACHE_DIR.mkdir(parents=True, exist_ok=True)
AST_CACHE_DIR = DATA_DIR / "cache"
AST_CACHE_DIR.mkdir(parents=True, exist_ok=True)
USERS_DIR = DATA_DIR / "users"
USERS_DIR.mkdir(parents=True, exist_ok=True)
USERS_FILE = DATA_DIR / "users.json"
STATE_FILE = DATA_DIR / "state.json"

DEFAULT_HOST = "0.0.0.0"
DEFAULT_PORT = int(os.getenv("KAIZEN_PORT", "8977"))
DEFAULT_VOICE = os.getenv("KAIZEN_VOICE", "af_bella")
DEFAULT_SPEED = float(os.getenv("KAIZEN_SPEED", "1.0"))
DEFAULT_LANG = "en-us"

# Mechanical Sympathy & Semantic Rigor defaults
SMART_AUDIO_MODE = True           # Skip code blocks and mute footnote indicators during speech
LOOKAHEAD_CHUNKS = 4              # Number of sentences to synthesize ahead of playhead
MAX_AUDIO_CACHE_BYTES = 32 * 1024 * 1024  # 32 MB strict in-memory LRU ring buffer
ONNX_INTRA_THREADS = int(os.getenv("KAIZEN_THREADS", "4"))


def get_local_ip() -> str:
    """Detect LAN IP address to display the mobile companion URL."""
    try:
        s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        s.connect(("8.8.8.8", 80))
        ip = s.getsockname()[0]
        s.close()
        return ip
    except Exception:
        return "127.0.0.1"
