from __future__ import annotations

from datetime import datetime, timedelta, timezone

from apscheduler.schedulers.asyncio import AsyncIOScheduler
import discord

from shrimpicus.config import Settings
from shrimpicus.db import Database


class ReminderCheckinView(discord.ui.View):
    def __init__(self, scheduler: "ShrimpScheduler", reminder_id: int):
        super().__init__(timeout=None)
        self.scheduler = scheduler
        self.reminder_id = reminder_id

    @discord.ui.button(label="Yes", style=discord.ButtonStyle.success)
    async def yes_button(self, interaction: discord.Interaction, button: discord.ui.Button) -> None:
        _ = button
        _, msg = self.scheduler.apply_checkin_answer(
            self.reminder_id,
            yes=True,
            discord_user_id=interaction.user.id,
        )
        await interaction.response.send_message(msg, ephemeral=True)

    @discord.ui.button(label="No", style=discord.ButtonStyle.danger)
    async def no_button(self, interaction: discord.Interaction, button: discord.ui.Button) -> None:
        _ = button
        _, msg = self.scheduler.apply_checkin_answer(
            self.reminder_id,
            yes=False,
            discord_user_id=interaction.user.id,
        )
        await interaction.response.send_message(msg, ephemeral=True)


class ShrimpScheduler:
    def __init__(self, settings: Settings, db: Database, bot: discord.Client):
        self.settings = settings
        self.db = db
        self.bot = bot
        self.scheduler = AsyncIOScheduler(timezone=settings.tz)

    def start(self) -> None:
        self.scheduler.add_job(self._check_reminders, "interval", seconds=self.settings.check_interval_seconds)
        self.scheduler.add_job(self._check_birthdays, "interval", minutes=15)
        self.scheduler.start()

    async def shutdown(self) -> None:
        self.scheduler.shutdown(wait=False)

    async def _check_reminders(self) -> None:
        now_iso = datetime.now(timezone.utc).isoformat()
        now_dt = datetime.now(timezone.utc)
        reminders = self.db.due_reminders(now_iso)
        for reminder in reminders:
            channel = await self._resolve_channel(reminder.chat_id)
            if channel is None:
                continue

            if reminder.recur_kind:
                # Catch-up detection: if last fire was much older than the
                # expected cadence, log the gap but emit a normal-looking msg.
                self._log_catchup_if_missed(reminder, now_dt)

            if reminder.poll_required:
                view = ReminderCheckinView(self, reminder_id=reminder.id)
                msg = await channel.send(
                    f"Did you complete this task?\n**{reminder.content}**",
                    view=view,
                )
                if reminder.recur_kind:
                    # Stay in awaiting_poll; re-arm on Yes/No click so the
                    # same row carries the next occurrence.
                    self.db.mark_reminder_poll_sent(reminder.id, str(msg.id))
                else:
                    self.db.mark_reminder_poll_sent(reminder.id, str(msg.id))
            else:
                await channel.send(f"Reminder: {reminder.content}")
                if reminder.recur_kind:
                    # Fire-and-forget recurring: re-arm immediately.
                    self._rearm_recurring(reminder, now_dt)
                else:
                    self.db.mark_reminder_notified(reminder.id)

    def _log_catchup_if_missed(self, reminder, now_dt: datetime) -> None:
        """If the recurrence cadence suggests multiple missed fires, log it
        silently. The user-visible message stays normal-looking."""
        last_iso = reminder.last_fired_at or reminder.due_at
        try:
            last_dt = datetime.fromisoformat(last_iso)
            if last_dt.tzinfo is None:
                last_dt = last_dt.replace(tzinfo=timezone.utc)
        except (TypeError, ValueError):
            return
        gap_days = (now_dt - last_dt).days
        kind = reminder.recur_kind
        if kind == "daily" and gap_days >= 2:
            import logging
            logging.getLogger(__name__).info(
                "catch-up fire for daily reminder #%s (gap=%dd)", reminder.id, gap_days
            )
        elif kind == "weekly" and gap_days >= 14:
            import logging
            logging.getLogger(__name__).info(
                "catch-up fire for weekly reminder #%s (gap=%dd)", reminder.id, gap_days
            )
        elif kind == "monthly" and gap_days >= 60:
            import logging
            logging.getLogger(__name__).info(
                "catch-up fire for monthly reminder #%s (gap=%dd)", reminder.id, gap_days
            )

    def _rearm_recurring(self, reminder, after_dt: datetime) -> datetime | None:
        """Advance a recurring reminder to its next occurrence strictly after
        after_dt and persist via rearm_reminder. Returns the new UTC datetime
        or None if recurrence could not be computed."""
        from shrimpicus import recur
        if not reminder.recur_kind or not reminder.recur_time:
            return None
        tz = self.db.get_user_timezone(reminder.user_id)
        try:
            next_utc = recur.next_occurrence(
                kind=reminder.recur_kind,
                after_utc=after_dt,
                user_tz=tz,
                time_hhmm=reminder.recur_time,
                dow=reminder.recur_dow,
                dom=reminder.recur_dom,
            )
        except (ValueError, RuntimeError) as exc:
            import logging
            logging.getLogger(__name__).exception(
                "failed to re-arm recurring reminder #%s: %s", reminder.id, exc
            )
            return None
        self.db.rearm_reminder(reminder.id, next_utc.isoformat(), after_dt.isoformat())
        return next_utc

    async def _check_birthdays(self) -> None:
        today = datetime.now(timezone.utc).date()
        date_key = today.isoformat()
        if self.db.get_meta("last_birthday_check_date") == date_key:
            return

        month_day = today.strftime("%m-%d")
        for row in self.db.birthdays_for_month_day(month_day):
            channel = await self._resolve_channel(row["chat_id"])
            if channel is not None:
                await channel.send(
                    f"Birthday reminder: {row['person_name']} has a birthday today ({row['date_ymd']})."
                )
        self.db.set_meta("last_birthday_check_date", date_key)

    async def _resolve_channel(self, channel_id: int):
        channel = self.bot.get_channel(channel_id)
        if channel is not None:
            return channel
        try:
            channel = await self.bot.fetch_channel(channel_id)
        except Exception:  # noqa: BLE001
            return None
        return channel

    def apply_checkin_answer(
        self,
        reminder_id: int,
        yes: bool,
        discord_user_id: int | None = None,
    ) -> tuple[int | None, str]:
        row = self.db.conn.execute(
            "SELECT * FROM reminders WHERE id = ? LIMIT 1",
            (reminder_id,),
        ).fetchone()
        if not row:
            return None, "No matching reminder found."

        if discord_user_id is not None:
            user = self.db.get_user_by_discord_id(discord_user_id)
            if user is None or int(user["id"]) != int(row["user_id"]):
                return None, "This reminder belongs to another Shrimpicus user."

        is_recurring = row["recur_kind"] is not None if "recur_kind" in row.keys() else False

        if yes:
            self.db.mark_reminder_completed(reminder_id)
            if is_recurring:
                # Re-arm to next occurrence after the moment the user clicked Yes.
                reminder_obj = self._row_to_reminder_obj(row)
                next_dt = self._rearm_recurring(reminder_obj, datetime.now(timezone.utc))
                if next_dt is not None:
                    return reminder_id, (
                        f"Nice work. Marked reminder #{reminder_id} complete. "
                        f"Next fire: {next_dt.isoformat()}."
                    )
                return reminder_id, f"Nice work. Marked reminder #{reminder_id} complete."
            return reminder_id, f"Nice work. Marked reminder #{reminder_id} complete."

        # 'No' clicked
        if is_recurring:
            # No snooze for recurring — skip and re-arm immediately.
            reminder_obj = self._row_to_reminder_obj(row)
            next_dt = self._rearm_recurring(reminder_obj, datetime.now(timezone.utc))
            if next_dt is not None:
                return reminder_id, (
                    f"Reminder #{reminder_id} skipped. Next fire: {next_dt.isoformat()}."
                )
            return reminder_id, f"Reminder #{reminder_id} skipped."

        current_due = datetime.fromisoformat(row["due_at"])
        next_due = current_due + timedelta(minutes=self.settings.default_snooze_minutes)
        self.db.snooze_reminder(reminder_id, next_due.isoformat())
        return reminder_id, (
            f"Reminder #{reminder_id} snoozed for {self.settings.default_snooze_minutes} minutes."
        )

    def _row_to_reminder_obj(self, row):
        """Coerce a sqlite3.Row / RealDictRow into a Reminder dataclass."""
        from shrimpicus.db import Reminder
        return Reminder(
            id=row["id"],
            chat_id=row["chat_id"],
            user_id=row["user_id"],
            content=row["content"],
            due_at=row["due_at"],
            status=row["status"],
            poll_required=bool(row["poll_required"]),
            poll_id=row["poll_id"],
            recur_kind=row["recur_kind"] if "recur_kind" in row.keys() else None,
            recur_dow=row["recur_dow"] if "recur_dow" in row.keys() else None,
            recur_dom=row["recur_dom"] if "recur_dom" in row.keys() else None,
            recur_time=row["recur_time"] if "recur_time" in row.keys() else None,
            last_fired_at=row["last_fired_at"] if "last_fired_at" in row.keys() else None,
        )
