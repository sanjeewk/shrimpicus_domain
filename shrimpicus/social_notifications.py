"""Social notifications for group activity."""

from __future__ import annotations

import logging
from datetime import datetime, timezone

import discord

from shrimpicus.db import Database

logger = logging.getLogger(__name__)


async def check_and_notify_goals(db: Database, bot: discord.Client, channel_id: int) -> None:
    """Check for goal completions and notify groups.

    Called after a user completes a todo. Checks if:
    1. User completed all their open todos (goals for the day)
    2. User completed 2+ todos today

    Notifies all groups the user is in.
    """
    try:
        conn = db.conn
        today = datetime.now(timezone.utc).date().isoformat()

        # Get all users who need notifications
        users_to_notify = []

        # Find users who completed 2+ todos today
        heavy_completers = conn.execute(
            """
            SELECT user_id, username, COUNT(*) as completed_count
            FROM todos t
            JOIN users u ON u.id = t.user_id
            WHERE t.done = 1 AND DATE(t.created_at) = ?
            GROUP BY user_id, username
            HAVING completed_count >= 2
            """,
            (today,),
        ).fetchall()

        for user in heavy_completers:
            # Check if we already notified today
            last_notif = db.get_meta(f"last_heavy_notif_{user['user_id']}")
            if last_notif != today:
                users_to_notify.append({
                    "user_id": user["user_id"],
                    "username": user["username"],
                    "type": "heavy",
                    "count": user["completed_count"],
                })
                db.set_meta(f"last_heavy_notif_{user['user_id']}", today)

        # Find users who completed all their todos
        users_with_open = conn.execute(
            """
            SELECT DISTINCT user_id FROM todos WHERE done = 0
            """
        ).fetchall()
        open_user_ids = {row["user_id"] for row in users_with_open}

        all_users = conn.execute("SELECT id, username FROM users").fetchall()
        for user in all_users:
            if user["id"] not in open_user_ids:
                # User has no open todos - completed all goals
                last_notif = db.get_meta(f"last_goals_notif_{user['id']}")
                if last_notif != today:
                    users_to_notify.append({
                        "user_id": user["id"],
                        "username": user["username"],
                        "type": "goals",
                    })
                    db.set_meta(f"last_goals_notif_{user['id']}", today)

        # Send notifications
        channel = await _get_channel(bot, channel_id)
        if not channel:
            return

        for notif in users_to_notify:
            # Get user's groups
            groups = conn.execute(
                """
                SELECT g.name FROM groups g
                JOIN group_members gm ON gm.group_id = g.id
                WHERE gm.user_id = ?
                """,
                (notif["user_id"],),
            ).fetchall()

            if not groups:
                continue

            if notif["type"] == "heavy":
                msg = f"🔥 **{notif['username']}** completed {notif['count']} todos today! Keep crushing it!"
            else:
                msg = f"🎉 **{notif['username']}** completed all their goals for the day!"

            group_names = ", ".join(g["name"] for g in groups)
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
