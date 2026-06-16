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

## RAG + Tool Calling

The assistant now uses **RAG (Retrieval-Augmented Generation)** to inject context about your todos, reminders, and habits into every conversation, and **tool calling** to directly add, complete, or modify your data when you ask in natural language.

**Examples:**
- *"add buy milk to my list"* — uses the `add_todo` tool
- *"mark todo 3 done and add a reminder to stretch in 20 minutes"* — chains `complete_todo` + `add_reminder`
- *"I went to the gym today"* — logs a habit (auto-creates if needed)

The model decides which tools to call based on your request. Fast regex shortcuts (`td`, `tdl`) still work and are faster for exact patterns.

## MCP Server

The same tool registry is exposed as an **MCP server** so external clients (Claude Desktop, etc.) can manage your todos/reminders/habits.

**Install the MCP dependency:**
```bash
pip install -e '.[mcp]'
```

**Run the server:**
```bash
shrimpicus-mcp
```

**Configure Claude Desktop** — add to `~/Library/Application Support/Claude/claude_desktop_config.json`:
```json
{
  "mcpServers": {
    "shrimpicus": {
      "command": "/path/to/shrimpicus/.venv/bin/shrimpicus-mcp"
    }
  }
}
```

The server uses `MCP_CHAT_ID` from `.env` (defaults to `0`) to scope all operations.

## Social Features

Shrimpicus now supports multi-user accounts with groups and friend connections.

### Getting Started

1. **Sign up** — Visit `http://127.0.0.1:5005` and create an account (3-20 character username, 6+ char password)
2. **Add friends** — Go to `/social` and add friends by username
3. **Create groups** — Create a group (up to 10 members), add friends to it
4. **Track progress** — See real-time stats for each group member (todos done today, habits logged today)

### Group Notifications (Discord)

When any user in a group:
- ✅ Completes **all their open todos** for the day, OR
- 🔥 Completes **2+ todos in one day**

The Discord bot sends a notification to the shared channel celebrating their progress.

### Data Migration

Existing todos, reminders, habits, and other data automatically belong to **User ID 1** (the default user). Create that account first to access your existing data, or your data will be isolated until you log in as user 1.

## Screenshots

### Login Page
![Login](docs/screenshots/login.png)

### Board (Kanban View)
![Board](docs/screenshots/board.png)

### Habits Tracker
![Habits](docs/screenshots/habits.png)

### Social Page
![Social](docs/screenshots/social.png)

## Changelog

### Unreleased

- **PostgreSQL support for production** — database layer now supports both SQLite (local development) and PostgreSQL (production hosting). Set `DATABASE_URL` in `.env` to use PostgreSQL. Migration script included (`migrate_to_postgres.py`) to transfer existing SQLite data to PostgreSQL.
- **Production deployment preparation** — added `psycopg2-binary` and `gunicorn` dependencies, created `.env.production.example` template, added `shrimpicus-bot` entrypoint alias. See `DEPLOYMENT_PLAN.md` for full hosting guide.
- **Social features with multi-user authentication** — user accounts with username/password (argon2 hashing), login/signup pages, session management. Create groups (max 10 members), add friends, and view real-time stats (todos done, habits logged) for each group member.
- **Group notifications** — Discord bot notifies groups when members complete all their daily todos or complete 2+ todos in one day. Notifications appear in the shared Discord channel with group context.
- **Multi-user data model** — all entities (todos, reminders, habits, birthdays, journal) now scoped to `user_id`. Existing data migrates to default user (ID 1) automatically.
- **Social page** — new `/social` web interface to manage groups, add friends by username, and see group members' daily progress at a glance.
- **RAG + tool calling** — the assistant now injects a context snapshot (todos, reminders, habits, completion count) into every free-text conversation and can directly add, complete, or modify your data via an agentic tool-calling loop. Natural commands like "add buy milk and mark todo 3 done" just work.
- **MCP server** — `shrimpicus-mcp` exposes the same tool registry over stdio so Claude Desktop (or any MCP client) can manage your todos/reminders/habits. Install with `pip install -e '.[mcp]'`.
- **Habit tracking** — log daily habits via Discord (`log_habit` tool, or "I went to the gym"), list habits with completion status, and auto-create habits on first mention. New `list_habits_text` and `log_habit_today` methods in `AssistantService`.
- **Database bug fix** — `set_meta` was unreachable dead code after `get_meta`'s return; split into a working method so the birthday scheduler no longer crashes on its daily check.
- **Habit tracker page** — new `/habits` page in the web viewer. Add habits, toggle today's completion with a tap, view current/longest streak stats per habit, 7-day history strip, and bottom totals panel (tracked count, done-today count, best streak). Habits scoped per chat like todos. Backend: `habits` + `habit_completions` tables in `db.py` and web app, streak calculation, `/api/habits/<id>/toggle` endpoint.
- **Feature roadmap** — added FEATURES.md documenting planned features including recurring reminders, habit tracking, social features, and expanded integrations.
- **Multi-page web interface** — the web viewer is now three pages: a drag-and-drop kanban **Board** (to_do/doing/done) backed by a new `status` column and `/api/todos/<id>/status` endpoint, an **XP** quest-log scoreboard, and a pixel **Field** that grows a daisy per completed todo (debug slider + WebAudio chiptune toggle).
- **Retro pixel-art web viewer** — `shrimpicus-web` launches a Flask app that reads the existing SQLite DB and renders a single-page Quest Log of todos. Stats panel with XP/HP completion bar, per-chat ("SELECT WORLD") filter, SHOW DEFEATED toggle. Theme synthesizes arcade-cabinet neon (cyan/lime/hot pink/gold), JRPG quest-log framing, and Game-Boy/CRT chrome (scanlines, vignette, boot-flicker, chunky pixel borders). Header has three pixel-SVG spinners (coin, floppy, star).
- **Todo categories with auto-classification** — todos are now grouped into Job / Home / Finance / General by keyword scoring of the task text. New `category` column on the todos table (idempotent ALTER TABLE migration). Two free-text shortcuts: `td <task>` to add and `tdl` to list (grouped by category).
- **Assistant channels and DM routing** — the bot now replies to free-text in any of: a DM, a message that mentions it, or a message in a channel listed in `ASSISTANT_CHANNELS` (comma-separated, default `general`). Previously required an @-mention everywhere.
- **Voice transcription** — audio attachments (`.ogg`/`.mp3`/`.wav`/`.m4a`/`.webm`/`.flac`) on free-text messages are downloaded, transcribed via faster-whisper on a worker thread, echoed back to the channel, and fed to the assistant. Optional install: `pip install -e .[voice]`. Configured via `WHISPER_ENABLED` / `WHISPER_MODEL`.
# shrimpicus_domain
