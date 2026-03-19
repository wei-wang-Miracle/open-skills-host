"""FastAPI 应用工厂"""

from __future__ import annotations

import asyncio
from concurrent.futures import ThreadPoolExecutor
from contextlib import asynccontextmanager

from fastapi import FastAPI

from api.routes.skills import router as skills_router


@asynccontextmanager
async def lifespan(app: FastAPI):
    # 配置线程池，用于将 run_skill() 等阻塞调用放入线程
    # max_workers=10 适合 I/O 密集型 LLM 调用；按需调整
    executor = ThreadPoolExecutor(max_workers=10, thread_name_prefix="skill-worker")
    loop = asyncio.get_event_loop()
    loop.set_default_executor(executor)
    yield
    executor.shutdown(wait=False)


def create_app() -> FastAPI:
    app = FastAPI(
        title="Open Skills Host",
        description="LangChain Agent 驱动的 Skill 执行宿主，为 AI 引擎提供远程技能调用能力。",
        version="0.1.0",
        lifespan=lifespan,
    )
    app.include_router(skills_router)
    return app


app = create_app()
