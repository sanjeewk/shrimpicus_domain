# Shrimpicus

Shrimpicus is a personal AI assistant built with Python. It runs as a Discord bot, uses a local Ollama model for lightweight reasoning, stores reminders/todos/birthdays in SQLite, optionally syncs todos to Notion, and appends journal notes to an Obsidian vault.

## Features

- Add and list reminders from chat
- Yes/No poll check-ins for due reminders
- Todo tracking with optional Notion page creation
- Birthday tracking with daily check
- Journal note capture into Obsidian markdown files
- Optional free-text assistant replies via Ollama

## Quick start

1. Create a Discord bot in the Discord Developer Portal.
2. In **Bot** settings, enable **Message Content Intent**.
3. In **OAuth2 > URL Generator**, select scopes `bot` (and `applications.commands` if needed), then grant permissions like `Send Messages` and `Read Message History`.
4. Open the generated URL and invite the bot to your server.
5. Install and run Ollama (optional but recommended).
6. Copy `.env.example` to `.env`, then set `DISCORD_BOT_TOKEN`.
7. Install and run:

```bash
cd shrimpicus
python -m venv .venv
source .venv/bin/activate
pip install -e .
shrimpicus
```

## Verify connection

- Start the app and wait for `Shrimpicus logged in as ...` in terminal output.
- In Discord, type `!start` and `!helpme` in a channel where the bot has access.

## Security note

- Never commit real Discord bot tokens.
- If a token is exposed, rotate it immediately in the Discord Developer Portal.

## Commands

- `!start`
- `!helpme`
- `!remind <minutes> <text>`
- `!list`
- `!todo add <task>`
- `!todo list`
- `!birthday add <name> <YYYY-MM-DD>`
- `!birthday list`
- `!journal <text>`
- `!ask <question>`

## Notes

- Discord sends Yes/No button check-ins for due reminders.
- If a reminder receives "No", it is snoozed by `DEFAULT_SNOOZE_MINUTES`.
- Notion integration is optional and only active when token/database env vars are set.

## Changelog

### Unreleased

- **Feature roadmap** — added FEATURES.md documenting planned features including recurring reminders, habit tracking, social features, and expanded integrations.
- **Multi-page web interface** — the web viewer is now three pages: a drag-and-drop kanban **Board** (to_do/doing/done) backed by a new `status` column and `/api/todos/<id>/status` endpoint, an **XP** quest-log scoreboard, and a pixel **Field** that grows a daisy per completed todo (debug slider + WebAudio chiptune toggle).
- **Retro pixel-art web viewer** — `shrimpicus-web` launches a Flask app that reads the existing SQLite DB and renders a single-page Quest Log of todos. Stats panel with XP/HP completion bar, per-chat ("SELECT WORLD") filter, SHOW DEFEATED toggle. Theme synthesizes arcade-cabinet neon (cyan/lime/hot pink/gold), JRPG quest-log framing, and Game-Boy/CRT chrome (scanlines, vignette, boot-flicker, chunky pixel borders). Header has three pixel-SVG spinners (coin, floppy, star).
- **Todo categories with auto-classification** — todos are now grouped into Job / Home / Finance / General by keyword scoring of the task text. New `category` column on the todos table (idempotent ALTER TABLE migration). Two free-text shortcuts: `td <task>` to add and `tdl` to list (grouped by category).
- **Assistant channels and DM routing** — the bot now replies to free-text in any of: a DM, a message that mentions it, or a message in a channel listed in `ASSISTANT_CHANNELS` (comma-separated, default `general`). Previously required an @-mention everywhere.
- **Voice transcription** — audio attachments (`.ogg`/`.mp3`/`.wav`/`.m4a`/`.webm`/`.flac`) on free-text messages are downloaded, transcribed via faster-whisper on a worker thread, echoed back to the channel, and fed to the assistant. Optional install: `pip install -e .[voice]`. Configured via `WHISPER_ENABLED` / `WHISPER_MODEL`.
# shrimpicus_domain
