"""KaizenReader Configuration & Runtime Constants.

Adheres to Mechanical Sympathy and Semantic Rigor.
"""
from pathlib import Path
import os
import socket

ROOT_DIR = Path(__file__).resolve().parent.parent
MODELS_DIR = ROOT_DIR / "models"
MODEL_PATH = MODELS_DIR / "kokoro-v1.0.onnx"
VOICES_PATH = MODELS_DIR / "voices-v1.0.bin"

DATA_DIR = ROOT_DIR / "data"
DATA_DIR.mkdir(parents=True, exist_ok=True)
UPLOAD_DIR = DATA_DIR / "uploads"
UPLOAD_DIR.mkdir(parents=True, exist_ok=True)
CACHE_DIR = DATA_DIR / "audio_cache"
CACHE_DIR.mkdir(parents=True, exist_ok=True)

DEFAULT_HOST = "0.0.0.0"
DEFAULT_PORT = int(os.getenv("KAIZEN_PORT", "8977"))
DEFAULT_VOICE = os.getenv("KAIZEN_VOICE", "af_bella")
DEFAULT_SPEED = float(os.getenv("KAIZEN_SPEED", "1.0"))
DEFAULT_LANG = "en-us"

# Semantic Rigor defaults
SMART_AUDIO_MODE = True  # Skip code blocks and mute footnote indicators during speech
LOOKAHEAD_CHUNKS = 4     # Number of sentences to synthesize ahead of playhead

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
