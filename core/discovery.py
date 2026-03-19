"""技能发现 - 渐进式披露的第 1 阶段

本模块实现了发现阶段，从目录中扫描技能并加载其轻量级元数据。

发现过程遵循以下原则:
1. 扫描技能目录中的 SKILL.md 文件
2. 仅加载前置元数据（每个技能约 100 个令牌）
3. 根据 Agent Skills 规范验证元数据
4. 返回轻量级的 SkillMetadata 对象用于提示词注入
"""

import logging
from pathlib import Path
from typing import List, Optional

# 从统一模块导入
from .parser import find_skill_md, load_metadata
from .errors import ParseError, ValidationError
from .models import SkillProperties

logger = logging.getLogger(__name__)


def is_safe_path(path: Path, base_dir: Path) -> bool:
    """验证路径是否安全地包含在 base_dir 内

    防止通过符号链接或路径操作进行目录遍历攻击。

    参数:
        path: 要验证的路径
        base_dir: 应该包含该路径的基础目录

    返回:
        如果路径安全则返回 True，否则返回 False
    """
    try:
        resolved_path = path.resolve()
        resolved_base = base_dir.resolve()
        resolved_path.relative_to(resolved_base)
        return True
    except (ValueError, OSError, RuntimeError):
        return False


def discover_skills(skills_dir: str | Path) -> List[SkillProperties]:
    """发现目录中的所有技能

    扫描技能目录并从每个技能的 SKILL.md 前置元数据中加载元数据。
    这是渐进式披露的第 1 阶段。

    目录结构:
        skills/
        ├── web-research/
        │   ├── SKILL.md          # 必需
        │   ├── scripts/          # 可选
        │   │   └── helper.py
        │   └── references/       # 可选
        │       └── docs.md
        └── code-review/
            └── SKILL.md

    参数:
        skills_dir: 包含技能子目录的目录路径

    返回:
        按技能名称排序的 SkillProperties 对象列表

    示例:
        >>> skills = discover_skills("./skills")
        >>> for skill in skills:
        ...     print(f"{skill.name}: {skill.description}")
        ...     print(f"  Location: {skill.path}")
    """
    skills_dir = Path(skills_dir).expanduser().resolve()

    if not skills_dir.exists():
        logger.info(f"Skills directory does not exist: {skills_dir}")
        return []

    if not skills_dir.is_dir():
        logger.warning(f"Skills path is not a directory: {skills_dir}")
        return []

    skills: List[SkillProperties] = []

    # 扫描每个子目录
    for skill_dir in skills_dir.iterdir():
        try:
            if not skill_dir.is_dir():
                continue
        except (PermissionError, OSError) as e:
            # macOS 上 .DS_Store 等系统文件可能无权限访问，尝试继续
            logger.debug(f"is_dir引发无权限异常，尝试继续: {skill_dir} error={e}")

        # 安全验证: 验证路径
        if not is_safe_path(skill_dir, skills_dir):
            logger.warning(f"跳过不安全的路径: {skill_dir}")
            continue

        # 查找 SKILL.md
        skill_md_path = find_skill_md(skill_dir)
        if skill_md_path is None:
            logger.debug(f"在 {skill_dir} 中未找到 SKILL.md")
            continue

        # 安全验证: 验证 SKILL.md 路径
        if not is_safe_path(skill_md_path, skills_dir):
            logger.warning(f"跳过不安全的 SKILL.md: {skill_md_path}")
            continue

        # 解析元数据
        try:
            skill_props = load_metadata(skill_dir)
            skills.append(skill_props)
            logger.debug(f"发现技能: {skill_props.name}")

        except (ParseError, ValidationError) as e:
            logger.warning(f"跳过 {skill_dir} 中的无效技能: {e}")
            continue
        except Exception as e:
            logger.error(f"解析 {skill_dir} 时发生意外错误: {e}")
            continue

    # 按名称排序以保持一致性
    skills.sort(key=lambda s: s.name)

    logger.info(f"在 {skills_dir} 中发现了 {len(skills)} 个技能")
    return skills
