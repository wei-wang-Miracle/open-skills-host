"""Agent 执行事件回调 — 基于 LangChain BaseCallbackHandler

通过订阅 LangChain 运行时事件实现日志打印，与主流程完全解耦：

    on_tool_start   → 打印工具调用参数
    on_tool_end     → 打印工具返回摘要
    on_tool_error   → 打印工具执行错误
    on_llm_start    → 打印 LLM 推理开始（DEBUG 级别）
    on_agent_finish → 打印最终结论

使用方式:
    from agent.callbacks import SkillEventLogger
    callback = SkillEventLogger()
    agent.invoke(..., config={"callbacks": [callback]})
"""

from __future__ import annotations

import logging
from typing import Any, Union
from uuid import UUID

from langchain_core.callbacks import BaseCallbackHandler
from langchain_core.outputs import LLMResult

logger = logging.getLogger(__name__)

_RESULT_PREVIEW_LEN = 300


class SkillEventLogger(BaseCallbackHandler):
    """将 Agent 运行时事件转换为结构化日志 / 控制台输出。

    设计原则：
    - 控制台输出（print）用于面向用户的实时进度展示
    - logger.debug 用于面向开发者的详细诊断信息
    - 不持有任何业务状态，纯粹作为旁路观察者
    """

    def on_tool_start(
        self,
        serialized: dict[str, Any],
        input_str: str,
        *,
        run_id: UUID,
        parent_run_id: UUID | None = None,
        tags: list[str] | None = None,
        metadata: dict[str, Any] | None = None,
        inputs: dict[str, Any] | None = None,
        **kwargs: Any,
    ) -> None:
        tool_name = serialized.get("name", "unknown")
        # 优先使用结构化 inputs，回退到原始字符串
        args_display = _format_inputs(inputs) if inputs else input_str[:200]
        print(f"  >> tool_start  [{tool_name}]  args={args_display}")
        logger.debug("tool_start: tool=%s run_id=%s inputs=%s", tool_name, run_id, inputs)

    def on_tool_end(
        self,
        output: Any,
        *,
        run_id: UUID,
        parent_run_id: UUID | None = None,
        tags: list[str] | None = None,
        **kwargs: Any,
    ) -> None:
        output_str = str(output)
        preview = output_str[:_RESULT_PREVIEW_LEN]
        suffix = "…" if len(output_str) > _RESULT_PREVIEW_LEN else ""
        print(f"  << tool_end    result={preview}{suffix}")
        logger.debug("tool_end: run_id=%s output_len=%d", run_id, len(output_str))

    def on_tool_error(
        self,
        error: BaseException,
        *,
        run_id: UUID,
        parent_run_id: UUID | None = None,
        tags: list[str] | None = None,
        **kwargs: Any,
    ) -> None:
        print(f"  !! tool_error  {type(error).__name__}: {error}")
        logger.warning("tool_error: run_id=%s error=%s", run_id, error)

    def on_llm_start(
        self,
        serialized: dict[str, Any],
        prompts: list[str],
        *,
        run_id: UUID,
        parent_run_id: UUID | None = None,
        tags: list[str] | None = None,
        metadata: dict[str, Any] | None = None,
        **kwargs: Any,
    ) -> None:
        model_name = serialized.get("kwargs", {}).get("model_name") or serialized.get("name", "llm")
        logger.debug("llm_start: model=%s run_id=%s", model_name, run_id)

    def on_llm_end(
        self,
        response: LLMResult,
        *,
        run_id: UUID,
        parent_run_id: UUID | None = None,
        tags: list[str] | None = None,
        **kwargs: Any,
    ) -> None:
        logger.debug("llm_end: run_id=%s generations=%d", run_id, len(response.generations))

    def on_agent_finish(
        self,
        finish: Any,
        *,
        run_id: UUID,
        parent_run_id: UUID | None = None,
        tags: list[str] | None = None,
        **kwargs: Any,
    ) -> None:
        log_msg = getattr(finish, "log", "") or str(finish)
        preview = log_msg[:200] + "…" if len(log_msg) > 200 else log_msg
        print(f"  -- agent_finish  {preview}")
        logger.debug("agent_finish: run_id=%s", run_id)


# ── 私有辅助 ──

def _format_inputs(inputs: dict[str, Any]) -> str:
    """将工具输入字典格式化为简洁的单行展示。"""
    parts = []
    for k, v in inputs.items():
        v_str = repr(v)
        parts.append(f"{k}={v_str[:80]}{'…' if len(v_str) > 80 else ''}")
    return "{" + ", ".join(parts) + "}"
