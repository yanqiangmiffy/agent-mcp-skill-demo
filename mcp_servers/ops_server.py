from __future__ import annotations

import os
import sqlite3
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from mcp.server.fastmcp import FastMCP

try:
    from dotenv import load_dotenv
except ImportError:  # pragma: no cover - dependency is listed in requirements.
    load_dotenv = None


ROOT = Path(__file__).resolve().parents[1]
if load_dotenv is not None:
    load_dotenv(ROOT / ".env", override=False)

DB_PATH = Path(os.environ.get("OPS_DB", "{root}/ops.db").replace("{root}", str(ROOT))).resolve()

mcp = FastMCP("ops")


@mcp.tool()
def get_current_oncall() -> dict[str, Any]:
    """返回当前值班工程师。"""
    missing = _missing_db_error()
    if missing:
        return missing

    now = datetime.now(timezone.utc).isoformat()
    with _connect() as conn:
        row = conn.execute(
            """
            SELECT e.engineer_id, e.name, e.github_login, e.email,
                   e.country_code, e.timezone, r.starts_at, r.ends_at
            FROM rotations r
            JOIN engineers e ON e.engineer_id = r.engineer_id
            WHERE r.starts_at <= ? AND r.ends_at > ?
            ORDER BY r.starts_at DESC
            LIMIT 1
            """,
            (now, now),
        ).fetchone()
    return dict(row) if row else {"error": "当前没有工程师在值班"}


@mcp.tool()
def list_open_issues(
    priority: str | None = None,
    assignee_id: int | None = None,
) -> list[dict[str, Any]]:
    """列出开放问题，可按优先级和负责人过滤。"""
    missing = _missing_db_error()
    if missing:
        return [missing]

    clauses = ["status = 'open'"]
    params: list[Any] = []
    if priority:
        clauses.append("priority = ?")
        params.append(priority.upper())
    if assignee_id is not None:
        clauses.append("assignee_id = ?")
        params.append(assignee_id)

    sql = (
        "SELECT issue_id, title, priority, assignee_id, opened_at "
        "FROM issues WHERE "
        + " AND ".join(clauses)
        + " ORDER BY opened_at"
    )
    with _connect() as conn:
        rows = conn.execute(sql, params).fetchall()
    return [dict(row) for row in rows]


@mcp.tool()
def get_engineer(github_login: str) -> dict[str, Any]:
    """按 GitHub 账号查找工程师。"""
    missing = _missing_db_error()
    if missing:
        return missing

    with _connect() as conn:
        row = conn.execute(
            """
            SELECT engineer_id, name, github_login, email, country_code, timezone
            FROM engineers
            WHERE github_login = ?
            """,
            (github_login,),
        ).fetchone()
    return dict(row) if row else {"error": f"未找到工程师：{github_login}"}


@mcp.tool()
def list_engineers() -> list[dict[str, Any]]:
    """列出全部工程师。"""
    missing = _missing_db_error()
    if missing:
        return [missing]

    with _connect() as conn:
        rows = conn.execute(
            """
            SELECT engineer_id, name, github_login, email, country_code, timezone
            FROM engineers
            ORDER BY engineer_id
            """
        ).fetchall()
    return [dict(row) for row in rows]


def _connect() -> sqlite3.Connection:
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    return conn


def _missing_db_error() -> dict[str, str] | None:
    if DB_PATH.exists():
        return None
    return {
        "error": (
            f"未找到数据库：{DB_PATH}。"
            "请先运行：python scripts/seed_db.py"
        )
    }


if __name__ == "__main__":
    mcp.run(transport="stdio")
