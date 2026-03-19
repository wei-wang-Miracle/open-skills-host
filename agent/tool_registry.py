"""基础能力工具集 — 为 Agent 提供与平台无关的通用能力

所有技能共用同一套基础工具，不再按技能脚本生成专属工具。

工具清单:
    get_env_context — 获取当前系统与项目执行环境快照（执行前调用）
    assess_command  — 对待执行命令进行安全风险评估，返回风险等级与分析报告
    shell           — 在宿主系统执行任意 Shell 命令（含静态极端情况兜底）
    read_file       — 读取任意可访问文件的内容
    write_file      — 向指定路径写入文件内容（自动创建父目录）
    zip_path        — 将文件或目录压缩为 zip 文件
    download_file   — 通过 URL 下载文件到指定路径

安全设计:
    双层防护 —
      1. assess_command（方案 C）: Agent 在 ReAct 推理中主动调用，获取结构化风险报告后自行决策
      2. shell 静态兜底（方案 B）: 拦截明确的极端破坏性命令（如 rm -rf /），其余不强制阻断

使用方式:
    from agent.tool_registry import get_builtin_tools
    tools = get_builtin_tools(output_dir)
"""

from __future__ import annotations

import logging
import os
import platform
import re
import shutil
import subprocess
import sys
import urllib.request
from pathlib import Path
from typing import Optional

from langchain_core.tools import StructuredTool
from pydantic import BaseModel, Field

from core.config import get_output_dir

logger = logging.getLogger(__name__)


# ============================================================
# 受保护路径集合（静态兜底 & 风险评估共用）
# ============================================================

def _protected_roots() -> list[str]:
    """返回绝对不应被破坏性操作触及的系统/用户关键路径列表。"""
    home = str(Path.home())
    roots = ["/", "/bin", "/sbin", "/usr", "/etc", "/lib", "/lib64",
             "/boot", "/dev", "/proc", "/sys", "/var/log"]
    # macOS
    roots += ["/System", "/Library", "/Applications", "/private/etc"]
    # 用户家目录本身（允许操作家目录下的子目录，但不允许直接 rm -rf ~）
    roots.append(home)
    return roots


# ============================================================
# get_env_context — 获取系统与项目执行环境快照
# ============================================================

class _GetEnvContextInput(BaseModel):
    pass  # 无需参数


def _make_get_env_context_tool(output_dir: str, project_dir: str) -> StructuredTool:
    def get_env_context() -> str:
        """收集当前系统与项目运行环境的关键信息，返回文本快照。"""
        lines: list[str] = []

        # ── 系统基础信息 ──
        lines.append("## 系统环境")
        lines.append(f"  OS         : {platform.system()} {platform.release()} ({platform.machine()})")
        lines.append(f"  Python     : {sys.version.split()[0]}  ({sys.executable})")
        lines.append(f"  用户       : {os.environ.get('USER', os.environ.get('USERNAME', 'unknown'))}")
        lines.append(f"  Home       : {Path.home()}")
        lines.append(f"  CWD        : {Path.cwd()}")

        # ── 项目路径 ──
        lines.append("\n## 项目路径")
        lines.append(f"  project_dir: {project_dir}")
        lines.append(f"  output_dir : {output_dir}")

        # ── 受保护路径 ──
        lines.append("\n## 受保护路径（破坏性操作禁止触及）")
        for p in _protected_roots():
            lines.append(f"  {p}")

        # ── 关键工具可用性 ──
        lines.append("\n## 关键工具可用性")
        for cmd in ["python3", "uv", "pip3", "brew", "git", "curl", "wget"]:
            path = shutil.which(cmd)
            lines.append(f"  {cmd:10s}: {'可用  ' + path if path else '不可用'}")

        # ── 磁盘空间（output_dir 所在挂载点）──
        lines.append("\n## 磁盘空间")
        try:
            usage = shutil.disk_usage(output_dir)
            lines.append(f"  output_dir 可用: {usage.free // (1024**3)} GB / 总计 {usage.total // (1024**3)} GB")
        except Exception as e:
            lines.append(f"  获取失败: {e}")

        # ── 环境变量摘要（仅列出关键项）──
        lines.append("\n## 关键环境变量")
        for key in ["PATH", "VIRTUAL_ENV", "CONDA_DEFAULT_ENV", "PYENV_VERSION"]:
            val = os.environ.get(key, "")
            if val:
                # PATH 太长，只显示前 3 段
                display = ":".join(val.split(":")[:3]) + ":..." if key == "PATH" else val
                lines.append(f"  {key}: {display}")

        return "\n".join(lines)

    return StructuredTool.from_function(
        func=get_env_context,
        name="get_env_context",
        description=(
            "获取当前系统与项目执行环境的快照，包括:\n"
            "  - OS 版本、Python 路径、当前用户、工作目录\n"
            "  - 项目目录与 output_dir\n"
            "  - 受保护路径列表\n"
            "  - 关键工具可用性（python3、uv、pip3 等）\n"
            "  - 磁盘空间\n"
            "在执行有副作用的 shell 命令前调用，为 assess_command 提供上下文。"
        ),
        args_schema=_GetEnvContextInput,
    )


# ============================================================
# assess_command — 命令安全风险评估
# ============================================================

# 极端破坏性模式：无论如何都应拒绝执行
_HARD_BLOCK_PATTERNS: list[tuple[re.Pattern, str]] = [
    (re.compile(r"rm\s+-[a-zA-Z]*r[a-zA-Z]*f\s+/\s*$"),       "rm -rf / 会清空整个根文件系统"),
    (re.compile(r"rm\s+-[a-zA-Z]*f[a-zA-Z]*r\s+/\s*$"),       "rm -rf / 会清空整个根文件系统"),
    (re.compile(r":\(\)\{.*:\|:&\s*\};:"),                     "fork 炸弹，会耗尽系统进程资源"),
    (re.compile(r"mkfs\b"),                                     "mkfs 会格式化磁盘分区"),
    (re.compile(r"dd\s+.*of=/dev/[a-z]+\b"),                   "dd 写入裸设备，可能损毁磁盘"),
    (re.compile(r">\s*/dev/sd[a-z]\b"),                        "重定向写入裸磁盘设备"),
    (re.compile(r"chmod\s+-[rR]\s+777\s+/\s*$"),               "递归改变根目录权限"),
    (re.compile(r"chown\s+-[rR].*\s+/\s*$"),                   "递归改变根目录所有者"),
]

# 高风险模式：不强制阻断，但评级为 danger，要求 Agent 谨慎决策
_DANGER_PATTERNS: list[tuple[re.Pattern, str]] = [
    (re.compile(r"rm\s+-[a-zA-Z]*r"),                          "递归删除，需确认路径在安全范围内"),
    (re.compile(r"rm\s+-[a-zA-Z]*f"),                          "强制删除，不可恢复"),
    (re.compile(r"sudo\b"),                                     "提权执行，操作范围扩大"),
    (re.compile(r"curl\s+.*\|\s*(bash|sh|python|python3)\b"),  "管道执行远程脚本，存在供应链风险"),
    (re.compile(r"wget\s+.*-O\s*-.*\|\s*(bash|sh)\b"),         "下载并执行远程脚本"),
    (re.compile(r">\s*/etc/"),                                  "重定向写入 /etc/ 系统配置目录"),
    (re.compile(r"pkill\b|killall\b"),                          "批量终止进程，可能影响系统服务"),
    (re.compile(r"shutdown\b|reboot\b|halt\b"),                 "关机/重启命令"),
    (re.compile(r"iptables\b|ufw\b"),                           "修改防火墙规则"),
]

# 需关注模式：评级为 caution
_CAUTION_PATTERNS: list[tuple[re.Pattern, str]] = [
    (re.compile(r"rm\b"),                                       "删除文件，确认路径正确"),
    (re.compile(r"mv\b"),                                       "移动/重命名，确认源路径和目标"),
    (re.compile(r"pip\s+install|pip3\s+install"),               "安装 Python 包，会修改环境"),
    (re.compile(r"npm\s+install|yarn\s+add"),                   "安装 Node 包，会修改环境"),
    (re.compile(r"brew\s+install|brew\s+uninstall"),            "修改 Homebrew 包"),
    (re.compile(r"git\s+reset|git\s+clean"),                    "git 重置/清理，可能丢失未提交更改"),
    (re.compile(r"truncate\b|>\s*\w"),                          "截断或覆盖文件"),
    (re.compile(r"nohup\b|&\s*$"),                              "后台运行，需确认任务可监控"),
]


class _AssessCommandInput(BaseModel):
    command: str = Field(description="待评估的完整 Shell 命令字符串。")
    context: Optional[str] = Field(
        default=None,
        description="可选：将 get_env_context 的输出粘贴于此，提升评估准确性。",
    )


def _make_assess_command_tool(output_dir: str, project_dir: str) -> StructuredTool:
    protected = _protected_roots()

    def assess_command(command: str, context: Optional[str] = None) -> str:
        """对命令进行静态风险分析，返回结构化评估报告。"""
        cmd = command.strip()
        report: list[str] = [f"## 命令安全评估报告", f"命令: `{cmd}`", ""]

        # ── 1. 极端阻断检测 ──
        hard_blocks = []
        for pattern, reason in _HARD_BLOCK_PATTERNS:
            if pattern.search(cmd):
                hard_blocks.append(reason)

        if hard_blocks:
            report.append("### 风险等级: 🔴 BLOCK（强烈建议拒绝执行）")
            report.append("检测到极端破坏性操作模式，执行将造成不可逆系统损坏：")
            for r in hard_blocks:
                report.append(f"  ✗ {r}")
            report.append("")
            report.append("**建议**: 拒绝执行此命令。若任务确实需要类似操作，请重新分解为更安全的子命令。")
            return "\n".join(report)

        # ── 2. 受保护路径检测 ──
        path_risks = []
        for protected_path in protected:
            # 检查命令中是否出现受保护路径（以空格/引号/行尾为边界）
            pattern = re.compile(
                r'(?:^|\s|["\'])' + re.escape(protected_path) + r'(?:\s|["\']|$)'
            )
            if pattern.search(cmd):
                # 只有出现在破坏性命令（rm/mv/chmod/chown/dd）中才告警
                if re.search(r'\b(rm|mv|chmod|chown|dd|truncate|shred)\b', cmd):
                    path_risks.append(f"命令涉及受保护路径: {protected_path}")

        # ── 3. 高风险模式检测 ──
        dangers = []
        for pattern, reason in _DANGER_PATTERNS:
            if pattern.search(cmd):
                dangers.append(reason)

        # ── 4. 关注模式检测 ──
        cautions = []
        for pattern, reason in _CAUTION_PATTERNS:
            if pattern.search(cmd):
                # 避免与 danger 重复
                if not any(reason == d for d in dangers):
                    cautions.append(reason)

        # ── 5. 路径合法性检测 ──
        # 提取命令中所有看起来像路径的参数，检查是否在 output_dir 或 project_dir 内
        safe_roots = [output_dir, project_dir, str(Path.home() / "Downloads"),
                      str(Path.home() / "Desktop"), "/tmp", "/var/folders"]
        extracted_paths = re.findall(r'(?:^|\s)(/[^\s\'\"]+)', cmd)
        outside_safe = []
        for ep in extracted_paths:
            p = Path(ep)
            in_safe = any(
                str(p).startswith(sr) for sr in safe_roots if sr
            )
            in_protected = any(str(p) == pr or str(p).startswith(pr + "/") for pr in protected)
            if in_protected and not in_safe:
                outside_safe.append(ep)

        # ── 6. 综合评级 ──
        if path_risks or dangers:
            level = "🟠 DANGER"
            level_text = "高风险，建议谨慎评估后再决定是否执行"
        elif outside_safe or cautions:
            level = "🟡 CAUTION"
            level_text = "需关注，确认操作范围和意图后可执行"
        else:
            level = "🟢 SAFE"
            level_text = "未检测到明显风险，可正常执行"

        report.append(f"### 风险等级: {level}")
        report.append(f"{level_text}")
        report.append("")

        if path_risks:
            report.append("#### 受保护路径告警")
            for r in path_risks:
                report.append(f"  ⚠ {r}")
            report.append("")

        if dangers:
            report.append("#### 高风险项")
            for d in dangers:
                report.append(f"  ⚠ {d}")
            report.append("")

        if outside_safe:
            report.append("#### 路径范围提示")
            for p in outside_safe:
                report.append(f"  ℹ 路径 '{p}' 不在常用安全目录内，请确认是否预期")
            report.append("")

        if cautions:
            report.append("#### 注意事项")
            for c in cautions:
                report.append(f"  · {c}")
            report.append("")

        # ── 7. 决策建议 ──
        report.append("#### 决策建议")
        if level.startswith("🟠"):
            report.append("  建议先调用 get_env_context 确认受影响范围，确认安全后再执行。")
            report.append("  若命令路径涉及项目外部，请重新规划，限制操作范围在 output_dir 内。")
        elif level.startswith("🟡"):
            report.append("  操作范围在预期内则可执行；若不确定，先用 ls/find 确认目标路径存在。")
        else:
            report.append("  可直接执行。")

        if context:
            report.append("")
            report.append("#### 参考环境上下文（已提供）")
            report.append("  已结合 get_env_context 输出进行综合分析。")

        return "\n".join(report)

    return StructuredTool.from_function(
        func=assess_command,
        name="assess_command",
        description=(
            "对待执行的 Shell 命令进行安全风险静态评估，返回结构化报告。\n"
            "报告包含:\n"
            "  - 风险等级: BLOCK / DANGER / CAUTION / SAFE\n"
            "  - 受保护路径告警（系统目录、家目录等）\n"
            "  - 高风险操作模式识别（递归删除、提权、远程脚本等）\n"
            "  - 路径范围合法性分析\n"
            "  - 具体决策建议\n"
            "使用时机: 执行 rm、mv、sudo、管道执行远程脚本等有副作用命令前调用。\n"
            "可将 get_env_context 的输出传入 context 参数以提升评估准确性。"
        ),
        args_schema=_AssessCommandInput,
    )




class _ShellInput(BaseModel):
    command: str = Field(
        description=(
            "要执行的完整 Shell 命令字符串。支持管道、重定向、多行（用 && 或 ; 连接）。\n"
            "示例:\n"
            "  ls ~/Downloads/data.xlsx\n"
            "  cd ~/Downloads && python3 -c \"import pandas as pd; print(pd.read_excel('data.xlsx').head())\"\n"
            "  uv run --with pandas python3 script.py\n"
            "  pip install openpyxl 2>&1 | tail -5"
        )
    )
    work_dir: Optional[str] = Field(
        default=None,
        description="可选的工作目录（绝对路径）。若为 None，则使用当前进程目录。",
    )
    timeout: int = Field(
        default=120,
        description="命令超时秒数，默认 120。长时间运行的脚本可适当调大。",
    )


def _make_shell_tool() -> StructuredTool:
    def shell(command: str, work_dir: Optional[str] = None, timeout: int = 120) -> str:
        """在宿主系统执行 Shell 命令，返回 stdout + stderr 合并输出及退出码。"""
        # ── 静态兜底：拦截极端破坏性命令 ──
        for pattern, reason in _HARD_BLOCK_PATTERNS:
            if pattern.search(command.strip()):
                return (
                    f"[BLOCKED] 命令被安全策略阻断，拒绝执行。\n"
                    f"原因: {reason}\n"
                    f"命令: {command}\n"
                    f"请调用 assess_command 工具重新评估，或改用更安全的替代命令。"
                )
        try:
            result = subprocess.run(
                command,
                shell=True,
                capture_output=True,
                text=True,
                cwd=work_dir,
                timeout=timeout,
            )
        except subprocess.TimeoutExpired:
            return f"[超时] 命令在 {timeout}s 内未完成: {command}"
        except Exception as e:
            return f"[执行异常] {e}"

        lines = []
        if result.stdout:
            lines.append(result.stdout)
        if result.stderr:
            lines.append(f"[stderr]\n{result.stderr}")
        if result.returncode != 0:
            lines.append(f"[exit code: {result.returncode}]")

        return "\n".join(lines) if lines else "(命令执行成功，无输出)"

    return StructuredTool.from_function(
        func=shell,
        name="shell",
        description=(
            "在宿主系统执行任意 Shell 命令并返回输出（stdout + stderr）。\n"
            "适用场景:\n"
            "  - 信息搜集: ls、find、cat、head、wc、file 等\n"
            "  - Python 执行: python3 -c '...' 或 python3 script.py\n"
            "  - 包管理: pip install、uv add、brew install\n"
            "  - 数据分析: 调用 pandas/openpyxl/等内联代码\n"
            "  - 文件转换、压缩、解压等系统操作\n"
            "返回 stdout 与 stderr 合并文本，以及非零退出码提示。\n"
            "如果命令失败，可读取 [stderr] 和 [exit code] 后修正命令重试。"
        ),
        args_schema=_ShellInput,
    )


# ============================================================
# read_file — 读取任意文件内容
# ============================================================

class _ReadFileInput(BaseModel):
    path: str = Field(
        description=(
            "要读取的文件的绝对路径，或相对于 output_dir 的路径。\n"
            "示例: '/tmp/result.csv'  或  'report/summary.md'"
        )
    )
    encoding: str = Field(
        default="utf-8",
        description="文件编码，默认 utf-8。若读取乱码可尝试 'gbk' 或 'latin-1'。",
    )


def _make_read_file_tool(output_dir: str) -> StructuredTool:
    base = Path(output_dir)

    def read_file(path: str, encoding: str = "utf-8") -> str:
        """读取文件内容。优先尝试绝对路径，否则相对于 output_dir 解析。"""
        p = Path(path)
        target = p if p.is_absolute() else (base / path).resolve()

        if not target.exists():
            return f"[文件不存在] {target}"
        if not target.is_file():
            return f"[不是文件] {target}"
        try:
            return target.read_text(encoding=encoding)
        except Exception as e:
            return f"[读取失败] {target}: {e}"

    return StructuredTool.from_function(
        func=read_file,
        name="read_file",
        description=(
            "读取指定文件的文本内容。\n"
            "path 可以是绝对路径，也可以是相对于 output_dir 的路径。\n"
            "适用于查看脚本、配置、CSV、Markdown、JSON 等文本文件。"
        ),
        args_schema=_ReadFileInput,
    )


# ============================================================
# write_file — 写入文件
# ============================================================

class _WriteFileInput(BaseModel):
    path: str = Field(
        description=(
            "目标文件路径。绝对路径直接写入；相对路径基于 output_dir 解析。\n"
            "父目录不存在时自动创建。禁止 '..' 路径穿越到 output_dir 以外。\n"
            "示例: 'report.md'  或  '/tmp/my_script.py'"
        )
    )
    content: str = Field(description="要写入文件的完整文本内容，覆盖已有内容。")
    encoding: str = Field(default="utf-8", description="文件编码，默认 utf-8。")


def _make_write_file_tool(output_dir: str) -> StructuredTool:
    base = Path(output_dir)

    def write_file(path: str, content: str, encoding: str = "utf-8") -> str:
        """向指定路径写入文件内容，自动创建父目录。"""
        p = Path(path)
        if p.is_absolute():
            target = p
        else:
            target = (base / path).resolve()
            # 安全检查：相对路径不能穿越到 output_dir 外
            try:
                target.relative_to(base.resolve())
            except ValueError:
                return f"[安全错误] 相对路径 '{path}' 超出 output_dir 范围，请使用绝对路径或合法相对路径。"

        try:
            target.parent.mkdir(parents=True, exist_ok=True)
            target.write_text(content, encoding=encoding)
            return f"[已写入] {target}  ({len(content)} 字节)"
        except Exception as e:
            return f"[写入失败] {target}: {e}"

    return StructuredTool.from_function(
        func=write_file,
        name="write_file",
        description=(
            "向指定路径写入文本内容，自动创建父目录。\n"
            "path 可以是绝对路径，也可以是相对于 output_dir 的路径。\n"
            "适用于保存脚本、报告、配置文件等。"
        ),
        args_schema=_WriteFileInput,
    )


# ============================================================
# zip_path — 压缩文件或目录
# ============================================================

class _ZipPathInput(BaseModel):
    source_path: str = Field(
        description=(
            "要压缩的文件或目录的绝对路径，或相对于 output_dir 的路径。\n"
            "示例: '/tmp/my_folder'  或  'results/'"
        )
    )
    output_zip: Optional[str] = Field(
        default=None,
        description=(
            "输出 zip 文件路径（不含 .zip 后缀）。\n"
            "若不指定，则在 source_path 同级生成同名 .zip 文件。"
        ),
    )


def _make_zip_path_tool(output_dir: str) -> StructuredTool:
    base = Path(output_dir)

    def zip_path(source_path: str, output_zip: Optional[str] = None) -> str:
        """将文件或目录压缩为 zip，返回 zip 文件的绝对路径。"""
        sp = Path(source_path)
        src = sp if sp.is_absolute() else (base / source_path).resolve()

        if not src.exists():
            return f"[不存在] {src}"

        if output_zip:
            op = Path(output_zip)
            zip_base = str(op if op.is_absolute() else (base / output_zip).resolve())
        else:
            zip_base = str(src)

        try:
            if src.is_dir():
                zip_file = shutil.make_archive(zip_base, "zip", root_dir=str(src.parent), base_dir=src.name)
            else:
                zip_file = shutil.make_archive(zip_base, "zip", root_dir=str(src.parent), base_dir=src.name)
                # 单文件：用 zipfile 更精确
                import zipfile
                zip_file = zip_base + ".zip"
                with zipfile.ZipFile(zip_file, "w", zipfile.ZIP_DEFLATED) as zf:
                    zf.write(src, src.name)
            return f"[已压缩] {zip_file}"
        except Exception as e:
            return f"[压缩失败] {src}: {e}"

    return StructuredTool.from_function(
        func=zip_path,
        name="zip_path",
        description=(
            "将指定文件或目录压缩为 zip 文件，返回 zip 文件绝对路径。\n"
            "source_path 可以是绝对路径，也可以是相对于 output_dir 的路径。\n"
            "当产出物为目录时，用此工具打包后再返回路径。"
        ),
        args_schema=_ZipPathInput,
    )


# ============================================================
# download_file — 通过 URL 下载文件
# ============================================================

class _DownloadFileInput(BaseModel):
    url: str = Field(description="要下载的文件 URL（http/https）。")
    dest_path: str = Field(
        description=(
            "保存目标路径。绝对路径直接保存；相对路径基于 output_dir 解析。\n"
            "示例: 'data/input.csv'  或  '/tmp/raw.json'"
        )
    )
    timeout: int = Field(default=60, description="下载超时秒数，默认 60。")


def _make_download_file_tool(output_dir: str) -> StructuredTool:
    base = Path(output_dir)

    def download_file(url: str, dest_path: str, timeout: int = 60) -> str:
        """通过 HTTP/HTTPS 下载文件到指定路径。"""
        dp = Path(dest_path)
        dest = dp if dp.is_absolute() else (base / dest_path).resolve()

        try:
            dest.parent.mkdir(parents=True, exist_ok=True)
            req = urllib.request.Request(url, headers={"User-Agent": "Mozilla/5.0"})
            with urllib.request.urlopen(req, timeout=timeout) as resp, open(dest, "wb") as f:
                shutil.copyfileobj(resp, f)
            size = dest.stat().st_size
            return f"[已下载] {dest}  ({size} 字节)"
        except Exception as e:
            return f"[下载失败] {url} → {dest}: {e}"

    return StructuredTool.from_function(
        func=download_file,
        name="download_file",
        description=(
            "通过 HTTP/HTTPS URL 下载文件并保存到指定路径。\n"
            "dest_path 可以是绝对路径，也可以是相对于 output_dir 的路径。\n"
            "适用于下载数据文件、模型权重、远程资源等。"
        ),
        args_schema=_DownloadFileInput,
    )


# ============================================================
# 公共入口
# ============================================================

def get_builtin_tools(output_dir: str | None = None, project_dir: str | None = None) -> list:
    """返回所有技能共用的基础能力工具列表。

    包含:
        get_env_context — 获取系统与项目执行环境快照
        assess_command  — 命令安全风险评估（BLOCK/DANGER/CAUTION/SAFE）
        shell           — 执行任意 Shell 命令（含极端情况静态兜底）
        read_file       — 读取任意可访问文件内容
        write_file      — 写入文件到指定路径
        zip_path        — 压缩文件或目录为 zip
        download_file   — 通过 URL 下载文件

    Args:
        output_dir:  产出物目录路径。None 时从环境变量读取。
        project_dir: 项目根目录路径。None 时使用当前工作目录。
    """
    resolved_output = output_dir or get_output_dir()
    resolved_project = project_dir or str(Path.cwd())
    tools = [
        _make_get_env_context_tool(resolved_output, resolved_project),
        _make_assess_command_tool(resolved_output, resolved_project),
        _make_shell_tool(),
        _make_read_file_tool(resolved_output),
        _make_write_file_tool(resolved_output),
        _make_zip_path_tool(resolved_output),
        _make_download_file_tool(resolved_output),
    ]
    logger.debug("基础工具已初始化: %s", [t.name for t in tools])
    return tools


# 向后兼容：runner.py 仍调用 resolve_allowed_tools，返回空列表即可
def resolve_allowed_tools(
    allowed_tools: str | list | None,
    output_dir: str | None = None,
) -> list:
    """已废弃。基础工具由 get_builtin_tools() 统一提供，不再按技能声明动态注册。"""
    _ = (allowed_tools, output_dir)
    return []
