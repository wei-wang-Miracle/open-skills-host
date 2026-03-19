"""Agent 模块 - 基于 LangChain 的技能执行引擎

本模块负责将已发现的 Skill 转化为 LangChain Tool，
然后通过 LangChain Agent 驱动 LLM 来自动编排和执行技能。
"""

from .runner import run_skill

__all__ = ["run_skill"]
