"""KaizenReader Main Entrypoint.

Usage:
  python src/main.py                        # Launch native macOS desktop app
  python src/main.py --server               # Launch headless daemon server only
  python src/main.py --server --https       # Launch server with local Root CA + SAN TLS for iPhone PWA
  python src/main.py --open PATH            # Ingest book and launch
  python src/main.py --export-cartridge ID  # Compile and export a .kzn Sovereign Cartridge file
"""
import argparse
import shutil
import sys
from pathlib import Path

# Ensure root directory is on Python path
ROOT_DIR = Path(__file__).resolve().parent.parent
if str(ROOT_DIR) not in sys.path:
    sys.path.insert(0, str(ROOT_DIR))

from src.config import DEFAULT_HOST, DEFAULT_PORT, DEFAULT_SPEED, DEFAULT_VOICE, UPLOAD_DIR, get_local_ip
from src.parsers import parse_document


def main():
    parser = argparse.ArgumentParser(description="KaizenReader — Studio TTS & Sovereign Vault for Apple Silicon")
    parser.add_argument("--server", action="store_true", help="Run background daemon server only without macOS window")
    parser.add_argument("--https", action="store_true", help="Enable local Root CA + SAN HTTPS for iPhone Service Worker & Vault")
    parser.add_argument("--port", type=int, default=DEFAULT_PORT, help=f"Port to bind (default: {DEFAULT_PORT})")
    parser.add_argument("--open", type=str, help="Open and ingest a specific document file path on launch")
    parser.add_argument("--export-cartridge", type=str, metavar="BOOK_ID_OR_PATH", help="Export a book as a standalone .kzn Sovereign Cartridge")
    parser.add_argument("--voice", type=str, default=DEFAULT_VOICE, help=f"Voice for cartridge export (default: {DEFAULT_VOICE})")
    parser.add_argument("--speed", type=float, default=DEFAULT_SPEED, help=f"Speed for cartridge export (default: {DEFAULT_SPEED})")
    parser.add_argument("--pack-audio", action="store_true", help="Compile .m4a chapter sprites into exported .kzn cartridge")
    args = parser.parse_args()

    if args.open:
        p = Path(args.open)
        if p.exists():
            print(f"[KaizenReader] Ingesting document: {p.name}")
            dest = UPLOAD_DIR / p.name
            if not dest.exists():
                shutil.copy(p, dest)
            doc = parse_document(dest)
            print(f"[KaizenReader] Parsed '{doc.title}' ({len(doc.chapters)} chapters, {doc.total_words} words)")

    if args.export_cartridge:
        from src.server.app import _loaded_documents, index_existing_books
        from src.tts.sprite_compiler import export_kzn_cartridge

        index_existing_books()
        target = args.export_cartridge
        doc = _loaded_documents.get(target)
        if doc is None and Path(target).exists():
            doc = parse_document(Path(target))
        if doc is None:
            # Try partial title or ID match
            for k, v in _loaded_documents.items():
                if target.lower() in k.lower() or target.lower() in v.title.lower():
                    doc = v
                    break
        if doc is None:
            print(f"[KaizenReader] Could not find book matching '{target}'. Available IDs: {list(_loaded_documents.keys())}")
            sys.exit(1)

        safe_title = "".join(c if c.isalnum() or c in "-_" else "_" for c in doc.title).strip("_") or doc.id
        out_file = ROOT_DIR / f"{safe_title}_{doc.id}.kzn"
        print(f"[KaizenReader] Exporting cartridge for '{doc.title}' (pack_audio={args.pack_audio}, voice={args.voice})...")
        kzn_bytes = export_kzn_cartridge(
            doc,
            voice=args.voice,
            speed=args.speed,
            compile_missing=args.pack_audio,
        )
        out_file.write_bytes(kzn_bytes)
        print(f"[KaizenReader] Wrote {len(kzn_bytes) / 1024:.1f} KB cartridge -> {out_file}")
        return

    if args.server:
        import uvicorn
        from src.server.app import app

        local_ip = get_local_ip()
        if args.https:
            from src.certs import ensure_local_tls_certs

            cert_path, key_path, ca_path = ensure_local_tls_certs()
            print(f"[KaizenReader] HTTPS Sovereign Vault Server active:")
            print(f"  • iPhone / LAN URL : https://{local_ip}:{args.port}")
            print(f"  • Local Root CA    : https://{local_ip}:{args.port}/api/trust-profile ({ca_path})")
            uvicorn.run(
                app,
                host=DEFAULT_HOST,
                port=args.port,
                ssl_certfile=str(cert_path),
                ssl_keyfile=str(key_path),
            )
        else:
            print(f"[KaizenReader] Starting server on http://{local_ip}:{args.port}")
            uvicorn.run(app, host=DEFAULT_HOST, port=args.port)
    else:
        from src.macos.app_shell import launch_native_window

        launch_native_window()


if __name__ == "__main__":
    main()
