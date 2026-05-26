from __future__ import annotations

from discord.ext import commands
import discord

from shrimpicus.assistant import AssistantService


def build_bot(
    command_prefix: str,
    assistant: AssistantService,
) -> commands.Bot:
    intents = discord.Intents.default()
    intents.message_content = True
    intents.guilds = True

    bot = commands.Bot(command_prefix=command_prefix, intents=intents)

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
            "- !todo add Buy groceries\n"
            "- !birthday add Alice 1998-07-10\n"
            "- !journal Today I felt focused\n"
        )

    @bot.command(name="helpme")
    async def cmd_help(ctx: commands.Context) -> None:
        await ctx.send(
            "Commands:\n"
            "!remind <minutes> <text>\n"
            "!list\n"
            "!todo add <task>\n"
            "!todo list\n"
            "!todo done <id>\n"
            "!birthday add <name> <YYYY-MM-DD>\n"
            "!birthday list\n"
            "!journal <text>\n"
            "!ask <question>\n"
            "\nYou can also send natural text like: remind me to stretch in 30 minutes"
        )

    @bot.command(name="remind")
    async def cmd_remind(ctx: commands.Context, minutes: int | None = None, *, text: str | None = None) -> None:
        if minutes is None or text is None:
            await ctx.send("Usage: !remind <minutes> <text>")
            return
        if minutes <= 0:
            await ctx.send("Minutes must be a positive integer.")
            return

        reminder_id = assistant.add_reminder_minutes(ctx.channel.id, minutes, text, poll_required=True)
        await ctx.send(f"Reminder #{reminder_id} scheduled in {minutes} minute(s).")

    @bot.command(name="list")
    async def cmd_list(ctx: commands.Context) -> None:
        await ctx.send(assistant.list_reminders_text(ctx.channel.id))

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
            result = await assistant.add_todo(ctx.channel.id, value)
            await ctx.send(result)
            return

        if action == "list":
            await ctx.send(assistant.list_todos_text(ctx.channel.id))
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
            await ctx.send(assistant.mark_todo_done(todo_id))
            return

        await ctx.send("Usage: !todo add <task> | !todo list | !todo done <id>")

    @bot.command(name="birthday")
    async def cmd_birthday(ctx: commands.Context, action: str | None = None, name: str | None = None, date: str | None = None) -> None:
        if action is None:
            await ctx.send("Usage: !birthday add <name> <YYYY-MM-DD> | !birthday list")
            return
        action = action.lower()
        if action == "list":
            await ctx.send(assistant.list_birthdays_text(ctx.channel.id))
            return
        if action == "add":
            if not name or not date:
                await ctx.send("Usage: !birthday add <name> <YYYY-MM-DD>")
                return
            try:
                result = assistant.add_birthday(ctx.channel.id, name, date)
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
        await ctx.send(assistant.journal(ctx.channel.id, text))

    @bot.command(name="ask")
    async def cmd_ask(ctx: commands.Context, *, question: str | None = None) -> None:
        if not question:
            await ctx.send("Usage: !ask <question>")
            return
        reply = await assistant.free_text(ctx.channel.id, question)
        await ctx.send(reply)

    @bot.event
    async def on_message(message: discord.Message) -> None:
        if message.author.bot:
            return
        await bot.process_commands(message)
        if message.content.startswith(command_prefix):
            return
        if message.guild and bot.user and bot.user not in message.mentions:
            return
        reply = await assistant.free_text(message.channel.id, message.content)
        await message.channel.send(reply)

    return bot
