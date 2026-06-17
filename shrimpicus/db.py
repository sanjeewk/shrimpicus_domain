from __future__ import annotations

import sqlite3
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

# Try to import psycopg2, fall back to None if not available
try:
    import psycopg2
    import psycopg2.extras
    HAS_POSTGRES = True
except ImportError:
    HAS_POSTGRES = False


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
    def __init__(self, db_path: Path | None = None, database_url: str | None = None):
        """Initialize database connection.

        Args:
            db_path: Path to SQLite database file (used if database_url is not set)
            database_url: PostgreSQL connection string (takes precedence over db_path)
        """
        self.is_postgres = False
        self.conn = None

        if database_url and database_url.startswith('postgresql://'):
            if not HAS_POSTGRES:
                raise RuntimeError(
                    "PostgreSQL support requires psycopg2-binary. "
                    "Install with: pip install psycopg2-binary"
                )
            self.is_postgres = True
            self.conn = psycopg2.connect(database_url)
            self.conn.autocommit = False
            # Use RealDictRow for psycopg2 to match sqlite3.Row behavior
            import psycopg2.extras
            self.cursor_factory = psycopg2.extras.RealDictCursor
        else:
            # Fall back to SQLite
            if db_path is None:
                raise ValueError("Either db_path or database_url must be provided")
            db_path.parent.mkdir(parents=True, exist_ok=True)
            self.conn = sqlite3.connect(db_path, check_same_thread=False)
            self.conn.row_factory = sqlite3.Row
            self.cursor_factory = None

    def _get_cursor(self):
        """Get a cursor with the appropriate factory."""
        if self.is_postgres:
            return self.conn.cursor(cursor_factory=self.cursor_factory)
        return self.conn.cursor()

    def _param(self, query: str) -> str:
        """Convert SQLite placeholders (?) to PostgreSQL (%s) if needed."""
        if self.is_postgres:
            return query.replace('?', '%s')
        return query

    def init(self) -> None:
        """Initialize database schema. Handles both SQLite and PostgreSQL."""
        if self.is_postgres:
            self._init_postgres()
        else:
            self._init_sqlite()
        self._migrate()
        self.conn.commit()

    def _init_sqlite(self) -> None:
        """Initialize SQLite schema."""
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
              user_id INTEGER,
              task TEXT NOT NULL,
              category TEXT NOT NULL DEFAULT 'General',
              status TEXT NOT NULL DEFAULT 'to_do',
              done INTEGER NOT NULL DEFAULT 0,
              notion_page_id TEXT,
              created_at TEXT NOT NULL,
              FOREIGN KEY(user_id) REFERENCES users(id) ON DELETE CASCADE
            );

            CREATE INDEX IF NOT EXISTS idx_todos_user ON todos(user_id);

            CREATE TABLE IF NOT EXISTS birthdays (
              id INTEGER PRIMARY KEY AUTOINCREMENT,
              chat_id INTEGER NOT NULL,
              user_id INTEGER,
              person_name TEXT NOT NULL,
              date_ymd TEXT NOT NULL,
              created_at TEXT NOT NULL,
              FOREIGN KEY(user_id) REFERENCES users(id) ON DELETE CASCADE
            );

            CREATE TABLE IF NOT EXISTS journal_entries (
              id INTEGER PRIMARY KEY AUTOINCREMENT,
              chat_id INTEGER NOT NULL,
              user_id INTEGER,
              content TEXT NOT NULL,
              file_path TEXT,
              created_at TEXT NOT NULL,
              FOREIGN KEY(user_id) REFERENCES users(id) ON DELETE CASCADE
            );

            CREATE TABLE IF NOT EXISTS habits (
              id INTEGER PRIMARY KEY AUTOINCREMENT,
              chat_id INTEGER NOT NULL,
              user_id INTEGER,
              name TEXT NOT NULL,
              weekly_goal INTEGER NOT NULL DEFAULT 7,
              created_at TEXT NOT NULL,
              FOREIGN KEY(user_id) REFERENCES users(id) ON DELETE CASCADE
            );

            CREATE INDEX IF NOT EXISTS idx_habits_user ON habits(user_id);

            CREATE TABLE IF NOT EXISTS habit_completions (
              id INTEGER PRIMARY KEY AUTOINCREMENT,
              habit_id INTEGER NOT NULL,
              date_ymd TEXT NOT NULL,
              created_at TEXT NOT NULL,
              UNIQUE(habit_id, date_ymd),
              FOREIGN KEY(habit_id) REFERENCES habits(id) ON DELETE CASCADE
            );

            CREATE INDEX IF NOT EXISTS idx_habit_completions
              ON habit_completions(habit_id, date_ymd);

            CREATE TABLE IF NOT EXISTS meta (
              key TEXT PRIMARY KEY,
              value TEXT NOT NULL
            );

            CREATE TABLE IF NOT EXISTS users (
              id INTEGER PRIMARY KEY AUTOINCREMENT,
              username TEXT NOT NULL UNIQUE COLLATE NOCASE,
              password_hash TEXT NOT NULL,
              created_at TEXT NOT NULL
            );

            CREATE INDEX IF NOT EXISTS idx_users_username
              ON users(username COLLATE NOCASE);

            CREATE TABLE IF NOT EXISTS groups (
              id INTEGER PRIMARY KEY AUTOINCREMENT,
              name TEXT NOT NULL,
              created_by_user_id INTEGER NOT NULL,
              created_at TEXT NOT NULL,
              FOREIGN KEY(created_by_user_id) REFERENCES users(id) ON DELETE CASCADE
            );

            CREATE TABLE IF NOT EXISTS group_members (
              id INTEGER PRIMARY KEY AUTOINCREMENT,
              group_id INTEGER NOT NULL,
              user_id INTEGER NOT NULL,
              joined_at TEXT NOT NULL,
              UNIQUE(group_id, user_id),
              FOREIGN KEY(group_id) REFERENCES groups(id) ON DELETE CASCADE,
              FOREIGN KEY(user_id) REFERENCES users(id) ON DELETE CASCADE
            );

            CREATE INDEX IF NOT EXISTS idx_group_members_group
              ON group_members(group_id);
            CREATE INDEX IF NOT EXISTS idx_group_members_user
              ON group_members(user_id);

            CREATE TABLE IF NOT EXISTS friendships (
              id INTEGER PRIMARY KEY AUTOINCREMENT,
              user_id INTEGER NOT NULL,
              friend_id INTEGER NOT NULL,
              created_at TEXT NOT NULL,
              UNIQUE(user_id, friend_id),
              FOREIGN KEY(user_id) REFERENCES users(id) ON DELETE CASCADE,
              FOREIGN KEY(friend_id) REFERENCES users(id) ON DELETE CASCADE
            );

            CREATE INDEX IF NOT EXISTS idx_friendships_user
              ON friendships(user_id);
            CREATE INDEX IF NOT EXISTS idx_friendships_friend
              ON friendships(friend_id);
            """
        )

    def _init_postgres(self) -> None:
        """Initialize PostgreSQL schema."""
        cur = self._get_cursor()

        # PostgreSQL uses SERIAL instead of AUTOINCREMENT, and different syntax
        cur.execute("""
            CREATE TABLE IF NOT EXISTS reminders (
              id SERIAL PRIMARY KEY,
              chat_id INTEGER NOT NULL,
              content TEXT NOT NULL,
              due_at TEXT NOT NULL,
              status TEXT NOT NULL DEFAULT 'pending',
              poll_required INTEGER NOT NULL DEFAULT 1,
              poll_id TEXT,
              created_at TEXT NOT NULL,
              completed_at TEXT,
              user_id INTEGER DEFAULT 1
            );
        """)

        cur.execute("""
            CREATE INDEX IF NOT EXISTS idx_reminders_due_status
              ON reminders(due_at, status);
        """)
        cur.execute("""
            CREATE INDEX IF NOT EXISTS idx_reminders_poll
              ON reminders(poll_id);
        """)

        cur.execute("""
            CREATE TABLE IF NOT EXISTS users (
              id SERIAL PRIMARY KEY,
              username TEXT NOT NULL UNIQUE,
              password_hash TEXT NOT NULL,
              created_at TEXT NOT NULL
            );
        """)

        cur.execute("""
            CREATE INDEX IF NOT EXISTS idx_users_username
              ON users(LOWER(username));
        """)

        cur.execute("""
            CREATE TABLE IF NOT EXISTS todos (
              id SERIAL PRIMARY KEY,
              chat_id INTEGER NOT NULL,
              user_id INTEGER,
              task TEXT NOT NULL,
              category TEXT NOT NULL DEFAULT 'General',
              status TEXT NOT NULL DEFAULT 'to_do',
              done INTEGER NOT NULL DEFAULT 0,
              notion_page_id TEXT,
              created_at TEXT NOT NULL,
              FOREIGN KEY(user_id) REFERENCES users(id) ON DELETE CASCADE
            );
        """)

        cur.execute("""
            CREATE INDEX IF NOT EXISTS idx_todos_user ON todos(user_id);
        """)

        cur.execute("""
            CREATE TABLE IF NOT EXISTS birthdays (
              id SERIAL PRIMARY KEY,
              chat_id INTEGER NOT NULL,
              user_id INTEGER,
              person_name TEXT NOT NULL,
              date_ymd TEXT NOT NULL,
              created_at TEXT NOT NULL,
              FOREIGN KEY(user_id) REFERENCES users(id) ON DELETE CASCADE
            );
        """)

        cur.execute("""
            CREATE TABLE IF NOT EXISTS journal_entries (
              id SERIAL PRIMARY KEY,
              chat_id INTEGER NOT NULL,
              user_id INTEGER,
              content TEXT NOT NULL,
              file_path TEXT,
              created_at TEXT NOT NULL,
              FOREIGN KEY(user_id) REFERENCES users(id) ON DELETE CASCADE
            );
        """)

        cur.execute("""
            CREATE TABLE IF NOT EXISTS habits (
              id SERIAL PRIMARY KEY,
              chat_id INTEGER NOT NULL,
              user_id INTEGER,
              name TEXT NOT NULL,
              weekly_goal INTEGER NOT NULL DEFAULT 7,
              created_at TEXT NOT NULL,
              FOREIGN KEY(user_id) REFERENCES users(id) ON DELETE CASCADE
            );
        """)

        cur.execute("""
            CREATE INDEX IF NOT EXISTS idx_habits_user ON habits(user_id);
        """)

        cur.execute("""
            CREATE TABLE IF NOT EXISTS habit_completions (
              id SERIAL PRIMARY KEY,
              habit_id INTEGER NOT NULL,
              date_ymd TEXT NOT NULL,
              created_at TEXT NOT NULL,
              UNIQUE(habit_id, date_ymd),
              FOREIGN KEY(habit_id) REFERENCES habits(id) ON DELETE CASCADE
            );
        """)

        cur.execute("""
            CREATE INDEX IF NOT EXISTS idx_habit_completions
              ON habit_completions(habit_id, date_ymd);
        """)

        cur.execute("""
            CREATE TABLE IF NOT EXISTS meta (
              key TEXT PRIMARY KEY,
              value TEXT NOT NULL
            );
        """)

        cur.execute("""
            CREATE TABLE IF NOT EXISTS groups (
              id SERIAL PRIMARY KEY,
              name TEXT NOT NULL,
              created_by_user_id INTEGER NOT NULL,
              created_at TEXT NOT NULL,
              FOREIGN KEY(created_by_user_id) REFERENCES users(id) ON DELETE CASCADE
            );
        """)

        cur.execute("""
            CREATE TABLE IF NOT EXISTS group_members (
              id SERIAL PRIMARY KEY,
              group_id INTEGER NOT NULL,
              user_id INTEGER NOT NULL,
              joined_at TEXT NOT NULL,
              UNIQUE(group_id, user_id),
              FOREIGN KEY(group_id) REFERENCES groups(id) ON DELETE CASCADE,
              FOREIGN KEY(user_id) REFERENCES users(id) ON DELETE CASCADE
            );
        """)

        cur.execute("""
            CREATE INDEX IF NOT EXISTS idx_group_members_group
              ON group_members(group_id);
        """)
        cur.execute("""
            CREATE INDEX IF NOT EXISTS idx_group_members_user
              ON group_members(user_id);
        """)

        cur.execute("""
            CREATE TABLE IF NOT EXISTS friendships (
              id SERIAL PRIMARY KEY,
              user_id INTEGER NOT NULL,
              friend_id INTEGER NOT NULL,
              created_at TEXT NOT NULL,
              UNIQUE(user_id, friend_id),
              FOREIGN KEY(user_id) REFERENCES users(id) ON DELETE CASCADE,
              FOREIGN KEY(friend_id) REFERENCES users(id) ON DELETE CASCADE
            );
        """)

        cur.execute("""
            CREATE INDEX IF NOT EXISTS idx_friendships_user
              ON friendships(user_id);
        """)
        cur.execute("""
            CREATE INDEX IF NOT EXISTS idx_friendships_friend
              ON friendships(friend_id);
        """)

        cur.close()

    def _migrate(self) -> None:
        """Run migrations for SQLite only. PostgreSQL schema is created with all columns."""
        if self.is_postgres:
            return  # PostgreSQL schema is already complete

        # Todos migration
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
        if "user_id" not in cols:
            self.conn.execute("ALTER TABLE todos ADD COLUMN user_id INTEGER DEFAULT 1")

        # Reminders migration
        reminder_cols = {row["name"] for row in self.conn.execute("PRAGMA table_info(reminders)").fetchall()}
        if "user_id" not in reminder_cols:
            self.conn.execute("ALTER TABLE reminders ADD COLUMN user_id INTEGER DEFAULT 1")

        # Habits migration
        habit_cols = {row["name"] for row in self.conn.execute("PRAGMA table_info(habits)").fetchall()}
        if "user_id" not in habit_cols:
            self.conn.execute("ALTER TABLE habits ADD COLUMN user_id INTEGER DEFAULT 1")
        if "weekly_goal" not in habit_cols:
            self.conn.execute("ALTER TABLE habits ADD COLUMN weekly_goal INTEGER NOT NULL DEFAULT 7")

        # Birthdays migration
        birthday_cols = {row["name"] for row in self.conn.execute("PRAGMA table_info(birthdays)").fetchall()}
        if "user_id" not in birthday_cols:
            self.conn.execute("ALTER TABLE birthdays ADD COLUMN user_id INTEGER DEFAULT 1")

        # Journal entries migration
        journal_cols = {row["name"] for row in self.conn.execute("PRAGMA table_info(journal_entries)").fetchall()}
        if "user_id" not in journal_cols:
            self.conn.execute("ALTER TABLE journal_entries ADD COLUMN user_id INTEGER DEFAULT 1")

    def add_reminder(self, chat_id: int, content: str, due_at_iso: str, poll_required: bool = True) -> int:
        cur = self._get_cursor()
        query = self._param("""
            INSERT INTO reminders(chat_id, content, due_at, status, poll_required, created_at, user_id)
            VALUES (?, ?, ?, 'pending', ?, ?, ?)
        """)
        cur.execute(query, (chat_id, content, due_at_iso, 1 if poll_required else 0, utc_now_iso(), chat_id))
        self.conn.commit()

        if self.is_postgres:
            # PostgreSQL requires RETURNING to get the ID
            cur.execute("SELECT lastval()")
            row_id = cur.fetchone()[0]
            cur.close()
            return int(row_id)
        else:
            row_id = cur.lastrowid
            cur.close()
            return int(row_id)

    def list_reminders(self, chat_id: int, limit: int = 20) -> list[Reminder]:
        cur = self._get_cursor()
        query = self._param("""
            SELECT id, chat_id, content, due_at, status, poll_required, poll_id
            FROM reminders
            WHERE chat_id = ?
            ORDER BY due_at ASC
            LIMIT ?
        """)
        rows = cur.execute(query, (chat_id, limit)).fetchall()
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
            INSERT INTO todos(chat_id, task, category, done, notion_page_id, created_at, user_id)
            VALUES (?, ?, ?, 0, ?, ?, ?)
            """,
            (chat_id, task, category, notion_page_id, utc_now_iso(), chat_id),
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
            INSERT INTO birthdays(chat_id, person_name, date_ymd, created_at, user_id)
            VALUES (?, ?, ?, ?, ?)
            """,
            (chat_id, person_name, date_ymd, utc_now_iso(), chat_id),
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

    def add_habit(self, chat_id: int, name: str, weekly_goal: int = 7) -> int:
        cur = self.conn.execute(
            "INSERT INTO habits(chat_id, name, weekly_goal, created_at, user_id) VALUES (?, ?, ?, ?, ?)",
            (chat_id, name, weekly_goal, utc_now_iso(), chat_id),
        )
        self.conn.commit()
        return int(cur.lastrowid)

    def list_habits(self, chat_id: int) -> list[sqlite3.Row]:
        return self.conn.execute(
            "SELECT * FROM habits WHERE chat_id = ? ORDER BY id ASC",
            (chat_id,),
        ).fetchall()

    def delete_habit(self, habit_id: int) -> None:
        self.conn.execute("DELETE FROM habit_completions WHERE habit_id = ?", (habit_id,))
        self.conn.execute("DELETE FROM habits WHERE id = ?", (habit_id,))
        self.conn.commit()

    def toggle_habit_completion(self, habit_id: int, date_ymd: str) -> bool:
        """Toggle a habit's completion for a date. Returns True if now completed."""
        existing = self.conn.execute(
            "SELECT id FROM habit_completions WHERE habit_id = ? AND date_ymd = ?",
            (habit_id, date_ymd),
        ).fetchone()
        if existing:
            self.conn.execute("DELETE FROM habit_completions WHERE id = ?", (existing["id"],))
            self.conn.commit()
            return False
        self.conn.execute(
            "INSERT INTO habit_completions(habit_id, date_ymd, created_at) VALUES (?, ?, ?)",
            (habit_id, date_ymd, utc_now_iso()),
        )
        self.conn.commit()
        return True

    def habit_completion_dates(self, habit_id: int) -> list[str]:
        rows = self.conn.execute(
            "SELECT date_ymd FROM habit_completions WHERE habit_id = ? ORDER BY date_ymd ASC",
            (habit_id,),
        ).fetchall()
        return [r["date_ymd"] for r in rows]

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

    # --- read helpers used for RAG context and stats ------------------------ #
    def find_habit(self, chat_id: int, name_or_id: str) -> sqlite3.Row | None:
        """Resolve a habit by numeric id or (case-insensitive) name for a chat."""
        text = str(name_or_id).strip()
        if text.lstrip("#").isdigit():
            return self.conn.execute(
                "SELECT * FROM habits WHERE chat_id = ? AND id = ? LIMIT 1",
                (chat_id, int(text.lstrip("#"))),
            ).fetchone()
        return self.conn.execute(
            "SELECT * FROM habits WHERE chat_id = ? AND lower(name) = lower(?) LIMIT 1",
            (chat_id, text),
        ).fetchone()

    def completed_todo_count(self, chat_id: int) -> int:
        row = self.conn.execute(
            "SELECT COUNT(*) AS n FROM todos WHERE chat_id = ? AND done = 1",
            (chat_id,),
        ).fetchone()
        return int(row["n"]) if row else 0

    # --- user management ---------------------------------------------------- #
    def create_user(self, username: str, password_hash: str) -> int:
        """Create a new user. Username is stored lowercase for case-insensitive uniqueness."""
        cur = self.conn.execute(
            "INSERT INTO users(username, password_hash, created_at) VALUES (?, ?, ?)",
            (username.lower(), password_hash, utc_now_iso()),
        )
        self.conn.commit()
        return int(cur.lastrowid)

    def get_user_by_username(self, username: str) -> sqlite3.Row | None:
        return self.conn.execute(
            "SELECT * FROM users WHERE username = ? COLLATE NOCASE LIMIT 1",
            (username,),
        ).fetchone()

    def get_user_by_id(self, user_id: int) -> sqlite3.Row | None:
        return self.conn.execute(
            "SELECT * FROM users WHERE id = ? LIMIT 1",
            (user_id,),
        ).fetchone()

    # --- friendship management ---------------------------------------------- #
    def add_friend(self, user_id: int, friend_id: int) -> None:
        """Add bidirectional friendship."""
        try:
            self.conn.execute(
                "INSERT INTO friendships(user_id, friend_id, created_at) VALUES (?, ?, ?)",
                (user_id, friend_id, utc_now_iso()),
            )
            self.conn.execute(
                "INSERT INTO friendships(user_id, friend_id, created_at) VALUES (?, ?, ?)",
                (friend_id, user_id, utc_now_iso()),
            )
            self.conn.commit()
        except sqlite3.IntegrityError:
            pass  # already friends

    def list_friends(self, user_id: int) -> list[sqlite3.Row]:
        return self.conn.execute(
            """
            SELECT u.* FROM users u
            JOIN friendships f ON f.friend_id = u.id
            WHERE f.user_id = ?
            ORDER BY u.username
            """,
            (user_id,),
        ).fetchall()

    def remove_friend(self, user_id: int, friend_id: int) -> None:
        self.conn.execute("DELETE FROM friendships WHERE user_id = ? AND friend_id = ?", (user_id, friend_id))
        self.conn.execute("DELETE FROM friendships WHERE user_id = ? AND friend_id = ?", (friend_id, user_id))
        self.conn.commit()

    # --- group management --------------------------------------------------- #
    def create_group(self, name: str, created_by_user_id: int) -> int:
        cur = self.conn.execute(
            "INSERT INTO groups(name, created_by_user_id, created_at) VALUES (?, ?, ?)",
            (name, created_by_user_id, utc_now_iso()),
        )
        # Auto-add creator to the group
        group_id = int(cur.lastrowid)
        self.conn.execute(
            "INSERT INTO group_members(group_id, user_id, joined_at) VALUES (?, ?, ?)",
            (group_id, created_by_user_id, utc_now_iso()),
        )
        self.conn.commit()
        return group_id

    def add_group_member(self, group_id: int, user_id: int) -> bool:
        """Add a user to a group. Returns False if group is full (10 members)."""
        count = self.conn.execute(
            "SELECT COUNT(*) AS n FROM group_members WHERE group_id = ?",
            (group_id,),
        ).fetchone()["n"]
        if count >= 10:
            return False
        try:
            self.conn.execute(
                "INSERT INTO group_members(group_id, user_id, joined_at) VALUES (?, ?, ?)",
                (group_id, user_id, utc_now_iso()),
            )
            self.conn.commit()
            return True
        except sqlite3.IntegrityError:
            return False  # already a member

    def list_user_groups(self, user_id: int) -> list[sqlite3.Row]:
        return self.conn.execute(
            """
            SELECT g.* FROM groups g
            JOIN group_members gm ON gm.group_id = g.id
            WHERE gm.user_id = ?
            ORDER BY g.created_at DESC
            """,
            (user_id,),
        ).fetchall()

    def list_group_members(self, group_id: int) -> list[sqlite3.Row]:
        return self.conn.execute(
            """
            SELECT u.* FROM users u
            JOIN group_members gm ON gm.user_id = u.id
            WHERE gm.group_id = ?
            ORDER BY gm.joined_at ASC
            """,
            (group_id,),
        ).fetchall()

    def get_group(self, group_id: int) -> sqlite3.Row | None:
        return self.conn.execute(
            "SELECT * FROM groups WHERE id = ? LIMIT 1",
            (group_id,),
        ).fetchone()

    def remove_group_member(self, group_id: int, user_id: int) -> None:
        self.conn.execute(
            "DELETE FROM group_members WHERE group_id = ? AND user_id = ?",
            (group_id, user_id),
        )
        self.conn.commit()

    # --- social stats for notifications ------------------------------------- #
    def user_completed_all_todos_today(self, user_id: int) -> bool:
        """Check if user completed all their open todos today."""
        open_count = self.conn.execute(
            "SELECT COUNT(*) AS n FROM todos WHERE user_id = ? AND done = 0",
            (user_id,),
        ).fetchone()["n"]
        return open_count == 0

    def user_completed_todos_count_today(self, user_id: int) -> int:
        """Count todos completed today."""
        today = datetime.now(timezone.utc).date().isoformat()
        row = self.conn.execute(
            """
            SELECT COUNT(*) AS n FROM todos
            WHERE user_id = ? AND done = 1
              AND DATE(created_at) = ?
            """,
            (user_id, today),
        ).fetchone()
        return int(row["n"]) if row else 0

    def user_stats_today(self, user_id: int) -> dict:
        """Get today's stats for a user."""
        today = datetime.now(timezone.utc).date().isoformat()

        todos_done_today = self.conn.execute(
            """
            SELECT COUNT(*) AS n FROM todos
            WHERE user_id = ? AND done = 1
              AND DATE(created_at) = ?
            """,
            (user_id, today),
        ).fetchone()["n"]

        habits_logged_today = self.conn.execute(
            """
            SELECT COUNT(*) AS n FROM habit_completions hc
            JOIN habits h ON h.id = hc.habit_id
            WHERE h.user_id = ? AND hc.date_ymd = ?
            """,
            (user_id, today),
        ).fetchone()["n"]

        return {
            "todos_done_today": todos_done_today,
            "habits_logged_today": habits_logged_today,
        }
