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
        raise ValueError(f"工具调用缺少 id：{call_dict}")

    function = _to_plain_dict(call_dict.get("function", {}))
    name = function.get("name")
    if not name:
        raise ValueError(f"工具调用缺少函数名：{call_dict}")

    arguments = function.get("arguments") or {}
    if isinstance(arguments, str):
        try:
            arguments = json.loads(arguments)
        except json.JSONDecodeError as exc:
            raise ValueError(f"{name} 的工具参数不是合法 JSON") from exc
    if not isinstance(arguments, dict):
        raise ValueError(f"{name} 的工具参数必须是对象")

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
                trace(f"[已注册] {server_name}.{tool.name}")

        system = (
            f"今天日期是 {date.today().isoformat()}。\n\n"
            "请严格按下面的 Skill 作为执行策略。\n\n"
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
                print("\n=== 最终回答 ===\n")
                print(assistant_message.get("content") or "(空内容)")
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
                    trace(f"[第 {step} 步] 工具调用无效：{exc}")
                    continue

                owner = tool_owner.get(tool_name)
                if owner is None:
                    result_text = json.dumps(
                        {"error": f"未知工具：{tool_name}"},
                        ensure_ascii=False,
                    )
                    trace(f"[第 {step} 步] -> ?? {tool_name}({arguments}) [未知]")
                else:
                    trace(f"[第 {step} 步] -> {owner}.{tool_name}({arguments})")
                    result = await sessions[owner].call_tool(
                        tool_name,
                        arguments=arguments,
                    )
                    result_text = serialize_tool_result(result)
                    trace(f"[第 {step} 步] <- {result_text.replace(chr(10), ' ')[:160]}")

                messages.append(
                    {
                        "role": "tool",
                        "tool_call_id": tool_call_id,
                        "content": result_text,
                    }
                )

        trace(f"[已停止] 达到 max_steps={config.max_steps}，仍未得到最终回答")


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="运行 OpenAI SDK 兼容的 MCP + Skill Agent。")
    parser.add_argument(
        "--config",
        type=Path,
        default=DEFAULT_CONFIG,
        help="config.json 路径。",
    )
    parser.add_argument(
        "question",
        nargs="*",
        help="给 Agent 的问题。默认使用 DEFAULT_QUESTION/config.json。",
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
        "使用 OpenAI 官方 API 时必须设置 OPENAI_API_KEY。"
        "如果使用本地或第三方兼容端点，请把 OPENAI_BASE_URL "
        "设置为该服务的 /v1 地址。"
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
