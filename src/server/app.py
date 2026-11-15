"""KaizenReader High-Performance Streaming & Sovereign Vault Server.

Provides RESTful endpoints for document ingestion, Quad-Engine speech synthesis
(Kokoro-82M FP16 + Apple Neural TTS), `.m4a` hardware chapter sprite compilation,
`.kzn` Sovereign Cartridge export/import, inline phonetic inspection, local TLS
certificate provisioning, persistent reading state, and WebSocket sync.
"""
from pathlib import Path
import json
import re
import shutil
import threading
import time
import uuid
from typing import Dict, List, Optional

from fastapi import FastAPI, UploadFile, File, HTTPException, WebSocket, WebSocketDisconnect, Query
from fastapi.responses import Response, StreamingResponse, FileResponse
from fastapi.staticfiles import StaticFiles
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel

from src.config import (
    ROOT_DIR, UPLOAD_DIR, STATE_FILE, DEFAULT_PORT,
    DEFAULT_VOICE, DEFAULT_SPEED, SMART_AUDIO_MODE, get_local_ip
)
from src.certs import ensure_local_tls_certs, get_tls_info, CA_CERT_PATH
from src.tts.engine import TTSEngine
from src.tts.apple_engine import AppleTTSEngine, build_apple_speech_payload
from src.tts.lexicon import LexiconManager, respelling_to_ipa, is_ipa
from src.tts.normalizer import normalize_text_for_tts
from src.tts.sprite_compiler import (
    compile_chapter_sprite,
    export_kzn_cartridge,
    get_book_packed_chapters,
    get_cached_sprite_paths,
    import_kzn_cartridge,
)
from src.parsers import parse_document
from src.users import UserManager, UserProfile, UserMemory, NoteEntry
from src.parsers.base import Document

app = FastAPI(title="KaizenReader Atelier & Acoustic Chronograph Core", version="3.0.0")

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
    expose_headers=[
        "X-Audio-Duration",
        "X-Sample-Rate",
        "X-Sentence-ID",
        "X-Word-Timings",
        "X-Engine-Used",
        "X-Sprite-Format",
    ],
)

_loaded_documents: Dict[str, Document] = {}
_state_lock = threading.Lock()


def get_engine() -> TTSEngine:
    return TTSEngine.get_instance()


def get_apple_engine() -> AppleTTSEngine:
    return AppleTTSEngine.get_instance()


def index_existing_books():
    """Load user uploaded books FIRST, then sample books (tagged is_sample=True)."""
    supported = {".epub", ".pdf", ".md", ".markdown", ".txt", ".docx", ".html", ".htm"}

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
    index_existing_books()
    UserManager.get_instance()
    threading.Thread(target=get_engine, daemon=True).start()
    threading.Thread(target=get_apple_engine, daemon=True).start()


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
    get_engine().clear_cache()
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


# ----------------- Status, Voices, TLS & Phonetics Lens ----------------- #

@app.get("/api/status")
def get_status():
    um = UserManager.get_instance()
    user = um.get_active_user()
    tls_info = get_tls_info(DEFAULT_PORT)
    return {
        "status": "online",
        "version": "3.0.0",
        "engine": "Quad-Engine (Kokoro-82M FP16 + Apple Neural TTS + Hardware Sprite Deck)",
        "engines_available": [
            {"id": "kokoro_auto", "label": "Kokoro-82M Studio (Vault + M1 Live)"},
            {"id": "apple_ios_neural", "label": "Apple Neural Live (On-Device ANE / SSML)"},
            {"id": "apple_mac_neural", "label": "Apple Neural Foundry (macOS Studio)"},
        ],
        "default_voice": user.voice or DEFAULT_VOICE,
        "default_speed": user.speed or DEFAULT_SPEED,
        "active_user": user.username,
        "smart_audio_mode": SMART_AUDIO_MODE,
        "local_ip": get_local_ip(),
        "port": DEFAULT_PORT,
        "companion_url": f"http://{get_local_ip()}:{DEFAULT_PORT}",
        "https_companion_url": tls_info["https_url"],
        "tls": tls_info,
        "total_books_loaded": len(_loaded_documents),
    }


@app.get("/api/tls-info")
def tls_status():
    return get_tls_info(DEFAULT_PORT)


@app.get("/api/trust-profile")
def download_local_ca_cert():
    """Generate (if needed) and serve the local Root CA certificate so iOS can trust HTTPS."""
    _, _, ca_path = ensure_local_tls_certs()
    return FileResponse(
        path=str(ca_path),
        media_type="application/x-x509-ca-cert",
        filename="kaizen-local-root-ca.pem",
    )


GDRIVE_CONFIG_FILE = ROOT_DIR / "data" / "gdrive_config.json"


class GDriveConfigUpdate(BaseModel):
    client_id: str = ""
    folder_name: str = "KaizenReader"


@app.get("/api/gdrive/config")
def get_gdrive_config():
    if GDRIVE_CONFIG_FILE.exists():
        try:
            return json.loads(GDRIVE_CONFIG_FILE.read_text(encoding="utf-8"))
        except Exception:
            pass
    return {"client_id": "", "folder_name": "KaizenReader"}


@app.post("/api/gdrive/config")
def save_gdrive_config(req: GDriveConfigUpdate):
    GDRIVE_CONFIG_FILE.parent.mkdir(parents=True, exist_ok=True)
    payload = {
        "client_id": req.client_id.strip(),
        "folder_name": req.folder_name.strip() or "KaizenReader",
    }
    GDRIVE_CONFIG_FILE.write_text(json.dumps(payload, indent=2), encoding="utf-8")
    return {"success": True, **payload}


@app.get("/api/voices")
def list_voices(include_apple: bool = True):
    kokoro_voices = get_engine().get_available_voices()
    for v in kokoro_voices:
        v["engine"] = "kokoro"
    if not include_apple:
        return kokoro_voices
    apple_voices = get_apple_engine().get_available_voices()
    return kokoro_voices + apple_voices


@app.get("/api/apple-voices")
def list_apple_voices():
    return get_apple_engine().get_available_voices()


@app.get("/api/phonetics/inspect")
def inspect_word_phonetics(word: str, context: Optional[str] = None):
    """Inspect a word or phrase for the Floating Inline Phonetic & IPA Lens.

    Returns compiled Kokoro IPA, Apple SSML payload, syllable breakdown for
    interactive stress shifting, and current Lexicon override status.
    """
    clean_word = word.strip().strip(".,!?;:\"'()[]{}")
    if not clean_word:
        raise HTTPException(status_code=400, detail="Word cannot be empty")

    lex = LexiconManager.get_instance()
    existing_override = lex.get_all().get(clean_word) or lex.get_ipa(clean_word)

    engine = get_engine()
    kokoro_ipa, _ = engine.build_phonemes(clean_word)
    apple_spoken, apple_ssml = build_apple_speech_payload(context or clean_word)

    # Generate interactive syllable candidates for 1-tap stress shifting in the UI
    syllables = _split_word_into_syllables(clean_word)
    stress_variants = []
    for idx in range(len(syllables)):
        parts = [
            s.upper() if i == idx else s.lower()
            for i, s in enumerate(syllables)
        ]
        respelling = "-".join(parts)
        compiled_ipa = respelling_to_ipa(respelling)
        stress_variants.append(
            {
                "stressed_index": idx,
                "respelling": respelling,
                "ipa": f"/{compiled_ipa}/" if compiled_ipa else "",
            }
        )

    return {
        "word": clean_word,
        "has_override": existing_override is not None,
        "override_value": existing_override,
        "kokoro_ipa": f"/{kokoro_ipa}/" if kokoro_ipa else "",
        "apple_spoken": apple_spoken,
        "apple_ssml": apple_ssml,
        "syllables": syllables,
        "stress_variants": stress_variants,
        "normalized_context": normalize_text_for_tts(context) if context else normalize_text_for_tts(clean_word),
    }


def _split_word_into_syllables(word: str) -> List[str]:
    """Heuristic vowel-nucleus syllable splitter for interactive stress pills."""
    w = re.sub(r"[^a-zA-Z]", "", word)
    if len(w) <= 3:
        return [w] if w else [word]
    chunks = re.findall(r"[^aeiouyAEIOUY]*[aeiouyAEIOUY]+(?:[^aeiouyAEIOUY](?=[aeiouyAEIOUY])|[^aeiouyAEIOUY]*$)", w)
    if not chunks:
        return [w]
    return chunks


class LexiconEntry(BaseModel):
    word: str
    phonetic: str


@app.get("/api/lexicon")
def get_lexicon():
    return LexiconManager.get_instance().get_all()


@app.post("/api/lexicon")
def add_lexicon_entry(entry: LexiconEntry):
    LexiconManager.get_instance().add_override(entry.word, entry.phonetic)
    get_engine().clear_cache()
    return {
        "success": True,
        "word": entry.word,
        "phonetic": entry.phonetic,
        "compiled_ipa": f"/{respelling_to_ipa(entry.phonetic)}/",
    }


@app.delete("/api/lexicon/{word}")
def delete_lexicon_entry(word: str):
    LexiconManager.get_instance().remove_override(word)
    get_engine().clear_cache()
    return {"success": True, "deleted": word}


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


# ----------------- Library, Books, Chapter Sprites & Cartridges ----------------- #

@app.get("/api/library")
def get_library(voice: str = DEFAULT_VOICE, speed: float = DEFAULT_SPEED):
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

        packed_info = get_book_packed_chapters(doc, voice=voice, speed=speed)
        packed_indices = [c["chapter_index"] for c in packed_info if c["packed"]]

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
            "packed_chapters": packed_indices,
            "packed_count": len(packed_indices),
        })

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

    if doc.file_path:
        file_p = Path(doc.file_path)
        if file_p.exists() and UPLOAD_DIR in file_p.parents:
            try:
                file_p.unlink()
            except Exception:
                pass

    del _loaded_documents[book_id]

    from src.config import AST_CACHE_DIR
    ast_cache = AST_CACHE_DIR / f"ast_{book_id}.json"
    if ast_cache.exists():
        try:
            ast_cache.unlink()
        except Exception:
            pass

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
    if suffix == ".kzn":
        raw_bytes = await file.read()
        try:
            doc, manifest = import_kzn_cartridge(raw_bytes)
            doc.is_sample = False
            doc.created_at = time.time()
            _loaded_documents[doc.id] = doc
            um = UserManager.get_instance()
            um.update_user_state(book_id=doc.id, chapter_index=0, sentence_index=0)
            return {
                "success": True,
                "is_cartridge": True,
                "manifest": manifest,
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
            raise HTTPException(status_code=400, detail=f"Invalid .kzn cartridge: {str(e)}")

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
            dest_path.unlink(missing_ok=True)
            doc = _loaded_documents[doc.id]
        else:
            _loaded_documents[doc.id] = doc

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


@app.get("/api/book/{book_id}/pack-status")
def get_book_pack_status(book_id: str, voice: str = DEFAULT_VOICE, speed: float = DEFAULT_SPEED):
    if book_id not in _loaded_documents:
        raise HTTPException(status_code=404, detail="Book not found")
    doc = _loaded_documents[book_id]
    chapters_status = get_book_packed_chapters(doc, voice=voice, speed=speed)
    total_bytes = sum(int(c["size_bytes"]) for c in chapters_status)
    packed_count = sum(1 for c in chapters_status if c["packed"])
    return {
        "book_id": book_id,
        "voice": voice,
        "speed": speed,
        "total_chapters": len(doc.chapters),
        "packed_chapters_count": packed_count,
        "total_sprite_bytes": total_bytes,
        "chapters": chapters_status,
    }


@app.get("/api/book/{book_id}/chapter/{ch_idx}/timings")
def get_chapter_sprite_timings(
    book_id: str,
    ch_idx: int,
    voice: str = DEFAULT_VOICE,
    speed: float = DEFAULT_SPEED,
    compile_if_missing: bool = True,
):
    if book_id not in _loaded_documents:
        raise HTTPException(status_code=404, detail="Book not found")
    doc = _loaded_documents[book_id]
    if ch_idx < 0 or ch_idx >= len(doc.chapters):
        raise HTTPException(status_code=404, detail="Chapter index out of range")

    audio_p, timings_p = get_cached_sprite_paths(book_id, ch_idx, voice, speed)
    if not (audio_p.exists() and timings_p.exists()):
        if not compile_if_missing:
            raise HTTPException(status_code=404, detail="Sprite not compiled yet")
        _, _, timings_data = compile_chapter_sprite(doc, ch_idx, voice=voice, speed=speed)
        return timings_data

    return json.loads(timings_p.read_text(encoding="utf-8"))


@app.get("/api/book/{book_id}/chapter/{ch_idx}/sprite")
def get_chapter_sprite_audio(
    book_id: str,
    ch_idx: int,
    voice: str = DEFAULT_VOICE,
    speed: float = DEFAULT_SPEED,
):
    """Compile (if needed) and stream the hardware-decoded `.m4a` chapter audio sprite."""
    if book_id not in _loaded_documents:
        raise HTTPException(status_code=404, detail="Book not found")
    doc = _loaded_documents[book_id]
    if ch_idx < 0 or ch_idx >= len(doc.chapters):
        raise HTTPException(status_code=404, detail="Chapter index out of range")

    audio_p, timings_p, timings_data = compile_chapter_sprite(doc, ch_idx, voice=voice, speed=speed)
    media_type = "audio/mp4" if audio_p.suffix == ".m4a" else "audio/wav"
    headers = {
        "X-Audio-Duration": str(timings_data.get("total_duration", 0.0)),
        "X-Sprite-Format": audio_p.suffix.lstrip("."),
        "X-Engine-Used": str(timings_data.get("engine", "kokoro_fp16")),
        "Accept-Ranges": "bytes",
    }
    return FileResponse(path=str(audio_p), media_type=media_type, headers=headers)


@app.get("/api/book/{book_id}/cartridge")
def download_book_cartridge(
    book_id: str,
    voice: str = DEFAULT_VOICE,
    speed: float = DEFAULT_SPEED,
    chapters: Optional[str] = Query(default=None, description="Comma-separated chapter indices to include"),
    compile_missing: bool = False,
):
    """Export a `.kzn` Sovereign Cartridge ZIP archive for AirDrop / USB Files app transfer."""
    if book_id not in _loaded_documents:
        raise HTTPException(status_code=404, detail="Book not found")
    doc = _loaded_documents[book_id]

    ch_list: Optional[List[int]] = None
    if chapters:
        ch_list = [int(x.strip()) for x in chapters.split(",") if x.strip().isdigit()]

    um = UserManager.get_instance()
    state_data = um.get_user_state()
    bookmark = state_data.get("positions", {}).get(book_id, {"chapter_index": 0, "sentence_index": 0})
    notes = [n.model_dump() for n in um.get_notes(book_id=book_id)]

    cartridge_bytes = export_kzn_cartridge(
        doc,
        voice=voice,
        speed=speed,
        chapters_to_pack=ch_list,
        compile_missing=compile_missing,
        state_bookmark=bookmark,
        notes=notes,
    )
    safe_title = "".join(c if c.isalnum() or c in "-_" else "_" for c in doc.title).strip("_") or doc.id
    filename = f"{safe_title}_{doc.id}.kzn"
    return Response(
        content=cartridge_bytes,
        media_type="application/zip",
        headers={"Content-Disposition": f'attachment; filename="{filename}"'},
    )


@app.post("/api/cartridge/import")
async def import_cartridge_endpoint(file: UploadFile = File(...)):
    raw_bytes = await file.read()
    try:
        doc, manifest = import_kzn_cartridge(raw_bytes)
        doc.is_sample = False
        doc.created_at = time.time()
        _loaded_documents[doc.id] = doc
        return {
            "success": True,
            "manifest": manifest,
            "book_id": doc.id,
            "title": doc.title,
        }
    except Exception as e:
        raise HTTPException(status_code=400, detail=str(e))


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


# ----------------- Real-Time Sentence TTS (Kokoro & Apple Neural) ----------------- #

@app.api_route("/api/tts/sentence", methods=["GET", "HEAD"])
def synthesize_sentence(
    text: str,
    voice: str = DEFAULT_VOICE,
    speed: float = DEFAULT_SPEED,
    sentence_id: Optional[str] = None,
    node_type: str = "p",
    engine_mode: Optional[str] = None,
):
    """Synthesize sentence audio in-memory via Kokoro-82M or Apple Neural TTS with word timings."""
    use_apple = voice.startswith("apple:") or (engine_mode == "apple_mac_neural")
    if use_apple:
        apple_eng = get_apple_engine()
        wav_bytes, duration, sample_rate, word_timings = apple_eng.synthesize(
            text, voice=voice, speed=speed, node_type=node_type
        )
        engine_used = "apple_mac_neural"
    else:
        eng = get_engine()
        wav_bytes, duration, sample_rate, word_timings = eng.synthesize(
            text, voice=voice, speed=speed, node_type=node_type, is_preempt=True
        )
        engine_used = "kokoro_fp16"

    headers = {
        "Content-Type": "audio/wav",
        "X-Audio-Duration": f"{duration:.3f}",
        "X-Sample-Rate": str(sample_rate),
        "X-Word-Timings": json.dumps(word_timings, separators=(",", ":")),
        "X-Engine-Used": engine_used,
        "Cache-Control": "no-store",
    }
    if sentence_id:
        headers["X-Sentence-ID"] = sentence_id

    return Response(content=wav_bytes, media_type="audio/wav", headers=headers)


@app.get("/api/tts/apple-sentence")
def synthesize_apple_sentence_direct(
    text: str,
    voice: str = "apple:Samantha",
    speed: float = DEFAULT_SPEED,
    node_type: str = "p",
):
    """Dedicated endpoint for Apple Neural sentence synthesis & Phonetic Lens A/B auditioning."""
    apple_eng = get_apple_engine()
    wav_bytes, duration, sample_rate, word_timings = apple_eng.synthesize(
        text, voice=voice, speed=speed, node_type=node_type
    )
    headers = {
        "Content-Type": "audio/wav",
        "X-Audio-Duration": f"{duration:.3f}",
        "X-Sample-Rate": str(sample_rate),
        "X-Word-Timings": json.dumps(word_timings, separators=(",", ":")),
        "X-Engine-Used": "apple_mac_neural",
        "Cache-Control": "no-store",
    }
    return Response(content=wav_bytes, media_type="audio/wav", headers=headers)


class LookaheadItem(BaseModel):
    text: str
    voice: str = DEFAULT_VOICE
    speed: float = DEFAULT_SPEED
    node_type: str = "p"


class LookaheadRequest(BaseModel):
    items: List[LookaheadItem]


@app.post("/api/tts/lookahead")
def queue_lookahead(req: LookaheadRequest):
    kokoro_tuples = [
        (it.text, it.voice, float(it.speed), it.node_type)
        for it in req.items
        if not it.voice.startswith("apple:")
    ]
    if kokoro_tuples:
        get_engine().queue_lookahead(kokoro_tuples)
    return {"queued": len(kokoro_tuples)}


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
