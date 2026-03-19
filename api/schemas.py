"""API 请求/响应 Pydantic 模型"""

from __future__ import annotations

from typing import Literal, Optional

from pydantic import BaseModel, Field


# ── 请求体 ──────────────────────────────────────────────────────

class InvokeRequest(BaseModel):
    """POST /skills/invoke 请求体。"""
    skill_name: str = Field(
        ...,
        min_length=1,
        description="要执行的技能名称",
        examples=["file-processing"],
    )
    request: str = Field(
        ...,
        min_length=1,
        description="转发给 Agent 的自然语言执行请求",
        examples=["分析 Q4 销售数据并生成摘要报告"],
    )
    input_files: list[str] = Field(
        default_factory=list,
        description=(
            "可选的输入文件 URL 列表（公司 CDN 或任意可公开访问的 URL）。"
            "系统自动下载到执行临时目录，并将目录路径通过 SKILL_INPUT_DIR 环境变量注入给脚本。"
        ),
        examples=[["https://example.com/report.pdf"]],
    )


# ── 响应模型 ────────────────────────────────────────────────────

class SkillSummary(BaseModel):
    """GET /skills 列表中的单条技能摘要。"""
    name: str
    description: str


class SkillListResponse(BaseModel):
    """GET /skills 完整响应。"""
    skills: list[SkillSummary]
    total: int


class SkillDetail(BaseModel):
    """GET /skills/{name} 完整响应 — 元数据 + 使用说明。"""
    name: str
    description: str
    license: Optional[str] = None
    compatibility: Optional[str] = None
    allowed_tools: Optional[str] = None
    metadata: dict[str, str] = Field(default_factory=dict)
    instructions: str = Field(
        description="SKILL.md 的 Markdown 正文（完整使用说明文档）"
    )


class InvokeResponse(BaseModel):
    """POST /skills/invoke 响应。

    产出文件已上传至公司 CDN，download_url 为 CDN 公网地址。
    本系统不持久化任何文件，执行完成后本地临时目录自动清理。
    """
    execution_id: str
    success: bool
    skill_name: str
    artifact_type: Literal["file", "text"] = "text"
    download_url: Optional[str] = Field(
        default=None,
        description=(
            "仅当 artifact_type=='file' 时存在。"
            "产出文件的 CDN 公网下载地址。"
        ),
    )
    text_content: str = ""
    summary: str = ""
    error: str = ""
