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

M5 (ADR 0024) adds two tables to the same file, so that one transaction covers a message and its
place in the conversation:

- ``contacts``: the **single authoritative contact store**. Contacts from the app's Configuration
  tab are imported at every start (by address; a contact the user removed from the dashboard is
  not imported again while it stays in the options); the dashboard adds, renames and removes them.
- ``history``: the conversation history shown in Home Assistant, both directions, in arrival order
  (``seq``). Inbound messages are de-duplicated by their LXMF hash for as long as they are kept.
  At most ``HISTORY_MAX`` messages and ``HISTORY_BYTES_MAX`` of text; the oldest go first.

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
HISTORY_MAX = 10_000
HISTORY_BYTES_MAX = 8 * 1024 * 1024
CONTACTS_MAX = 100
PREVIEW_CHARS = 120
RETRYABLE = ("failed", "rejected", "expired", "sent_unconfirmed")

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
CREATE TABLE IF NOT EXISTS contacts (
    id TEXT PRIMARY KEY,
    name TEXT NOT NULL,
    destination TEXT NOT NULL UNIQUE,
    origin TEXT NOT NULL,
    created REAL NOT NULL
);
CREATE TABLE IF NOT EXISTS removed_contacts (destination TEXT PRIMARY KEY, removed REAL NOT NULL);
CREATE TABLE IF NOT EXISTS history (
    seq INTEGER PRIMARY KEY AUTOINCREMENT,
    message_id TEXT NOT NULL UNIQUE,
    source_key TEXT UNIQUE,
    contact TEXT NOT NULL,
    direction TEXT NOT NULL,
    title TEXT NOT NULL,
    content TEXT NOT NULL,
    size INTEGER NOT NULL,
    at REAL NOT NULL,
    state TEXT,
    reason TEXT,
    auto INTEGER NOT NULL DEFAULT 0,
    unread INTEGER NOT NULL DEFAULT 0
);
CREATE INDEX IF NOT EXISTS history_contact ON history(contact, seq);
CREATE TABLE IF NOT EXISTS meta (name TEXT PRIMARY KEY, value REAL NOT NULL);
"""


class QueueFullError(Exception):
    """Too many messages are waiting to be sent."""


class ContactError(ValueError):
    """A contact change the store refuses. ``code`` is safe to return to the caller."""

    def __init__(self, code: str) -> None:
        super().__init__(code)
        self.code = code


@dataclass(frozen=True)
class StoredContact:
    id: str
    name: str
    destination: str  # hex
    origin: str  # "configuration" (imported from the app's options) or "dashboard"


def _slug(name: str) -> str:
    out = "".join(ch if ch.isascii() and (ch.isalnum() or ch in "_-") else "-" for ch in name.lower())
    return "-".join(p for p in out.split("-") if p)[:28].strip("_") or "contact"


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

    def count(self, name: str, by: int = 1) -> None:
        """Add to a persistent counter (refusals and other events the engine counts)."""
        self._count(name, by)

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
            self.db.execute(
                "UPDATE history SET state = 'expired', reason = 'expired' WHERE message_id IN "
                "(SELECT message_id FROM outbound WHERE state IN ('queued', 'sending') AND created < ?)",
                (now - EXPIRY,),
            )
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
            self._prune_history()
            self.db.execute("COMMIT")
        last = self.db.execute("SELECT value FROM meta WHERE name = 'vacuum'").fetchone()
        if self.size() > FILE_MAX or last is None or now - last[0] > VACUUM_INTERVAL:
            self._shrink(now)

    def _shrink(self, now: float) -> None:
        if self.size() > FILE_MAX:  # keep only what matters: undelivered, unacknowledged, recent history
            with self.db:
                self.db.execute("DELETE FROM inbound WHERE acked IS NOT NULL")
                self.db.execute("DELETE FROM outbound WHERE state NOT IN ('queued', 'sending')")
                self.db.execute(
                    "DELETE FROM history WHERE seq <= (SELECT seq FROM history ORDER BY seq DESC LIMIT 1 OFFSET ?)",
                    (HISTORY_MAX // 2,),
                )
        self.db.execute("VACUUM")
        self.db.execute("PRAGMA wal_checkpoint(TRUNCATE)")
        self.db.execute(
            "INSERT INTO meta(name, value) VALUES ('vacuum', ?) ON CONFLICT(name) DO UPDATE SET value = ?",
            (now, now),
        )

    # -- outbound ---------------------------------------------------------------------------
    def enqueue(
        self, contact: str, title: str, content: str, idempotency_key: str, *, auto: bool = False
    ) -> tuple[str, bool]:
        """(message ID, created now). The same idempotency key within 24 h returns the same ID.

        The message also takes its place in the contact's conversation (``auto``: an automatic
        reply, shown as such)."""
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
            self.db.execute(
                "INSERT INTO history(message_id, contact, direction, title, content, size, at, state, auto) "
                "VALUES (?, ?, 'out', ?, ?, ?, ?, 'queued', ?)",
                (message_id, contact, title, content, len(title.encode()) + len(content.encode()), now, int(auto)),
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
            self.db.execute(
                "UPDATE history SET state = ?, reason = ? WHERE message_id = ?", (state, reason, message_id)
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
            if self.db.execute("SELECT 1 FROM inbound WHERE source_key = ?", (source_key,)).fetchone() or (
                self.db.execute("SELECT 1 FROM history WHERE source_key = ?", (source_key,)).fetchone()
            ):
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
            self.db.execute(
                "INSERT INTO history(message_id, source_key, contact, direction, title, content, size, at, unread) "
                "VALUES (?, ?, ?, 'in', ?, ?, ?, ?, 1)",
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

    # -- conversation history (M5, ADR 0024) -------------------------------------------------
    def _prune_history(self) -> None:
        """Keep at most HISTORY_MAX messages and HISTORY_BYTES_MAX of text; the oldest go first.
        Messages still waiting to be sent are never pruned."""
        count, total = self.db.execute("SELECT COUNT(*), COALESCE(SUM(size), 0) FROM history").fetchone()
        while count > HISTORY_MAX or total > HISTORY_BYTES_MAX:
            row = self.db.execute(
                "SELECT seq, size FROM history WHERE state IS NULL OR state NOT IN ('queued', 'sending') "
                "ORDER BY seq LIMIT 1"
            ).fetchone()
            if row is None:
                return
            self.db.execute("DELETE FROM history WHERE seq = ?", (row[0],))
            self._count("history_pruned")
            count, total = count - 1, total - row[1]

    @staticmethod
    def _message(row: Any) -> dict[str, Any]:
        return {
            "seq": row[0],
            "message_id": row[1],
            "direction": row[2],
            "title": row[3],
            "text": row[4],
            "at": row[5],
            "state": row[6],
            "reason": row[7],
            "auto": bool(row[8]),
            "unread": bool(row[9]),
        }

    _HISTORY = "seq, message_id, direction, title, content, at, state, reason, auto, unread"

    def history(self, contact: str, before: int | None = None, limit: int = 50) -> list[dict[str, Any]]:
        """The newest ``limit`` messages of a conversation (older than ``before``), oldest first."""
        rows = self.db.execute(
            f"SELECT {self._HISTORY} FROM history WHERE contact = ? AND seq < ? ORDER BY seq DESC LIMIT ?",  # noqa: S608
            (contact, before if before is not None else 2**62, limit),
        ).fetchall()
        return [self._message(r) for r in reversed(rows)]

    def conversations(self) -> dict[str, dict[str, Any]]:
        """Per contact ID: the unread count and the newest message (text cut to a preview)."""
        out: dict[str, dict[str, Any]] = {}
        for contact, unread in self.db.execute("SELECT contact, SUM(unread) FROM history GROUP BY contact"):
            row = self.db.execute(
                f"SELECT {self._HISTORY} FROM history WHERE contact = ? ORDER BY seq DESC LIMIT 1",  # noqa: S608
                (contact,),
            ).fetchone()
            last = self._message(row)
            last["text"] = last["text"][:PREVIEW_CHARS]
            out[contact] = {"unread": int(unread or 0), "last": last}
        return out

    def mark_read(self, contact: str) -> int:
        with self.db:
            sql = "UPDATE history SET unread = 0 WHERE contact = ? AND unread = 1"
            return self.db.execute(sql, (contact,)).rowcount

    def clear_history(self, contact: str) -> int:
        """Delete a conversation. Messages still waiting to be sent are kept (and still sent)."""
        with self.db:
            return self.db.execute(
                "DELETE FROM history WHERE contact = ? AND (state IS NULL OR state NOT IN ('queued', 'sending'))",
                (contact,),
            ).rowcount

    def history_entry(self, message_id: str) -> dict[str, Any] | None:
        row = self.db.execute(
            f"SELECT {self._HISTORY}, contact FROM history WHERE message_id = ?",  # noqa: S608
            (message_id,),
        ).fetchone()
        if row is None:
            return None
        return {**self._message(row), "contact": row[10]}

    def requeue(self, message_id: str) -> str:
        """A new outbound message with the text of a final, undelivered one, in its place in the
        conversation (its history row takes the new ID). Returns the new ID."""
        now = self.clock()
        with self.db:
            self.db.execute("BEGIN IMMEDIATE")
            row = self.db.execute(
                "SELECT contact, title, content, state FROM history WHERE message_id = ? AND direction = 'out'",
                (message_id,),
            ).fetchone()
            if row is None or row[3] not in RETRYABLE:
                self.db.execute("ROLLBACK")
                raise ContactError("not_retryable")
            pending = self.db.execute("SELECT COUNT(*) FROM outbound WHERE state IN ('queued', 'sending')").fetchone()[
                0
            ]
            if pending >= PENDING_MAX:
                self.db.execute("ROLLBACK")
                raise QueueFullError
            new_id = new_message_id()
            self.db.execute(
                "INSERT INTO outbound(message_id, contact, title, content, state, created, updated) "
                "VALUES (?, ?, ?, ?, 'queued', ?, ?)",
                (new_id, row[0], row[1], row[2], now, now),
            )
            self.db.execute(
                "UPDATE history SET message_id = ?, state = 'queued', reason = NULL, at = ? WHERE message_id = ?",
                (new_id, now, message_id),
            )
            self.db.execute("COMMIT")
        return new_id

    # -- contacts (M5: the single authoritative store) ----------------------------------------
    def contacts(self) -> list[StoredContact]:
        rows = self.db.execute("SELECT id, name, destination, origin FROM contacts ORDER BY created, id").fetchall()
        return [StoredContact(*r) for r in rows]

    def _free_id(self, wanted: str) -> str:
        taken = {r[0] for r in self.db.execute("SELECT id FROM contacts")}
        # An ID still used by a conversation is never given to someone else.
        taken |= {r[0] for r in self.db.execute("SELECT DISTINCT contact FROM history")}
        base = wanted if contract.CONTACT_ID.match(wanted) else "contact"
        candidate, n = base, 2
        while candidate in taken or candidate == "unknown":
            candidate, n = f"{base[:28]}-{n}", n + 1
        return candidate

    def add_contact(self, name: str, destination: str, *, origin: str = "dashboard", wanted_id: str = "") -> str:
        now = self.clock()
        with self.db:
            self.db.execute("BEGIN IMMEDIATE")
            if self.db.execute("SELECT 1 FROM contacts WHERE destination = ?", (destination,)).fetchone():
                self.db.execute("ROLLBACK")
                raise ContactError("contact_exists")
            if self.db.execute("SELECT COUNT(*) FROM contacts").fetchone()[0] >= CONTACTS_MAX:
                self.db.execute("ROLLBACK")
                raise ContactError("too_many_contacts")
            contact_id = self._free_id(wanted_id or _slug(name))
            self.db.execute(
                "INSERT INTO contacts(id, name, destination, origin, created) VALUES (?, ?, ?, ?, ?)",
                (contact_id, name, destination, origin, now),
            )
            self.db.execute("DELETE FROM removed_contacts WHERE destination = ?", (destination,))
            self.db.execute("COMMIT")
        return contact_id

    def rename_contact(self, contact_id: str, name: str) -> None:
        with self.db:
            if not self.db.execute("UPDATE contacts SET name = ? WHERE id = ?", (name, contact_id)).rowcount:
                raise ContactError("unknown_contact")

    def remove_contact(self, contact_id: str, *, remember: bool) -> None:
        """Remove a contact, its conversation and anything still waiting to be sent to it.
        ``remember``: the address is still in the app's options, so do not import it again."""
        now = self.clock()
        with self.db:
            self.db.execute("BEGIN IMMEDIATE")
            row = self.db.execute("SELECT destination FROM contacts WHERE id = ?", (contact_id,)).fetchone()
            if row is None:
                self.db.execute("ROLLBACK")
                raise ContactError("unknown_contact")
            self.db.execute("DELETE FROM contacts WHERE id = ?", (contact_id,))
            self.db.execute("DELETE FROM history WHERE contact = ?", (contact_id,))
            self.db.execute(
                "UPDATE outbound SET state = 'failed', reason = 'unknown_contact', content = '', title = '', "
                "updated = ? WHERE contact = ? AND state IN ('queued', 'sending')",
                (now, contact_id),
            )
            if remember:
                self.db.execute(
                    "INSERT OR REPLACE INTO removed_contacts(destination, removed) VALUES (?, ?)", (row[0], now)
                )
            self.db.execute("COMMIT")

    def import_contacts(self, configured: list[tuple[str, str, str]]) -> None:
        """Contacts from the app's Configuration tab, as (wanted ID, name, destination).

        Added when their address is new; a contact the user removed from the dashboard stays
        removed while it is still listed in the options. An existing contact keeps its name (a
        rename in the dashboard wins). Nothing configured is ever deleted here."""
        listed = {dest for _, _, dest in configured}
        with self.db:
            # A removal is remembered only while the address is still in the options.
            for (dest,) in self.db.execute("SELECT destination FROM removed_contacts").fetchall():
                if dest not in listed:
                    self.db.execute("DELETE FROM removed_contacts WHERE destination = ?", (dest,))
        for wanted, name, dest in configured:
            if self.db.execute("SELECT 1 FROM removed_contacts WHERE destination = ?", (dest,)).fetchone():
                continue
            with contextlib.suppress(ContactError):
                self.add_contact(name, dest, origin="configuration", wanted_id=wanted)
