"""HTTP 服务器入口 — 通过 uvicorn 启动 FastAPI 应用。

用法:
    uv run server.py
    uv run server.py --host 0.0.0.0 --port 8080
    uv run server.py --reload          # 开发模式，文件变更自动重启
"""

from __future__ import annotations

import argparse

import uvicorn


def main() -> None:
    parser = argparse.ArgumentParser(description="Open Skills Host HTTP Server")
    parser.add_argument("--host", default="127.0.0.1", help="监听地址（默认 127.0.0.1）")
    parser.add_argument("--port", type=int, default=8000, help="监听端口（默认 8000）")
    parser.add_argument("--reload", action="store_true", help="开发模式：文件变更时自动重启")
    args = parser.parse_args()

    uvicorn.run(
        "api.main:app",
        host=args.host,
        port=args.port,
        reload=args.reload,
        log_level="info",
    )


if __name__ == "__main__":
    main()
