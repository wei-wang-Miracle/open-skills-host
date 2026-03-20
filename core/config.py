"""运行时路径配置 — 从环境变量解析 skills 目录和交换空间目录

支持绝对路径和相对路径（相对于项目根目录）。

环境变量:
    SKILLS_DIR    技能目录（默认 ./skills）
    SKILLS_SWAP_DIR 交换空间目录（默认 ./swap）
"""

from __future__ import annotations

import os
from pathlib import Path

# 项目根目录（core/config.py 的上两级）
_PROJECT_ROOT = Path(__file__).parent.parent.resolve()


def _resolve(env_var: str, default: str) -> str:
    """读取环境变量并将相对路径转为绝对路径（以项目根为基准）。
    支持:
        - 绝对路径: /abs/path/skills
        - ~ 展开:   ~/Downloads/skills
        - 相对路径: ./skills 或 skills（相对于项目根）
    """
    raw = os.environ.get(env_var, "").strip()
    p = Path(raw) if raw else Path(default)
    p = p.expanduser()          # 展开 ~ / ~user
    return str(p if p.is_absolute() else (_PROJECT_ROOT / p).resolve())


def get_skills_dir() -> str:
    """返回技能目录的绝对路径（来自 SKILLS_DIR 环境变量，默认 ./skills）。"""
    return _resolve("SKILLS_DIR", "./skills")


def get_swap_dir() -> str:
    """返回交换空间目录的绝对路径（来自 SKILLS_SWAP_DIR 环境变量，默认 ./swap）。"""
    return _resolve("SKILLS_SWAP_DIR", "./swap")
