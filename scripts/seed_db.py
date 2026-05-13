from __future__ import annotations

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
    ("陈思远", "siyuan-chen", "siyuan.chen@example.cn", "CN", "Asia/Shanghai"),
    ("李若彤", "ruotong-li", "ruotong.li@example.cn", "CN", "Asia/Shanghai"),
    ("王启航", "qihang-wang", "qihang.wang@example.cn", "CN", "Asia/Shanghai"),
    ("赵明轩", "mingxuan-zhao", "mingxuan.zhao@example.cn", "CN", "Asia/Shanghai"),
    ("周可欣", "kexin-zhou", "kexin.zhou@example.cn", "CN", "Asia/Shanghai"),
]

ISSUE_TITLES = [
    ("生产网关高峰期出现 502", "P1"),
    ("订单同步任务内存持续上涨", "P1"),
    ("主库故障切换未成功提升从库", "P0"),
    ("企业微信单点登录刷新失败", "P1"),
    ("日志归档节点磁盘空间告警", "P2"),
    ("运营看板数据延迟超过 5 分钟", "P1"),
    ("客户检索接口慢查询", "P2"),
    ("支付回调重试间隔未按指数退避", "P2"),
    ("对账 CSV 导出超过 1 万行被截断", "P1"),
    ("开放平台 OAuth 回调状态校验失败", "P1"),
    ("夜间批处理任务卡在运行中", "P2"),
    ("缓存响应被错误计入限流", "P3"),
]

ASSIGNEE_IDS = [1, 2, 3, 1, 4, 1, 2, 3, 1, 5, 2, 4]
OPENED_HOURS_AGO = [3, 7, 11, 18, 26, 31, 44, 58, 72, 96, 120, 168]


def main() -> int:
    config = load_config(DEFAULT_CONFIG)
    db_path = Path(config.mcp_servers["ops"].env["OPS_DB"]).resolve()
    db_path.parent.mkdir(parents=True, exist_ok=True)

    if db_path.exists():
        db_path.unlink()

    now = datetime.now(timezone.utc).replace(microsecond=0)
    monday = (now - timedelta(days=now.weekday())).replace(hour=0, minute=0, second=0)

    conn = sqlite3.connect(db_path)
    try:
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
        for issue_id, ((title, priority), assignee_id, hours_ago) in enumerate(
            zip(ISSUE_TITLES, ASSIGNEE_IDS, OPENED_HOURS_AGO),
            start=1,
        ):
            opened_at = (now - timedelta(hours=hours_ago)).isoformat()
            issue_rows.append((issue_id, title, priority, "open", assignee_id, opened_at))
        conn.executemany("INSERT INTO issues VALUES (?, ?, ?, ?, ?, ?)", issue_rows)
        conn.commit()
    finally:
        conn.close()

    print(
        f"已创建 {db_path}：{len(ENGINEERS)} 位工程师、"
        f"{len(rota_rows)} 条值班轮次、{len(issue_rows)} 条开放问题。"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
