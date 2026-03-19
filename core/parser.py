"""SKILL.md 文件的 YAML 前置元数据解析

本模块处理遵循 AgentSkills.io 规范的 SKILL.md 文件解析。
"""

import re
from pathlib import Path
from typing import Optional

import strictyaml

from .errors import ParseError, ValidationError


def find_skill_md(skill_dir: Path) -> Optional[Path]:
    """在技能目录中查找 SKILL.md 文件

    优先使用 SKILL.md（大写），但也接受 skill.md（小写）。

    参数:
        skill_dir: 技能目录的路径

    返回:
        SKILL.md 文件的路径，如果未找到则返回 None
    """
    for name in ("SKILL.md", "skill.md"):
        path = skill_dir / name
        if path.exists():
            return path
    return None


def _parse_skill_md(content: str) -> tuple[dict, str]:
    """将 SKILL.md 内容解析为前置元数据和正文

    这是核心解析函数，将 SKILL.md 分割为：
    - frontmatter: YAML 元数据
    - body: Markdown 指令

    参数:
        content: 原始 SKILL.md 内容

    返回:
        (前置元数据字典, 正文字符串) 的元组

    引发:
        ParseError: 如果前置元数据无效
    """
    match = re.match(r'^---\s*\n(.*?)\n---\s*\n?(.*)$', content, re.DOTALL)
    if not match:
        raise ParseError("SKILL.md must start with YAML frontmatter (---) and close with ---")

    frontmatter_str = match.group(1)
    body = match.group(2).strip()

    try:
        parsed = strictyaml.load(frontmatter_str)
        frontmatter = parsed.data
    except strictyaml.YAMLError as e:
        raise ParseError(f"Invalid YAML in frontmatter: {e}")

    if not isinstance(frontmatter, dict):
        raise ParseError("SKILL.md frontmatter must be a YAML mapping")

    # Ensure metadata field is dict of strings
    if "metadata" in frontmatter and isinstance(frontmatter["metadata"], dict):
        frontmatter["metadata"] = {
            str(k): str(v) for k, v in frontmatter["metadata"].items()
        }

    return frontmatter, body


def load_metadata(skill_dir: str | Path):
    """从 SKILL.md 前置元数据加载技能元数据（第 1 阶段：约 100 个令牌）

    这是渐进式披露的第 1 阶段 - 仅加载轻量级元数据，
    不包含完整的指令正文。

    参数:
        skill_dir: 技能目录的路径

    返回:
        包含解析后元数据的 SkillProperties（未加载指令）

    引发:
        ParseError: 如果 SKILL.md 缺失或 YAML 无效
        ValidationError: 如果缺少必填字段（name, description）
    """
    from .models import SkillProperties

    skill_dir = Path(skill_dir).resolve()
    skill_md = find_skill_md(skill_dir)

    if skill_md is None:
        raise ParseError(f"SKILL.md not found in {skill_dir}")

    # Read file and extract frontmatter (ignoring body)
    content = skill_md.read_text()
    frontmatter, _ = _parse_skill_md(content)

    # Validate required fields
    if "name" not in frontmatter:
        raise ValidationError("Missing required field in frontmatter: name")
    if "description" not in frontmatter:
        raise ValidationError("Missing required field in frontmatter: description")

    name = frontmatter["name"]
    description = frontmatter["description"]

    if not isinstance(name, str) or not name.strip():
        raise ValidationError("Field 'name' must be a non-empty string")
    if not isinstance(description, str) or not description.strip():
        raise ValidationError("Field 'description' must be a non-empty string")

    return SkillProperties(
        name=name.strip(),
        description=description.strip(),
        path=str(skill_md.absolute()),
        skill_dir=str(skill_dir.absolute()),
        license=frontmatter.get("license"),
        compatibility=frontmatter.get("compatibility"),
        allowed_tools=frontmatter.get("allowed-tools"),
        metadata=frontmatter.get("metadata"),
    )


def load_instructions(skill_path: str | Path) -> str:
    """从 SKILL.md 正文加载技能指令（第 2 阶段：<5000 个令牌）

    这是渐进式披露的第 2 阶段 - 在技能激活时加载完整的 Markdown 正文（指令）。

    参数:
        skill_path: SKILL.md 文件的路径

    返回:
        不含前置元数据的 Markdown 正文（指令）

    引发:
        ParseError: 如果文件无法读取或解析
    """
    skill_path = Path(skill_path)

    try:
        content = skill_path.read_text(encoding="utf-8")
        _, instructions = _parse_skill_md(content)
        return instructions
    except Exception as e:
        raise ParseError(f"Failed to read instructions from {skill_path}: {e}")


def load_resource(skill_dir: str | Path, resource_path: str) -> str:
    """从技能目录加载资源文件（第 3 阶段：按需加载）

    这是渐进式披露的第 3 阶段 - 仅在明确需要时从 scripts/、
    references/ 或 assets/ 加载文件。

    参数:
        skill_dir: 技能目录的路径
        resource_path: 资源的相对路径（例如 "scripts/helper.py"）

    返回:
        资源文件的内容

    引发:
        ParseError: 如果资源无法读取或在技能目录之外

    示例:
        >>> content = load_resource("/path/to/skill", "references/api-docs.md")
    """
    skill_dir = Path(skill_dir).resolve()
    resource_file = (skill_dir / resource_path).resolve()

    # Security: ensure resource is within skill directory
    try:
        resource_file.relative_to(skill_dir)
    except ValueError:
        raise ParseError(f"Resource path '{resource_path}' is outside skill directory")

    if not resource_file.exists():
        raise ParseError(f"Resource not found: {resource_path}")

    if not resource_file.is_file():
        raise ParseError(f"Resource is not a file: {resource_path}")

    # File size limit (10MB)
    MAX_FILE_SIZE = 10 * 1024 * 1024
    if resource_file.stat().st_size > MAX_FILE_SIZE:
        raise ParseError(f"Resource too large (max 10MB): {resource_path}")

    try:
        return resource_file.read_text(encoding="utf-8")
    except Exception as e:
        raise ParseError(f"Failed to read resource {resource_path}: {e}")


__all__ = [
    "find_skill_md",
    "load_metadata",
    "load_instructions",
    "load_resource",
]
