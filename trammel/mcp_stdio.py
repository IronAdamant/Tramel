"""Stdio-based MCP server for Trammel using the ``mcp`` Python package.

Entry point::

    trammel-mcp              (installed via pyproject.toml console_scripts)
    python -m trammel.mcp_stdio

Requires the optional ``mcp`` dependency:
    pip install trammel[mcp]
"""

from __future__ import annotations

import asyncio
import json
import logging
import os
import sys
from typing import Any

from .mcp_server import _TOOL_SCHEMAS, dispatch_tool
from .store import RecipeStore
from .utils import DEFAULT_DB_PATH

logging.basicConfig(level=logging.WARNING, stream=sys.stderr)
logger = logging.getLogger(__name__)

try:
    from mcp.server import Server
    from mcp.server.stdio import stdio_server
    from mcp.types import TextContent, Tool

    _MCP_AVAILABLE = True
except ImportError:
    _MCP_AVAILABLE = False


def _configure_server(db_path: str) -> Server:
    """Register all Trammel tools on an MCP Server instance.

    Each tool call creates its own ``RecipeStore`` (and thus its own
    ``sqlite3.Connection``) inside the worker thread spawned by
    ``asyncio.to_thread``.  This avoids the *"SQLite objects created in a
    thread can only be used in that same thread"* error that occurs when a
    connection created on the event-loop thread is reused in a worker.
    """
    server = Server("trammel")

    @server.list_tools()
    async def list_tools() -> list[Tool]:
        return [
            Tool(
                name=name,
                description=schema["description"],
                inputSchema=schema["parameters"],
            )
            for name, schema in _TOOL_SCHEMAS.items()
        ]

    @server.call_tool()
    async def call_tool(name: str, arguments: dict[str, Any]) -> list[TextContent]:
        try:
            def _run() -> object:
                with RecipeStore(db_path) as thread_store:
                    return dispatch_tool(thread_store, name, arguments)

            result = await asyncio.to_thread(_run)
        except Exception as exc:
            logger.exception("Error executing tool %s", name)
            return [TextContent(type="text", text=f"Error: {exc}")]

        text = json.dumps(result, indent=2, default=str)
        return [TextContent(type="text", text=text)]

    return server


async def _run_server() -> None:
    """Start the stdio MCP server and run until the client disconnects."""
    db_path = os.environ.get("TRAMMEL_DB_PATH", DEFAULT_DB_PATH)
    server = _configure_server(db_path)

    async with stdio_server() as (read_stream, write_stream):
        await server.run(
            read_stream,
            write_stream,
            server.create_initialization_options(),
        )


def main() -> None:
    """Entry point for ``trammel-mcp`` console script."""
    if not _MCP_AVAILABLE:
        print(
            "Error: The 'mcp' package is not installed.\n"
            "\n"
            "The Trammel stdio MCP server requires the 'mcp' Python package.\n"
            "Install it with:\n"
            "\n"
            "    pip install trammel[mcp]\n"
            "\n"
            "Or install the mcp package directly:\n"
            "\n"
            "    pip install mcp\n",
            file=sys.stderr,
        )
        sys.exit(1)

    try:
        asyncio.run(_run_server())
    except KeyboardInterrupt:
        pass


if __name__ == "__main__":
    main()
