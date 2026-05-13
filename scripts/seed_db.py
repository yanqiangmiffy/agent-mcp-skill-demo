from __future__ import annotations

import random
import sqlite3
import sys
from datetime import datetime, timedelta, timezone
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
SRC = ROOT / "src"
if str(SRC) not in sys.path:
    sys.path.insert(0, str(SRC))

from agentic_stack.config import DEFAULT_CONFIG, load_config


ENGINEERS = [
    ("Sara Chen", "schen", "sara@example.com", "US", "America/Los_Angeles"),
    ("Marco Rossi", "marco-r", "marco@example.com", "IT", "Europe/Rome"),
    ("Priya Patel", "priya-p", "priya@example.com", "IN", "Asia/Kolkata"),
    ("Felix Mueller", "fmueller", "felix@example.com", "DE", "Europe/Berlin"),
    ("Yuki Tanaka", "ytanaka", "yuki@example.com", "JP", "Asia/Tokyo"),
]

ISSUE_TITLES = [
    ("API gateway returns 502 under load", "P1"),
    ("Memory leak in ingestion worker", "P1"),
    ("Database failover does not promote replica", "P0"),
    ("Auth token refresh fails for SSO users", "P1"),
    ("Disk usage alert on log-archive node", "P2"),
    ("Stale data shown on dashboard for 5+ min", "P1"),
    ("Slow query on customer search endpoint", "P2"),
    ("Webhook delivery retries not exponential", "P2"),
    ("CSV export truncates rows over 10k", "P1"),
    ("OAuth callback rejects valid state token", "P1"),
    ("Background job stuck in running state", "P2"),
    ("Rate limiter counts cached responses", "P3"),
]


def main() -> int:
    config = load_config(DEFAULT_CONFIG)
    db_path = Path(config.mcp_servers["ops"].env["OPS_DB"]).resolve()
    db_path.parent.mkdir(parents=True, exist_ok=True)

    if db_path.exists():
        db_path.unlink()

    random.seed(42)
    now = datetime.now(timezone.utc).replace(microsecond=0)
    monday = (now - timedelta(days=now.weekday())).replace(hour=0, minute=0, second=0)

    with sqlite3.connect(db_path) as conn:
        conn.executescript(
            """
            CREATE TABLE engineers (
                engineer_id INTEGER PRIMARY KEY,
                name TEXT NOT NULL,
                github_login TEXT NOT NULL UNIQUE,
                email TEXT NOT NULL,
                country_code TEXT NOT NULL,
                timezone TEXT NOT NULL
            );

            CREATE TABLE rotations (
                engineer_id INTEGER NOT NULL,
                starts_at TEXT NOT NULL,
                ends_at TEXT NOT NULL,
                FOREIGN KEY (engineer_id) REFERENCES engineers(engineer_id)
            );
            CREATE INDEX idx_rotations_window ON rotations (starts_at, ends_at);

            CREATE TABLE issues (
                issue_id INTEGER PRIMARY KEY,
                title TEXT NOT NULL,
                priority TEXT NOT NULL,
                status TEXT NOT NULL,
                assignee_id INTEGER,
                opened_at TEXT NOT NULL,
                FOREIGN KEY (assignee_id) REFERENCES engineers(engineer_id)
            );
            """
        )
        conn.executemany(
            """
            INSERT INTO engineers (name, github_login, email, country_code, timezone)
            VALUES (?, ?, ?, ?, ?)
            """,
            ENGINEERS,
        )

        rota_rows = []
        for week in range(-2, 8):
            start = monday + timedelta(weeks=week)
            end = start + timedelta(weeks=1)
            engineer_id = (week % len(ENGINEERS)) + 1
            rota_rows.append((engineer_id, start.isoformat(), end.isoformat()))
        conn.executemany("INSERT INTO rotations VALUES (?, ?, ?)", rota_rows)

        issue_rows = []
        for issue_id, (title, priority) in enumerate(ISSUE_TITLES, start=1):
            assignee_id = random.randint(1, len(ENGINEERS))
            opened_at = (now - timedelta(hours=random.randint(2, 240))).isoformat()
            issue_rows.append((issue_id, title, priority, "open", assignee_id, opened_at))
        conn.executemany("INSERT INTO issues VALUES (?, ?, ?, ?, ?, ?)", issue_rows)
        conn.commit()

    print(
        f"Created {db_path} with {len(ENGINEERS)} engineers, "
        f"{len(rota_rows)} rotations, and {len(issue_rows)} open issues."
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
