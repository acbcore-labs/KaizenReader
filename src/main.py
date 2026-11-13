"""KaizenReader Main Entrypoint.

Usage:
  python src/main.py              # Launch native macOS desktop app
  python src/main.py --server     # Launch headless daemon server only
  python src/main.py --open PATH  # Ingest book and launch
"""
import sys
import argparse
from pathlib import Path

# Ensure root directory is on Python path
ROOT_DIR = Path(__file__).resolve().parent.parent
if str(ROOT_DIR) not in sys.path:
    sys.path.insert(0, str(ROOT_DIR))

from src.config import DEFAULT_PORT, DEFAULT_HOST, UPLOAD_DIR
from src.parsers import parse_document

def main():
    parser = argparse.ArgumentParser(description="KaizenReader — Studio TTS for Apple Silicon M1")
    parser.add_argument("--server", action="store_true", help="Run background daemon server only without macOS window")
    parser.add_argument("--port", type=int, default=DEFAULT_PORT, help=f"Port to bind (default: {DEFAULT_PORT})")
    parser.add_argument("--open", type=str, help="Open and ingest a specific document file path on launch")
    args = parser.parse_args()

    if args.open:
        p = Path(args.open)
        if p.exists():
            print(f"[KaizenReader] Ingesting document: {p.name}")
            dest = UPLOAD_DIR / p.name
            if not dest.exists():
                import shutil
                shutil.copy(p, dest)
            doc = parse_document(dest)
            print(f"[KaizenReader] Parsed '{doc.title}' ({len(doc.chapters)} chapters, {doc.total_words} words)")

    if args.server:
        import uvicorn
        from src.server.app import app
        print(f"[KaizenReader] Starting server on http://{DEFAULT_HOST}:{args.port}")
        uvicorn.run(app, host=DEFAULT_HOST, port=args.port)
    else:
        from src.macos.app_shell import launch_native_window
        launch_native_window()

if __name__ == "__main__":
    main()
