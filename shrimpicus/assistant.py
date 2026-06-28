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
        bot=None,  # Optional Discord bot for social notifications
    ):
        self.settings = settings
        self.db = db
        self.notion = notion
        self.journal = journal
        self.ollama = ollama
        self.bot = bot

    def add_reminder_minutes(
        self,
        user_id: int,
        minutes: int,
        content: str,
        poll_required: bool = True,
        delivery_chat_id: int | None = None,
    ) -> int:
        due_at = datetime.now(timezone.utc) + timedelta(minutes=minutes)
        return self.db.add_reminder(
            user_id,
            delivery_chat_id if delivery_chat_id is not None else user_id,
            content.strip(),
            due_at.isoformat(),
            poll_required=poll_required,
        )

    def list_reminders_text(self, user_id: int) -> str:
        reminders = self.db.list_reminders(user_id)
        if not reminders:
            return "No reminders yet."
        lines = []
        for r in reminders:
            tag = ""
            if r.recur_kind:
                from shrimpicus import recur
                tag = f"[recurring {recur.describe_schedule(kind=r.recur_kind, time_hhmm=r.recur_time or '', dow=r.recur_dow, dom=r.recur_dom)}] "
            lines.append(f"#{r.id} [{r.status}] {tag}{r.due_at} - {r.content}")
        return "\n".join(lines)

    def list_recurring_reminders_text(self, user_id: int) -> str:
        reminders = self.db.list_recurring_reminders(user_id)
        if not reminders:
            return "No recurring reminders yet. Use add_recurring_reminder to create one."
        from shrimpicus import recur
        tz = self.db.get_user_timezone(user_id)
        lines = []
        for r in reminders:
            schedule = recur.describe_schedule(
                kind=r.recur_kind or "daily",
                time_hhmm=r.recur_time or "",
                dow=r.recur_dow,
                dom=r.recur_dom,
            )
            next_local = ""
            try:
                due_dt = dt_parser.parse(r.due_at)
                if due_dt.tzinfo is None:
                    due_dt = due_dt.replace(tzinfo=timezone.utc)
                next_local = recur.format_local(due_dt, tz)
            except Exception:
                next_local = r.due_at
            lines.append(f"#{r.id} [{schedule}] next: {next_local} - {r.content}")
        return "\n".join(lines)

    def add_recurring_reminder(
        self,
        user_id: int,
        kind: str,
        time_str: str,
        content: str,
        weekday: str | None = None,
        dom: int | None = None,
        delivery_chat_id: int | None = None,
    ) -> str:
        from shrimpicus import recur

        kind = (kind or "").strip().lower()
        if kind not in recur.VALID_KINDS:
            return f"kind must be one of {recur.VALID_KINDS}, got {kind!r}."
        content = (content or "").strip()
        if not content:
            return "Cannot add an empty reminder."

        dow: int | None = None
        dom_int: int | None = None
        if kind == "weekly":
            if not weekday:
                return "weekly reminders need a weekday (mon/tue/wed/thu/fri/sat/sun)."
            dow = recur.parse_weekday(weekday)
        elif kind == "monthly":
            if dom is None:
                return "monthly reminders need a day-of-month (1-31)."
            try:
                dom_int = int(dom)
            except (TypeError, ValueError):
                return "monthly day-of-month must be an integer 1-31."
            if not (1 <= dom_int <= 31):
                return "monthly day-of-month must be between 1 and 31."

        # Validate time format before touching the DB.
        try:
            recur.parse_time(time_str)
        except ValueError as exc:
            return f"Invalid time format: {exc}"

        tz = self.db.get_user_timezone(user_id)
        try:
            first_utc = recur.next_occurrence(
                kind=kind,
                after_utc=datetime.now(timezone.utc),
                user_tz=tz,
                time_hhmm=time_str,
                dow=dow,
                dom=dom_int,
            )
        except ValueError as exc:
            return f"Could not schedule recurring reminder: {exc}"

        rid = self.db.add_recurring_reminder(
            user_id=user_id,
            chat_id=delivery_chat_id if delivery_chat_id is not None else user_id,
            content=content,
            recur_kind=kind,
            recur_time=time_str,
            first_due_utc_iso=first_utc.isoformat(),
            recur_dow=dow,
            recur_dom=dom_int,
            poll_required=True,
        )
        schedule = recur.describe_schedule(kind=kind, time_hhmm=time_str, dow=dow, dom=dom_int)
        return (
            f"Recurring reminder #{rid} added ({schedule}). "
            f"Next fire: {recur.format_local(first_utc, tz)} ({tz})."
        )

    def delete_reminder(self, reminder_id: int, user_id: int) -> str:
        ok = self.db.delete_reminder(reminder_id, user_id)
        if ok:
            return f"Deleted reminder #{reminder_id}."
        return f"No reminder #{reminder_id} on your account."

    async def add_todo(
        self,
        user_id: int,
        task: str,
        category: str | None = None,
        delivery_chat_id: int | None = None,
    ) -> str:
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

        todo_id = self.db.add_todo(
            user_id,
            task,
            category=category,
            notion_page_id=notion_page_id,
            chat_id=delivery_chat_id,
        )
        if notion_page_id:
            return f"Todo #{todo_id} [{category}] added and synced to Notion. {err}".strip()
        return f"Todo #{todo_id} [{category}] added. {err}".strip()

    def list_todos_text(self, user_id: int) -> str:
        rows = self.db.list_todos(user_id, include_done=False)
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

    def mark_todo_done(self, todo_id: int, user_id: int, delivery_chat_id: int | None = None) -> str:
        if not self.db.set_todo_done(todo_id, True, user_id=user_id):
            return f"No todo #{todo_id} found for your account."
        # Trigger social notifications if bot is available
        if self.bot and delivery_chat_id:
            import asyncio
            from shrimpicus import social_notifications
            asyncio.create_task(
                social_notifications.check_and_notify_goals(self.db, self.bot, delivery_chat_id, user_id=user_id)
            )
        return f"Marked todo #{todo_id} as done."

    def add_birthday(
        self,
        user_id: int,
        person_name: str,
        date_text: str,
        delivery_chat_id: int | None = None,
    ) -> str:
        dt = dt_parser.parse(date_text).date()
        birthday_id = self.db.add_birthday(user_id, person_name.strip(), dt.isoformat(), chat_id=delivery_chat_id)
        return f"Birthday #{birthday_id} saved for {person_name.strip()} on {dt.isoformat()}."

    def list_birthdays_text(self, user_id: int) -> str:
        rows = self.db.list_birthdays(user_id)
        if not rows:
            return "No birthdays saved."
        return "\n".join([f"#{r['id']} {r['person_name']} - {r['date_ymd']}" for r in rows])

    def journal(self, user_id: int, content: str, delivery_chat_id: int | None = None) -> str:
        file_path = self.journal.append(content)
        self.db.add_journal_entry(user_id, content, file_path, chat_id=delivery_chat_id)
        if file_path:
            return f"Journal saved to {file_path}."
        return "Journal saved in database. Set OBSIDIAN_VAULT_PATH to write files."

    # --- habits ------------------------------------------------------------- #
    def list_habits_text(self, user_id: int) -> str:
        rows = self.db.list_habits(user_id)
        if not rows:
            return "No habits tracked yet."
        today = datetime.now(timezone.utc).date().isoformat()
        lines = []
        for h in rows:
            done = today in self.db.habit_completion_dates(h["id"])
            mark = "x" if done else " "
            lines.append(f"#{h['id']} [{mark}] {h['name']}")
        return "\n".join(lines)

    def log_habit_today(self, user_id: int, name_or_id: str) -> str:
        name_or_id = str(name_or_id).strip()
        if not name_or_id:
            return "Which habit? Give a name or id."
        habit = self.db.find_habit(user_id, name_or_id)
        if habit is None:
            # auto-create by name so "I went to the gym" just works
            if name_or_id.lstrip("#").isdigit():
                return f"No habit #{name_or_id.lstrip('#')} found."
            habit_id = self.db.add_habit(user_id, name_or_id)
            name = name_or_id
        else:
            habit_id = habit["id"]
            name = habit["name"]
        today = datetime.now(timezone.utc).date().isoformat()
        now_done = self.db.toggle_habit_completion(habit_id, today)
        if now_done:
            return f"Logged '{name}' for today. Keep the streak going."
        return f"Unlogged '{name}' for today."

    # --- RAG context -------------------------------------------------------- #
    def build_context(self, user_id: int) -> str:
        """Snapshot of the user's current state, injected into the LLM prompt."""
        parts: list[str] = []
        todos = self.list_todos_text(user_id)
        if todos and todos != "No open todos.":
            parts.append("OPEN TODOS:\n" + todos)
        reminders = self.list_reminders_text(user_id)
        if reminders and reminders != "No reminders yet.":
            parts.append("REMINDERS:\n" + reminders)
        habits = self.list_habits_text(user_id)
        if habits and habits != "No habits tracked yet.":
            parts.append("HABITS (today):\n" + habits)
        done_count = self.db.completed_todo_count(user_id)
        parts.append(f"Completed todos all-time: {done_count}.")
        if not parts:
            return "The user has no todos, reminders, or habits yet."
        return "\n\n".join(parts)

    async def free_text(self, user_id: int, text: str, delivery_chat_id: int | None = None) -> str:
        parsed = await self._try_rule_based(user_id, text, delivery_chat_id=delivery_chat_id)
        if parsed:
            return parsed
        try:
            acted = await self._run_agent(user_id, text, delivery_chat_id=delivery_chat_id)
            if acted:
                return acted
            return await self.ollama.answer(text)
        except Exception as exc:  # noqa: BLE001
            return (
                f"Ollama is unavailable ({exc}). Try !helpme for command-based control "
                "while the model is offline."
            )

    async def _run_agent(
        self,
        user_id: int,
        text: str,
        max_steps: int = 4,
        delivery_chat_id: int | None = None,
    ) -> str | None:
        """Agentic tool-calling loop with RAG context.

        Injects a snapshot of the user's data (RAG), offers the tool registry,
        and runs the model→tool→model loop until it produces a plain reply or
        the step budget is exhausted. Returns None if the model never used a
        tool *and* gave no content, so the caller can fall back to plain chat.
        """
        from shrimpicus import tools as tools_mod  # local import avoids a cycle

        context = self.build_context(user_id)
        messages: list[dict] = [
            {
                "role": "system",
                "content": (
                    "You are Shrimpicus, a concise personal assistant. Use the provided "
                    "tools to manage the user's todos, reminders, habits, birthdays, and "
                    "journal whenever they ask you to add, change, complete, or list "
                    "anything. Do not invent ids — call a list tool first if you need one. "
                    "After acting, confirm briefly in one or two sentences.\n\n"
                    "IMPORTANT: Only call each tool ONCE. Do not make duplicate tool calls.\n\n"
                    "Here is the user's current data for reference:\n" + context
                ),
            },
            {"role": "user", "content": text},
        ]
        schemas = tools_mod.ollama_tool_schemas()

        used_a_tool = False
        # Move seen_calls OUTSIDE the loop to persist across all steps
        seen_calls = {}

        for step in range(max_steps):
            msg = await self.ollama.chat(messages, tools=schemas)
            tool_calls = msg.get("tool_calls") or []

            # Debug logging
            if tool_calls:
                print(f"[DEBUG] Step {step}: Model requested {len(tool_calls)} tool call(s)")
                for i, call in enumerate(tool_calls):
                    fn = call.get("function", {})
                    print(f"  Tool {i+1}: {fn.get('name', 'unknown')}")

            if not tool_calls:
                content = (msg.get("content") or "").strip()
                if used_a_tool:
                    return content or "Done."
                return content or None

            used_a_tool = True

            # Echo the assistant turn that requested the tools
            # OpenRouter requires content field even if empty
            assistant_msg = dict(msg)
            if "content" not in assistant_msg or assistant_msg["content"] is None:
                assistant_msg["content"] = ""
            messages.append(assistant_msg)

            # Deduplicate tool calls - some models make identical duplicate calls
            # NOTE: seen_calls is now outside the loop to catch duplicates across multiple steps
            for call in tool_calls:
                fn = call.get("function", {})
                name = fn.get("name", "")
                args = fn.get("arguments") or {}
                if isinstance(args, str):
                    import json
                    try:
                        args = json.loads(args)
                    except json.JSONDecodeError:
                        args = {}

                # Create a signature for deduplication
                import json
                call_signature = (name, json.dumps(args, sort_keys=True))

                # Skip if we've already processed this exact call
                if call_signature in seen_calls:
                    print(f"[DEBUG] Skipping duplicate call to {name}")
                    continue

                seen_calls[call_signature] = True
                result = await tools_mod.dispatch(
                    self,
                    user_id,
                    name,
                    args,
                    delivery_chat_id=delivery_chat_id,
                )

                # Build tool response message
                tool_msg = {"role": "tool", "content": result}

                # Include tool_call_id if present (required by OpenRouter/OpenAI)
                tool_call_id = call.get("id")
                if tool_call_id:
                    tool_msg["tool_call_id"] = tool_call_id
                else:
                    # Fallback for Ollama which may not have id
                    tool_msg["name"] = name

                messages.append(tool_msg)

        # Ran out of steps mid-loop; surface whatever the last tool said.
        for m in reversed(messages):
            if m.get("role") == "tool":
                return m.get("content")
        return "I wasn't able to finish that."

    async def _try_rule_based(
        self,
        user_id: int,
        text: str,
        delivery_chat_id: int | None = None,
    ) -> str | None:
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
            rid = self.add_reminder_minutes(
                user_id,
                n,
                content,
                poll_required=True,
                delivery_chat_id=delivery_chat_id,
            )
            return f"Reminder #{rid} added."

        if lower == "tdl" or lower.startswith("tdl "):
            return self.list_todos_text(user_id)

        match = re.match(r"td\s+(.+)$", t, re.I)
        if match:
            task = match.group(1).strip()
            if task:
                return await self.add_todo(user_id, task, delivery_chat_id=delivery_chat_id)

        if lower.startswith("add todo "):
            task = t[9:].strip()
            if task:
                return await self.add_todo(user_id, task, delivery_chat_id=delivery_chat_id)

        if lower.startswith("journal "):
            content = t[8:].strip()
            if content:
                return self.journal(user_id, content, delivery_chat_id=delivery_chat_id)

        match = re.search(r"birthday\s+(.+)\s+on\s+(.+)$", t, re.I)
        if match:
            return self.add_birthday(user_id, match.group(1), match.group(2), delivery_chat_id=delivery_chat_id)

        match = re.search(r"done todo\s+#?(\d+)", t, re.I)
        if match:
            todo_id = int(match.group(1))
            return self.mark_todo_done(todo_id, user_id, delivery_chat_id=delivery_chat_id)

        return None
