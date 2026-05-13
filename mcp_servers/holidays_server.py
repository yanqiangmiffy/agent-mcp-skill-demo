from __future__ import annotations

import os
from datetime import date as date_cls
from pathlib import Path
from typing import Any

import httpx
from mcp.server.fastmcp import FastMCP

try:
    from dotenv import load_dotenv
except ImportError:  # pragma: no cover - dependency is listed in requirements.
    load_dotenv = None


ROOT = Path(__file__).resolve().parents[1]
if load_dotenv is not None:
    load_dotenv(ROOT / ".env", override=False)

API_BASE = os.environ.get("HOLIDAY_API_BASE", "https://date.nager.at/api/v3")
USER_AGENT = "agent-mcp-skill-demo/0.1.0"

mcp = FastMCP("holidays")

# 2026 年中国节假日安排来自国务院办公厅国办发明电〔2025〕7号。
CHINA_PUBLIC_HOLIDAYS_2026 = {
    "2026-01-01": "元旦",
    "2026-01-02": "元旦",
    "2026-01-03": "元旦",
    "2026-02-15": "春节",
    "2026-02-16": "春节",
    "2026-02-17": "春节",
    "2026-02-18": "春节",
    "2026-02-19": "春节",
    "2026-02-20": "春节",
    "2026-02-21": "春节",
    "2026-02-22": "春节",
    "2026-02-23": "春节",
    "2026-04-04": "清明节",
    "2026-04-05": "清明节",
    "2026-04-06": "清明节",
    "2026-05-01": "劳动节",
    "2026-05-02": "劳动节",
    "2026-05-03": "劳动节",
    "2026-05-04": "劳动节",
    "2026-05-05": "劳动节",
    "2026-06-19": "端午节",
    "2026-06-20": "端午节",
    "2026-06-21": "端午节",
    "2026-09-25": "中秋节",
    "2026-09-26": "中秋节",
    "2026-09-27": "中秋节",
    "2026-10-01": "国庆节",
    "2026-10-02": "国庆节",
    "2026-10-03": "国庆节",
    "2026-10-04": "国庆节",
    "2026-10-05": "国庆节",
    "2026-10-06": "国庆节",
    "2026-10-07": "国庆节",
}


@mcp.tool()
async def is_public_holiday(country_code: str, on_date: str) -> dict[str, Any]:
    """检查指定国家/地区在某天是否为公共假日。

    Args:
        country_code: ISO 3166-1 alpha-2 两位国家/地区代码，例如 CN、US、JP。
        on_date: 日期，格式为 YYYY-MM-DD。

    Returns:
        包含 is_holiday 的字典。命中假日时会返回 holiday_name 和
        holiday_local_name。出错时返回包含 error 键的字典。
    """
    try:
        target = date_cls.fromisoformat(on_date)
    except ValueError:
        return {"error": "on_date 必须使用 YYYY-MM-DD 格式"}

    if len(country_code) != 2:
        return {"error": "country_code 必须是两位 ISO 国家/地区代码"}

    holidays = await _fetch_public_holidays(country_code.upper(), target.year)
    if isinstance(holidays, dict) and "error" in holidays:
        return holidays

    target_iso = target.isoformat()
    for holiday in holidays:
        if holiday.get("date") == target_iso:
            return {
                "is_holiday": True,
                "holiday_name": holiday.get("name"),
                "holiday_local_name": holiday.get("localName"),
            }
    return {"is_holiday": False}


@mcp.tool()
async def list_country_holidays(country_code: str, year: int) -> list[dict[str, Any]]:
    """列出某个国家/地区在指定年份的公共假日。"""
    if len(country_code) != 2:
        return [{"error": "country_code 必须是两位 ISO 国家/地区代码"}]

    holidays = await _fetch_public_holidays(country_code.upper(), year)
    if isinstance(holidays, dict) and "error" in holidays:
        return [holidays]

    return [
        {
            "date": holiday.get("date"),
            "name": holiday.get("name"),
            "local_name": holiday.get("localName"),
        }
        for holiday in holidays
    ]


async def _fetch_public_holidays(
    country_code: str,
    year: int,
) -> list[dict[str, Any]] | dict[str, str]:
    local_holidays = _china_public_holidays(country_code, year)
    if local_holidays is not None:
        return local_holidays

    url = f"{API_BASE}/PublicHolidays/{year}/{country_code}"
    headers = {"User-Agent": USER_AGENT, "Accept": "application/json"}
    try:
        async with httpx.AsyncClient(timeout=10.0) as client:
            response = await client.get(url, headers=headers)
            if response.status_code == 404:
                return {"error": f"未知国家/地区代码：{country_code}"}
            response.raise_for_status()
            data = response.json()
    except httpx.HTTPError as exc:
        return {"error": f"假日 API 请求失败：{exc}"}
    except ValueError as exc:
        return {"error": f"假日 API 返回了无效 JSON：{exc}"}

    if not isinstance(data, list):
        return {"error": "假日 API 返回了非预期数据结构"}
    return data


def _china_public_holidays(country_code: str, year: int) -> list[dict[str, Any]] | None:
    if country_code != "CN" or year != 2026:
        return None
    return [
        {
            "date": holiday_date,
            "name": holiday_name,
            "localName": holiday_name,
        }
        for holiday_date, holiday_name in CHINA_PUBLIC_HOLIDAYS_2026.items()
    ]


if __name__ == "__main__":
    mcp.run(transport="stdio")
