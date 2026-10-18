"""Durable GatorConnect progress, successful lookups, and provider cooldowns.

SQLite is built into Python. This file never stores API keys, image bytes, or
Google Maps responses. Each write commits independently, so a later failed
event does not discard earlier extraction work.
"""

import json
import os
from pathlib import Path
import sqlite3

if __package__:
    from .runtime_utils import ScraperError
else:
    from runtime_utils import ScraperError


class GatorConnectState:
    """One run owns an OS lock; concurrent runs cannot pay for the same revision.

    The OS releases the lock if the process crashes. It is separate from the
    database transaction, so network calls never hold a SQLite write transaction.
    Separate state directories/machines do not share this protection.
    """

    def __init__(self, directory=None):
        base = Path(os.getenv("LOCALAPPDATA") or os.getenv("XDG_STATE_HOME")
                    or Path.home() / ".local" / "state")
        self.directory = Path(directory or os.getenv("GATORCONNECT_STATE_DIR")
                              or base / "UFEventTracker")
        self.lock = None
        self.connection = None

    def __enter__(self):
        try:
            self.directory.mkdir(parents=True, exist_ok=True)
            self.lock = (self.directory / "gatorconnect.lock").open("a+b")
            self.lock.seek(0, 2)
            if self.lock.tell() == 0:
                self.lock.write(b"0")
                self.lock.flush()
            self.lock.seek(0)
            try:
                if os.name == "nt":
                    import msvcrt
                    msvcrt.locking(self.lock.fileno(), msvcrt.LK_NBLCK, 1)
                else:
                    import fcntl
                    fcntl.flock(self.lock.fileno(), fcntl.LOCK_EX | fcntl.LOCK_NB)
            except OSError:
                self.lock.close()
                self.lock = None
                raise ScraperError("storage", "already_running",
                                   "Another GatorConnect run is using this state directory.") from None
            self.connection = sqlite3.connect(self.directory / "gatorconnect-state.sqlite3", timeout=5)
            with self.connection:
                self.connection.execute("CREATE TABLE IF NOT EXISTS scraper_state (key TEXT PRIMARY KEY, value TEXT NOT NULL)")
            return self
        except (OSError, sqlite3.Error):
            self.__exit__(None, None, None)
            raise ScraperError("storage", "state_unavailable",
                               "Cannot open GatorConnect state; stopping before paid calls.") from None

    def __exit__(self, *args):
        if self.connection is not None:
            self.connection.close()
        if self.lock is not None:
            # Closing the file releases the OS lock on both supported platforms.
            self.lock.close()
        self.connection = self.lock = None

    def get(self, key):
        """Bad storage stops processing instead of silently dropping duplicate protection."""
        try:
            row = self.connection.execute("SELECT value FROM scraper_state WHERE key = ?", (key,)).fetchone()
            value = json.loads(row[0]) if row else None
            if value is not None and not isinstance(value, dict):
                raise ValueError()
            return value
        except (sqlite3.Error, ValueError, TypeError):
            raise ScraperError("storage", "state_invalid", "Cannot read GatorConnect state safely.") from None

    def put(self, key, value):
        """Parameterize keys and data; commit each completed stage atomically."""
        try:
            with self.connection:
                self.connection.execute(
                    "INSERT INTO scraper_state(key, value) VALUES (?, ?) "
                    "ON CONFLICT(key) DO UPDATE SET value=excluded.value",
                    (key, json.dumps(value, sort_keys=True, ensure_ascii=True, allow_nan=False)))
        except (sqlite3.Error, ValueError, TypeError):
            raise ScraperError("storage", "state_write_failed", "Cannot save GatorConnect progress safely.") from None
