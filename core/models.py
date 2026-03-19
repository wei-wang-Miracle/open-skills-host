"""Agent Skills 的数据模型

本模块提供了用于处理 Agent Skills 的数据模型，
遵循 AgentSkills.io 规范。
"""

from dataclasses import dataclass, field
from typing import Optional


@dataclass
class SkillProperties:
    """来自 SKILL.md 前置元数据的技能元数据（第 1 阶段：约 100 个令牌）

    这是渐进式披露的第 1 阶段 - 仅包含在发现过程中加载的轻量级元数据。
    指令（第 2 阶段）和资源（第 3 阶段）按需单独加载。

    属性:
        name: 短横线连接格式的技能名称（必需）
        description: 技能的用途和使用时机（必需）
        path: SKILL.md 文件的绝对路径（用于加载指令）
        skill_dir: 技能目录的绝对路径（用于加载资源）
        license: 技能许可证（可选）
        compatibility: 兼容性信息（可选）
        allowed_tools: 技能所需的工具模式（可选）
        metadata: 自定义属性的键值对（可选）
    """

    name: str
    description: str
    path: str
    skill_dir: str
    license: Optional[str] = None
    compatibility: Optional[str] = None
    allowed_tools: Optional[str] = None
    metadata: dict[str, str] = field(default_factory=dict)

    def to_dict(self) -> dict:
        """转换为字典，排除 None 值和路径"""
        result = {
            "name": self.name,
            "description": self.description,
            "path": self.path,
            "skill_dir": self.skill_dir,
        }
        if self.license is not None:
            result["license"] = self.license
        if self.compatibility is not None:
            result["compatibility"] = self.compatibility
        if self.allowed_tools is not None:
            result["allowed-tools"] = self.allowed_tools
        if self.metadata:
            result["metadata"] = self.metadata
        return result


__all__ = [
    "SkillProperties",
]
