"""SQLite response cache so reruns cost nothing."""

from __future__ import annotations

import hashlib
import json
import sqlite3
import time
from pathlib import Path
from typing import Any

from evalkit.providers.base import Request, Response

_SCHEMA = """
CREATE TABLE IF NOT EXISTS responses (
    key TEXT PRIMARY KEY,
    provider TEXT NOT NULL,
    text TEXT NOT NULL,
    input_tokens INTEGER,
    output_tokens INTEGER,
    cost_usd REAL,
    latency_ms REAL NOT NULL,
    created_at REAL NOT NULL
)
"""


def cache_key(identity: dict[str, Any], request: Request) -> str:
    payload = {
        "identity": identity,
        "prompt": request.prompt,
        "system": request.system,
        "seed": request.seed,
        "repeat": request.repeat,
    }
    encoded = json.dumps(payload, sort_keys=True, ensure_ascii=False, default=str)
    return hashlib.sha256(encoded.encode()).hexdigest()


class ResponseCache:
    """A tiny key-value store keyed by provider identity plus request."""

    def __init__(self, path: str | Path) -> None:
        self.path = Path(path)
        if str(self.path) != ":memory:":
            self.path.parent.mkdir(parents=True, exist_ok=True)
        self._db = sqlite3.connect(str(self.path), check_same_thread=False)
        self._db.execute("PRAGMA journal_mode=WAL") if str(self.path) != ":memory:" else None
        self._db.execute(_SCHEMA)
        self._db.commit()
        self.hits = 0
        self.misses = 0

    def get(self, key: str) -> Response | None:
        row = self._db.execute(
            "SELECT text, input_tokens, output_tokens, cost_usd, latency_ms FROM responses WHERE key = ?",
            (key,),
        ).fetchone()
        if row is None:
            self.misses += 1
            return None
        self.hits += 1
        return Response(
            text=row[0],
            input_tokens=row[1],
            output_tokens=row[2],
            cost_usd=row[3],
            latency_ms=row[4],
            cached=True,
        )

    def put(self, key: str, provider: str, response: Response) -> None:
        self._db.execute(
            "INSERT OR REPLACE INTO responses VALUES (?, ?, ?, ?, ?, ?, ?, ?)",
            (
                key,
                provider,
                response.text,
                response.input_tokens,
                response.output_tokens,
                response.cost_usd,
                response.latency_ms,
                time.time(),
            ),
        )
        self._db.commit()

    def stats(self) -> dict[str, Any]:
        count, size = self._db.execute(
            "SELECT COUNT(*), COALESCE(SUM(LENGTH(text)), 0) FROM responses"
        ).fetchone()
        by_provider = dict(
            self._db.execute(
                "SELECT provider, COUNT(*) FROM responses GROUP BY provider ORDER BY provider"
            ).fetchall()
        )
        return {
            "path": str(self.path),
            "entries": count,
            "text_bytes": size,
            "by_provider": by_provider,
        }

    def clear(self) -> int:
        deleted = self._db.execute("DELETE FROM responses").rowcount
        self._db.commit()
        return int(deleted)

    def close(self) -> None:
        self._db.close()
