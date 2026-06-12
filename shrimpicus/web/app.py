from __future__ import annotations

import argparse
import sqlite3
from datetime import datetime, timezone
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


def _stats(conn: sqlite3.Connection, selected_chat: int | None) -> dict:
    where = ""
    params: list[object] = []
    if selected_chat is not None:
        where = " WHERE chat_id = ?"
        params.append(selected_chat)
    row = conn.execute(
        f"SELECT COUNT(*) AS total, SUM(done) AS done_count FROM todos{where}",
        params,
    ).fetchone()
    total = row["total"] or 0
    done_count = row["done_count"] or 0
    pending = total - done_count
    xp_pct = int(round((done_count / total) * 100)) if total else 0
    return {
        "total": total,
        "done": done_count,
        "pending": pending,
        "xp": xp_pct,
        "level": 1 + done_count // 5,
        "score": done_count * 100 + pending * 10,
    }


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

    @app.route("/xp")
    def xp():
        conn = _connect(app.config["DB_PATH"])
        try:
            _ensure_status_column(conn)
            chats, selected_chat = _load_chats_and_filter(conn)
            stats = _stats(conn, selected_chat)
            recent_done = conn.execute(
                """
                SELECT id, chat_id, task, created_at
                FROM todos
                WHERE done = 1
                ORDER BY id DESC
                LIMIT 10
                """
            ).fetchall()
            return render_template(
                "xp.html",
                active_page="xp",
                stats=stats,
                chats=[{"id": c["chat_id"], "n": c["n"]} for c in chats],
                selected_chat=selected_chat,
                recent_done=[
                    {
                        "id": r["id"],
                        "chat_id": r["chat_id"],
                        "task": r["task"],
                        "created_human": _humanize(_parse_iso(r["created_at"])),
                    }
                    for r in recent_done
                ],
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
