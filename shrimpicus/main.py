from __future__ import annotations

import asyncio
import logging
from pathlib import Path

from pydantic import ValidationError

from shrimpicus.assistant import AssistantService
from shrimpicus.bot import build_bot
from shrimpicus.config import DEFAULT_ENV_FILE, Settings
from shrimpicus.db import Database
from shrimpicus.notion import NotionService
from shrimpicus.obsidian import ObsidianJournal
from shrimpicus.ollama import OllamaClient
from shrimpicus.scheduler import ShrimpScheduler
from shrimpicus.transcribe import Transcriber


async def run() -> None:
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s | %(levelname)s | %(name)s | %(message)s",
    )
    logging.getLogger("httpx").setLevel(logging.WARNING)
    logger = logging.getLogger("shrimpicus")
    logger.info("Starting Shrimpicus...")

    try:
        settings = Settings()
    except ValidationError as exc:
        cwd = Path.cwd()
        logger.error("Failed to load settings from .env (cwd=%s).", cwd)
        if any(err.get("loc") == ("discord_bot_token",) for err in exc.errors()):
            logger.error(
                "DISCORD_BOT_TOKEN is required. Set it in '%s' "
                "or export it in your shell before running `shrimpicus`.",
                DEFAULT_ENV_FILE,
            )
        raise SystemExit(2) from exc

    db = Database(settings.db_file)
    db.init()

    notion = NotionService(settings)
    journal = ObsidianJournal(settings.obsidian_journal_file)
    ollama = OllamaClient(settings)
    assistant = AssistantService(settings, db, notion, journal, ollama)
    transcriber = Transcriber(settings.whisper_enabled, settings.whisper_model)
    bot = build_bot(
        settings.discord_command_prefix,
        assistant,
        assistant_channels=settings.assistant_channels,
        transcriber=transcriber,
    )
    scheduler = ShrimpScheduler(settings, db, bot)
    bot.shrimp_scheduler = scheduler  # type: ignore[attr-defined]
    try:
        await bot.start(settings.discord_bot_token)
    finally:
        if scheduler.scheduler.running:
            await scheduler.shutdown()
        await bot.close()


def main() -> None:
    asyncio.run(run())


if __name__ == "__main__":
    main()
