"""PyCharm 直接运行此文件，启动 TrendScope Agent API。"""

import uvicorn


if __name__ == "__main__":
    uvicorn.run("trendscope.api:app", host="127.0.0.1", port=8000, reload=True)

