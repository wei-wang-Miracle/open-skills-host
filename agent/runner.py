"""技能执行器 — 基于 LangChain Agent 的单技能执行入口

核心流程:
    1. 发现阶段 — 从 skills/ 目录定位技能
    2. 工具构建 — 将技能脚本/参考文件转换为 LangChain Tools
    3. 执行阶段 — 创建 Agent 并处理用户请求，结果由 Agent 直接以
                  SkillExecutionResult 结构化输出返回，无需二次处理

使用方式:
    from agent.runner import run_skill
    result = run_skill("file-processing", "分析 data.csv 文件")
"""

from __future__ import annotations

import logging
from typing import Literal

from pydantic import BaseModel
from langchain.agents import create_agent

from core.config import get_skills_dir, get_swap_dir
from core.discovery import discover_skills, scan_skill_scripts
from core.errors import SkillNotFoundError
from core.parser import load_instructions
from agent.llm import get_chat_model
from agent.tool_registry import get_builtin_tools
from agent.callbacks import SkillEventLogger

logger = logging.getLogger(__name__)


class SkillExecutionResult(BaseModel):
    """技能执行的完整结果，由 Agent 直接以结构化输出填充。

    Fields:
        success:       是否执行成功
        skill_name:    技能名称
        artifact_type: 产出物类型 — "file" 表示生成了文件，"text" 表示纯文本输出
        file_path:     当 artifact_type=="file" 时，最终产出物的单一文件路径
                       （若产出为目录，须先调用 finalize_folder 压缩为 zip，再填写 zip 路径）
        text_content:  当 artifact_type=="text" 时，Agent 最终回复的文本内容
        summary:       执行过程简述（工具调用次数、关键步骤）
        error:         失败时的错误信息
    """
    success: bool
    skill_name: str
    artifact_type: Literal["file", "text"] = "text"
    file_path: str = ""
    text_content: str = ""
    summary: str = ""
    error: str = ""


# ── 主入口 ──

def run_skill(
    skill_name: str,
    user_request: str,
    skills_dir: str | None = None,
    output_dir: str | None = None,
    input_dir: str | None = None,
) -> SkillExecutionResult:
    """执行单个技能的主入口函数。

    Args:
        skill_name:   技能名称。
        user_request: 自然语言执行请求。
        skills_dir:   技能目录，None 时从环境变量读取。
        output_dir:   产出物目录，None 时从环境变量读取。
        input_dir:    输入文件目录，非 None 时通过 SKILL_INPUT_DIR 环境变量注入给脚本。
    """
    logger.info("开始执行技能: name=%s", skill_name)
    resolved_dir = skills_dir or get_skills_dir()
    resolved_swap = output_dir or get_swap_dir()
    print(f"[1/3] 发现阶段  扫描技能目录: {resolved_dir}")
    skills = discover_skills(resolved_dir)
    target_skill = next((s for s in skills if s.name == skill_name), None)
    if target_skill is None:
        available = [s.name for s in skills]
        raise SkillNotFoundError(f"未找到技能 '{skill_name}'。可用技能: {available}")
    print(f"         定位技能: {target_skill.name}  ({target_skill.path})")

    # ── 2. 构建工具集 ──
    print(f"[2/3] 工具构建  加载基础能力工具")
    llm = get_chat_model()

    all_tools = get_builtin_tools(output_dir=resolved_swap, project_dir=resolved_dir)

    tool_names = [t.name for t in all_tools]
    print(f"         注册工具: {tool_names}")

    # ── 3. 执行 Agent ──
    print(f"[3/3] 执行阶段  启动 Agent")
    instructions = load_instructions(target_skill.path)
    skill_desc = f"{target_skill.description}\n\n## 技能指令\n{instructions}"

    # 扫描技能目录下所有可执行脚本
    skill_scripts = scan_skill_scripts(target_skill.skill_dir)
    if skill_scripts:
        scripts_lines = "\n".join(
            f"    - {s['rel_path']}  →  {s['path']}" for s in skill_scripts
        )
        scripts_hint = f"\n\n    ## 技能脚本清单\n    当前技能包含以下可执行脚本（可通过 shell 工具直接调用绝对路径）:\n{scripts_lines}"
    else:
        scripts_hint = ""

    # 若有输入文件目录，将其告知 Agent（可通过 shell 或 read_file 工具直接访问）
    input_dir_hint = (
        f"\n    ## 输入文件\n    本次调用提供了输入文件，已下载到目录: '{input_dir}'\n"
        f"    可通过 shell 工具（如 ls、python3 -c 等）或 read_file 工具直接读取该目录下的文件。\n"
        if input_dir else ""
    )

    system_prompt = f'''
    你是一个专业的Agent Skill技能执行器，你的目标是保证Agent Skill完整执行，包含脚本。
    当前激活的技能是 '{target_skill.name}'
    当前激活的技能描述是 '{target_skill.description}'
    当前激活的使用说明文档是 '{skill_desc}'
    当前激活的可用工具是 '{tool_names}'{input_dir_hint}
    当前技能本身存在的脚本是 '{scripts_hint}'，你可以使用shell调用他们

    ## 产出物质量标准（必须遵守）

    ### 通用质量要求
    1. 【专业级别】产出物应达到专业从业者标准，不能只完成最低要求或敷衍了事
    2. 【业务相关性】深入理解用户的业务意图，产出物应直接解决用户的实际问题
    3. 【完整性】确保产出物包含所有必要的组成部分，不遗漏关键内容
    4. 【可用性】产出物应立即可用，无需用户二次加工或修复
    5. 【最终性】产出物应遵循最终性，即不需要关注中间过程，只产出最终产物

    ### 格式与结构要求
    1. 【层次分明】产出物应有清晰的结构层次（如：总览→详情→原始数据）
    2. 【格式规范】遵循行业通用格式标准，保持专业外观
    3. 【可读性】使用适当的排版、标题、分隔，便于阅读和理解
    4. 【元信息】包含必要的元信息（如：生成时间、数据来源、统计口径说明）

    ### 数据分析类产出物（Excel/报告）特别要求
    1. 【多维度分析】不能只做表面统计，必须从多个业务维度深入分析
    2. 【多工作表结构】Excel报告应包含多个工作表而非单一数据堆砌
    3. 【可视化增强】优先通过在Excel报告插入图表和条件格式提升信息传达效率
    4. 【数据质量】检查并报告数据质量问题（空值、异常值、重复等）

    ### 代码/文档类产出物特别要求
    1. 【结构清晰】代码有合理的模块划分，文档有清晰的章节结构
    2. 【注释/说明】关键逻辑有必要的注释或说明
    3. 【可维护性】产出物易于后续修改和扩展

    ## 执行铁律（不得违反）
    1. 【禁止幻觉】未调用工具并收到成功返回前，绝对不能声称任务已完成或描述任何执行结果。
    2. 【工具优先】所有实质性操作（创建文件、执行脚本、修改内容）必须通过调用工具完成，不能以文字描述代替。
    3. 【工具执行】需要执行代码或查阅文件时，优先使用 shell 工具（支持 python3 -c、cat、ls 等）或 read_file 工具，不要猜测内容。
    4. 【脚本执行】需要执行 skill 下的 scripts 目录下的脚本时，优先使用 shell 工具（如 python3 -c、bash、uv 命令等）执行，并根据说明书提供的用法说明替换脚本中的必要内容，不要随意替换。
    5. 【如实报告错误】工具调用失败时，必须如实汇报错误信息，分析失败原因后再尝试修正。
    - 禁止在工具持续失败后改用文字描述来假装完成任务。
    - 同一工具调用失败超过 3 次后，立即停止重试，将 success=false、error 填写失败原因，直接返回结构化结果。
    - 【严禁无限循环】不得对同一操作反复尝试超过 5 次。超过限制后必须立即终止并返回带有 error 字段的结构化结果。
    6. 【产出物核实】最终回复中填写的 file_path，必须是工具调用返回结果中真实存在的路径，不得自行编造。
    ## 安全评估规范（ReAct 顺序）
    在执行任何有副作用的 shell 命令之前，按以下顺序推理：
    Step 1 — 调用 assess_command，传入待执行命令，获取风险评估报告。
    Step 2 — 阅读报告中的风险等级：
      · SAFE    → 直接执行 shell。
      · CAUTION → 确认命令路径和意图符合任务预期后再执行 shell。
      · DANGER  → 必须先调用 get_env_context 确认环境，再结合报告重新规划命令，
                   确保操作范围限定在 output_dir 或任务所需的最小范围内，方可执行。
      · BLOCK   → 禁止执行，立即将 success=false、error 填写评估报告中的阻断原因，终止任务。
    Step 3 — 执行 shell（若评估允许），观察结果，继续任务。
    以下场景可跳过评估直接执行（风险极低）：
      - 只读命令: ls、cat、head、tail、find、which、echo、pwd、env、python3 --version 等
      - 包安装到虚拟环境: pip install、uv add（无 sudo）
      - 在 output_dir 内的文件创建/修改操作
    ## 产出物处理规则
    - 产出物是单个文件：直接将文件路径填入 file_path。
    - 产出物是一个目录（文件夹）：必须先调用 zip_path 工具将该目录打包为 zip，
      再将 zip_path 返回的 zip 文件路径填入 file_path。
      禁止将目录路径直接填入 file_path。
    ## 输出要求（结构化）
    执行完成后，直接以 JSON 返回 SkillExecutionResult 结构：
    - success: 是否执行成功（布尔值）
    - skill_name: "{target_skill.name}"
    - artifact_type: "file"（有生成文件时）或 "text"（纯文本输出时）
    - file_path: 工具调用返回的真实文件路径（仅 artifact_type=="file" 时填写，目录须先压缩）
    - text_content: Agent 的文本回答（仅 artifact_type=="text" 时填写）
    - summary: 用中文简述：调用了哪些工具、工具返回了什么、是否成功
    - error: 失败原因（成功时留空字符串）
    '''

    callback = SkillEventLogger()

    try:
        agent = create_agent(
            model=llm,
            tools=all_tools,
            system_prompt=system_prompt,
            response_format=SkillExecutionResult,
        )
        raw = agent.invoke(
            {"messages": [{"role": "user", "content": user_request}]},
            config={"callbacks": [callback], "recursion_limit": 100},
        )
        result: SkillExecutionResult = raw["structured_response"]

        print(f"         完成")
        return result

    except Exception as e:
        err_msg = str(e)
        # LangGraph recursion_limit 超出时给出更明确的错误信息
        if "recursion_limit" in err_msg.lower() or "graphrecursionerror" in type(e).__name__.lower():
            err_msg = f"Agent 超出最大步骤限制（recursion_limit=100），可能陷入无限循环。请检查技能脚本或降低任务复杂度。原始错误: {err_msg}"
        logger.error("技能执行失败: %s - %s", target_skill.name, e)
        return SkillExecutionResult(
            success=False,
            skill_name=target_skill.name,
            summary=f"执行异常: {type(e).__name__}",
            error=err_msg,
        )


def list_available_skills(skills_dir: str | None = None) -> list[dict]:
    """列出所有可用技能的摘要信息。"""
    return [
        {"name": s.name, "description": s.description}
        for s in discover_skills(skills_dir or get_skills_dir())
    ]
