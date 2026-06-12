"""MCP server exposing Shrimpicus tools to any MCP client (Claude Desktop, etc.).

This reuses the *exact same* tool registry as the Discord agent loop
(:mod:`shrimpicus.tools`), so there is one source of truth for what the
assistant can do. The server builds its own :class:`AssistantService` with the
same wiring as ``main.py``.

Because MCP has no Discord channel, the ``chat_id`` that every tool is scoped to
comes from config: ``MCP_CHAT_ID`` (falls back to ``0``). Run it with::

    shrimpicus-mcp

or point an MCP client's ``command`` at that entry point. Transport is stdio.
"""

from __future__ import annotations

import asyncio

from shrimpicus import tools as tools_mod
from shrimpicus.assistant import AssistantService
from shrimpicus.config import Settings
from shrimpicus.db import Database
from shrimpicus.notion import NotionService
from shrimpicus.obsidian import ObsidianJournal
from shrimpicus.ollama import OllamaClient

try:
    from mcp.server import Server
    from mcp.server.stdio import stdio_server
    import mcp.types as mcp_types
except ImportError as exc:  # pragma: no cover - optional dependency
    raise SystemExit(
        "The MCP server needs the 'mcp' package. Install it with:\n"
        "    pip install -e '.[mcp]'"
    ) from exc


def _build_assistant(settings: Settings) -> AssistantService:
    db = Database(settings.db_file)
    db.init()
    notion = NotionService(settings)
    journal = ObsidianJournal(settings.obsidian_journal_file)
    ollama = OllamaClient(settings)
    return AssistantService(settings, db, notion, journal, ollama)


def build_server() -> Server:
    settings = Settings()
    assistant = _build_assistant(settings)
    chat_id = settings.mcp_chat_id

    server = Server("shrimpicus")

    @server.list_tools()
    async def list_tools() -> list[mcp_types.Tool]:
        return [
            mcp_types.Tool(
                name=t.name,
                description=t.description,
                inputSchema=t.parameters,
            )
            for t in tools_mod.TOOLS
        ]

    @server.call_tool()
    async def call_tool(name: str, arguments: dict | None) -> list[mcp_types.TextContent]:
        result = await tools_mod.dispatch(assistant, chat_id, name, arguments or {})
        return [mcp_types.TextContent(type="text", text=result)]

    return server


async def _run() -> None:
    server = build_server()
    async with stdio_server() as (read_stream, write_stream):
        await server.run(
            read_stream,
            write_stream,
            server.create_initialization_options(),
        )


def main() -> None:
    asyncio.run(_run())


if __name__ == "__main__":
    main()
