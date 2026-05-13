from __future__ import annotations

import asyncio
import os
import sqlite3
import sys
import tempfile
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
SRC = ROOT / "src"
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))
if str(SRC) not in sys.path:
    sys.path.insert(0, str(SRC))

from mcp_servers.holidays_server import _fetch_public_holidays
from scripts import seed_db


class LocalizedDemoTests(unittest.TestCase):
    def test_seed_db_uses_chinese_engineers_and_issues(self) -> None:
        original_ops_db = os.environ.get("OPS_DB")
        with tempfile.TemporaryDirectory() as tmp_dir:
            db_path = Path(tmp_dir) / "ops.db"
            os.environ["OPS_DB"] = str(db_path)
            try:
                self.assertEqual(seed_db.main(), 0)
            finally:
                if original_ops_db is None:
                    os.environ.pop("OPS_DB", None)
                else:
                    os.environ["OPS_DB"] = original_ops_db

            conn = sqlite3.connect(db_path)
            try:
                names = {
                    row[0]
                    for row in conn.execute("SELECT name FROM engineers ORDER BY engineer_id")
                }
                countries = {
                    row[0]
                    for row in conn.execute("SELECT DISTINCT country_code FROM engineers")
                }
                p1_titles = [
                    row[0]
                    for row in conn.execute(
                        "SELECT title FROM issues WHERE priority = 'P1' ORDER BY issue_id"
                    )
                ]
            finally:
                conn.close()

        self.assertIn("陈思远", names)
        self.assertIn("李若彤", names)
        self.assertEqual(countries, {"CN"})
        self.assertIn("生产网关高峰期出现 502", p1_titles)
        self.assertIn("企业微信单点登录刷新失败", p1_titles)

    def test_china_2026_holiday_fallback_is_localized(self) -> None:
        holidays = asyncio.run(_fetch_public_holidays("CN", 2026))
        self.assertIsInstance(holidays, list)

        holiday_by_date = {holiday["date"]: holiday for holiday in holidays}
        self.assertEqual(holiday_by_date["2026-10-01"]["localName"], "国庆节")
        self.assertEqual(holiday_by_date["2026-02-17"]["localName"], "春节")


if __name__ == "__main__":
    unittest.main()
