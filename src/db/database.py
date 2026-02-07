import sqlite3
import json
import logging
import threading
import time
from datetime import datetime
from pathlib import Path

logger = logging.getLogger(__name__)

DB_PATH = Path(__file__).resolve().parent.parent.parent / "baby_monitor.db"


class Database:
    _instance = None
    _lock = threading.Lock()

    def __new__(cls):
        if cls._instance is None:
            with cls._lock:
                if cls._instance is None:
                    cls._instance = super().__new__(cls)
                    cls._instance._initialized = False
        return cls._instance

    def __init__(self):
        if self._initialized:
            return
        self._initialized = True
        self._local = threading.local()
        self._init_db()

    def _get_conn(self) -> sqlite3.Connection:
        if not hasattr(self._local, "conn") or self._local.conn is None:
            self._local.conn = sqlite3.connect(str(DB_PATH), check_same_thread=False)
            self._local.conn.row_factory = sqlite3.Row
            self._local.conn.execute("PRAGMA journal_mode=WAL")
        return self._local.conn

    def _init_db(self):
        conn = self._get_conn()
        conn.executescript("""
            CREATE TABLE IF NOT EXISTS events (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                timestamp TEXT NOT NULL,
                event_type TEXT NOT NULL,
                severity TEXT DEFAULT 'info',
                data TEXT,
                created_at REAL NOT NULL
            );

            CREATE TABLE IF NOT EXISTS discord_messages (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                timestamp TEXT NOT NULL,
                channel TEXT NOT NULL,
                title TEXT,
                description TEXT,
                risk_level TEXT,
                has_image INTEGER DEFAULT 0,
                success INTEGER DEFAULT 1,
                error TEXT,
                created_at REAL NOT NULL
            );

            CREATE TABLE IF NOT EXISTS vision_logs (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                timestamp TEXT NOT NULL,
                face_covered INTEGER,
                position TEXT,
                in_crib INTEGER,
                risk_level TEXT,
                description TEXT,
                created_at REAL NOT NULL
            );

            CREATE TABLE IF NOT EXISTS motion_logs (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                timestamp TEXT NOT NULL,
                has_motion INTEGER,
                magnitude REAL,
                description TEXT,
                created_at REAL NOT NULL
            );

            CREATE TABLE IF NOT EXISTS audio_logs (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                timestamp TEXT NOT NULL,
                is_crying INTEGER,
                cry_type TEXT,
                breathing_detected INTEGER,
                description TEXT,
                created_at REAL NOT NULL
            );

            CREATE TABLE IF NOT EXISTS config (
                key TEXT PRIMARY KEY,
                value TEXT NOT NULL,
                updated_at REAL NOT NULL
            );

            CREATE INDEX IF NOT EXISTS idx_events_type ON events(event_type);
            CREATE INDEX IF NOT EXISTS idx_events_ts ON events(created_at);
            CREATE INDEX IF NOT EXISTS idx_discord_channel ON discord_messages(channel);
            CREATE INDEX IF NOT EXISTS idx_discord_ts ON discord_messages(created_at);
            CREATE INDEX IF NOT EXISTS idx_vision_ts ON vision_logs(created_at);
            CREATE INDEX IF NOT EXISTS idx_motion_ts ON motion_logs(created_at);
            CREATE INDEX IF NOT EXISTS idx_audio_ts ON audio_logs(created_at);
        """)
        conn.commit()
        self._init_default_config()
        logger.info(f"Database initialized at {DB_PATH}")

    def _init_default_config(self):
        """Initialize default config values if not set."""
        from src.vision.analyzer import DEFAULT_ANALYSIS_PROMPT
        defaults = {
            "vlm_prompt": DEFAULT_ANALYSIS_PROMPT,
            "ai_camera_id": "0",
        }
        for key, value in defaults.items():
            if self.get_config(key) is None:
                self.set_config(key, value)

    def get_config(self, key: str) -> str | None:
        conn = self._get_conn()
        row = conn.execute("SELECT value FROM config WHERE key = ?", (key,)).fetchone()
        return row["value"] if row else None

    def set_config(self, key: str, value: str):
        conn = self._get_conn()
        conn.execute(
            "INSERT OR REPLACE INTO config (key, value, updated_at) VALUES (?, ?, ?)",
            (key, value, time.time()),
        )
        conn.commit()

    def get_all_config(self) -> dict[str, str]:
        conn = self._get_conn()
        rows = conn.execute("SELECT key, value FROM config").fetchall()
        return {r["key"]: r["value"] for r in rows}

    def log_event(self, event_type: str, severity: str = "info", data: dict | None = None):
        now = datetime.now()
        conn = self._get_conn()
        conn.execute(
            "INSERT INTO events (timestamp, event_type, severity, data, created_at) VALUES (?, ?, ?, ?, ?)",
            (now.isoformat(), event_type, severity, json.dumps(data) if data else None, time.time()),
        )
        conn.commit()

    def log_discord_message(self, channel: str, title: str, description: str,
                            risk_level: str = "", has_image: bool = False,
                            success: bool = True, error: str = ""):
        now = datetime.now()
        conn = self._get_conn()
        conn.execute(
            "INSERT INTO discord_messages (timestamp, channel, title, description, risk_level, has_image, success, error, created_at) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)",
            (now.isoformat(), channel, title, description, risk_level, int(has_image), int(success), error, time.time()),
        )
        conn.commit()

    def log_vision(self, face_covered: bool, position: str, in_crib: bool,
                   risk_level: str, description: str):
        now = datetime.now()
        conn = self._get_conn()
        conn.execute(
            "INSERT INTO vision_logs (timestamp, face_covered, position, in_crib, risk_level, description, created_at) VALUES (?, ?, ?, ?, ?, ?, ?)",
            (now.isoformat(), int(face_covered), position, int(in_crib), risk_level, description, time.time()),
        )
        conn.commit()

    def log_motion(self, has_motion: bool, magnitude: float, description: str):
        now = datetime.now()
        conn = self._get_conn()
        conn.execute(
            "INSERT INTO motion_logs (timestamp, has_motion, magnitude, description, created_at) VALUES (?, ?, ?, ?, ?)",
            (now.isoformat(), int(has_motion), magnitude, description, time.time()),
        )
        conn.commit()

    def log_audio(self, is_crying: bool, cry_type: str, breathing_detected: bool, description: str):
        now = datetime.now()
        conn = self._get_conn()
        conn.execute(
            "INSERT INTO audio_logs (timestamp, is_crying, cry_type, breathing_detected, description, created_at) VALUES (?, ?, ?, ?, ?, ?)",
            (now.isoformat(), int(is_crying), cry_type, int(breathing_detected), description, time.time()),
        )
        conn.commit()

    def get_recent_events(self, limit: int = 50, event_type: str | None = None) -> list[dict]:
        conn = self._get_conn()
        if event_type:
            rows = conn.execute(
                "SELECT * FROM events WHERE event_type = ? ORDER BY created_at DESC LIMIT ?",
                (event_type, limit),
            ).fetchall()
        else:
            rows = conn.execute(
                "SELECT * FROM events ORDER BY created_at DESC LIMIT ?", (limit,)
            ).fetchall()
        return [dict(r) for r in rows]

    def get_recent_discord_messages(self, limit: int = 50, channel: str | None = None) -> list[dict]:
        conn = self._get_conn()
        if channel:
            rows = conn.execute(
                "SELECT * FROM discord_messages WHERE channel = ? ORDER BY created_at DESC LIMIT ?",
                (channel, limit),
            ).fetchall()
        else:
            rows = conn.execute(
                "SELECT * FROM discord_messages ORDER BY created_at DESC LIMIT ?", (limit,)
            ).fetchall()
        return [dict(r) for r in rows]

    def get_recent_vision(self, limit: int = 50) -> list[dict]:
        conn = self._get_conn()
        rows = conn.execute(
            "SELECT * FROM vision_logs ORDER BY created_at DESC LIMIT ?", (limit,)
        ).fetchall()
        return [dict(r) for r in rows]

    def get_recent_motion(self, limit: int = 50) -> list[dict]:
        conn = self._get_conn()
        rows = conn.execute(
            "SELECT * FROM motion_logs ORDER BY created_at DESC LIMIT ?", (limit,)
        ).fetchall()
        return [dict(r) for r in rows]

    def get_recent_audio(self, limit: int = 50) -> list[dict]:
        conn = self._get_conn()
        rows = conn.execute(
            "SELECT * FROM audio_logs ORDER BY created_at DESC LIMIT ?", (limit,)
        ).fetchall()
        return [dict(r) for r in rows]

    def get_stats(self) -> dict:
        conn = self._get_conn()
        stats = {}
        for table in ["events", "discord_messages", "vision_logs", "motion_logs", "audio_logs"]:
            row = conn.execute(f"SELECT COUNT(*) as cnt FROM {table}").fetchone()
            stats[table] = row["cnt"]

        # danger/warning counts
        row = conn.execute(
            "SELECT COUNT(*) as cnt FROM vision_logs WHERE risk_level IN ('danger', 'warning')"
        ).fetchone()
        stats["alerts_count"] = row["cnt"]

        row = conn.execute(
            "SELECT COUNT(*) as cnt FROM audio_logs WHERE is_crying = 1"
        ).fetchone()
        stats["cry_count"] = row["cnt"]

        # Vision error stats
        row = conn.execute(
            "SELECT COUNT(*) as cnt FROM events WHERE event_type = 'vision_error'"
        ).fetchone()
        stats["vision_errors"] = row["cnt"]

        row = conn.execute(
            "SELECT data, created_at FROM events WHERE event_type = 'vision_error' ORDER BY created_at DESC LIMIT 1"
        ).fetchone()
        if row:
            stats["last_vision_error"] = row["data"]
            stats["last_vision_error_at"] = row["created_at"]

        return stats
