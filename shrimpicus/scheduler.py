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
        _, msg = self.scheduler.apply_checkin_answer(self.reminder_id, yes=True)
        await interaction.response.send_message(msg, ephemeral=True)

    @discord.ui.button(label="No", style=discord.ButtonStyle.danger)
    async def no_button(self, interaction: discord.Interaction, button: discord.ui.Button) -> None:
        _ = button
        _, msg = self.scheduler.apply_checkin_answer(self.reminder_id, yes=False)
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
        reminders = self.db.due_reminders(now_iso)
        for reminder in reminders:
            channel = await self._resolve_channel(reminder.chat_id)
            if channel is None:
                continue
            if reminder.poll_required:
                view = ReminderCheckinView(self, reminder_id=reminder.id)
                msg = await channel.send(
                    f"Did you complete this task?\n**{reminder.content}**",
                    view=view,
                )
                self.db.mark_reminder_poll_sent(reminder.id, str(msg.id))
            else:
                await channel.send(f"Reminder: {reminder.content}")
                self.db.mark_reminder_notified(reminder.id)

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

    def apply_checkin_answer(self, reminder_id: int, yes: bool) -> tuple[int | None, str]:
        row = self.db.conn.execute(
            "SELECT * FROM reminders WHERE id = ? LIMIT 1",
            (reminder_id,),
        ).fetchone()
        if not row:
            return None, "No matching reminder found."

        if yes:
            self.db.mark_reminder_completed(reminder_id)
            return reminder_id, f"Nice work. Marked reminder #{reminder_id} complete."

        current_due = datetime.fromisoformat(row["due_at"])
        next_due = current_due + timedelta(minutes=self.settings.default_snooze_minutes)
        self.db.snooze_reminder(reminder_id, next_due.isoformat())
        return reminder_id, (
            f"Reminder #{reminder_id} snoozed for {self.settings.default_snooze_minutes} minutes."
        )
