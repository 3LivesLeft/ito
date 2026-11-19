# SPDX-License-Identifier: Apache-2.0
"""The persistent message queue and receipts (ADR 0011).

``/data/messaging/queue.db`` (SQLite from the standard library, WAL, ``synchronous=NORMAL``), owned
by the engine's user. Outbound messages move through the contract's states; inbound messages are
kept until acknowledged (at-least-once). Every limit here is a hard limit:

- pending outbound ≤ 200; expiry after 7 days; idempotency keys remembered for 24 h;
- inbound ≤ 500 messages and ≤ 2 MiB of content; when full, the oldest is dropped and counted;
- acknowledged content is deleted at once (default) or kept for at most 30 days;
- the file ≤ 16 MiB; weekly ``VACUUM`` when idle;
- a corrupt file is quarantined and a fresh queue started; it never blocks transport.

Content is never logged.
"""

from __future__ import annotations

import contextlib
import secrets
import sqlite3
import time
from collections.abc import Callable
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from . import contract

PENDING_MAX = 200
EXPIRY = 7 * 86400.0
IDEMPOTENCY_TTL = 86400.0
INBOUND_MAX = 500
INBOUND_BYTES_MAX = 2 * 1024 * 1024
FILE_MAX = 16 * 1024 * 1024
RETENTION_MAX_DAYS = 30
VACUUM_INTERVAL = 7 * 86400.0
PENDING_STATES = ("queued", "sending")

SCHEMA = """
CREATE TABLE IF NOT EXISTS outbound (
    message_id TEXT PRIMARY KEY,
    contact TEXT NOT NULL,
    title TEXT NOT NULL,
    content TEXT NOT NULL,
    state TEXT NOT NULL,
    reason TEXT,
    created REAL NOT NULL,
    updated REAL NOT NULL,
    attempts INTEGER NOT NULL DEFAULT 0,
    propagated INTEGER NOT NULL DEFAULT 0
);
CREATE TABLE IF NOT EXISTS idempotency (
    key TEXT PRIMARY KEY,
    message_id TEXT NOT NULL,
    created REAL NOT NULL
);
CREATE TABLE IF NOT EXISTS inbound (
    seq INTEGER PRIMARY KEY AUTOINCREMENT,
    message_id TEXT NOT NULL UNIQUE,
    source_key TEXT NOT NULL UNIQUE,
    contact TEXT NOT NULL,
    title TEXT,
    content TEXT,
    size INTEGER NOT NULL,
    received REAL NOT NULL,
    acked REAL
);
CREATE TABLE IF NOT EXISTS counters (name TEXT PRIMARY KEY, value INTEGER NOT NULL);
CREATE TABLE IF NOT EXISTS meta (name TEXT PRIMARY KEY, value REAL NOT NULL);
"""


class QueueFullError(Exception):
    """Too many messages are waiting to be sent."""


@dataclass(frozen=True)
class Outbound:
    message_id: str
    contact: str
    title: str
    content: str
    state: str
    reason: str | None
    created: float
    updated: float
    attempts: int
    propagated: bool


def new_message_id() -> str:
    """A random message ID: it says nothing about the sender, the recipient or the content."""
    return secrets.token_hex(16)


class Queue:
    def __init__(self, path: Path, *, retention_days: int = 0, clock: Callable[[], float] = time.time) -> None:
        self.path = path
        self.clock = clock
        self.retention = min(max(int(retention_days), 0), RETENTION_MAX_DAYS) * 86400.0
        self.quarantined: Path | None = None
        self.db = self._open()

    # -- opening, corruption and maintenance -------------------------------------------------
    def _connect(self) -> sqlite3.Connection:
        db = sqlite3.connect(str(self.path), isolation_level=None, check_same_thread=False)
        db.execute("PRAGMA journal_mode=WAL")
        db.execute("PRAGMA synchronous=NORMAL")
        db.execute("PRAGMA foreign_keys=ON")
        return db

    def _open(self) -> sqlite3.Connection:
        try:
            db = self._connect()
            if db.execute("PRAGMA quick_check").fetchone() != ("ok",):
                raise sqlite3.DatabaseError("integrity check failed")
            db.executescript(SCHEMA)
            return db
        except sqlite3.DatabaseError:
            with contextlib.suppress(Exception):
                db.close()
            return self._quarantine_and_restart()

    def _quarantine_and_restart(self) -> sqlite3.Connection:
        stamp = time.strftime("%Y%m%dT%H%M%SZ", time.gmtime(self.clock()))
        target = self.path.with_name(f"{self.path.name}.corrupt-{stamp}")
        for suffix in ("", "-wal", "-shm"):
            source = Path(str(self.path) + suffix)
            if source.exists():
                source.rename(Path(str(target) + suffix))
        self.quarantined = target
        db = self._connect()
        db.executescript(SCHEMA)
        return db

    def close(self) -> None:
        self.db.close()

    def _count(self, name: str, by: int = 1) -> None:
        self.db.execute(
            "INSERT INTO counters(name, value) VALUES (?, ?) ON CONFLICT(name) DO UPDATE SET value = value + ?",
            (name, by, by),
        )

    def counters(self) -> dict[str, int]:
        return dict(self.db.execute("SELECT name, value FROM counters").fetchall())

    def size(self) -> int:
        return sum(
            Path(str(self.path) + suffix).stat().st_size
            for suffix in ("", "-wal")
            if Path(str(self.path) + suffix).exists()
        )

    def maintenance(self) -> None:
        """Expiry, retention, the size cap and the weekly VACUUM. Cheap; call it now and then."""
        now = self.clock()
        with self.db:
            self.db.execute("BEGIN IMMEDIATE")
            expired = self.db.execute(
                "UPDATE outbound SET state = 'expired', reason = 'expired', content = '', title = '', updated = ? "
                "WHERE state IN ('queued', 'sending') AND created < ?",
                (now, now - EXPIRY),
            ).rowcount
            if expired:
                self._count("expired", expired)
            self.db.execute("DELETE FROM idempotency WHERE created < ?", (now - IDEMPOTENCY_TTL,))
            self.db.execute(
                "DELETE FROM outbound WHERE state NOT IN ('queued', 'sending') AND updated < ?",
                (now - EXPIRY,),
            )
            self.db.execute("DELETE FROM inbound WHERE acked IS NOT NULL AND acked < ?", (now - self.retention,))
            self.db.execute("COMMIT")
        last = self.db.execute("SELECT value FROM meta WHERE name = 'vacuum'").fetchone()
        if self.size() > FILE_MAX or last is None or now - last[0] > VACUUM_INTERVAL:
            self._shrink(now)

    def _shrink(self, now: float) -> None:
        if self.size() > FILE_MAX:  # keep only what matters: undelivered and unacknowledged
            with self.db:
                self.db.execute("DELETE FROM inbound WHERE acked IS NOT NULL")
                self.db.execute("DELETE FROM outbound WHERE state NOT IN ('queued', 'sending')")
        self.db.execute("VACUUM")
        self.db.execute("PRAGMA wal_checkpoint(TRUNCATE)")
        self.db.execute(
            "INSERT INTO meta(name, value) VALUES ('vacuum', ?) ON CONFLICT(name) DO UPDATE SET value = ?",
            (now, now),
        )

    # -- outbound ---------------------------------------------------------------------------
    def enqueue(self, contact: str, title: str, content: str, idempotency_key: str) -> tuple[str, bool]:
        """(message ID, created now). The same idempotency key within 24 h returns the same ID."""
        now = self.clock()
        with self.db:
            self.db.execute("BEGIN IMMEDIATE")
            known = self.db.execute(
                "SELECT message_id FROM idempotency WHERE key = ? AND created >= ?",
                (idempotency_key, now - IDEMPOTENCY_TTL),
            ).fetchone()
            if known is not None:
                self.db.execute("COMMIT")
                return known[0], False
            pending = self.db.execute("SELECT COUNT(*) FROM outbound WHERE state IN ('queued', 'sending')").fetchone()[
                0
            ]
            if pending >= PENDING_MAX:
                self.db.execute("ROLLBACK")
                raise QueueFullError
            message_id = new_message_id()
            self.db.execute(
                "INSERT INTO outbound(message_id, contact, title, content, state, created, updated) "
                "VALUES (?, ?, ?, ?, 'queued', ?, ?)",
                (message_id, contact, title, content, now, now),
            )
            self.db.execute(
                "INSERT OR REPLACE INTO idempotency(key, message_id, created) VALUES (?, ?, ?)",
                (idempotency_key, message_id, now),
            )
            self.db.execute("COMMIT")
        return message_id, True

    def _row(self, row: Any) -> Outbound:
        return Outbound(
            message_id=row[0],
            contact=row[1],
            title=row[2],
            content=row[3],
            state=row[4],
            reason=row[5],
            created=row[6],
            updated=row[7],
            attempts=row[8],
            propagated=bool(row[9]),
        )

    _COLUMNS = "message_id, contact, title, content, state, reason, created, updated, attempts, propagated"

    def get(self, message_id: str) -> Outbound | None:
        row = self.db.execute(f"SELECT {self._COLUMNS} FROM outbound WHERE message_id = ?", (message_id,)).fetchone()  # noqa: S608 - fixed columns
        return None if row is None else self._row(row)

    def pending(self) -> list[Outbound]:
        """Queued and sending messages, oldest first: resubmitted after a restart (ADR 0011)."""
        rows = self.db.execute(
            f"SELECT {self._COLUMNS} FROM outbound WHERE state IN ('queued', 'sending') ORDER BY created"  # noqa: S608
        ).fetchall()
        return [self._row(r) for r in rows]

    def set_state(
        self, message_id: str, state: str, reason: str | None = None, *, propagated: bool | None = None
    ) -> None:
        if state not in contract.STATES:
            raise ValueError("unknown state")
        now = self.clock()
        with self.db:
            current = self.db.execute("SELECT state FROM outbound WHERE message_id = ?", (message_id,)).fetchone()
            if current is None or current[0] in contract.FINAL_STATES:
                return  # final states never change (a late callback cannot undo "delivered")
            final = state in contract.FINAL_STATES
            self.db.execute(
                "UPDATE outbound SET state = ?, reason = ?, updated = ?, "
                "attempts = attempts + ?, propagated = COALESCE(?, propagated), "
                "content = CASE WHEN ? THEN '' ELSE content END, title = CASE WHEN ? THEN '' ELSE title END "
                "WHERE message_id = ?",
                (
                    state,
                    reason,
                    now,
                    1 if state == "sending" else 0,
                    None if propagated is None else int(propagated),
                    final,
                    final,
                    message_id,
                ),
            )
            if final:
                self._count(f"outbound_{state}")

    # -- inbound ----------------------------------------------------------------------------
    def receive(self, source_key: str, contact: str, title: str, content: str) -> str | None:
        """Store an inbound message. ``source_key`` (the LXMF message's own hash) de-duplicates it.

        Returns the new message ID, or None for a duplicate. When the store is full, the oldest
        unacknowledged message is dropped and counted (ADR 0011).
        """
        size = len(title.encode()) + len(content.encode())
        now = self.clock()
        with self.db:
            self.db.execute("BEGIN IMMEDIATE")
            if self.db.execute("SELECT 1 FROM inbound WHERE source_key = ?", (source_key,)).fetchone():
                self.db.execute("COMMIT")
                return None
            while True:
                count, total = self.db.execute(
                    "SELECT COUNT(*), COALESCE(SUM(size), 0) FROM inbound WHERE acked IS NULL"
                ).fetchone()
                if count < INBOUND_MAX and total + size <= INBOUND_BYTES_MAX:
                    break
                oldest = self.db.execute("SELECT seq FROM inbound WHERE acked IS NULL ORDER BY seq LIMIT 1").fetchone()
                if oldest is None:
                    break
                self.db.execute("DELETE FROM inbound WHERE seq = ?", oldest)
                self._count("inbound_dropped_full")
            message_id = new_message_id()
            self.db.execute(
                "INSERT INTO inbound(message_id, source_key, contact, title, content, size, received) "
                "VALUES (?, ?, ?, ?, ?, ?, ?)",
                (message_id, source_key, contact, title, content, size, now),
            )
            self._count("inbound_received")
            self.db.execute("COMMIT")
        return message_id

    def inbound_after(self, cursor: int, limit: int = 50) -> list[dict[str, Any]]:
        rows = self.db.execute(
            "SELECT seq, message_id, contact, title, content, received FROM inbound "
            "WHERE seq > ? AND acked IS NULL ORDER BY seq LIMIT ?",
            (cursor, limit),
        ).fetchall()
        return [
            {"cursor": r[0], "message_id": r[1], "contact": r[2], "title": r[3], "content": r[4], "received": r[5]}
            for r in rows
        ]

    def ack(self, cursor: int) -> int:
        """Acknowledge everything up to ``cursor``. Content is deleted at once unless retention is on."""
        now = self.clock()
        with self.db:
            if self.retention:
                done = self.db.execute(
                    "UPDATE inbound SET acked = ? WHERE seq <= ? AND acked IS NULL", (now, cursor)
                ).rowcount
            else:
                done = self.db.execute("DELETE FROM inbound WHERE seq <= ?", (cursor,)).rowcount
        return done

    def counts(self) -> dict[str, int]:
        pending = self.db.execute("SELECT COUNT(*) FROM outbound WHERE state IN ('queued', 'sending')").fetchone()[0]
        inbound = self.db.execute("SELECT COUNT(*) FROM inbound WHERE acked IS NULL").fetchone()[0]
        return {"outbound_pending": pending, "inbound_waiting": inbound}
