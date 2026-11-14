"""User Profile, Memory Bank & Multi-User State Manager for KaizenReader.

Provides isolated user profiles, reading state, memory banks, reading streaks,
and persistent note/annotation storage per user.
"""
import gc
import json
import os
import shutil
import threading
import time
import uuid
from pathlib import Path
from typing import Dict, List, Optional
from pydantic import BaseModel, Field

from src.config import DATA_DIR, USERS_DIR, USERS_FILE, STATE_FILE, CACHE_DIR, AST_CACHE_DIR, DEFAULT_VOICE, DEFAULT_SPEED

_user_lock = threading.Lock()


class UserProfile(BaseModel):
    id: str
    username: str
    display_name: str
    avatar: str = "⚡️"
    created_at: float = Field(default_factory=time.time)
    last_active_at: float = Field(default_factory=time.time)
    voice: str = DEFAULT_VOICE
    speed: float = DEFAULT_SPEED
    theme: str = "sepia"


class UserMemory(BaseModel):
    user_id: str
    total_words_read: int = 0
    total_seconds_listened: float = 0.0
    total_sessions: int = 1
    books_started: List[str] = Field(default_factory=list)
    books_completed: List[str] = Field(default_factory=list)
    reading_streak_days: int = 1
    last_active_book: Optional[str] = None
    favorite_voice: str = DEFAULT_VOICE


class NoteEntry(BaseModel):
    id: str
    book_id: str
    chapter_index: int
    sentence_index: int
    sentence_text: str
    note_text: str
    tags: List[str] = Field(default_factory=list)
    created_at: float = Field(default_factory=time.time)


class UserManager:
    _instance: Optional["UserManager"] = None
    _singleton_lock = threading.Lock()

    @classmethod
    def get_instance(cls) -> "UserManager":
        with cls._singleton_lock:
            if cls._instance is None:
                cls._instance = cls()
            return cls._instance

    def __init__(self):
        USERS_DIR.mkdir(parents=True, exist_ok=True)
        self._ensure_initial_user()

    def _ensure_initial_user(self):
        """Initialize default Josh profile and migrate root state.json if present."""
        with _user_lock:
            if not USERS_FILE.exists():
                default_user = UserProfile(
                    id="u_josh",
                    username="Josh",
                    display_name="Josh Shay",
                    avatar="⚡️",
                    voice=DEFAULT_VOICE,
                    speed=DEFAULT_SPEED,
                    theme="sepia",
                )
                data = {
                    "active_user_id": default_user.id,
                    "users": [default_user.model_dump()],
                }
                USERS_FILE.write_text(json.dumps(data, indent=2), encoding="utf-8")

                # Setup user directory
                user_dir = USERS_DIR / default_user.id
                user_dir.mkdir(parents=True, exist_ok=True)
                (user_dir / "voice_memos").mkdir(parents=True, exist_ok=True)

                # Migrate existing state.json if present
                if STATE_FILE.exists():
                    try:
                        shutil.copy2(STATE_FILE, user_dir / "state.json")
                    except Exception:
                        pass

                # Initialize memory
                mem = UserMemory(user_id=default_user.id, favorite_voice=default_user.voice)
                (user_dir / "memory.json").write_text(json.dumps(mem.model_dump(), indent=2), encoding="utf-8")
                (user_dir / "notes.json").write_text("[]", encoding="utf-8")

    def _read_users_data(self) -> dict:
        if not USERS_FILE.exists():
            self._ensure_initial_user()
        try:
            return json.loads(USERS_FILE.read_text(encoding="utf-8"))
        except Exception:
            return {"active_user_id": "u_josh", "users": []}

    def _write_users_data(self, data: dict):
        temp_file = USERS_FILE.with_suffix(".tmp")
        temp_file.write_text(json.dumps(data, indent=2), encoding="utf-8")
        temp_file.replace(USERS_FILE)

    def get_all_users(self) -> List[UserProfile]:
        with _user_lock:
            data = self._read_users_data()
            return [UserProfile.model_validate(u) for u in data.get("users", [])]

    def get_active_user(self) -> UserProfile:
        with _user_lock:
            data = self._read_users_data()
            active_id = data.get("active_user_id", "u_josh")
            for u in data.get("users", []):
                if u["id"] == active_id:
                    return UserProfile.model_validate(u)
            # Fallback
            if data.get("users"):
                return UserProfile.model_validate(data["users"][0])
            user = UserProfile(id="u_josh", username="Josh", display_name="Josh Shay")
            return user

    get_current_user = get_active_user


    def set_active_user(self, user_id: str) -> Optional[UserProfile]:
        with _user_lock:
            data = self._read_users_data()
            target = None
            for u in data.get("users", []):
                if u["id"] == user_id:
                    u["last_active_at"] = time.time()
                    target = UserProfile.model_validate(u)
                    break
            if target:
                data["active_user_id"] = user_id
                self._write_users_data(data)
                # Mirror user state to root state.json for backward compatibility
                self._sync_user_to_root_state(user_id)
            return target

    def create_user(
        self,
        username: str,
        display_name: Optional[str] = None,
        avatar: str = "👤",
        voice: str = DEFAULT_VOICE,
        speed: float = DEFAULT_SPEED,
        theme: str = "sepia",
    ) -> UserProfile:
        clean_username = username.strip()
        uid = f"u_{clean_username.lower().replace(' ', '_')[:16]}_{uuid.uuid4().hex[:4]}"
        user = UserProfile(
            id=uid,
            username=clean_username,
            display_name=display_name.strip() if display_name else clean_username,
            avatar=avatar,
            voice=voice,
            speed=speed,
            theme=theme,
        )

        with _user_lock:
            data = self._read_users_data()
            data.setdefault("users", []).append(user.model_dump())
            data["active_user_id"] = user.id
            self._write_users_data(data)

            # Create directories
            udir = USERS_DIR / user.id
            udir.mkdir(parents=True, exist_ok=True)
            (udir / "voice_memos").mkdir(parents=True, exist_ok=True)
            (udir / "notes.json").write_text("[]", encoding="utf-8")
            (udir / "state.json").write_text(json.dumps({"last_book_id": None, "positions": {}}, indent=2), encoding="utf-8")

            mem = UserMemory(user_id=user.id, favorite_voice=voice)
            (udir / "memory.json").write_text(json.dumps(mem.model_dump(), indent=2), encoding="utf-8")

        self._sync_user_to_root_state(user.id)
        return user

    def get_user_state(self, user_id: Optional[str] = None) -> dict:
        uid = user_id or self.get_active_user().id
        user_state_file = USERS_DIR / uid / "state.json"
        if user_state_file.exists():
            try:
                return json.loads(user_state_file.read_text(encoding="utf-8"))
            except Exception:
                pass
        # Fallback to root state.json
        if STATE_FILE.exists():
            try:
                return json.loads(STATE_FILE.read_text(encoding="utf-8"))
            except Exception:
                pass
        return {}

    def save_user_state(
        self,
        book_id: str,
        chapter_index: int,
        sentence_index: int,
        user_id: Optional[str] = None,
    ) -> dict:
        uid = user_id or self.get_active_user().id
        user_dir = USERS_DIR / uid
        user_dir.mkdir(parents=True, exist_ok=True)
        user_state_file = user_dir / "state.json"

        data = {}
        if user_state_file.exists():
            try:
                data = json.loads(user_state_file.read_text(encoding="utf-8"))
            except Exception:
                data = {}

        data["last_book_id"] = book_id
        positions = data.setdefault("positions", {})
        positions[book_id] = {
            "chapter_index": chapter_index,
            "sentence_index": sentence_index,
            "updated_at": time.time(),
        }

        # Atomic write to user's state.json
        temp_file = user_state_file.with_suffix(".tmp")
        temp_file.write_text(json.dumps(data, indent=2), encoding="utf-8")
        temp_file.replace(user_state_file)

        # Mirror to root state.json for server consistency
        try:
            root_temp = STATE_FILE.with_suffix(".tmp")
            root_temp.write_text(json.dumps(data, indent=2), encoding="utf-8")
            root_temp.replace(STATE_FILE)
        except Exception:
            pass

        # Update user memory
        self._update_user_memory(uid, book_id)

        return {"success": True, "user_id": uid, "book_id": book_id}

    def _sync_user_to_root_state(self, user_id: str):
        user_state_file = USERS_DIR / user_id / "state.json"
        if user_state_file.exists():
            try:
                shutil.copy2(user_state_file, STATE_FILE)
            except Exception:
                pass

    def _update_user_memory(self, user_id: str, book_id: str):
        mem_file = USERS_DIR / user_id / "memory.json"
        mem_data = {}
        if mem_file.exists():
            try:
                mem_data = json.loads(mem_file.read_text(encoding="utf-8"))
            except Exception:
                mem_data = {}

        mem = UserMemory.model_validate({**mem_data, "user_id": user_id})
        mem.last_active_book = book_id
        if book_id not in mem.books_started:
            mem.books_started.append(book_id)

        temp = mem_file.with_suffix(".tmp")
        temp.write_text(json.dumps(mem.model_dump(), indent=2), encoding="utf-8")
        temp.replace(mem_file)

    def get_user_memory(self, user_id: Optional[str] = None) -> UserMemory:
        uid = user_id or self.get_active_user().id
        mem_file = USERS_DIR / uid / "memory.json"
        if mem_file.exists():
            try:
                return UserMemory.model_validate(json.loads(mem_file.read_text(encoding="utf-8")))
            except Exception:
                pass
        return UserMemory(user_id=uid)

    def record_reading_stats(self, words: int, seconds: float, user_id: Optional[str] = None):
        uid = user_id or self.get_active_user().id
        mem = self.get_user_memory(uid)
        mem.total_words_read += max(0, words)
        mem.total_seconds_listened += max(0.0, seconds)

        mem_file = USERS_DIR / uid / "memory.json"
        temp = mem_file.with_suffix(".tmp")
        temp.write_text(json.dumps(mem.model_dump(), indent=2), encoding="utf-8")
        temp.replace(mem_file)

    def get_notes(self, book_id: Optional[str] = None, user_id: Optional[str] = None) -> List[NoteEntry]:
        uid = user_id or self.get_active_user().id
        notes_file = USERS_DIR / uid / "notes.json"
        if not notes_file.exists():
            return []
        try:
            raw = json.loads(notes_file.read_text(encoding="utf-8"))
            notes = [NoteEntry.model_validate(n) for n in raw]
            if book_id:
                notes = [n for n in notes if n.book_id == book_id]
            return sorted(notes, key=lambda n: n.created_at, reverse=True)
        except Exception:
            return []

    def add_note(
        self,
        book_id: str,
        chapter_index: int,
        sentence_index: int,
        sentence_text: str,
        note_text: str,
        tags: Optional[List[str]] = None,
        user_id: Optional[str] = None,
    ) -> NoteEntry:
        uid = user_id or self.get_active_user().id
        notes_file = USERS_DIR / uid / "notes.json"
        notes = self.get_notes(user_id=uid)

        new_note = NoteEntry(
            id=f"note_{uuid.uuid4().hex[:8]}",
            book_id=book_id,
            chapter_index=chapter_index,
            sentence_index=sentence_index,
            sentence_text=sentence_text.strip(),
            note_text=note_text.strip(),
            tags=tags or [],
        )
        notes.insert(0, new_note)

        temp = notes_file.with_suffix(".tmp")
        temp.write_text(json.dumps([n.model_dump() for n in notes], indent=2), encoding="utf-8")
        temp.replace(notes_file)
        return new_note

    def delete_note(self, note_id: str, user_id: Optional[str] = None) -> bool:
        uid = user_id or self.get_active_user().id
        notes_file = USERS_DIR / uid / "notes.json"
        notes = self.get_notes(user_id=uid)
        initial_len = len(notes)
        notes = [n for n in notes if n.id != note_id]
        if len(notes) < initial_len:
            temp = notes_file.with_suffix(".tmp")
            temp.write_text(json.dumps([n.model_dump() for n in notes], indent=2), encoding="utf-8")
            temp.replace(notes_file)
            return True
        return False

    def clear_memory_cache(self, clear_ast: bool = False) -> dict:
        """Clear audio caches, in-memory lookahead, and optionally AST cache."""
        audio_files_cleared = 0
        ast_files_cleared = 0

        # Clear audio cache
        if CACHE_DIR.exists():
            for f in CACHE_DIR.glob("*.*"):
                try:
                    f.unlink()
                    audio_files_cleared += 1
                except Exception:
                    pass

        # Optionally clear AST cache
        if clear_ast and AST_CACHE_DIR.exists():
            for f in AST_CACHE_DIR.glob("*.json"):
                try:
                    f.unlink()
                    ast_files_cleared += 1
                except Exception:
                    pass

        # Force python garbage collection
        gc.collect()

        return {
            "success": True,
            "audio_cache_files_cleared": audio_files_cleared,
            "ast_cache_files_cleared": ast_files_cleared,
            "timestamp": time.time(),
        }


def get_user_manager() -> UserManager:
    return UserManager.get_instance()

