from __future__ import annotations

import argparse
import secrets
import sqlite3
from datetime import date, datetime, timedelta, timezone
from functools import wraps
from pathlib import Path

from flask import Flask, abort, jsonify, redirect, render_template, request, session, url_for

from shrimpicus import auth as auth_utils
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


def login_required(f):
    """Decorator to require authentication for a route."""
    @wraps(f)
    def decorated_function(*args, **kwargs):
        if "user_id" not in session:
            return redirect(url_for("login"))
        return f(*args, **kwargs)
    return decorated_function


def get_current_user(conn: sqlite3.Connection) -> sqlite3.Row | None:
    """Get the currently logged-in user from session."""
    user_id = session.get("user_id")
    if not user_id:
        return None
    return conn.execute("SELECT * FROM users WHERE id = ?", (user_id,)).fetchone()



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
    app.secret_key = secrets.token_hex(32)  # Generate secure secret key for sessions
    app.config["PERMANENT_SESSION_LIFETIME"] = timedelta(days=7)

    @app.route("/")
    def root():
        # Redirect to login if not authenticated, otherwise to board
        if "user_id" not in session:
            return redirect(url_for("login"))
        return redirect(url_for("board"))

    @app.route("/login", methods=["GET", "POST"])
    def login():
        if request.method == "POST":
            username = request.form.get("username", "").strip()
            password = request.form.get("password", "").strip()

            if not username or not password:
                return render_template("login.html", error="Username and password are required.")

            conn = _connect(app.config["DB_PATH"])
            try:
                user = conn.execute(
                    "SELECT * FROM users WHERE username = ? COLLATE NOCASE",
                    (username,),
                ).fetchone()

                if user and auth_utils.verify_password(user["password_hash"], password):
                    session["user_id"] = user["id"]
                    session["username"] = user["username"]
                    session.permanent = True
                    return redirect(url_for("board"))
                else:
                    return render_template("login.html", error="Invalid username or password.")
            finally:
                conn.close()

        return render_template("login.html")

    @app.route("/signup", methods=["GET", "POST"])
    def signup():
        if request.method == "POST":
            username = request.form.get("username", "").strip()
            password = request.form.get("password", "").strip()
            password_confirm = request.form.get("password_confirm", "").strip()

            # Validation
            username_error = auth_utils.validate_username(username)
            if username_error:
                return render_template("signup.html", error=username_error)

            password_error = auth_utils.validate_password(password)
            if password_error:
                return render_template("signup.html", error=password_error)

            if password != password_confirm:
                return render_template("signup.html", error="Passwords do not match.")

            conn = _connect(app.config["DB_PATH"])
            try:
                # Check if username already exists
                existing = conn.execute(
                    "SELECT id FROM users WHERE username = ? COLLATE NOCASE",
                    (username,),
                ).fetchone()

                if existing:
                    return render_template("signup.html", error="Username already taken.")

                # Create user
                password_hash = auth_utils.hash_password(password)
                cur = conn.execute(
                    "INSERT INTO users(username, password_hash, created_at) VALUES (?, ?, ?)",
                    (username.lower(), password_hash, datetime.now(timezone.utc).isoformat()),
                )
                user_id = cur.lastrowid
                conn.commit()

                # Auto-login
                session["user_id"] = user_id
                session["username"] = username.lower()
                session.permanent = True
                return redirect(url_for("board"))
            finally:
                conn.close()

        return render_template("signup.html")

    @app.route("/logout")
    def logout():
        session.clear()
        return redirect(url_for("login"))

    @app.route("/board")
    @login_required
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

    @app.route("/social")
    @login_required
    def social():
        conn = _connect(app.config["DB_PATH"])
        try:
            user_id = session["user_id"]

            # Get user's groups
            groups_data = []
            groups = conn.execute(
                """
                SELECT g.* FROM groups g
                JOIN group_members gm ON gm.group_id = g.id
                WHERE gm.user_id = ?
                ORDER BY g.created_at DESC
                """,
                (user_id,),
            ).fetchall()

            for group in groups:
                members = conn.execute(
                    """
                    SELECT u.id, u.username FROM users u
                    JOIN group_members gm ON gm.user_id = u.id
                    WHERE gm.group_id = ?
                    ORDER BY gm.joined_at ASC
                    """,
                    (group["id"],),
                ).fetchall()

                # Get today's stats for each member
                today = datetime.now(timezone.utc).date().isoformat()
                members_with_stats = []
                for member in members:
                    todos_done = conn.execute(
                        """
                        SELECT COUNT(*) AS n FROM todos
                        WHERE user_id = ? AND done = 1
                          AND DATE(created_at) = ?
                        """,
                        (member["id"], today),
                    ).fetchone()["n"]

                    habits_logged = conn.execute(
                        """
                        SELECT COUNT(*) AS n FROM habit_completions hc
                        JOIN habits h ON h.id = hc.habit_id
                        WHERE h.user_id = ? AND hc.date_ymd = ?
                        """,
                        (member["id"], today),
                    ).fetchone()["n"]

                    members_with_stats.append({
                        "id": member["id"],
                        "username": member["username"],
                        "todos_done_today": todos_done,
                        "habits_logged_today": habits_logged,
                    })

                groups_data.append({
                    "id": group["id"],
                    "name": group["name"],
                    "members": members_with_stats,
                })

            # Get user's friends
            friends = conn.execute(
                """
                SELECT u.* FROM users u
                JOIN friendships f ON f.friend_id = u.id
                WHERE f.user_id = ?
                ORDER BY u.username
                """,
                (user_id,),
            ).fetchall()

            return render_template(
                "social.html",
                active_page="social",
                groups=groups_data,
                friends=[{"id": f["id"], "username": f["username"]} for f in friends],
            )
        finally:
            conn.close()

    @app.route("/social/group/create", methods=["POST"])
    @login_required
    def social_create_group():
        name = request.form.get("name", "").strip()
        if not name:
            return redirect(url_for("social"))

        conn = _connect(app.config["DB_PATH"])
        try:
            user_id = session["user_id"]
            cur = conn.execute(
                "INSERT INTO groups(name, created_by_user_id, created_at) VALUES (?, ?, ?)",
                (name, user_id, datetime.now(timezone.utc).isoformat()),
            )
            group_id = cur.lastrowid
            # Auto-add creator
            conn.execute(
                "INSERT INTO group_members(group_id, user_id, joined_at) VALUES (?, ?, ?)",
                (group_id, user_id, datetime.now(timezone.utc).isoformat()),
            )
            conn.commit()
        finally:
            conn.close()
        return redirect(url_for("social"))

    @app.route("/social/group/<int:group_id>/add_member", methods=["POST"])
    @login_required
    def social_add_member(group_id: int):
        username = request.form.get("username", "").strip()
        if not username:
            return redirect(url_for("social"))

        conn = _connect(app.config["DB_PATH"])
        try:
            # Check member count
            count = conn.execute(
                "SELECT COUNT(*) AS n FROM group_members WHERE group_id = ?",
                (group_id,),
            ).fetchone()["n"]
            if count >= 10:
                return redirect(url_for("social"))  # Group full

            # Find user by username
            target_user = conn.execute(
                "SELECT id FROM users WHERE username = ? COLLATE NOCASE",
                (username,),
            ).fetchone()
            if not target_user:
                return redirect(url_for("social"))  # User not found

            # Add to group
            try:
                conn.execute(
                    "INSERT INTO group_members(group_id, user_id, joined_at) VALUES (?, ?, ?)",
                    (group_id, target_user["id"], datetime.now(timezone.utc).isoformat()),
                )
                conn.commit()
            except sqlite3.IntegrityError:
                pass  # Already a member
        finally:
            conn.close()
        return redirect(url_for("social"))

    @app.route("/social/friend/add", methods=["POST"])
    @login_required
    def social_add_friend():
        username = request.form.get("username", "").strip()
        if not username:
            return redirect(url_for("social"))

        conn = _connect(app.config["DB_PATH"])
        try:
            user_id = session["user_id"]
            # Find friend by username
            friend = conn.execute(
                "SELECT id FROM users WHERE username = ? COLLATE NOCASE",
                (username,),
            ).fetchone()
            if not friend or friend["id"] == user_id:
                return redirect(url_for("social"))

            # Add bidirectional friendship
            try:
                conn.execute(
                    "INSERT INTO friendships(user_id, friend_id, created_at) VALUES (?, ?, ?)",
                    (user_id, friend["id"], datetime.now(timezone.utc).isoformat()),
                )
                conn.execute(
                    "INSERT INTO friendships(user_id, friend_id, created_at) VALUES (?, ?, ?)",
                    (friend["id"], user_id, datetime.now(timezone.utc).isoformat()),
                )
                conn.commit()
            except sqlite3.IntegrityError:
                pass  # Already friends
        finally:
            conn.close()
        return redirect(url_for("social"))

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
