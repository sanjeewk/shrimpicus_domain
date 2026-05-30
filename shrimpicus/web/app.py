from __future__ import annotations

import argparse
import sqlite3
from datetime import datetime, timezone
from pathlib import Path

from flask import Flask, abort, render_template, request

from shrimpicus.config import Settings


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
        return "UNKNOWN ERA"
    now = datetime.now(timezone.utc)
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=timezone.utc)
    delta = now - dt
    seconds = int(delta.total_seconds())
    if seconds < 60:
        return "MOMENTS AGO"
    if seconds < 3600:
        return f"{seconds // 60}M AGO"
    if seconds < 86400:
        return f"{seconds // 3600}H AGO"
    days = seconds // 86400
    if days < 30:
        return f"{days}D AGO"
    return dt.strftime("%Y-%m-%d").upper()


def create_app(db_path: Path | None = None) -> Flask:
    settings = Settings() if db_path is None else None
    resolved_db = db_path if db_path is not None else settings.db_file  # type: ignore[union-attr]

    app = Flask(__name__)
    app.config["DB_PATH"] = resolved_db

    @app.route("/")
    def index():
        conn = _connect(app.config["DB_PATH"])
        try:
            chats = conn.execute(
                """
                SELECT chat_id, COUNT(*) AS n
                FROM todos
                GROUP BY chat_id
                ORDER BY n DESC
                """
            ).fetchall()

            selected_chat = request.args.get("chat", type=int)
            show_done = request.args.get("done", default="0") == "1"

            params: list[object] = []
            where = []
            if selected_chat is not None:
                where.append("chat_id = ?")
                params.append(selected_chat)
            if not show_done:
                where.append("done = 0")
            sql = "SELECT id, chat_id, task, done, notion_page_id, created_at FROM todos"
            if where:
                sql += " WHERE " + " AND ".join(where)
            sql += " ORDER BY done ASC, id DESC LIMIT 200"

            rows = conn.execute(sql, params).fetchall()
            todos = []
            for r in rows:
                todos.append(
                    {
                        "id": r["id"],
                        "chat_id": r["chat_id"],
                        "task": r["task"],
                        "done": bool(r["done"]),
                        "linked_notion": bool(r["notion_page_id"]),
                        "created_human": _humanize(_parse_iso(r["created_at"])),
                    }
                )

            totals_row = conn.execute(
                "SELECT COUNT(*) AS total, SUM(done) AS done_count FROM todos"
            ).fetchone()
            total = totals_row["total"] or 0
            done_count = totals_row["done_count"] or 0
            pending = total - done_count
            xp_pct = int(round((done_count / total) * 100)) if total else 0

            return render_template(
                "index.html",
                todos=todos,
                chats=[{"id": c["chat_id"], "n": c["n"]} for c in chats],
                selected_chat=selected_chat,
                show_done=show_done,
                stats={
                    "total": total,
                    "done": done_count,
                    "pending": pending,
                    "xp": xp_pct,
                    "level": 1 + done_count // 5,
                    "score": done_count * 100 + pending * 10,
                },
            )
        finally:
            conn.close()

    return app


def main() -> None:
    parser = argparse.ArgumentParser(description="Shrimpicus retro todo viewer")
    parser.add_argument("--host", default="127.0.0.1")
    parser.add_argument("--port", type=int, default=5005)
    parser.add_argument("--db", type=Path, default=None, help="Override path to shrimpicus.db")
    parser.add_argument("--debug", action="store_true")
    args = parser.parse_args()

    app = create_app(args.db)
    app.run(host=args.host, port=args.port, debug=args.debug)


if __name__ == "__main__":
    main()
