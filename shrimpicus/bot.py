from __future__ import annotations

import logging
from pathlib import Path

from discord.ext import commands
import discord

from shrimpicus.assistant import AssistantService
from shrimpicus.transcribe import Transcriber

logger = logging.getLogger(__name__)

_AUDIO_EXTS = {".ogg", ".oga", ".mp3", ".wav", ".m4a", ".webm", ".flac"}


def build_bot(
    command_prefix: str,
    assistant: AssistantService,
    assistant_channels: list[str] | None = None,
    transcriber: Transcriber | None = None,
) -> commands.Bot:
    assistant_channel_names = {c.lower() for c in (assistant_channels or [])}

    intents = discord.Intents.default()
    intents.message_content = True
    intents.guilds = True

    bot = commands.Bot(command_prefix=command_prefix, intents=intents)
    assistant.bot = bot

    def _user_id_for(author: discord.abc.User) -> int:
        user = assistant.db.get_or_create_user_for_discord(
            author.id,
            display_name=getattr(author, "display_name", None) or author.name,
        )
        return int(user["id"])

    @bot.event
    async def on_ready() -> None:
        scheduler = getattr(bot, "shrimp_scheduler", None)
        if scheduler is None:
            return
        if not scheduler.scheduler.running:
            scheduler.start()
        print(f"Shrimpicus logged in as {bot.user}")

    @bot.command(name="start")
    async def cmd_start(ctx: commands.Context) -> None:
        await ctx.send(
            "Shrimpicus online.\n"
            "Use !helpme to see commands.\n"
            "Examples:\n"
            "- !remind 45 Prepare slides\n"
            "- !remind daily 09:00 Standup\n"
            "- !remind weekly mon 09:00 Weekly review\n"
            "- !remind monthly 1 10:00 Pay rent\n"
            "- !timezone Asia/Colombo\n"
            "- !todo add Buy groceries\n"
            "- !birthday add Alice 1998-07-10\n"
            "- !journal Today I felt focused\n"
        )

    @bot.command(name="helpme")
    async def cmd_help(ctx: commands.Context) -> None:
        await ctx.send(
            "Commands:\n"
            "!remind <minutes> <text>\n"
            "!remind daily <HH:MM> <text>\n"
            "!remind weekly <weekday> <HH:MM> <text>\n"
            "!remind monthly <day-of-month> <HH:MM> <text>\n"
            "!remind delete <id>\n"
            "!list\n"
            "!timezone [<IANA name, e.g. Europe/London>]\n"
            "!todo add <task>\n"
            "!todo list\n"
            "!todo done <id>\n"
            "!birthday add <name> <YYYY-MM-DD>\n"
            "!birthday list\n"
            "!journal <text>\n"
            "!ask <question>\n"
            "\nWeekdays: mon/tue/wed/thu/fri/sat/sun (full forms OK).\n"
            "\nYou can also send natural text like: remind me to stretch in 30 minutes"
        )

    @bot.command(name="remind")
    async def cmd_remind(ctx: commands.Context, *, text: str | None = None) -> None:
        if not text:
            await ctx.send(
                "Usage:\n"
                "  !remind <minutes> <text>\n"
                "  !remind daily <HH:MM> <text>\n"
                "  !remind weekly <weekday> <HH:MM> <text>\n"
                "  !remind monthly <day-of-month> <HH:MM> <text>\n"
                "  !remind delete <id>"
            )
            return

        tokens = text.split()
        user_id = _user_id_for(ctx.author)

        # Subcommand: delete
        if tokens[0].lower() == "delete":
            if len(tokens) < 2:
                await ctx.send("Usage: !remind delete <id>")
                return
            try:
                rid = int(tokens[1])
            except ValueError:
                await ctx.send("Reminder id must be an integer.")
                return
            await ctx.send(assistant.delete_reminder(rid, user_id))
            return

        # Subcommand: daily / weekly / monthly
        kind = tokens[0].lower()
        if kind in {"daily", "weekly", "monthly"}:
            rest = tokens[1:]
            if kind == "daily":
                if len(rest) < 2:
                    await ctx.send("Usage: !remind daily <HH:MM> <text>")
                    return
                time_str = rest[0]
                content = " ".join(rest[1:])
                result = assistant.add_recurring_reminder(
                    user_id, "daily", time_str, content, delivery_chat_id=ctx.channel.id
                )
                await ctx.send(result)
                return
            if kind == "weekly":
                if len(rest) < 3:
                    await ctx.send("Usage: !remind weekly <weekday> <HH:MM> <text>")
                    return
                weekday = rest[0]
                time_str = rest[1]
                content = " ".join(rest[2:])
                result = assistant.add_recurring_reminder(
                    user_id, "weekly", time_str, content,
                    weekday=weekday, delivery_chat_id=ctx.channel.id,
                )
                await ctx.send(result)
                return
            if kind == "monthly":
                if len(rest) < 3:
                    await ctx.send("Usage: !remind monthly <day-of-month> <HH:MM> <text>")
                    return
                try:
                    dom = int(rest[0])
                except ValueError:
                    await ctx.send("Day-of-month must be an integer 1-31.")
                    return
                time_str = rest[1]
                content = " ".join(rest[2:])
                result = assistant.add_recurring_reminder(
                    user_id, "monthly", time_str, content,
                    dom=dom, delivery_chat_id=ctx.channel.id,
                )
                await ctx.send(result)
                return

        # Default: one-shot relative reminder "<minutes> <text>"
        try:
            minutes = int(tokens[0])
        except ValueError:
            await ctx.send(
                "Usage: !remind <minutes> <text>  |  !remind daily/weekly/monthly ...  |  !remind delete <id>"
            )
            return
        content_text = " ".join(tokens[1:])
        if minutes <= 0 or not content_text:
            await ctx.send("Usage: !remind <minutes> <text>")
            return
        reminder_id = assistant.add_reminder_minutes(
            user_id,
            minutes,
            content_text,
            poll_required=True,
            delivery_chat_id=ctx.channel.id,
        )
        await ctx.send(f"Reminder #{reminder_id} scheduled in {minutes} minute(s).")

    @bot.command(name="timezone")
    async def cmd_timezone(ctx: commands.Context, *, tz: str | None = None) -> None:
        user_id = _user_id_for(ctx.author)
        if not tz:
            current = assistant.db.get_user_timezone(user_id)
            await ctx.send(
                f"Your timezone: {current}. Set with !timezone <IANA name> "
                f"(e.g. Europe/London, Asia/Colombo, America/New_York)."
            )
            return
        tz = tz.strip().strip('"').strip("'")
        try:
            assistant.db.set_user_timezone(user_id, tz)
            await ctx.send(f"Timezone set to {tz}.")
        except Exception as exc:  # noqa: BLE001
            await ctx.send(f"Unknown timezone {tz!r}: {exc}")

    @bot.command(name="list")
    async def cmd_list(ctx: commands.Context) -> None:
        user_id = _user_id_for(ctx.author)
        await ctx.send(assistant.list_reminders_text(user_id))

    @bot.command(name="todo")
    async def cmd_todo(ctx: commands.Context, action: str | None = None, *, value: str | None = None) -> None:
        if action is None:
            await ctx.send("Usage: !todo add <task> | !todo list | !todo done <id>")
            return

        action = action.lower()
        if action == "add":
            if not value:
                await ctx.send("Usage: !todo add <task>")
                return
            user_id = _user_id_for(ctx.author)
            result = await assistant.add_todo(user_id, value, delivery_chat_id=ctx.channel.id)
            await ctx.send(result)
            return

        if action == "list":
            user_id = _user_id_for(ctx.author)
            await ctx.send(assistant.list_todos_text(user_id))
            return

        if action == "done":
            if not value:
                await ctx.send("Usage: !todo done <id>")
                return
            try:
                todo_id = int(value)
            except ValueError:
                await ctx.send("Todo id must be an integer.")
                return
            user_id = _user_id_for(ctx.author)
            await ctx.send(assistant.mark_todo_done(todo_id, user_id, delivery_chat_id=ctx.channel.id))
            return

        await ctx.send("Usage: !todo add <task> | !todo list | !todo done <id>")

    @bot.command(name="birthday")
    async def cmd_birthday(ctx: commands.Context, action: str | None = None, name: str | None = None, date: str | None = None) -> None:
        if action is None:
            await ctx.send("Usage: !birthday add <name> <YYYY-MM-DD> | !birthday list")
            return
        action = action.lower()
        if action == "list":
            user_id = _user_id_for(ctx.author)
            await ctx.send(assistant.list_birthdays_text(user_id))
            return
        if action == "add":
            if not name or not date:
                await ctx.send("Usage: !birthday add <name> <YYYY-MM-DD>")
                return
            try:
                user_id = _user_id_for(ctx.author)
                result = assistant.add_birthday(user_id, name, date, delivery_chat_id=ctx.channel.id)
            except Exception as exc:  # noqa: BLE001
                await ctx.send(f"Could not parse birthday date: {exc}")
                return
            await ctx.send(result)
            return
        await ctx.send("Usage: !birthday add <name> <YYYY-MM-DD> | !birthday list")

    @bot.command(name="journal")
    async def cmd_journal(ctx: commands.Context, *, text: str | None = None) -> None:
        if not text:
            await ctx.send("Usage: !journal <text>")
            return
        user_id = _user_id_for(ctx.author)
        await ctx.send(assistant.journal(user_id, text, delivery_chat_id=ctx.channel.id))

    @bot.command(name="ask")
    async def cmd_ask(ctx: commands.Context, *, question: str | None = None) -> None:
        if not question:
            await ctx.send("Usage: !ask <question>")
            return
        user_id = _user_id_for(ctx.author)
        reply = await assistant.free_text(user_id, question, delivery_chat_id=ctx.channel.id)
        await ctx.send(reply)

    @bot.command(name="link")
    async def cmd_link(ctx: commands.Context, code: str | None = None) -> None:
        if not code:
            await ctx.send("Usage: !link <code>")
            return
        ok, message = assistant.db.consume_discord_link_code(code, ctx.author.id)
        await ctx.send(message)

    async def _maybe_transcribe(message: discord.Message) -> str | None:
        if transcriber is None or not transcriber.enabled:
            return None
        for att in message.attachments:
            suffix = Path(att.filename or "").suffix.lower()
            if suffix not in _AUDIO_EXTS:
                continue
            try:
                audio = await att.read()
            except Exception:
                logger.exception("Failed to download attachment %s", att.filename)
                continue
            try:
                text = await transcriber.transcribe_bytes(audio, suffix=suffix or ".ogg")
            except Exception:
                logger.exception("Transcription failed for %s", att.filename)
                continue
            if text:
                return text
        return None

    @bot.event
    async def on_message(message: discord.Message) -> None:
        if message.author.bot:
            return
        await bot.process_commands(message)
        if message.content.startswith(command_prefix):
            return

        channel_name = (getattr(message.channel, "name", "") or "").lower()
        in_assistant_channel = channel_name in assistant_channel_names
        mentioned = bool(bot.user and bot.user in message.mentions)
        is_dm = message.guild is None

        in_server_channel = message.guild is not None

        if not (is_dm or in_server_channel or mentioned or in_assistant_channel):
            return

        transcript = await _maybe_transcribe(message)
        text = (transcript or message.content or "").strip()
        if not text:
            return

        if transcript:
            await message.channel.send(f"(transcribed) {transcript}")
        user_id = _user_id_for(message.author)
        reply = await assistant.free_text(user_id, text, delivery_chat_id=message.channel.id)
        await message.channel.send(reply)

    return bot
