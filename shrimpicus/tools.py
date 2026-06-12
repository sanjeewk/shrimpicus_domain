"""Single source of truth for assistant tools.

Each :class:`Tool` carries a JSON Schema (consumed by Ollama's ``tools`` array
*and* by the MCP server's ``list_tools``) plus an async handler that runs the
action against :class:`AssistantService`.

The ``chat_id`` is **never** a tool parameter — it is injected by the caller
(``dispatch``) from a trusted context (the Discord channel id, or the MCP
server's configured default). The model only ever picks a tool name and its
domain arguments, so it cannot reach another chat's data by naming an id.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import TYPE_CHECKING, Any, Awaitable, Callable

if TYPE_CHECKING:  # avoid a circular import; AssistantService imports this module
    from shrimpicus.assistant import AssistantService

Handler = Callable[["AssistantService", int, dict[str, Any]], Awaitable[str]]


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
async def _add_todo(svc: "AssistantService", chat_id: int, args: dict[str, Any]) -> str:
    task = str(args.get("task", "")).strip()
    if not task:
        return "Cannot add an empty todo."
    category = args.get("category") or None
    return await svc.add_todo(chat_id, task, category)


async def _list_todos(svc: "AssistantService", chat_id: int, args: dict[str, Any]) -> str:
    return svc.list_todos_text(chat_id)


async def _complete_todo(svc: "AssistantService", chat_id: int, args: dict[str, Any]) -> str:
    return svc.mark_todo_done(int(args["todo_id"]))


async def _set_todo_status(svc: "AssistantService", chat_id: int, args: dict[str, Any]) -> str:
    status = str(args["status"]).strip().lower()
    todo_id = int(args["todo_id"])
    try:
        svc.db.set_todo_status(todo_id, status)
    except ValueError as exc:
        return str(exc)
    return f"Todo #{todo_id} moved to {status}."


async def _add_reminder(svc: "AssistantService", chat_id: int, args: dict[str, Any]) -> str:
    minutes = int(args["minutes"])
    content = str(args.get("content", "")).strip()
    if minutes <= 0 or not content:
        return "Need a positive minute count and reminder text."
    rid = svc.add_reminder_minutes(chat_id, minutes, content, poll_required=True)
    return f"Reminder #{rid} set in {minutes} minute(s)."


async def _list_reminders(svc: "AssistantService", chat_id: int, args: dict[str, Any]) -> str:
    return svc.list_reminders_text(chat_id)


async def _add_habit(svc: "AssistantService", chat_id: int, args: dict[str, Any]) -> str:
    name = str(args.get("name", "")).strip()
    if not name:
        return "Cannot add an unnamed habit."
    hid = svc.db.add_habit(chat_id, name)
    return f"Habit #{hid} '{name}' added."


async def _list_habits(svc: "AssistantService", chat_id: int, args: dict[str, Any]) -> str:
    return svc.list_habits_text(chat_id)


async def _log_habit(svc: "AssistantService", chat_id: int, args: dict[str, Any]) -> str:
    return svc.log_habit_today(chat_id, args.get("name_or_id", ""))


async def _add_birthday(svc: "AssistantService", chat_id: int, args: dict[str, Any]) -> str:
    return svc.add_birthday(chat_id, str(args["name"]), str(args["date"]))


async def _list_birthdays(svc: "AssistantService", chat_id: int, args: dict[str, Any]) -> str:
    return svc.list_birthdays_text(chat_id)


async def _add_journal(svc: "AssistantService", chat_id: int, args: dict[str, Any]) -> str:
    content = str(args.get("content", "")).strip()
    if not content:
        return "Nothing to journal."
    return svc.journal(chat_id, content)


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
        description="List the user's current open (not done) todos, grouped by category.",
        parameters={"type": "object", "properties": {}},
        handler=_list_todos,
    ),
    Tool(
        name="complete_todo",
        description="Mark a todo as done by its id number.",
        parameters={
            "type": "object",
            "properties": {"todo_id": {"type": "integer"}},
            "required": ["todo_id"],
        },
        handler=_complete_todo,
    ),
    Tool(
        name="set_todo_status",
        description="Move a todo on the kanban board. Status is one of to_do, doing, done.",
        parameters={
            "type": "object",
            "properties": {
                "todo_id": {"type": "integer"},
                "status": {"type": "string", "enum": ["to_do", "doing", "done"]},
            },
            "required": ["todo_id", "status"],
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
    chat_id: int,
    name: str,
    args: dict[str, Any] | None,
) -> str:
    """Run a tool by name. Errors are returned as text so the model can recover."""
    tool = TOOLS_BY_NAME.get(name)
    if tool is None:
        return f"Unknown tool: {name}"
    try:
        return await tool.handler(assistant, chat_id, args or {})
    except (KeyError, ValueError, TypeError) as exc:
        return f"Tool {name} got bad arguments: {exc}"
    except Exception as exc:  # noqa: BLE001 — surface, don't crash the loop
        return f"Tool {name} failed: {exc}"
