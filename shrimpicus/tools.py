"""Single source of truth for assistant tools.

Each :class:`Tool` carries a JSON Schema (consumed by Ollama's ``tools`` array
*and* by the MCP server's ``list_tools``) plus an async handler that runs the
action against :class:`AssistantService`.

The ``user_id``/delivery chat is **never** a tool parameter — it is injected by the caller
(``dispatch``) from a trusted context (the Discord channel id, or the MCP
server's configured default). The model only ever picks a tool name and its
domain arguments, so it cannot reach another chat's data by naming an id.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import TYPE_CHECKING, Any, Awaitable, Callable

if TYPE_CHECKING:  # avoid a circular import; AssistantService imports this module
    from shrimpicus.assistant import AssistantService

Handler = Callable[["AssistantService", int, dict[str, Any], int | None], Awaitable[str]]


@dataclass(frozen=True)
class Tool:
    name: str
    description: str
    parameters: dict[str, Any]  # JSON Schema for the arguments object
    handler: Handler

    def ollama_schema(self) -> dict[str, Any]:
        """Shape expected by Ollama's /api/chat ``tools`` array."""
        return {
            "type": "function",
            "function": {
                "name": self.name,
                "description": self.description,
                "parameters": self.parameters,
            },
        }


# --------------------------------------------------------------------------- #
# Handlers — thin adapters over AssistantService. Keep arg coercion here so the
# model can be sloppy (ints as strings, missing optionals) without crashing.
# --------------------------------------------------------------------------- #
async def _add_todo(svc: "AssistantService", user_id: int, args: dict[str, Any], delivery_chat_id: int | None) -> str:
    task = str(args.get("task", "")).strip()
    if not task:
        return "Cannot add an empty todo."
    category = args.get("category") or None
    return await svc.add_todo(user_id, task, category, delivery_chat_id=delivery_chat_id)


async def _list_todos(svc: "AssistantService", user_id: int, args: dict[str, Any], delivery_chat_id: int | None) -> str:
    return svc.list_todos_text_indexed(user_id)


async def _complete_todo(svc: "AssistantService", user_id: int, args: dict[str, Any], delivery_chat_id: int | None) -> str:
    try:
        position = int(args["position"])
    except (KeyError, TypeError, ValueError):
        return "position must be an integer (1-indexed, as shown by list_todos)."
    todo_id = svc.todo_id_at_position(user_id, position)
    if todo_id is None:
        return f"No todo at position {position}. Call list_todos to see current positions."
    return svc.mark_todo_done(todo_id, user_id, delivery_chat_id=delivery_chat_id)


async def _set_todo_status(svc: "AssistantService", user_id: int, args: dict[str, Any], delivery_chat_id: int | None) -> str:
    status = str(args["status"]).strip().lower()
    try:
        position = int(args["position"])
    except (KeyError, TypeError, ValueError):
        return "position must be an integer (1-indexed, as shown by list_todos)."
    todo_id = svc.todo_id_at_position(user_id, position)
    if todo_id is None:
        return f"No todo at position {position}. Call list_todos to see current positions."
    try:
        updated = svc.db.set_todo_status(todo_id, status, user_id=user_id)
    except ValueError as exc:
        return str(exc)
    if not updated:
        return f"No todo at position {position}."
    return f"Todo at position {position} moved to {status}."


async def _add_reminder(svc: "AssistantService", user_id: int, args: dict[str, Any], delivery_chat_id: int | None) -> str:
    minutes = int(args["minutes"])
    content = str(args.get("content", "")).strip()
    if minutes <= 0 or not content:
        return "Need a positive minute count and reminder text."
    rid = svc.add_reminder_minutes(user_id, minutes, content, poll_required=True, delivery_chat_id=delivery_chat_id)
    return f"Reminder #{rid} set in {minutes} minute(s)."


async def _list_reminders(svc: "AssistantService", user_id: int, args: dict[str, Any], delivery_chat_id: int | None) -> str:
    return svc.list_reminders_text(user_id)


async def _add_recurring_reminder(svc: "AssistantService", user_id: int, args: dict[str, Any], delivery_chat_id: int | None) -> str:
    kind = str(args["kind"]).strip().lower()
    time_str = str(args["time"]).strip()
    content = str(args.get("content", "")).strip()
    weekday = args.get("weekday")
    day_of_month = args.get("day_of_month")
    if not content:
        return "Cannot add an empty reminder."
    return svc.add_recurring_reminder(
        user_id, kind, time_str, content,
        weekday=str(weekday) if weekday is not None else None,
        dom=int(day_of_month) if day_of_month is not None else None,
        delivery_chat_id=delivery_chat_id,
    )


async def _list_recurring_reminders(svc: "AssistantService", user_id: int, args: dict[str, Any], delivery_chat_id: int | None) -> str:
    return svc.list_recurring_reminders_text(user_id)


async def _delete_reminder(svc: "AssistantService", user_id: int, args: dict[str, Any], delivery_chat_id: int | None) -> str:
    try:
        rid = int(args["reminder_id"])
    except (KeyError, TypeError, ValueError):
        return "reminder_id must be an integer."
    return svc.delete_reminder(rid, user_id)


async def _add_habit(svc: "AssistantService", user_id: int, args: dict[str, Any], delivery_chat_id: int | None) -> str:
    name = str(args.get("name", "")).strip()
    if not name:
        return "Cannot add an unnamed habit."
    hid = svc.db.add_habit(user_id, name, chat_id=delivery_chat_id)
    return f"Habit #{hid} '{name}' added."


async def _list_habits(svc: "AssistantService", user_id: int, args: dict[str, Any], delivery_chat_id: int | None) -> str:
    return svc.list_habits_text(user_id)


async def _log_habit(svc: "AssistantService", user_id: int, args: dict[str, Any], delivery_chat_id: int | None) -> str:
    return svc.log_habit_today(user_id, args.get("name_or_id", ""))


async def _add_birthday(svc: "AssistantService", user_id: int, args: dict[str, Any], delivery_chat_id: int | None) -> str:
    return svc.add_birthday(user_id, str(args["name"]), str(args["date"]), delivery_chat_id=delivery_chat_id)


async def _list_birthdays(svc: "AssistantService", user_id: int, args: dict[str, Any], delivery_chat_id: int | None) -> str:
    return svc.list_birthdays_text(user_id)


async def _add_journal(svc: "AssistantService", user_id: int, args: dict[str, Any], delivery_chat_id: int | None) -> str:
    content = str(args.get("content", "")).strip()
    if not content:
        return "Nothing to journal."
    return svc.journal(user_id, content, delivery_chat_id=delivery_chat_id)


# --------------------------------------------------------------------------- #
# Registry
# --------------------------------------------------------------------------- #
TOOLS: tuple[Tool, ...] = (
    Tool(
        name="add_todo",
        description="Add a new todo/task for the user. Category is auto-detected if omitted.",
        parameters={
            "type": "object",
            "properties": {
                "task": {"type": "string", "description": "The task text."},
                "category": {
                    "type": "string",
                    "enum": ["Job", "Home", "Finance", "General"],
                    "description": "Optional category. Leave out to auto-classify.",
                },
            },
            "required": ["task"],
        },
        handler=_add_todo,
    ),
    Tool(
        name="list_todos",
        description=(
            "List the user's current open (not done) todos. Returns a "
            "1-indexed position list grouped by category — NO database ids "
            "are exposed. Use the position number (1, 2, 3...) as the "
            "'position' argument in complete_todo / set_todo_status."
        ),
        parameters={"type": "object", "properties": {}},
        handler=_list_todos,
    ),
    Tool(
        name="complete_todo",
        description=(
            "Mark a todo as done by its 1-indexed position (NOT a database "
            "id). The position comes from list_todos. Positions reflect the "
            "current open-todo list; if it has changed since you listed, "
            "re-list first."
        ),
        parameters={
            "type": "object",
            "properties": {"position": {"type": "integer", "minimum": 1}},
            "required": ["position"],
        },
        handler=_complete_todo,
    ),
    Tool(
        name="set_todo_status",
        description=(
            "Move a todo on the kanban board by its 1-indexed position (NOT "
            "a database id). The position comes from list_todos. Status is "
            "one of to_do, doing, done."
        ),
        parameters={
            "type": "object",
            "properties": {
                "position": {"type": "integer", "minimum": 1},
                "status": {"type": "string", "enum": ["to_do", "doing", "done"]},
            },
            "required": ["position", "status"],
        },
        handler=_set_todo_status,
    ),
    Tool(
        name="add_reminder",
        description="Remind the user about something after a number of minutes from now.",
        parameters={
            "type": "object",
            "properties": {
                "minutes": {"type": "integer", "description": "Minutes from now."},
                "content": {"type": "string", "description": "What to be reminded about."},
            },
            "required": ["minutes", "content"],
        },
        handler=_add_reminder,
    ),
    Tool(
        name="list_reminders",
        description="List the user's reminders with their status and due time.",
        parameters={"type": "object", "properties": {}},
        handler=_list_reminders,
    ),
    Tool(
        name="add_recurring_reminder",
        description=(
            "Schedule a recurring reminder that fires on a fixed cadence. "
            "Use for habits like 'standup every Monday 09:00' or 'pay rent "
            "monthly on the 1st at 10:00'. For one-shot 'in N minutes' "
            "reminders use add_reminder instead. Times are interpreted in "
            "the user's configured timezone (default UTC)."
        ),
        parameters={
            "type": "object",
            "properties": {
                "kind": {"type": "string", "enum": ["daily", "weekly", "monthly"]},
                "time": {
                    "type": "string",
                    "description": "Local time in HH:MM 24-hour format, e.g. '09:00'.",
                },
                "content": {"type": "string", "description": "What to be reminded about."},
                "weekday": {
                    "type": "string",
                    "enum": ["mon", "tue", "wed", "thu", "fri", "sat", "sun"],
                    "description": "Required when kind=weekly. Ignored otherwise.",
                },
                "day_of_month": {
                    "type": "integer",
                    "minimum": 1,
                    "maximum": 31,
                    "description": "Required when kind=monthly. Day-of-month; short months clamp to last day.",
                },
            },
            "required": ["kind", "time", "content"],
        },
        handler=_add_recurring_reminder,
    ),
    Tool(
        name="list_recurring_reminders",
        description=(
            "List only the user's recurring (daily/weekly/monthly) reminders "
            "with their schedule and next fire time. Use list_reminders for "
            "all reminders including one-shot."
        ),
        parameters={"type": "object", "properties": {}},
        handler=_list_recurring_reminders,
    ),
    Tool(
        name="delete_reminder",
        description=(
            "Permanently delete a reminder by id. Works for both one-shot and "
            "recurring reminders. Use list_reminders or list_recurring_reminders "
            "first to find the id."
        ),
        parameters={
            "type": "object",
            "properties": {"reminder_id": {"type": "integer"}},
            "required": ["reminder_id"],
        },
        handler=_delete_reminder,
    ),
    Tool(
        name="add_habit",
        description="Create a new habit to track (e.g. 'gym', 'read', 'meditate').",
        parameters={
            "type": "object",
            "properties": {"name": {"type": "string"}},
            "required": ["name"],
        },
        handler=_add_habit,
    ),
    Tool(
        name="list_habits",
        description="List the user's habits and whether each was done today.",
        parameters={"type": "object", "properties": {}},
        handler=_list_habits,
    ),
    Tool(
        name="log_habit",
        description="Log a habit as done for today, by habit name or id. Creates the habit if it does not exist.",
        parameters={
            "type": "object",
            "properties": {
                "name_or_id": {
                    "type": "string",
                    "description": "Habit name (e.g. 'gym') or its numeric id.",
                }
            },
            "required": ["name_or_id"],
        },
        handler=_log_habit,
    ),
    Tool(
        name="add_birthday",
        description="Save a person's birthday.",
        parameters={
            "type": "object",
            "properties": {
                "name": {"type": "string"},
                "date": {"type": "string", "description": "A date like 1998-07-10."},
            },
            "required": ["name", "date"],
        },
        handler=_add_birthday,
    ),
    Tool(
        name="list_birthdays",
        description="List saved birthdays.",
        parameters={"type": "object", "properties": {}},
        handler=_list_birthdays,
    ),
    Tool(
        name="add_journal",
        description="Append a journal note for the user.",
        parameters={
            "type": "object",
            "properties": {"content": {"type": "string"}},
            "required": ["content"],
        },
        handler=_add_journal,
    ),
)

TOOLS_BY_NAME: dict[str, Tool] = {t.name: t for t in TOOLS}


def ollama_tool_schemas() -> list[dict[str, Any]]:
    return [t.ollama_schema() for t in TOOLS]


async def dispatch(
    assistant: "AssistantService",
    user_id: int,
    name: str,
    args: dict[str, Any] | None,
    delivery_chat_id: int | None = None,
) -> str:
    """Run a tool by name. Errors are returned as text so the model can recover."""
    tool = TOOLS_BY_NAME.get(name)
    if tool is None:
        return f"Unknown tool: {name}"
    try:
        return await tool.handler(assistant, user_id, args or {}, delivery_chat_id)
    except (KeyError, ValueError, TypeError) as exc:
        return f"Tool {name} got bad arguments: {exc}"
    except Exception as exc:  # noqa: BLE001 — surface, don't crash the loop
        return f"Tool {name} failed: {exc}"
