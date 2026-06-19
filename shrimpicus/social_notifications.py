"""Social notifications for group activity."""

from __future__ import annotations

import logging
from datetime import datetime, timezone

import discord

from shrimpicus.db import Database

logger = logging.getLogger(__name__)


async def check_and_notify_goals(db: Database, bot: discord.Client, channel_id: int, user_id: int) -> None:
    """Check one user's goal completions and notify their groups."""
    try:
        conn = db.conn
        today = datetime.now(timezone.utc).date().isoformat()

        user = conn.execute(
            "SELECT id, username FROM users WHERE id = ?",
            (user_id,),
        ).fetchone()
        if user is None:
            return

        users_to_notify = []

        completed_count = conn.execute(
            """
            SELECT COUNT(*) AS n
            FROM todos
            WHERE user_id = ? AND done = 1 AND DATE(created_at) = ?
            """,
            (user_id, today),
        ).fetchone()["n"]

        if completed_count >= 2:
            last_notif = db.get_meta(f"last_heavy_notif_{user_id}")
            if last_notif != today:
                users_to_notify.append({
                    "user_id": user_id,
                    "username": user["username"],
                    "type": "heavy",
                    "count": completed_count,
                })
                db.set_meta(f"last_heavy_notif_{user_id}", today)

        open_count = conn.execute(
            "SELECT COUNT(*) AS n FROM todos WHERE user_id = ? AND done = 0",
            (user_id,),
        ).fetchone()["n"]
        if open_count == 0:
            last_notif = db.get_meta(f"last_goals_notif_{user_id}")
            if last_notif != today:
                users_to_notify.append({
                    "user_id": user_id,
                    "username": user["username"],
                    "type": "goals",
                })
                db.set_meta(f"last_goals_notif_{user_id}", today)

        if not users_to_notify:
            return

        channel = await _get_channel(bot, channel_id)
        if not channel:
            return

        groups = conn.execute(
            """
            SELECT g.name FROM groups g
            JOIN group_members gm ON gm.group_id = g.id
            WHERE gm.user_id = ?
            """,
            (user_id,),
        ).fetchall()
        if not groups:
            return

        group_names = ", ".join(g["name"] for g in groups)
        for notif in users_to_notify:
            if notif["type"] == "heavy":
                msg = f"🔥 **{notif['username']}** completed {notif['count']} todos today! Keep crushing it!"
            else:
                msg = f"🎉 **{notif['username']}** completed all their goals for the day!"
            msg += f"\n_(Groups: {group_names})_"
            await channel.send(msg)

    except Exception as exc:
        logger.exception("Failed to send social notifications: %s", exc)


async def _get_channel(bot: discord.Client, channel_id: int) -> discord.TextChannel | None:
    """Get Discord channel by ID."""
    try:
        channel = bot.get_channel(channel_id)
        if channel:
            return channel
        return await bot.fetch_channel(channel_id)
    except Exception:
        return None
