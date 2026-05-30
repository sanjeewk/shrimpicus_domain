from __future__ import annotations

import re
from datetime import datetime, timedelta, timezone

from dateutil import parser as dt_parser

from shrimpicus.config import Settings
from shrimpicus.db import Database
from shrimpicus.notion import NotionService
from shrimpicus.obsidian import ObsidianJournal
from shrimpicus.ollama import OllamaClient


TODO_CATEGORIES = ("Job", "Home", "Finance", "General")

_CATEGORY_KEYWORDS: dict[str, tuple[str, ...]] = {
    "Job": (
        "work", "job", "office", "boss", "client", "meeting", "standup",
        "deadline", "report", "deck", "slides", "email", "interview",
        "resume", "cv", "linkedin", "project", "ticket", "jira", "pr",
        "code review", "deploy", "release", "presentation",
    ),
    "Home": (
        "home", "house", "kitchen", "laundry", "clean", "vacuum", "dishes",
        "groceries", "grocery", "fridge", "cook", "dinner", "lunch",
        "trash", "garbage", "repair", "fix", "plumber", "garden", "lawn",
        "vacation", "pack", "room",
    ),
    "Finance": (
        "pay", "bill", "rent", "mortgage", "loan", "invoice", "tax",
        "taxes", "bank", "credit", "card", "budget", "subscription",
        "insurance", "transfer", "deposit", "salary", "invest", "stock",
        "crypto", "expense", "refund",
    ),
}


def classify_todo(task: str) -> str:
    text = task.lower()
    scores: dict[str, int] = {}
    for category, keywords in _CATEGORY_KEYWORDS.items():
        hits = sum(1 for kw in keywords if re.search(rf"\b{re.escape(kw)}\b", text))
        if hits:
            scores[category] = hits
    if not scores:
        return "General"
    return max(scores.items(), key=lambda kv: kv[1])[0]


class AssistantService:
    def __init__(
        self,
        settings: Settings,
        db: Database,
        notion: NotionService,
        journal: ObsidianJournal,
        ollama: OllamaClient,
    ):
        self.settings = settings
        self.db = db
        self.notion = notion
        self.journal = journal
        self.ollama = ollama

    def add_reminder_minutes(self, chat_id: int, minutes: int, content: str, poll_required: bool = True) -> int:
        due_at = datetime.now(timezone.utc) + timedelta(minutes=minutes)
        return self.db.add_reminder(chat_id, content.strip(), due_at.isoformat(), poll_required=poll_required)

    def list_reminders_text(self, chat_id: int) -> str:
        reminders = self.db.list_reminders(chat_id)
        if not reminders:
            return "No reminders yet."
        lines = []
        for r in reminders:
            lines.append(f"#{r.id} [{r.status}] {r.due_at} - {r.content}")
        return "\n".join(lines)

    async def add_todo(self, chat_id: int, task: str, category: str | None = None) -> str:
        task = task.strip()
        category = category if category in TODO_CATEGORIES else classify_todo(task)
        notion_page_id = None
        if self.notion.enabled:
            try:
                notion_page_id = await self.notion.create_todo_page(task)
            except Exception as exc:  # noqa: BLE001
                notion_page_id = None
                err = f"(Notion sync failed: {exc})"
            else:
                err = ""
        else:
            err = ""

        todo_id = self.db.add_todo(chat_id, task, category=category, notion_page_id=notion_page_id)
        if notion_page_id:
            return f"Todo #{todo_id} [{category}] added and synced to Notion. {err}".strip()
        return f"Todo #{todo_id} [{category}] added. {err}".strip()

    def list_todos_text(self, chat_id: int) -> str:
        rows = self.db.list_todos(chat_id, include_done=False)
        if not rows:
            return "No open todos."
        grouped: dict[str, list[str]] = {c: [] for c in TODO_CATEGORIES}
        for row in rows:
            cat = row["category"] if "category" in row.keys() else "General"
            if cat not in grouped:
                grouped[cat] = []
            grouped[cat].append(f"#{row['id']} [ ] {row['task']}")
        lines: list[str] = []
        for cat in TODO_CATEGORIES:
            if grouped.get(cat):
                lines.append(f"**{cat}**")
                lines.extend(grouped[cat])
        return "\n".join(lines)

    def mark_todo_done(self, todo_id: int) -> str:
        self.db.set_todo_done(todo_id, True)
        return f"Marked todo #{todo_id} as done."

    def add_birthday(self, chat_id: int, person_name: str, date_text: str) -> str:
        dt = dt_parser.parse(date_text).date()
        birthday_id = self.db.add_birthday(chat_id, person_name.strip(), dt.isoformat())
        return f"Birthday #{birthday_id} saved for {person_name.strip()} on {dt.isoformat()}."

    def list_birthdays_text(self, chat_id: int) -> str:
        rows = self.db.list_birthdays(chat_id)
        if not rows:
            return "No birthdays saved."
        return "\n".join([f"#{r['id']} {r['person_name']} - {r['date_ymd']}" for r in rows])

    def journal(self, chat_id: int, content: str) -> str:
        file_path = self.journal.append(content)
        self.db.add_journal_entry(chat_id, content, file_path)
        if file_path:
            return f"Journal saved to {file_path}."
        return "Journal saved in database. Set OBSIDIAN_VAULT_PATH to write files."

    async def free_text(self, chat_id: int, text: str) -> str:
        parsed = await self._try_rule_based(chat_id, text)
        if parsed:
            return parsed
        try:
            return await self.ollama.answer(text)
        except Exception as exc:  # noqa: BLE001
            return (
                f"Ollama is unavailable ({exc}). Try !helpme for command-based control "
                "while the model is offline."
            )

    async def _try_rule_based(self, chat_id: int, text: str) -> str | None:
        t = text.strip()
        lower = t.lower()

        match = re.search(r"remind me to (.+) in (\d+)\s*(minute|minutes|min|hour|hours|day|days)", t, re.I)
        if match:
            content = match.group(1).strip()
            n = int(match.group(2))
            unit = match.group(3).lower()
            if unit.startswith("hour"):
                n *= 60
            elif unit.startswith("day"):
                n *= 60 * 24
            rid = self.add_reminder_minutes(chat_id, n, content, poll_required=True)
            return f"Reminder #{rid} added."

        if lower == "tdl" or lower.startswith("tdl "):
            return self.list_todos_text(chat_id)

        match = re.match(r"td\s+(.+)$", t, re.I)
        if match:
            task = match.group(1).strip()
            if task:
                return await self.add_todo(chat_id, task)

        if lower.startswith("add todo "):
            task = t[9:].strip()
            if task:
                return await self.add_todo(chat_id, task)

        if lower.startswith("journal "):
            content = t[8:].strip()
            if content:
                return self.journal(chat_id, content)

        match = re.search(r"birthday\s+(.+)\s+on\s+(.+)$", t, re.I)
        if match:
            return self.add_birthday(chat_id, match.group(1), match.group(2))

        match = re.search(r"done todo\s+#?(\d+)", t, re.I)
        if match:
            todo_id = int(match.group(1))
            return self.mark_todo_done(todo_id)

        return None
