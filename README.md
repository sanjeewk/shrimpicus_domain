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
# shrimpicus_domain
