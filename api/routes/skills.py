"""Skill 相关端点

GET  /skills           — 列出所有技能（元数据）
GET  /skills/{name}    — 查询单个技能详情（元数据 + instructions）
POST /skills/invoke    — 执行技能，返回结构化结果
"""

from __future__ import annotations

import asyncio
import logging
import shutil
import uuid
from functools import partial
from pathlib import Path
from urllib.parse import urlparse

from fastapi import APIRouter, HTTPException

from agent.runner import run_skill
from api.cdn import download_file, upload_file
from api.schemas import (
    InvokeRequest,
    InvokeResponse,
    SkillDetail,
    SkillListResponse,
    SkillSummary,
)
from core.config import get_swap_dir, get_skills_dir
from core.discovery import discover_skills
from core.errors import SkillNotFoundError
from core.parser import load_instructions

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/skills", tags=["skills"])


@router.get("", response_model=SkillListResponse)
async def list_skills() -> SkillListResponse:
    """列出所有可用技能的元数据摘要。"""
    loop = asyncio.get_event_loop()
    skills = await loop.run_in_executor(None, discover_skills, get_skills_dir())
    items = [SkillSummary(name=s.name, description=s.description) for s in skills]
    return SkillListResponse(skills=items, total=len(items))


@router.get("/{name}", response_model=SkillDetail)
async def get_skill(name: str) -> SkillDetail:
    """查询单个技能的完整信息（含 SKILL.md instructions）。"""
    loop = asyncio.get_event_loop()
    skills = await loop.run_in_executor(None, discover_skills, get_skills_dir())
    skill = next((s for s in skills if s.name == name), None)
    if skill is None:
        raise HTTPException(status_code=404, detail=f"技能 '{name}' 不存在")

    instructions = await loop.run_in_executor(None, load_instructions, skill.path)
    return SkillDetail(
        name=skill.name,
        description=skill.description,
        license=skill.license,
        compatibility=skill.compatibility,
        allowed_tools=skill.allowed_tools,
        metadata=skill.metadata or {},
        instructions=instructions,
    )


@router.post("/invoke", response_model=InvokeResponse)
async def invoke_skill(body: InvokeRequest) -> InvokeResponse:
    """执行指定技能，返回结构化执行结果。

    完整流程：
      1. 从 input_files URL 列表下载输入文件到 exec_input_dir/
      2. 通过 SKILL_INPUT_DIR 环境变量将输入目录路径注入给脚本
      3. run_skill() 在线程池执行（阻塞调用不阻塞事件循环）
      4. 将产出文件上传至公司 CDN，返回 CDN URL
      5. 清理本次执行的临时目录（输入 + 输出）
    """
    name = body.skill_name
    execution_id = str(uuid.uuid4())
    base_tmp = Path(get_swap_dir()) / execution_id
    exec_input_dir = base_tmp / "inputs"
    exec_output_dir = base_tmp / "outputs"
    exec_input_dir.mkdir(parents=True, exist_ok=True)
    exec_output_dir.mkdir(parents=True, exist_ok=True)

    logger.info("invoke skill=%s execution_id=%s input_files=%d",
                name, execution_id, len(body.input_files))

    # ── 1. 下载输入文件 ──────────────────────────────────────────
    for url in body.input_files:
        filename = _filename_from_url(url)
        dest = exec_input_dir / filename
        try:
            await download_file(url, dest)
        except Exception as e:
            _cleanup(base_tmp)
            raise HTTPException(
                status_code=422,
                detail=f"输入文件下载失败 [{url}]: {e}",
            )

    # ── 2. 执行技能（线程池，非阻塞事件循环）───────────────────
    loop = asyncio.get_event_loop()
    try:
        result = await loop.run_in_executor(
            None,
            partial(
                run_skill,
                name,
                body.request,
                get_skills_dir(),
                str(exec_output_dir),
                str(exec_input_dir) if body.input_files else None,
            ),
        )
    except SkillNotFoundError:
        _cleanup(base_tmp)
        raise HTTPException(status_code=404, detail=f"技能 '{name}' 不存在")
    except Exception as e:
        _cleanup(base_tmp)
        logger.exception("invoke 执行异常: skill=%s execution_id=%s", name, execution_id)
        raise HTTPException(status_code=500, detail=str(e))

    # ── 3. 上传产出文件到 CDN ────────────────────────────────────
    download_url: str | None = None
    upload_failed = False
    if result.artifact_type == "file" and result.file_path:
        try:
            download_url = await upload_file(result.file_path)
        except Exception as e:
            upload_failed = True
            logger.error("CDN 上传失败 execution_id=%s: %s", execution_id, e)
            result = result.model_copy(update={
                "success": False,
                "error": f"技能执行成功但产出文件上传 CDN 失败: {e}",
            })

    # ── 4. 清理临时目录（上传失败时保留产出文件）───────────────
    if upload_failed:
        # 只清理输入目录，保留 outputs 供排查
        _cleanup(exec_input_dir)
        logger.warning("CDN 上传失败，产出文件已保留: %s", exec_output_dir)
    else:
        _cleanup(base_tmp)

    return InvokeResponse(
        execution_id=execution_id,
        success=result.success,
        skill_name=result.skill_name,
        artifact_type=result.artifact_type,
        download_url=download_url,
        text_content=result.text_content,
        summary=result.summary,
        error=result.error,
    )


# ── 工具函数 ─────────────────────────────────────────────────────

def _filename_from_url(url: str) -> str:
    """从 URL 提取文件名，无法提取时生成 uuid 作为兜底。"""
    name = Path(urlparse(url).path).name
    return name if name else f"input_{uuid.uuid4().hex[:8]}"


def _cleanup(path: Path) -> None:
    """静默删除临时目录，失败只记录日志不抛异常。"""
    try:
        if path.exists():
            shutil.rmtree(path)
            logger.debug("临时目录已清理: %s", path)
    except Exception as e:
        logger.warning("临时目录清理失败: %s — %s", path, e)
