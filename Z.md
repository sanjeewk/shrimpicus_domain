# Z.md

This file gives condensed context about the Shrimpicus repo for quick reference when asking questions. It complements `CLAUDE.md` (which focuses on workflow/conventions) by summarizing *what the project is* and *where things live*.

## What it is

Shrimpicus is a **social task-management assistant**. It started as a single-process Discord bot and grew into three surfaces that share one data store:

1. **Discord bot** (`bot.py`) — prefixed commands (`!remind`, `!todo`, `!birthday`, `!journal`, `!ask`) plus free-text routing to an LLM assistant.
2. **Web app** (`web/app.py`) — Flask with login/signup, a kanban Board, a Habits tracker, an XP/quest scoreboard, a pixel-art "Field", and a `/social` page for friends/groups.
3. **MCP server** (`mcp_server.py`) — exposes the same tool registry over stdio so external clients (Claude Desktop) can manage todos/reminders/habits.

The pitch: self-improvement works better with friends. Letting your group see your todos/habits/progress adds recognition and accountability.

Named after the author's late pet cleaner shrimp.

## Entry points (pyproject `[project.scripts]`)

- `shrimpicus` / `shrimpicus-bot` → `shrimpicus.main:main` (the Discord bot)
- `shrimpicus-web` → `shrimpicus.web.app:main` (Flask UI)
- `shrimpicus-mcp` → `shrimpicus.mcp_server:main` (MCP server, install with `pip install -e '.[mcp]'`)
- `shrimpicus-all` → `shrimpicus.run_all:main` (runs Discord bot + Flask web app together; web in daemon thread, bot in main asyncio loop)
- Optional voice support: `pip install -e '.[voice]'` (faster-whisper)

## Architecture / module map

```
config.Settings ──► pydantic-settings, reads <repo>/.env
        │
        ▼
db.Database (sqlite or postgres via DATABASE_URL)
        │
   ┌────┴─────────────────────────────────┐
   ▼                                      ▼
integrations:                          AssistantService (assistant.py)
 notion.py   (optional Notion pages)     - sole business-logic layer over DB + integrations
 obsidian.py (markdown journal, noop     - rule-based free-text shortcuts (_try_rule_based)
   if vault path empty)                  - RAG + tool-calling agent loop (ollama/openrouter)
 ollama.py   (local or OpenRouter via    - exposes every feature as a method; bot.py + mcp + web call it
   openai SDK)
 transcribe.py (faster-whisper)
        │
        ▼
bot.build_bot() ──► discord.py commands.Bot
        │              on_message routes non-prefixed text → AssistantService.free_text
        ▼
ShrimpScheduler (scheduler.py) — APScheduler AsyncIOScheduler
   - interval job: poll due reminders
   - interval job: daily birthday check (idempotent via meta table)
   - attached to bot as `bot.shrimp_scheduler`, started from on_ready (needs bot's loop)
```

**Key seams (read these first when contributing):**

- `assistant.py:AssistantService` — the *only* layer that touches DB + integrations. Add new features here first, then expose from `bot.py` / `web/app.py` / `mcp_server.py`.
- `tools.py` — single source of truth for assistant tools. Each `Tool` has a JSON Schema (consumed by both Ollama and the MCP server) + an async handler. The `user_id`/chat id is **never** a tool parameter; it's injected by the dispatcher from trusted context (Discord channel id or MCP's `MCP_CHAT_ID`), so the model cannot reach another user's data by guessing ids.
- `db.py` — schema is created idempotently in `Database.init()`. Supports both SQLite (`db_path`) and PostgreSQL (`DATABASE_URL`, autodetected by `postgresql://` prefix). Uses `sqlite3.Row` / `psycopg2.extras.RealDictRow` for dict-like rows. Connection is shared across threads (`check_same_thread=False`) because APScheduler jobs and the discord.py loop both touch it.
- `bot.py` — has both `@bot.command(...)` handlers *and* an `on_message` that routes non-prefixed text. Free-text replies fire on: a DM, an @-mention, or any channel whose name is in `ASSISTANT_CHANNELS` (default `general`). Audio attachments are transcribed and fed to the assistant.
- `web/app.py` — standalone Flask app; reads the same DB the bot writes. Implements its own auth (argon2 via `auth.py`), session cookies, REST endpoints (`/api/todos/<id>/status`, `/api/habits/<id>/toggle`, etc.). Renders retro pixel-art templates from `web/templates/*.html`.

## Data model (db.py tables)

- `users` — id, username, argon2 hash, optional `discord_user_id` / `discord_display_name` for Discord↔web linking
- `todos` — `status` (to_do/doing/done), `category` (auto-classified Job/Home/Finance/General), `due_at`, `user_id`
- `reminders` — `due_at` (UTC ISO), `status` (pending/awaiting_poll/completed), `poll_required`, `poll_id`, scoped by `user_id` + `chat_id`
- `habits` + `habit_completions` — streak tracking
- `birthdays`, `journal_entries`
- `groups` + `group_members` (max 10) + `friends` — social graph
- `meta` — key/value (e.g. `last_birthday_check_date`) for idempotent scheduler jobs

Existing single-user data defaults to **user ID 1**; the Discord bot maps Discord users to `users` rows via `get_or_create_user_for_discord`.

## Reminder lifecycle

`pending` → (due, polled by scheduler) → if `poll_required`: `awaiting_poll` + Discord button view (`ReminderCheckinView`, `timeout=None`, recreated per send so stale buttons die after restart) → "Yes" → `completed`; "No" → snoozed back to `pending` with `due_at += default_snooze_minutes`.

## Optional integrations

Gated by **config presence**, not feature flags:
- `NotionService.enabled` ← `notion_token` + `notion_database_id`. Sync failures are swallowed and surfaced in the user-facing reply, not raised.
- `ObsidianJournal` ← `obsidian_vault_path`; no-ops when empty but the journal row is still saved to DB.
- Voice ← `WHISPER_ENABLED` / `WHISPER_MODEL` (needs the `[voice]` extra).
- LLM provider ← `LLM_PROVIDER` (`ollama` default, or `openrouter` for hosted models).

## Configuration

Loaded by `pydantic-settings` from `<repo-root>/.env`. The path is resolved relative to `config.py:parent.parent` (i.e. the repo root), so running from another cwd works but moving the package breaks env loading. Only `DISCORD_BOT_TOKEN` is required; see `.env.example`.

Notable settings: `tz`, `db_path`, `database_url`, `check_interval_seconds` (reminder poll), `default_snooze_minutes`, `assistant_channels`, `mcp_chat_id` (scopes MCP ops, default `0`), `web_host`/`web_port` (default `127.0.0.1:5005`), `secret_key` (Flask sessions).

## Commands (Discord)

`!start`, `!helpme`, `!remind <minutes> <text>`, `!list`, `!todo add <task>`, `!todo list`, `!birthday add <name> <YYYY-MM-DD>`, `!birthday list`, `!journal <text>`, `!ask <question>`. Free-text shortcuts: `td <task>` (add), `tdl` (list, grouped by category).

## Setup

```bash
python -m venv .venv
source .venv/bin/activate
pip install -e .          # add [mcp] and/or [voice] as needed
cp .env.example .env      # set DISCORD_BOT_TOKEN
shrimpicus                # bot; also: shrimpicus-web, shrimpicus-mcp
```

Requires Python >= 3.11. **No test suite, linter, or build step is configured.**

## Gotchas worth remembering

- Times in `reminders.due_at` are **UTC ISO strings**; APScheduler runs in `settings.tz`. Insert/compare with `datetime.now(timezone.utc).isoformat()` to stay consistent.
- The scheduler must be started from `on_ready` (needs the bot's event loop), never from `main.py` before login.
- `ReminderCheckinView` has `timeout=None` and is recreated per send — buttons in old chat history are dead after a restart.
- The DB connection is shared across threads (`check_same_thread=False`).
- Pre-existing `.venv` lives at `shrimpicus/.venv` (inside the package dir), not the repo root.
- `main.py` has a stale absolute path in the missing-token error message — cosmetic.
- Default Discord user mapping: existing data → user ID 1; new Discord users get their own rows.

## Commit workflow (see CLAUDE.md)

Commit after every feature/fix; tag messages `[feat]` / `[ref]` / `[doc]` / `[bug]`; update the **Changelog** section at the bottom of `README.md` under `### Unreleased` (newest entry on top) in the same commit. Check `git status` before starting a new task and remind the user to commit uncommitted work first.
