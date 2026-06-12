from __future__ import annotations

import sqlite3
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path


def utc_now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


@dataclass
class Reminder:
    id: int
    chat_id: int
    content: str
    due_at: str
    status: str
    poll_required: bool
    poll_id: str | None


class Database:
    def __init__(self, db_path: Path):
        db_path.parent.mkdir(parents=True, exist_ok=True)
        self.conn = sqlite3.connect(db_path, check_same_thread=False)
        self.conn.row_factory = sqlite3.Row

    def init(self) -> None:
        self.conn.executescript(
            """
            CREATE TABLE IF NOT EXISTS reminders (
              id INTEGER PRIMARY KEY AUTOINCREMENT,
              chat_id INTEGER NOT NULL,
              content TEXT NOT NULL,
              due_at TEXT NOT NULL,
              status TEXT NOT NULL DEFAULT 'pending',
              poll_required INTEGER NOT NULL DEFAULT 1,
              poll_id TEXT,
              created_at TEXT NOT NULL,
              completed_at TEXT
            );

            CREATE INDEX IF NOT EXISTS idx_reminders_due_status
              ON reminders(due_at, status);
            CREATE INDEX IF NOT EXISTS idx_reminders_poll
              ON reminders(poll_id);

            CREATE TABLE IF NOT EXISTS todos (
              id INTEGER PRIMARY KEY AUTOINCREMENT,
              chat_id INTEGER NOT NULL,
              task TEXT NOT NULL,
              category TEXT NOT NULL DEFAULT 'General',
              status TEXT NOT NULL DEFAULT 'to_do',
              done INTEGER NOT NULL DEFAULT 0,
              notion_page_id TEXT,
              created_at TEXT NOT NULL
            );

            CREATE TABLE IF NOT EXISTS birthdays (
              id INTEGER PRIMARY KEY AUTOINCREMENT,
              chat_id INTEGER NOT NULL,
              person_name TEXT NOT NULL,
              date_ymd TEXT NOT NULL,
              created_at TEXT NOT NULL
            );

            CREATE TABLE IF NOT EXISTS journal_entries (
              id INTEGER PRIMARY KEY AUTOINCREMENT,
              chat_id INTEGER NOT NULL,
              content TEXT NOT NULL,
              file_path TEXT,
              created_at TEXT NOT NULL
            );

            CREATE TABLE IF NOT EXISTS meta (
              key TEXT PRIMARY KEY,
              value TEXT NOT NULL
            );
            """
        )
        self._migrate()
        self.conn.commit()

    def _migrate(self) -> None:
        cols = {row["name"] for row in self.conn.execute("PRAGMA table_info(todos)").fetchall()}
        if "category" not in cols:
            self.conn.execute(
                "ALTER TABLE todos ADD COLUMN category TEXT NOT NULL DEFAULT 'General'"
            )
        if "status" not in cols:
            self.conn.execute(
                "ALTER TABLE todos ADD COLUMN status TEXT NOT NULL DEFAULT 'to_do'"
            )
            self.conn.execute("UPDATE todos SET status = 'done' WHERE done = 1")

    def add_reminder(self, chat_id: int, content: str, due_at_iso: str, poll_required: bool = True) -> int:
        cur = self.conn.execute(
            """
            INSERT INTO reminders(chat_id, content, due_at, status, poll_required, created_at)
            VALUES (?, ?, ?, 'pending', ?, ?)
            """,
            (chat_id, content, due_at_iso, 1 if poll_required else 0, utc_now_iso()),
        )
        self.conn.commit()
        return int(cur.lastrowid)

    def list_reminders(self, chat_id: int, limit: int = 20) -> list[Reminder]:
        rows = self.conn.execute(
            """
            SELECT id, chat_id, content, due_at, status, poll_required, poll_id
            FROM reminders
            WHERE chat_id = ?
            ORDER BY due_at ASC
            LIMIT ?
            """,
            (chat_id, limit),
        ).fetchall()
        return [
            Reminder(
                id=row["id"],
                chat_id=row["chat_id"],
                content=row["content"],
                due_at=row["due_at"],
                status=row["status"],
                poll_required=bool(row["poll_required"]),
                poll_id=row["poll_id"],
            )
            for row in rows
        ]

    def due_reminders(self, now_iso: str) -> list[Reminder]:
        rows = self.conn.execute(
            """
            SELECT id, chat_id, content, due_at, status, poll_required, poll_id
            FROM reminders
            WHERE due_at <= ?
              AND status = 'pending'
            ORDER BY due_at ASC
            """,
            (now_iso,),
        ).fetchall()
        return [
            Reminder(
                id=row["id"],
                chat_id=row["chat_id"],
                content=row["content"],
                due_at=row["due_at"],
                status=row["status"],
                poll_required=bool(row["poll_required"]),
                poll_id=row["poll_id"],
            )
            for row in rows
        ]

    def mark_reminder_notified(self, reminder_id: int) -> None:
        self.conn.execute("UPDATE reminders SET status = 'notified' WHERE id = ?", (reminder_id,))
        self.conn.commit()

    def mark_reminder_poll_sent(self, reminder_id: int, poll_id: str) -> None:
        self.conn.execute(
            "UPDATE reminders SET status = 'awaiting_poll', poll_id = ? WHERE id = ?",
            (poll_id, reminder_id),
        )
        self.conn.commit()

    def reminder_by_poll_id(self, poll_id: str) -> sqlite3.Row | None:
        return self.conn.execute(
            "SELECT * FROM reminders WHERE poll_id = ? LIMIT 1",
            (poll_id,),
        ).fetchone()

    def mark_reminder_completed(self, reminder_id: int) -> None:
        self.conn.execute(
            "UPDATE reminders SET status = 'completed', completed_at = ? WHERE id = ?",
            (utc_now_iso(), reminder_id),
        )
        self.conn.commit()

    def snooze_reminder(self, reminder_id: int, next_due_iso: str) -> None:
        self.conn.execute(
            "UPDATE reminders SET status = 'pending', due_at = ?, poll_id = NULL WHERE id = ?",
            (next_due_iso, reminder_id),
        )
        self.conn.commit()

    def add_todo(self, chat_id: int, task: str, category: str = "General", notion_page_id: str | None = None) -> int:
        cur = self.conn.execute(
            """
            INSERT INTO todos(chat_id, task, category, done, notion_page_id, created_at)
            VALUES (?, ?, ?, 0, ?, ?)
            """,
            (chat_id, task, category, notion_page_id, utc_now_iso()),
        )
        self.conn.commit()
        return int(cur.lastrowid)

    def list_todos(self, chat_id: int, include_done: bool = False) -> list[sqlite3.Row]:
        if include_done:
            query = "SELECT * FROM todos WHERE chat_id = ? ORDER BY id DESC LIMIT 50"
            args = (chat_id,)
        else:
            query = "SELECT * FROM todos WHERE chat_id = ? AND done = 0 ORDER BY id DESC LIMIT 50"
            args = (chat_id,)
        return self.conn.execute(query, args).fetchall()

    def set_todo_done(self, todo_id: int, done: bool = True) -> None:
        new_status = "done" if done else "to_do"
        self.conn.execute(
            "UPDATE todos SET done = ?, status = ? WHERE id = ?",
            (1 if done else 0, new_status, todo_id),
        )
        self.conn.commit()

    def set_todo_status(self, todo_id: int, status: str) -> None:
        if status not in ("to_do", "doing", "done"):
            raise ValueError(f"invalid todo status: {status!r}")
        done_flag = 1 if status == "done" else 0
        self.conn.execute(
            "UPDATE todos SET status = ?, done = ? WHERE id = ?",
            (status, done_flag, todo_id),
        )
        self.conn.commit()

    def add_birthday(self, chat_id: int, person_name: str, date_ymd: str) -> int:
        cur = self.conn.execute(
            """
            INSERT INTO birthdays(chat_id, person_name, date_ymd, created_at)
            VALUES (?, ?, ?, ?)
            """,
            (chat_id, person_name, date_ymd, utc_now_iso()),
        )
        self.conn.commit()
        return int(cur.lastrowid)

    def list_birthdays(self, chat_id: int) -> list[sqlite3.Row]:
        return self.conn.execute(
            "SELECT * FROM birthdays WHERE chat_id = ? ORDER BY date_ymd ASC",
            (chat_id,),
        ).fetchall()

    def birthdays_for_month_day(self, month_day: str) -> list[sqlite3.Row]:
        return self.conn.execute(
            """
            SELECT * FROM birthdays
            WHERE substr(date_ymd, 6, 5) = ?
            """,
            (month_day,),
        ).fetchall()

    def add_journal_entry(self, chat_id: int, content: str, file_path: str | None) -> int:
        cur = self.conn.execute(
            """
            INSERT INTO journal_entries(chat_id, content, file_path, created_at)
            VALUES (?, ?, ?, ?)
            """,
            (chat_id, content, file_path, utc_now_iso()),
        )
        self.conn.commit()
        return int(cur.lastrowid)

    def get_meta(self, key: str) -> str | None:
        row = self.conn.execute("SELECT value FROM meta WHERE key = ?", (key,)).fetchone()
        return row["value"] if row else None

    def set_meta(self, key: str, value: str) -> None:
        self.conn.execute(
            """
            INSERT INTO meta(key, value) VALUES (?, ?)
            ON CONFLICT(key) DO UPDATE SET value = excluded.value
            """,
            (key, value),
        )
        self.conn.commit()
