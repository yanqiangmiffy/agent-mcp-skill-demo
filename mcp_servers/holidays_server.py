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


@mcp.tool()
async def is_public_holiday(country_code: str, on_date: str) -> dict[str, Any]:
    """Check whether a date is a public holiday in a country.

    Args:
        country_code: ISO 3166-1 alpha-2 country code, such as US, IT, or JP.
        on_date: Date in YYYY-MM-DD format.

    Returns:
        A dict with is_holiday. Holiday names are included when the date matches.
        Errors are returned as a dict with an error key.
    """
    try:
        target = date_cls.fromisoformat(on_date)
    except ValueError:
        return {"error": "on_date must use YYYY-MM-DD format"}

    if len(country_code) != 2:
        return {"error": "country_code must be a two-letter ISO country code"}

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
    """List public holidays for a country and year."""
    if len(country_code) != 2:
        return [{"error": "country_code must be a two-letter ISO country code"}]

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
    url = f"{API_BASE}/PublicHolidays/{year}/{country_code}"
    headers = {"User-Agent": USER_AGENT, "Accept": "application/json"}
    try:
        async with httpx.AsyncClient(timeout=10.0) as client:
            response = await client.get(url, headers=headers)
            if response.status_code == 404:
                return {"error": f"unknown country code: {country_code}"}
            response.raise_for_status()
            data = response.json()
    except httpx.HTTPError as exc:
        return {"error": f"holiday API request failed: {exc}"}
    except ValueError as exc:
        return {"error": f"holiday API returned invalid JSON: {exc}"}

    if not isinstance(data, list):
        return {"error": "holiday API returned an unexpected payload"}
    return data


if __name__ == "__main__":
    mcp.run(transport="stdio")
