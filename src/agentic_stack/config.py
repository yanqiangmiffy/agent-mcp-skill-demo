from __future__ import annotations

import json
import os
import sys
from dataclasses import dataclass
from pathlib import Path
from typing import Any

try:
    from dotenv import load_dotenv
except ImportError:  # pragma: no cover - dependency is listed in requirements.
    load_dotenv = None


PROJECT_ROOT = Path(__file__).resolve().parents[2]
DEFAULT_CONFIG = PROJECT_ROOT / "config.json"


@dataclass(frozen=True)
class McpServerConfig:
    name: str
    script: Path
    env: dict[str, str]


@dataclass(frozen=True)
class AppConfig:
    root: Path
    python: str
    openai_api_key: str | None
    openai_base_url: str | None
    model: str
    max_steps: int
    skill_path: Path
    default_question: str
    mcp_servers: dict[str, McpServerConfig]


def load_config(config_path: Path = DEFAULT_CONFIG) -> AppConfig:
    config_path = config_path.resolve()
    root = config_path.parent
    _load_dotenv(root)

    raw = json.loads(config_path.read_text(encoding="utf-8"))
    servers = _load_servers(raw.get("mcp_servers", {}), root)

    return AppConfig(
        root=root,
        python=_choose_python(raw.get("python")),
        openai_api_key=_optional_env("OPENAI_API_KEY", raw.get("openai_api_key")),
        openai_base_url=_optional_env("OPENAI_BASE_URL", raw.get("openai_base_url")),
        model=str(os.getenv("OPENAI_MODEL") or raw.get("model", "gpt-4.1-mini")),
        max_steps=int(os.getenv("MAX_STEPS") or raw.get("max_steps", 10)),
        skill_path=_resolve_path(
            os.getenv("SKILL_PATH") or raw.get("skill_path", "skills/oncall_holiday_check.md"),
            root,
        ),
        default_question=str(
            os.getenv("DEFAULT_QUESTION")
            or raw.get("default_question", "当前值班工程师所在国家今天是否有公共假日？")
        ),
        mcp_servers=servers,
    )


def load_skill(config: AppConfig) -> str:
    return config.skill_path.read_text(encoding="utf-8")


def subprocess_env(server: McpServerConfig) -> dict[str, str]:
    env = os.environ.copy()
    env.update(server.env)
    return env


def _load_dotenv(root: Path) -> None:
    if load_dotenv is not None:
        load_dotenv(root / ".env", override=False)


def _choose_python(value: Any) -> str:
    env_python = os.getenv("PYTHON_EXECUTABLE")
    if env_python:
        return os.path.expanduser(env_python)

    configured = str(value or "").strip()
    if not configured or configured in {"python", "python3"}:
        return sys.executable
    return os.path.expanduser(configured)


def _optional_env(name: str, fallback: Any = None) -> str | None:
    value = os.getenv(name)
    if value is None:
        value = fallback
    if value is None:
        return None

    stripped = str(value).strip()
    return stripped or None


def _load_servers(raw_servers: dict[str, Any], root: Path) -> dict[str, McpServerConfig]:
    servers: dict[str, McpServerConfig] = {}
    for name, server in raw_servers.items():
        script = _resolve_path(server["script"], root)
        env = {
            key: _expand_value(os.getenv(key) or value, root)
            for key, value in server.get("env", {}).items()
        }
        servers[name] = McpServerConfig(name=name, script=script, env=env)
    return servers


def _resolve_path(value: Any, root: Path) -> Path:
    path = Path(_expand_value(value, root)).expanduser()
    return path if path.is_absolute() else root / path


def _expand_value(value: Any, root: Path) -> str:
    expanded = str(value).replace("{root}", str(root))
    return os.path.expandvars(expanded)
