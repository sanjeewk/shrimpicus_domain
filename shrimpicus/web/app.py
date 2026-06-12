from __future__ import annotations

import argparse
import sqlite3
from datetime import date, datetime, timedelta, timezone
from pathlib import Path

from flask import Flask, abort, jsonify, redirect, render_template, request, url_for

from shrimpicus.config import Settings


VALID_STATUSES = ("to_do", "doing", "done")


def _connect(db_path: Path) -> sqlite3.Connection:
    if not db_path.exists():
        abort(503, description=f"Database not found at {db_path}. Run shrimpicus first.")
    conn = sqlite3.connect(db_path, check_same_thread=False)
    conn.row_factory = sqlite3.Row
    return conn


def _parse_iso(value: str | None) -> datetime | None:
    if not value:
        return None
    try:
        return datetime.fromisoformat(value)
    except ValueError:
        return None


def _humanize(dt: datetime | None) -> str:
    if dt is None:
        return "unknown"
    now = datetime.now(timezone.utc)
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=timezone.utc)
    delta = now - dt
    seconds = int(delta.total_seconds())
    if seconds < 60:
        return "just now"
    if seconds < 3600:
        return f"{seconds // 60}m ago"
    if seconds < 86400:
        return f"{seconds // 3600}h ago"
    days = seconds // 86400
    if days < 30:
        return f"{days}d ago"
    return dt.strftime("%Y-%m-%d")


def _ensure_status_column(conn: sqlite3.Connection) -> None:
    cols = {row["name"] for row in conn.execute("PRAGMA table_info(todos)").fetchall()}
    if "status" not in cols:
        conn.execute(
            "ALTER TABLE todos ADD COLUMN status TEXT NOT NULL DEFAULT 'to_do'"
        )
        conn.execute("UPDATE todos SET status = 'done' WHERE done = 1")
        conn.commit()


def _ensure_habit_tables(conn: sqlite3.Connection) -> None:
    conn.executescript(
        """
        CREATE TABLE IF NOT EXISTS habits (
          id INTEGER PRIMARY KEY AUTOINCREMENT,
          chat_id INTEGER NOT NULL,
          name TEXT NOT NULL,
          weekly_goal INTEGER NOT NULL DEFAULT 7,
          created_at TEXT NOT NULL
        );
        CREATE TABLE IF NOT EXISTS habit_completions (
          id INTEGER PRIMARY KEY AUTOINCREMENT,
          habit_id INTEGER NOT NULL,
          date_ymd TEXT NOT NULL,
          created_at TEXT NOT NULL,
          UNIQUE(habit_id, date_ymd)
        );
        CREATE INDEX IF NOT EXISTS idx_habit_completions
          ON habit_completions(habit_id, date_ymd);
        """
    )
    # Lazy migration: add weekly_goal if missing
    cols = {row["name"] for row in conn.execute("PRAGMA table_info(habits)").fetchall()}
    if "weekly_goal" not in cols:
        conn.execute("ALTER TABLE habits ADD COLUMN weekly_goal INTEGER NOT NULL DEFAULT 7")
    conn.commit()


def _habit_stats(dates: list[str], today: date) -> dict:
    """Compute streaks and history from a list of YYYY-MM-DD completion dates."""
    done_set = set(dates)
    total = len(done_set)

    # Current streak: count back from today (or yesterday if today not yet done).
    current = 0
    cursor = today if today.isoformat() in done_set else today - timedelta(days=1)
    while cursor.isoformat() in done_set:
        current += 1
        cursor -= timedelta(days=1)

    # Longest streak across all completions.
    longest = 0
    run = 0
    prev: date | None = None
    for d in sorted(done_set):
        cur = date.fromisoformat(d)
        run = run + 1 if (prev is not None and (cur - prev).days == 1) else 1
        longest = max(longest, run)
        prev = cur

    # Last 7 days, oldest -> newest, for the history strip.
    last7 = [
        {
            "date": (today - timedelta(days=i)).isoformat(),
            "label": (today - timedelta(days=i)).strftime("%a")[0],
            "done": (today - timedelta(days=i)).isoformat() in done_set,
            "is_today": i == 0,
        }
        for i in range(6, -1, -1)
    ]

    # This week's completions (Monday-Sunday)
    # Find the most recent Monday
    days_since_monday = today.weekday()  # 0=Monday, 6=Sunday
    week_start = today - timedelta(days=days_since_monday)
    week_count = sum(
        1 for d in done_set
        if week_start.isoformat() <= d <= today.isoformat()
    )

    return {
        "total": total,
        "current_streak": current,
        "longest_streak": longest,
        "done_today": today.isoformat() in done_set,
        "week_count": week_count,
        "last7": last7,
    }


def _load_chats_and_filter(conn: sqlite3.Connection) -> tuple[list[sqlite3.Row], int | None]:
    chats = conn.execute(
        """
        SELECT chat_id, COUNT(*) AS n
        FROM todos
        GROUP BY chat_id
        ORDER BY n DESC
        """
    ).fetchall()
    selected_chat = request.args.get("chat", type=int)
    return chats, selected_chat


def _load_todos(conn: sqlite3.Connection, selected_chat: int | None) -> list[dict]:
    sql = "SELECT id, chat_id, task, done, status, notion_page_id, created_at FROM todos"
    params: list[object] = []
    if selected_chat is not None:
        sql += " WHERE chat_id = ?"
        params.append(selected_chat)
    sql += " ORDER BY id DESC LIMIT 500"
    rows = conn.execute(sql, params).fetchall()
    todos = []
    for r in rows:
        status = r["status"] if "status" in r.keys() else ("done" if r["done"] else "to_do")
        todos.append(
            {
                "id": r["id"],
                "chat_id": r["chat_id"],
                "task": r["task"],
                "done": bool(r["done"]),
                "status": status,
                "linked_notion": bool(r["notion_page_id"]),
                "created_human": _humanize(_parse_iso(r["created_at"])),
            }
        )
    return todos


def create_app(db_path: Path | None = None) -> Flask:
    settings = Settings() if db_path is None else None
    resolved_db = db_path if db_path is not None else settings.db_file  # type: ignore[union-attr]

    app = Flask(__name__)
    app.config["DB_PATH"] = resolved_db

    @app.route("/")
    def root():
        return redirect(url_for("board"))

    @app.route("/board")
    def board():
        conn = _connect(app.config["DB_PATH"])
        try:
            _ensure_status_column(conn)
            chats, selected_chat = _load_chats_and_filter(conn)
            todos = _load_todos(conn, selected_chat)
            columns = {"to_do": [], "doing": [], "done": []}
            for t in todos:
                columns.setdefault(t["status"], columns["to_do"]).append(t)
            return render_template(
                "board.html",
                active_page="board",
                columns=columns,
                chats=[{"id": c["chat_id"], "n": c["n"]} for c in chats],
                selected_chat=selected_chat,
            )
        finally:
            conn.close()

    @app.route("/field")
    def field():
        conn = _connect(app.config["DB_PATH"])
        try:
            _ensure_status_column(conn)
            row = conn.execute(
                "SELECT COUNT(*) AS n FROM todos WHERE done = 1"
            ).fetchone()
            done_count = row["n"] or 0
            return render_template(
                "field.html",
                active_page="field",
                done_count=done_count,
            )
        finally:
            conn.close()

    @app.route("/habits")
    def habits():
        conn = _connect(app.config["DB_PATH"])
        try:
            _ensure_habit_tables(conn)
            selected_chat = request.args.get("chat", type=int)

            # Worlds: union of chats with todos or habits, so a fresh install
            # with no todos can still pick a world for habits.
            chat_rows = conn.execute(
                "SELECT chat_id FROM todos UNION SELECT chat_id FROM habits"
            ).fetchall()
            chats = sorted({r["chat_id"] for r in chat_rows})
            if selected_chat is None and chats:
                selected_chat = chats[0]

            today = datetime.now(timezone.utc).date()
            habit_rows = (
                conn.execute(
                    "SELECT id, name, weekly_goal FROM habits WHERE chat_id = ? ORDER BY id ASC",
                    (selected_chat,),
                ).fetchall()
                if selected_chat is not None
                else []
            )

            habits_view = []
            totals = {"tracked": 0, "done_today": 0, "best_streak": 0}
            for h in habit_rows:
                dates = [
                    r["date_ymd"]
                    for r in conn.execute(
                        "SELECT date_ymd FROM habit_completions WHERE habit_id = ?",
                        (h["id"],),
                    ).fetchall()
                ]
                stats = _habit_stats(dates, today)
                goal_met = stats["week_count"] >= h["weekly_goal"]
                habits_view.append({
                    "id": h["id"],
                    "name": h["name"],
                    "weekly_goal": h["weekly_goal"],
                    "goal_met": goal_met,
                    **stats
                })
                totals["tracked"] += 1
                totals["done_today"] += 1 if stats["done_today"] else 0
                totals["best_streak"] = max(totals["best_streak"], stats["longest_streak"])

            return render_template(
                "habits.html",
                active_page="habits",
                habits=habits_view,
                totals=totals,
                chats=chats,
                selected_chat=selected_chat,
            )
        finally:
            conn.close()

    @app.route("/habits/add", methods=["POST"])
    def habits_add():
        name = (request.form.get("name") or "").strip()
        chat_id = request.form.get("chat", type=int)
        weekly_goal = request.form.get("goal", type=int, default=7)
        if not name or chat_id is None:
            return redirect(url_for("habits", chat=chat_id))
        if weekly_goal not in range(1, 8):
            weekly_goal = 7
        conn = _connect(app.config["DB_PATH"])
        try:
            _ensure_habit_tables(conn)
            conn.execute(
                "INSERT INTO habits(chat_id, name, weekly_goal, created_at) VALUES (?, ?, ?, ?)",
                (chat_id, name[:120], weekly_goal, datetime.now(timezone.utc).isoformat()),
            )
            conn.commit()
        finally:
            conn.close()
        return redirect(url_for("habits", chat=chat_id))

    @app.route("/habits/<int:habit_id>/delete", methods=["POST"])
    def habits_delete(habit_id: int):
        chat_id = request.form.get("chat", type=int)
        conn = _connect(app.config["DB_PATH"])
        try:
            _ensure_habit_tables(conn)
            conn.execute("DELETE FROM habit_completions WHERE habit_id = ?", (habit_id,))
            conn.execute("DELETE FROM habits WHERE id = ?", (habit_id,))
            conn.commit()
        finally:
            conn.close()
        return redirect(url_for("habits", chat=chat_id))

    @app.route("/api/habits/<int:habit_id>/toggle", methods=["POST"])
    def api_habit_toggle(habit_id: int):
        conn = _connect(app.config["DB_PATH"])
        try:
            _ensure_habit_tables(conn)
            owner = conn.execute(
                "SELECT id FROM habits WHERE id = ?", (habit_id,)
            ).fetchone()
            if owner is None:
                return jsonify({"error": "not found"}), 404

            # Accept optional date from JSON body, default to today
            payload = request.get_json(silent=True) or {}
            target_date = payload.get("date")
            if target_date:
                # Validate YYYY-MM-DD format
                try:
                    date.fromisoformat(target_date)
                except (ValueError, TypeError):
                    return jsonify({"error": "invalid date"}), 400
            else:
                target_date = datetime.now(timezone.utc).date().isoformat()

            existing = conn.execute(
                "SELECT id FROM habit_completions WHERE habit_id = ? AND date_ymd = ?",
                (habit_id, target_date),
            ).fetchone()
            if existing:
                conn.execute("DELETE FROM habit_completions WHERE id = ?", (existing["id"],))
            else:
                conn.execute(
                    "INSERT INTO habit_completions(habit_id, date_ymd, created_at) "
                    "VALUES (?, ?, ?)",
                    (habit_id, target_date, datetime.now(timezone.utc).isoformat()),
                )
            conn.commit()

            dates = [
                r["date_ymd"]
                for r in conn.execute(
                    "SELECT date_ymd FROM habit_completions WHERE habit_id = ?",
                    (habit_id,),
                ).fetchall()
            ]
            weekly_goal = conn.execute(
                "SELECT weekly_goal FROM habits WHERE id = ?", (habit_id,)
            ).fetchone()["weekly_goal"]
            stats = _habit_stats(dates, datetime.now(timezone.utc).date())
            goal_met = stats["week_count"] >= weekly_goal
            return jsonify({"id": habit_id, "goal_met": goal_met, "weekly_goal": weekly_goal, **stats})
        finally:
            conn.close()

    @app.route("/api/todos/<int:todo_id>/status", methods=["POST"])
    def api_set_status(todo_id: int):
        payload = request.get_json(silent=True) or {}
        status = payload.get("status")
        if status not in VALID_STATUSES:
            return jsonify({"error": "invalid status"}), 400
        conn = _connect(app.config["DB_PATH"])
        try:
            _ensure_status_column(conn)
            done_flag = 1 if status == "done" else 0
            cur = conn.execute(
                "UPDATE todos SET status = ?, done = ? WHERE id = ?",
                (status, done_flag, todo_id),
            )
            conn.commit()
            if cur.rowcount == 0:
                return jsonify({"error": "not found"}), 404
            return jsonify({"id": todo_id, "status": status})
        finally:
            conn.close()

    return app


def main() -> None:
    parser = argparse.ArgumentParser(description="Shrimpicus web viewer")
    parser.add_argument("--host", default="127.0.0.1")
    parser.add_argument("--port", type=int, default=5005)
    parser.add_argument("--db", type=Path, default=None, help="Override path to shrimpicus.db")
    parser.add_argument("--debug", action="store_true")
    args = parser.parse_args()

    app = create_app(args.db)
    app.run(host=args.host, port=args.port, debug=args.debug)


if __name__ == "__main__":
    main()
