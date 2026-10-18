"""Cache Gemini extraction only; never persist keys or Google Maps responses."""

import hashlib
from contextlib import closing
import json
import os
from pathlib import Path
import sqlite3
import sys
import tempfile
import time

if __package__:
    from .config import CACHE_TTL_SECONDS, EVENT_TAGS
else:
    from config import CACHE_TTL_SECONDS, EVENT_TAGS


def cache_key(images, caption, model, *, source_type="instagram"):
    """Image bytes detect changed flyers even when the post URL is unchanged."""
    digest = hashlib.sha256()
    # Changing prompts or validation code invalidates old extraction results.
    for name in ('gemini_extractor.py', 'event_validator.py'):
        digest.update(Path(__file__).with_name(name).read_bytes())
    digest.update(json.dumps([source_type, caption, model, EVENT_TAGS]).encode())
    for data, mime in images:
        digest.update(mime.encode())
        digest.update(hashlib.sha256(data).digest())
    return digest.hexdigest()


def cached_extraction(key, value=None):
    """Best-effort cache in the OS user cache folder; failure never loses events.

    Set SCRAPER_CACHE_DIR to choose a folder, or SCRAPER_DISABLE_CACHE=1 to
    disable persistence. Only raw model JSON is stored, for up to one day.
    """
    if os.getenv('SCRAPER_DISABLE_CACHE') == '1':
        return None
    base = Path(os.getenv('LOCALAPPDATA') or os.getenv('XDG_CACHE_HOME') or tempfile.gettempdir())
    folder = Path(os.getenv('SCRAPER_CACHE_DIR') or base / 'UFEventTracker')
    try:
        folder.mkdir(parents=True, exist_ok=True, mode=0o700)
        # SQLite safely handles overlapping scheduled runs and partial writes.
        # The sqlite transaction context commits, but does not close the file.
        # Explicit closing also avoids leaving the database locked on Windows.
        with closing(sqlite3.connect(folder / 'extractions.sqlite3', timeout=2)) as connection, connection:
            connection.execute('CREATE TABLE IF NOT EXISTS extractions (key TEXT PRIMARY KEY, created REAL, data TEXT)')
            connection.execute('DELETE FROM extractions WHERE created < ?', (time.time() - CACHE_TTL_SECONDS,))
            if value is not None:
                connection.execute('INSERT OR REPLACE INTO extractions VALUES (?, ?, ?)',
                                   (key, time.time(), json.dumps(value)))
                return None
            row = connection.execute('SELECT data FROM extractions WHERE key = ?', (key,)).fetchone()
            return json.loads(row[0]) if row else None
    except (OSError, sqlite3.Error, ValueError):
        print('Extraction cache unavailable; continuing without cached data.', file=sys.stderr)
        return None
