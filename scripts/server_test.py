from __future__ import annotations

import argparse
import asyncio
import json
import sys
from pathlib import Path

from mcp import ClientSession, StdioServerParameters
from mcp.client.stdio import stdio_client


ROOT = Path(__file__).resolve().parents[1]
SRC = ROOT / "src"
if str(SRC) not in sys.path:
    sys.path.insert(0, str(SRC))

from agentic_stack.config import DEFAULT_CONFIG, load_config, subprocess_env


DEFAULT_CALLS = {
    "holidays": (
        "is_public_holiday",
        {"country_code": "IT", "on_date": "2026-04-25"},
    ),
    "ops": ("get_current_oncall", {}),
}


async def run(server_name: str, tool_name: str, arguments: dict) -> None:
    config = load_config(DEFAULT_CONFIG)
    if server_name not in config.mcp_servers:
        known = ", ".join(sorted(config.mcp_servers))
        raise SystemExit(f"Unknown server {server_name!r}. Known servers: {known}")

    server = config.mcp_servers[server_name]
    params = StdioServerParameters(
        command=config.python,
        args=[str(server.script)],
        env=subprocess_env(server),
    )
    async with stdio_client(params) as (read, write):
        async with ClientSession(read, write) as session:
            await session.initialize()
            listed = await session.list_tools()
            print("Tools:")
            for tool in listed.tools:
                first_line = (tool.description or "").splitlines()[0]
                print(f"  - {tool.name}: {first_line}")

            print(f"\nCalling {tool_name}({arguments}):")
            result = await session.call_tool(tool_name, arguments=arguments)
            for chunk in result.content:
                text = getattr(chunk, "text", None)
                print(text if text is not None else chunk)


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Call one MCP server tool directly.")
    parser.add_argument("server", nargs="?", default="holidays", choices=sorted(DEFAULT_CALLS))
    parser.add_argument("tool", nargs="?")
    parser.add_argument("arguments", nargs="?", help="Tool arguments as a JSON object.")
    return parser


def main() -> int:
    args = build_parser().parse_args()
    default_tool, default_arguments = DEFAULT_CALLS[args.server]
    tool_name = args.tool or default_tool
    arguments = json.loads(args.arguments) if args.arguments else default_arguments
    if not isinstance(arguments, dict):
        raise SystemExit("arguments must be a JSON object")
    asyncio.run(run(args.server, tool_name, arguments))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
