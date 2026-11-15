"""KaizenReader High-Performance Streaming Server.

Provides RESTful endpoints for document ingestion, voice switching,
hybrid IPA lexicon management, persistent reading state, and WebSocket sync.
"""
from pathlib import Path
import json
import shutil
import threading
import time
import uuid
from typing import Dict, List, Optional

from fastapi import FastAPI, UploadFile, File, HTTPException, WebSocket, WebSocketDisconnect
from fastapi.responses import Response
from fastapi.staticfiles import StaticFiles
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel

from src.config import (
    ROOT_DIR, UPLOAD_DIR, STATE_FILE, DEFAULT_PORT,
    DEFAULT_VOICE, DEFAULT_SPEED, SMART_AUDIO_MODE, get_local_ip
)
from src.tts.engine import TTSEngine
from src.tts.lexicon import LexiconManager
from src.parsers import parse_document
from src.users import UserManager, UserProfile, UserMemory, NoteEntry
from src.parsers.base import Document

app = FastAPI(title="KaizenReader Core", version="2.0.0")

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
    expose_headers=["X-Audio-Duration", "X-Sample-Rate", "X-Sentence-ID", "X-Word-Timings"],
)

_loaded_documents: Dict[str, Document] = {}
_state_lock = threading.Lock()


def get_engine() -> TTSEngine:
    return TTSEngine.get_instance()


def index_existing_books():
    """Load user uploaded books FIRST, then sample books (tagged is_sample=True)."""
    supported = {".epub", ".pdf", ".md", ".markdown", ".txt", ".docx", ".html", ".htm"}

    # 1. Index user uploaded books first (most recently added/modified first)
    if UPLOAD_DIR.exists():
        for f in sorted(UPLOAD_DIR.glob("*.*"), key=lambda p: p.stat().st_mtime, reverse=True):
            if f.suffix.lower() not in supported:
                continue
            try:
                doc = parse_document(f)
                if doc.id in _loaded_documents:
                    continue
                doc.is_sample = False
                doc.created_at = f.stat().st_mtime
                _loaded_documents[doc.id] = doc
                print(f"[Library] Indexed uploaded book '{doc.title}' ({f.name})")
            except Exception as e:
                print(f"[Library] Could not parse uploaded {f.name}: {e}")

    # 2. Index sample/demo books
    sample_dir = ROOT_DIR / "sample_books"
    if sample_dir.exists():
        for f in sorted(sample_dir.glob("*.*")):
            if f.suffix.lower() not in supported:
                continue
            try:
                doc = parse_document(f)
                if doc.id in _loaded_documents:
                    continue
                doc.is_sample = True
                doc.created_at = f.stat().st_mtime
                _loaded_documents[doc.id] = doc
                print(f"[Library] Indexed sample book '{doc.title}' ({f.name})")
            except Exception as e:
                print(f"[Library] Could not parse sample {f.name}: {e}")


@app.on_event("startup")
def startup_event():
    # 1. Index library books immediately (takes <20ms with AST disk cache)
    index_existing_books()
    # 2. Ensure initial user profile & memory are ready
    UserManager.get_instance()
    # 3. Load Kokoro TTS model asynchronously
    threading.Thread(target=get_engine, daemon=True).start()


# ----------------- User Profiles, Memory & Notes ----------------- #

@app.get("/api/user/current")
def get_current_user():
    um = UserManager.get_instance()
    user = um.get_active_user()
    mem = um.get_user_memory(user.id)
    return {
        "user": user.model_dump(),
        "memory": mem.model_dump(),
    }


@app.get("/api/users")
def list_users():
    um = UserManager.get_instance()
    users = um.get_all_users()
    active_id = um.get_active_user().id
    return [
        {
            **u.model_dump(),
            "is_active": (u.id == active_id),
        }
        for u in users
    ]


class SwitchUserRequest(BaseModel):
    user_id: str


@app.post("/api/user/switch")
def switch_user(req: SwitchUserRequest):
    um = UserManager.get_instance()
    user = um.set_active_user(req.user_id)
    if not user:
        raise HTTPException(status_code=404, detail="User not found")
    state = um.get_user_state(user.id)
    mem = um.get_user_memory(user.id)
    return {
        "success": True,
        "user": user.model_dump(),
        "state": state,
        "memory": mem.model_dump(),
    }


class CreateUserRequest(BaseModel):
    username: str
    display_name: Optional[str] = None
    avatar: str = "👤"
    voice: Optional[str] = None
    speed: Optional[float] = None
    theme: Optional[str] = None


@app.post("/api/user/create")
def create_user(req: CreateUserRequest):
    if not req.username.strip():
        raise HTTPException(status_code=400, detail="Username cannot be empty")
    um = UserManager.get_instance()
    user = um.create_user(
        username=req.username,
        display_name=req.display_name,
        avatar=req.avatar,
        voice=req.voice or DEFAULT_VOICE,
        speed=req.speed or DEFAULT_SPEED,
        theme=req.theme or "sepia",
    )
    return {
        "success": True,
        "user": user.model_dump(),
    }


@app.get("/api/user/memory")
def get_user_memory():
    um = UserManager.get_instance()
    user = um.get_active_user()
    mem = um.get_user_memory(user.id)
    return mem.model_dump()


class RecordStatsRequest(BaseModel):
    words: int = 0
    seconds: float = 0.0
    words_read: Optional[int] = None
    seconds_listened: Optional[float] = None
    book_id: Optional[str] = None


@app.post("/api/user/stats")
def record_reading_stats(req: RecordStatsRequest):
    um = UserManager.get_instance()
    words = req.words_read if req.words_read is not None else req.words
    seconds = req.seconds_listened if req.seconds_listened is not None else req.seconds
    um.record_reading_stats(words, seconds)
    if req.book_id:
        active_user = um.get_active_user()
        um._update_user_memory(active_user.id, req.book_id)
    return um.get_user_memory().model_dump()


class ClearMemoryRequest(BaseModel):
    clear_ast: bool = False


@app.post("/api/memory/clear")
def clear_memory(req: ClearMemoryRequest = ClearMemoryRequest()):
    # 1. Clear in-memory TTS engine cache
    get_engine().clear_cache()
    # 2. Clear disk audio cache & run GC
    um = UserManager.get_instance()
    result = um.clear_memory_cache(clear_ast=req.clear_ast)
    return result


@app.get("/api/notes")
def get_notes(book_id: Optional[str] = None):
    um = UserManager.get_instance()
    notes = um.get_notes(book_id=book_id)
    return [n.model_dump() for n in notes]


class CreateNoteRequest(BaseModel):
    book_id: str
    chapter_index: int
    sentence_index: int
    sentence_text: str
    note_text: str
    tags: Optional[List[str]] = None


@app.post("/api/notes")
def add_note(req: CreateNoteRequest):
    um = UserManager.get_instance()
    note = um.add_note(
        book_id=req.book_id,
        chapter_index=req.chapter_index,
        sentence_index=req.sentence_index,
        sentence_text=req.sentence_text,
        note_text=req.note_text,
        tags=req.tags,
    )
    return {"success": True, "note": note.model_dump()}


@app.delete("/api/notes/{note_id}")
def delete_note(note_id: str):
    um = UserManager.get_instance()
    ok = um.delete_note(note_id)
    if not ok:
        raise HTTPException(status_code=404, detail="Note not found")
    return {"success": True, "deleted": note_id}


# ----------------- REST Endpoints ----------------- #

@app.get("/api/status")
def get_status():
    um = UserManager.get_instance()
    user = um.get_active_user()
    return {
        "status": "online",
        "engine": "Kokoro-82M FP16 (ONNX Runtime / Apple Silicon M1)",
        "default_voice": user.voice or DEFAULT_VOICE,
        "default_speed": user.speed or DEFAULT_SPEED,
        "active_user": user.username,
        "smart_audio_mode": SMART_AUDIO_MODE,
        "local_ip": get_local_ip(),
        "port": DEFAULT_PORT,
        "companion_url": f"http://{get_local_ip()}:{DEFAULT_PORT}",
        "total_books_loaded": len(_loaded_documents),
    }


@app.get("/api/voices")
def list_voices():
    return get_engine().get_available_voices()


class LexiconEntry(BaseModel):
    word: str
    phonetic: str
    book_id: Optional[str] = None
    book_title: Optional[str] = None
    scope: Optional[str] = None  # "book" or "general"


class PullLexiconRequest(BaseModel):
    word: str
    book_id: str
    book_title: Optional[str] = None
    phonetic: Optional[str] = None


@app.get("/api/lexicon")
def get_lexicon(book_id: Optional[str] = None):
    return LexiconManager.get_instance().get_lexicon_review(book_id=book_id)


@app.post("/api/lexicon")
def add_lexicon_entry(entry: LexiconEntry):
    saved = LexiconManager.get_instance().add_override(
        word=entry.word,
        phonetic=entry.phonetic,
        book_id=entry.book_id,
        book_title=entry.book_title,
        scope=entry.scope,
    )
    get_engine().clear_cache()
    return {"success": True, "entry": saved}


@app.post("/api/lexicon/pull")
def pull_lexicon_entry(req: PullLexiconRequest):
    saved = LexiconManager.get_instance().pull_to_book(
        word=req.word,
        book_id=req.book_id,
        book_title=req.book_title,
        phonetic=req.phonetic,
    )
    get_engine().clear_cache()
    return {"success": True, "entry": saved}


@app.delete("/api/lexicon/{word}")
def delete_lexicon_entry(word: str, book_id: Optional[str] = None, scope: Optional[str] = None):
    deleted = LexiconManager.get_instance().remove_override(word, book_id=book_id, scope=scope)
    get_engine().clear_cache()
    return {"success": True, "deleted": word, "count": deleted}


@app.get("/api/state")
def get_reading_state():
    return UserManager.get_instance().get_user_state()


class ReadingStateUpdate(BaseModel):
    book_id: str
    chapter_index: int = 0
    sentence_index: int = 0


@app.post("/api/state")
def save_reading_state(update: ReadingStateUpdate):
    return UserManager.get_instance().save_user_state(
        book_id=update.book_id,
        chapter_index=update.chapter_index,
        sentence_index=update.sentence_index,
    )


@app.get("/api/library")
def get_library():
    um = UserManager.get_instance()
    state_data = um.get_user_state()
    positions = state_data.get("positions", {})
    last_book_id = state_data.get("last_book_id")

    items = []
    for doc in _loaded_documents.values():
        pos = positions.get(doc.id, {})
        ch_idx = pos.get("chapter_index", 0)
        sent_idx = pos.get("sentence_index", 0)
        total_ch = len(doc.chapters)

        progress_pct = 0
        if total_ch > 0:
            progress_pct = round(((ch_idx + 1) / total_ch) * 100) if (ch_idx > 0 or sent_idx > 0) else 0
            if progress_pct > 100:
                progress_pct = 100

        items.append({
            "id": doc.id,
            "title": doc.title,
            "author": doc.author,
            "file_format": doc.file_format,
            "chapters_count": total_ch,
            "total_words": doc.total_words,
            "total_sentences": doc.total_sentences,
            "file_path": doc.file_path,
            "is_sample": getattr(doc, "is_sample", False),
            "is_last_read": (doc.id == last_book_id),
            "progress_pct": progress_pct,
            "last_chapter_index": ch_idx,
            "last_sentence_index": sent_idx,
            "updated_at": pos.get("updated_at"),
        })

    # Sort: User uploaded books first (last_read first), then sample demos at the bottom
    items.sort(key=lambda b: (
        1 if b["is_sample"] else 0,
        0 if b["is_last_read"] else 1,
        -b.get("last_chapter_index", 0),
        b["title"]
    ))

    return items


@app.delete("/api/book/{book_id}")
def delete_book(book_id: str):
    if book_id not in _loaded_documents:
        raise HTTPException(status_code=404, detail="Book not found")

    doc = _loaded_documents[book_id]

    # If it is an uploaded file in data/uploads, unlink it from disk
    if doc.file_path:
        file_p = Path(doc.file_path)
        if file_p.exists() and UPLOAD_DIR in file_p.parents:
            try:
                file_p.unlink()
                print(f"[Library] Removed uploaded file from disk: {file_p.name}")
            except Exception as e:
                print(f"[Library] Could not delete file {file_p}: {e}")

    # Remove from memory index
    del _loaded_documents[book_id]

    # Clean up AST cache if present
    from src.config import AST_CACHE_DIR
    ast_cache = AST_CACHE_DIR / f"ast_{book_id}.json"
    if ast_cache.exists():
        try:
            ast_cache.unlink()
        except Exception:
            pass

    # Clean up state positions in user manager and root state
    um = UserManager.get_instance()
    active_user = um.get_active_user()
    from src.config import USERS_DIR
    user_state_file = USERS_DIR / active_user.id / "state.json"
    for s_file in [STATE_FILE, user_state_file]:
        if s_file.exists():
            try:
                data = json.loads(s_file.read_text(encoding="utf-8"))
                positions = data.get("positions", {})
                if book_id in positions:
                    del positions[book_id]
                if data.get("last_book_id") == book_id:
                    remaining_user_books = [d.id for d in _loaded_documents.values() if not getattr(d, "is_sample", False)]
                    data["last_book_id"] = remaining_user_books[0] if remaining_user_books else (list(_loaded_documents.keys())[0] if _loaded_documents else None)
                temp_file = s_file.with_suffix(".tmp")
                temp_file.write_text(json.dumps(data, indent=2), encoding="utf-8")
                temp_file.replace(s_file)
            except Exception:
                pass

    return {"success": True, "deleted": book_id}


@app.post("/api/upload")
async def upload_document(file: UploadFile = File(...)):
    suffix = Path(file.filename or "").suffix.lower()
    if suffix not in {".epub", ".pdf", ".md", ".markdown", ".txt", ".docx", ".html", ".htm"}:
        raise HTTPException(status_code=400, detail=f"Unsupported format: {suffix}")

    dest_path = UPLOAD_DIR / f"{uuid.uuid4().hex[:8]}_{file.filename}"
    with open(dest_path, "wb") as buffer:
        shutil.copyfileobj(file.file, buffer)

    try:
        doc = parse_document(dest_path)
        doc.is_sample = False
        doc.created_at = time.time()

        if doc.id in _loaded_documents:
            # Duplicate content already in library; remove redundant file
            dest_path.unlink(missing_ok=True)
            doc = _loaded_documents[doc.id]
        else:
            _loaded_documents[doc.id] = doc

        # Set as last_book_id in state and user memory
        um = UserManager.get_instance()
        um.update_user_state(book_id=doc.id, chapter_index=0, sentence_index=0)

        return {
            "success": True,
            "document": {
                "id": doc.id,
                "title": doc.title,
                "author": doc.author,
                "file_format": doc.file_format,
                "chapters_count": len(doc.chapters),
                "total_words": doc.total_words,
                "total_sentences": doc.total_sentences,
                "is_sample": False,
            },
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


@app.get("/api/book/{book_id}/search")
def search_book(book_id: str, q: str):
    if book_id not in _loaded_documents:
        raise HTTPException(status_code=404, detail="Book not found")
    query = q.strip().lower()
    if len(query) < 2:
        return []

    doc = _loaded_documents[book_id]
    matches = []
    for ch_idx, ch in enumerate(doc.chapters):
        s_counter = 0
        for p in ch.paragraphs:
            for s in p.sentences:
                if query in s.text.lower():
                    matches.append({
                        "chapter_index": ch_idx,
                        "chapter_title": ch.title,
                        "sentence_index": s_counter,
                        "sentence_id": s.id,
                        "text": s.text[:160] + ("..." if len(s.text) > 160 else ""),
                    })
                    if len(matches) >= 50:
                        return matches
                s_counter += 1
    return matches


@app.api_route("/api/tts/sentence", methods=["GET", "HEAD"])
def synthesize_sentence(
    text: str,
    voice: str = DEFAULT_VOICE,
    speed: float = DEFAULT_SPEED,
    sentence_id: Optional[str] = None,
    node_type: str = "p",
    book_id: Optional[str] = None,
):
    """Synthesize sentence audio in-memory with zero disk writes and word-level timings."""
    engine = get_engine()
    wav_bytes, duration, sample_rate, word_timings = engine.synthesize(
        text, voice=voice, speed=speed, node_type=node_type, is_preempt=True, book_id=book_id
    )

    headers = {
        "Content-Type": "audio/wav",
        "X-Audio-Duration": f"{duration:.3f}",
        "X-Sample-Rate": str(sample_rate),
        "X-Word-Timings": json.dumps(word_timings, separators=(",", ":")),
        "Cache-Control": "no-store",
    }
    if sentence_id:
        headers["X-Sentence-ID"] = sentence_id

    return Response(content=wav_bytes, media_type="audio/wav", headers=headers)


class LookaheadItem(BaseModel):
    text: str
    voice: str = DEFAULT_VOICE
    speed: float = DEFAULT_SPEED
    node_type: str = "p"
    book_id: Optional[str] = None


class LookaheadRequest(BaseModel):
    items: List[LookaheadItem]


@app.post("/api/tts/lookahead")
def queue_lookahead(req: LookaheadRequest):
    engine = get_engine()
    tuples = [(it.text, it.voice, float(it.speed), it.node_type, it.book_id) for it in req.items]
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
                await manager.broadcast({
                    "type": "remote_sync",
                    "book_id": msg.get("book_id"),
                    "chapter_id": msg.get("chapter_id"),
                    "sentence_id": msg.get("sentence_id"),
                    "is_playing": msg.get("is_playing", False),
                })
    except WebSocketDisconnect:
        manager.disconnect(websocket)
    except Exception:
        manager.disconnect(websocket)


# ----------------- Static UI Mounting ----------------- #

UI_DIR = ROOT_DIR / "src" / "ui"
if UI_DIR.exists():
    app.mount("/", StaticFiles(directory=str(UI_DIR), html=True), name="ui")
