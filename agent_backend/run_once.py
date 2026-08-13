"""PyCharm 直接运行此文件，执行一次真实热点采集和分析。"""

import asyncio
import json

from trendscope.config import settings
from trendscope.database import Database
from trendscope.runner import TrendAgentRunner


async def run_once() -> None:
    db = Database(settings.database_path)
    db.initialize()
    run_id = await TrendAgentRunner(db, settings).run(task_id=1)
    print(json.dumps(db.get_run(run_id), ensure_ascii=False, indent=2, default=str))


if __name__ == "__main__":
    asyncio.run(run_once())
