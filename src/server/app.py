"""KaizenReader High-Performance Streaming Server.

Provides RESTful endpoints for document ingestion and voice switching,
coupled with an ultra-low latency WebSocket synchronization layer.
"""
from pathlib import Path
import json
import shutil
import uuid
from typing import Dict, List, Optional

from fastapi import FastAPI, UploadFile, File, Form, HTTPException, WebSocket, WebSocketDisconnect
from fastapi.responses import Response, JSONResponse, FileResponse
from fastapi.staticfiles import StaticFiles
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel

from src.config import (
    ROOT_DIR, UPLOAD_DIR, CACHE_DIR, DEFAULT_PORT,
    DEFAULT_VOICE, DEFAULT_SPEED, SMART_AUDIO_MODE, get_local_ip
)
from src.tts.engine import TTSEngine
from src.tts.lexicon import LexiconManager
from src.parsers import parse_document
from src.parsers.base import Document

app = FastAPI(title="KaizenReader Core", version="1.0.0")

# Enable CORS for local and LAN access
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# In-memory document store
_loaded_documents: Dict[str, Document] = {}

def get_engine() -> TTSEngine:
    return TTSEngine.get_instance()

def index_existing_books():
    """Load default sample books into library on boot."""
    sample_dir = ROOT_DIR / "sample_books"
    if sample_dir.exists():
        for f in sample_dir.glob("*.*"):
            if f.suffix.lower() in [".epub", ".pdf", ".md", ".txt", ".docx", ".html"]:
                try:
                    doc = parse_document(f)
                    _loaded_documents[doc.id] = doc
                    print(f"[Library] Indexed sample book '{doc.title}' ({f.name})")
                except Exception as e:
                    print(f"[Library] Could not parse {f.name}: {e}")

    # Also index any previously uploaded books
    for f in UPLOAD_DIR.glob("*.*"):
        if f.suffix.lower() in [".epub", ".pdf", ".md", ".txt", ".docx", ".html"]:
            try:
                doc = parse_document(f)
                _loaded_documents[doc.id] = doc
                print(f"[Library] Indexed uploaded book '{doc.title}' ({f.name})")
            except Exception as e:
                print(f"[Library] Could not parse uploaded {f.name}: {e}")

@app.on_event("startup")
def startup_event():
    # Run heavy initializations in background threads so server binds socket instantly (<50ms)
    import threading
    threading.Thread(target=get_engine, daemon=True).start()
    threading.Thread(target=index_existing_books, daemon=True).start()

# ----------------- REST Endpoints ----------------- #

@app.get("/api/status")
def get_status():
    return {
        "status": "online",
        "engine": "Kokoro-82M (ONNX Runtime / Apple Silicon M1)",
        "default_voice": DEFAULT_VOICE,
        "default_speed": DEFAULT_SPEED,
        "smart_audio_mode": SMART_AUDIO_MODE,
        "local_ip": get_local_ip(),
        "port": DEFAULT_PORT,
        "companion_url": f"http://{get_local_ip()}:{DEFAULT_PORT}",
        "total_books_loaded": len(_loaded_documents)
    }

@app.get("/api/voices")
def list_voices():
    engine = get_engine()
    return engine.get_available_voices()

class LexiconEntry(BaseModel):
    word: str
    phonetic: str

@app.get("/api/lexicon")
def get_lexicon():
    lex = LexiconManager.get_instance()
    return lex.get_all()

@app.post("/api/lexicon")
def add_lexicon_entry(entry: LexiconEntry):
    lex = LexiconManager.get_instance()
    lex.add_override(entry.word, entry.phonetic)
    return {"success": True, "word": entry.word, "phonetic": entry.phonetic}

@app.delete("/api/lexicon/{word}")
def delete_lexicon_entry(word: str):
    lex = LexiconManager.get_instance()
    lex.remove_override(word)
    return {"success": True, "deleted": word}

@app.get("/api/library")
def get_library():
    items = []
    for doc in _loaded_documents.values():
        items.append({
            "id": doc.id,
            "title": doc.title,
            "author": doc.author,
            "file_format": doc.file_format,
            "chapters_count": len(doc.chapters),
            "total_words": doc.total_words,
            "total_sentences": doc.total_sentences,
            "file_path": doc.file_path
        })
    return items

@app.post("/api/upload")
async def upload_document(file: UploadFile = File(...)):
    suffix = Path(file.filename or "").suffix.lower()
    if suffix not in [".epub", ".pdf", ".md", ".txt", ".docx", ".html", ".htm"]:
        raise HTTPException(status_code=400, detail=f"Unsupported format: {suffix}")

    dest_path = UPLOAD_DIR / f"{uuid.uuid4().hex[:8]}_{file.filename}"
    with open(dest_path, "wb") as buffer:
        shutil.copyfileobj(file.file, buffer)

    try:
        doc = parse_document(dest_path)
        _loaded_documents[doc.id] = doc
        return {
            "success": True,
            "document": {
                "id": doc.id,
                "title": doc.title,
                "author": doc.author,
                "file_format": doc.file_format,
                "chapters_count": len(doc.chapters),
                "total_words": doc.total_words,
                "total_sentences": doc.total_sentences
            }
        }
    except Exception as e:
        if dest_path.exists():
            dest_path.unlink()
        raise HTTPException(status_code=500, detail=f"Failed to parse document: {str(e)}")

@app.get("/api/book/{book_id}")
def get_book(book_id: str):
    if book_id not in _loaded_documents:
        raise HTTPException(status_code=404, detail="Book not found")
    return _loaded_documents[book_id].model_dump()

class TTSRequest(BaseModel):
    text: str
    voice: Optional[str] = DEFAULT_VOICE
    speed: Optional[float] = DEFAULT_SPEED
    sentence_id: Optional[str] = None

@app.api_route("/api/tts/sentence", methods=["GET", "HEAD"])
def synthesize_sentence(
    text: str,
    voice: str = DEFAULT_VOICE,
    speed: float = DEFAULT_SPEED,
    sentence_id: Optional[str] = None
):
    """Synthesize sentence audio with zero disk writes, directly returning in-memory WAV."""
    engine = get_engine()
    wav_bytes, duration, sample_rate = engine.synthesize(text, voice=voice, speed=speed)
    
    headers = {
        "Content-Type": "audio/wav",
        "X-Audio-Duration": str(duration),
        "X-Sample-Rate": str(sample_rate),
        "Cache-Control": "public, max-age=3600"
    }
    if sentence_id:
        headers["X-Sentence-ID"] = sentence_id

    return Response(content=wav_bytes, media_type="audio/wav", headers=headers)

class LookaheadRequest(BaseModel):
    items: List[Dict[str, str]]  # list of {text, voice, speed}

@app.post("/api/tts/lookahead")
def queue_lookahead(req: LookaheadRequest):
    engine = get_engine()
    tuples = [(item.get("text", ""), item.get("voice", DEFAULT_VOICE), float(item.get("speed", DEFAULT_SPEED))) for item in req.items]
    engine.queue_lookahead(tuples)
    return {"queued": len(tuples)}

# ----------------- WebSocket Live Synchronization ----------------- #

class ConnectionManager:
    def __init__(self):
        self.active_connections: List[WebSocket] = []

    async def connect(self, websocket: WebSocket):
        await websocket.accept()
        self.active_connections.append(websocket)

    def disconnect(self, websocket: WebSocket):
        if websocket in self.active_connections:
            self.active_connections.remove(websocket)

    async def broadcast(self, message: dict):
        for connection in list(self.active_connections):
            try:
                await connection.send_json(message)
            except Exception:
                pass

manager = ConnectionManager()

@app.websocket("/ws/sync")
async def websocket_sync_endpoint(websocket: WebSocket):
    await manager.connect(websocket)
    try:
        while True:
            data = await websocket.receive_text()
            msg = json.loads(data)
            action = msg.get("action")

            if action == "ping":
                await websocket.send_json({"type": "pong"})
            elif action == "sync_position":
                # Broadcast position updates across synced tabs / mobile devices
                await manager.broadcast({
                    "type": "remote_sync",
                    "book_id": msg.get("book_id"),
                    "chapter_id": msg.get("chapter_id"),
                    "sentence_id": msg.get("sentence_id"),
                    "is_playing": msg.get("is_playing", False)
                })
    except WebSocketDisconnect:
        manager.disconnect(websocket)
    except Exception:
        manager.disconnect(websocket)

# ----------------- Static UI Mounting ----------------- #

UI_DIR = ROOT_DIR / "src" / "ui"
if UI_DIR.exists():
    app.mount("/", StaticFiles(directory=str(UI_DIR), html=True), name="ui")
