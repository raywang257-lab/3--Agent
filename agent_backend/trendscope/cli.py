from __future__ import annotations

import argparse
import asyncio
import json

from .config import settings
from .database import Database
from .runner import TrendAgentRunner


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="TrendScope 热点发现 Agent")
    sub = parser.add_subparsers(dest="command", required=True)
    run = sub.add_parser("run", help="立即执行一次监控任务")
    run.add_argument("--task-id", type=int, default=1)
    sub.add_parser("hotspots", help="输出最近一轮热点 JSON")
    sub.add_parser("init-db", help="初始化 SQLite 数据库")
    return parser


async def async_main() -> None:
    args = build_parser().parse_args()
    db = Database(settings.database_path)
    db.initialize()
    if args.command == "init-db":
        print(f"数据库已初始化：{settings.database_path}")
        return
    if args.command == "hotspots":
        print(json.dumps(db.list_latest_events(), ensure_ascii=False, indent=2, default=str))
        return
    runner = TrendAgentRunner(db, settings)
    run_id = await runner.run(args.task_id)
    print(json.dumps(db.get_run(run_id), ensure_ascii=False, indent=2, default=str))


def main() -> None:
    asyncio.run(async_main())


if __name__ == "__main__":
    main()

