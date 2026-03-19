"""技能相关异常

本模块定义了 Agent Skills 系统使用的所有异常。
"""


class SkillError(Exception):
    """所有技能相关错误的基类异常"""
    pass


class ParseError(SkillError):
    """当 SKILL.md 解析失败时引发"""
    pass


class ValidationError(SkillError):
    """当技能属性无效时引发

    属性:
        errors: 验证错误消息列表（可能只包含一条）
    """

    def __init__(self, message: str, errors: list[str] | None = None):
        super().__init__(message)
        self.errors = errors if errors is not None else [message]


class SkillNotFoundError(SkillError):
    """当请求的技能找不到时引发"""
    pass


class SkillActivationError(SkillError):
    """当技能激活失败时引发"""
    pass


__all__ = [
    "SkillError",
    "ParseError",
    "ValidationError",
    "SkillNotFoundError",
    "SkillActivationError",
]
