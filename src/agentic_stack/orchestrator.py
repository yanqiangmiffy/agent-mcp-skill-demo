from __future__ import annotations

import argparse
import asyncio
import json
import sys
from contextlib import AsyncExitStack
from datetime import date
from pathlib import Path
from typing import Any, Mapping

from mcp import ClientSession, StdioServerParameters
from mcp.client.stdio import stdio_client
from openai import AsyncOpenAI

from agentic_stack.config import (
    AppConfig,
    DEFAULT_CONFIG,
    load_config,
    load_skill,
    subprocess_env,
)


def trace(message: str) -> None:
    print(message, file=sys.stderr, flush=True)


def mcp_tool_to_openai(tool: Any) -> dict[str, Any]:
    return {
        "type": "function",
        "function": {
            "name": tool.name,
            "description": tool.description or "",
            "parameters": tool.inputSchema,
        },
    }


def message_to_dict(message: Any) -> dict[str, Any]:
    if isinstance(message, dict):
        return message
    if hasattr(message, "model_dump"):
        return message.model_dump(exclude_none=True)
    if hasattr(message, "dict"):
        return message.dict(exclude_none=True)
    return {
        "role": "assistant",
        "content": getattr(message, "content", "") or "",
    }


def get_tool_calls(message: Mapping[str, Any]) -> list[Any]:
    return list(message.get("tool_calls") or [])


def parse_tool_call(call: Any) -> tuple[str, str, dict[str, Any]]:
    call_dict = _to_plain_dict(call)
    call_id = call_dict.get("id")
    if not call_id:
        raise ValueError(f"tool call missing id: {call_dict}")

    function = _to_plain_dict(call_dict.get("function", {}))
    name = function.get("name")
    if not name:
        raise ValueError(f"tool call missing function name: {call_dict}")

    arguments = function.get("arguments") or {}
    if isinstance(arguments, str):
        try:
            arguments = json.loads(arguments)
        except json.JSONDecodeError as exc:
            raise ValueError(f"tool arguments for {name} are not valid JSON") from exc
    if not isinstance(arguments, dict):
        raise ValueError(f"tool arguments for {name} must be an object")

    return str(call_id), str(name), arguments


def serialize_tool_result(result: Any) -> str:
    chunks: list[str] = []
    for content in getattr(result, "content", []):
        text = getattr(content, "text", None)
        if text is not None:
            chunks.append(text)
        elif hasattr(content, "model_dump"):
            chunks.append(json.dumps(content.model_dump(), ensure_ascii=False))
        else:
            chunks.append(str(content))
    return "\n".join(chunks) if chunks else "{}"


async def run(question: str, config: AppConfig) -> None:
    async with AsyncExitStack() as stack:
        sessions: dict[str, ClientSession] = {}
        tool_owner: dict[str, str] = {}
        openai_tools: list[dict[str, Any]] = []

        for server_name, server_config in config.mcp_servers.items():
            params = StdioServerParameters(
                command=config.python,
                args=[str(server_config.script)],
                env=subprocess_env(server_config),
            )
            read, write = await stack.enter_async_context(stdio_client(params))
            session = await stack.enter_async_context(ClientSession(read, write))
            await session.initialize()
            sessions[server_name] = session

            listed = await session.list_tools()
            for tool in listed.tools:
                if tool.name in tool_owner:
                    raise RuntimeError(f"duplicate MCP tool name: {tool.name}")
                tool_owner[tool.name] = server_name
                openai_tools.append(mcp_tool_to_openai(tool))
                trace(f"[registered] {server_name}.{tool.name}")

        system = (
            f"Today is {date.today().isoformat()}.\n\n"
            "Use the following Skill exactly as the execution policy.\n\n"
            f"---\n{load_skill(config)}\n---"
        )
        messages: list[dict[str, Any]] = [
            {"role": "system", "content": system},
            {"role": "user", "content": question},
        ]
        client = AsyncOpenAI(
            api_key=_client_api_key(config),
            base_url=config.openai_base_url,
        )

        for step in range(config.max_steps):
            response = await client.chat.completions.create(
                model=config.model,
                messages=messages,
                tools=openai_tools,
            )
            assistant_message = message_to_dict(response.choices[0].message)
            messages.append(assistant_message)

            tool_calls = get_tool_calls(assistant_message)
            if not tool_calls:
                print("\n=== Final Answer ===\n")
                print(assistant_message.get("content") or "(empty)")
                return

            for call in tool_calls:
                tool_call_id = _to_plain_dict(call).get("id")
                try:
                    tool_call_id, tool_name, arguments = parse_tool_call(call)
                except ValueError as exc:
                    result_text = json.dumps({"error": str(exc)}, ensure_ascii=False)
                    if tool_call_id:
                        messages.append(
                            {
                                "role": "tool",
                                "tool_call_id": str(tool_call_id),
                                "content": result_text,
                            }
                        )
                    trace(f"[step {step}] invalid tool call: {exc}")
                    continue

                owner = tool_owner.get(tool_name)
                if owner is None:
                    result_text = json.dumps(
                        {"error": f"unknown tool: {tool_name}"},
                        ensure_ascii=False,
                    )
                    trace(f"[step {step}] -> ?? {tool_name}({arguments}) [unknown]")
                else:
                    trace(f"[step {step}] -> {owner}.{tool_name}({arguments})")
                    result = await sessions[owner].call_tool(
                        tool_name,
                        arguments=arguments,
                    )
                    result_text = serialize_tool_result(result)
                    trace(f"[step {step}] <- {result_text.replace(chr(10), ' ')[:160]}")

                messages.append(
                    {
                        "role": "tool",
                        "tool_call_id": tool_call_id,
                        "content": result_text,
                    }
                )

        trace(f"[stopped] max_steps={config.max_steps} reached without final answer")


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Run an OpenAI-compatible MCP + Skill agent.")
    parser.add_argument(
        "--config",
        type=Path,
        default=DEFAULT_CONFIG,
        help="Path to config.json.",
    )
    parser.add_argument(
        "question",
        nargs="*",
        help="Question for the agent. Defaults to DEFAULT_QUESTION/config.json.",
    )
    return parser


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    config = load_config(args.config)
    question = " ".join(args.question) or config.default_question
    asyncio.run(run(question, config))
    return 0


def _client_api_key(config: AppConfig) -> str | None:
    if config.openai_api_key:
        return config.openai_api_key
    if config.openai_base_url and "api.openai.com" not in config.openai_base_url:
        return "not-needed"
    raise RuntimeError(
        "OPENAI_API_KEY is required for the OpenAI API. "
        "For local or third-party compatible endpoints, set OPENAI_BASE_URL "
        "to that service's /v1 URL."
    )


def _to_plain_dict(value: Any) -> dict[str, Any]:
    if isinstance(value, dict):
        return value
    if hasattr(value, "model_dump"):
        return value.model_dump(exclude_none=True)
    if hasattr(value, "dict"):
        return value.dict(exclude_none=True)
    if isinstance(value, Mapping):
        return dict(value)
    if hasattr(value, "__dict__"):
        return {
            key: item
            for key, item in vars(value).items()
            if not key.startswith("_")
        }
    return {}
