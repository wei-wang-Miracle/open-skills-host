"""Agent Skills 执行宿主 — CLI 入口

本模块提供命令行界面，支持以下功能：
    1. 列出所有可用技能
    2. 执行指定的单个技能

使用方式:
    # 列出可用技能
    uv run main.py --list

    # 执行技能（交互式输入请求）
    uv run main.py --skill file-processing

    # 执行技能（命令行指定请求）
    uv run main.py --skill file-processing --request "分析 data.csv 中的销售趋势"

    # 指定技能目录
    uv run main.py --skill file-processing --skills-dir ./my_skills
"""

import argparse
import logging
import sys

from agent.runner import run_skill, list_available_skills
from core.config import get_skills_dir


def setup_logging(verbose: bool = False) -> None:
    """配置日志系统

    功能:
        根据 verbose 参数设置日志级别。
        正常模式只显示 WARNING 及以上级别，
        调试模式显示所有 DEBUG 级别信息。

    参数:
        verbose: 是否启用详细日志模式
    """
    level = logging.DEBUG if verbose else logging.WARNING
    logging.basicConfig(
        level=level,
        format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
        datefmt="%H:%M:%S",
    )


def _print_discovered_skills(skills_dir: str) -> None:
    """启动时打印所有已发现技能的元数据。"""
    skills = list_available_skills(skills_dir)
    if not skills:
        print(f"[warn] 未发现任何技能，目录: {skills_dir}\n")
        return
    print(f"\n[skills] 已发现 {len(skills)} 个技能:\n")
    for s in skills:
        print(f"  - {s['name']} : {s['description']} \n")
    print()


def cmd_list(skills_dir: str) -> None:
    """列出所有可用技能

    功能:
        扫描技能目录并以表格形式打印每个技能的名称和描述。

    参数:
        skills_dir: 技能目录路径
    """
    skills = list_available_skills(skills_dir)

    if not skills:
        print("[warn] 未发现任何技能。请检查技能目录:", skills_dir)
        return

    print(f"\n[skills] 已发现 {len(skills)} 个可用技能:\n")
    print(f"{'名称':<25} {'描述'}")
    print("-" * 80)
    for s in skills:
        desc = s["description"]
        print(f"{s['name']:<25} {desc}")
    print()


def cmd_run(skill_name: str, request: str, skills_dir: str) -> None:
    """执行指定的技能

    功能:
        调用 Agent 系统执行指定技能，并格式化输出结果。

    参数:
        skill_name: 技能名称
        request: 用户的自然语言请求
        skills_dir: 技能目录路径
    """
    print(f"\n>> 执行技能: {skill_name}")
    print(f">> 用户请求: {request}")
    print("-" * 60)

    result = run_skill(skill_name, request, skills_dir)

    if result.success:
        print(f"\n[ok] 技能 '{result.skill_name}' 执行成功")
        print(f"[摘要] {result.summary}")
        print("-" * 60)
        if result.artifact_type == "file":
            print("[产出物] 类型: 文件")
            print(f"  - {result.file_path}")
        else:
            print("[产出物] 类型: 文本")
            print(result.text_content)
    else:
        print(f"\n[fail] 技能 '{result.skill_name}' 执行失败")
        print(f"[摘要] {result.summary}")
        print(f"错误信息: {result.error}")

    print("-" * 60)


def main() -> None:
    """CLI 主入口

    功能:
        解析命令行参数并分发到对应的子命令处理函数。
    """
    parser = argparse.ArgumentParser(
        description="Agent Skills 执行宿主 — 基于 LangChain Agent 的技能执行器",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog=(
            "示例:\n"
            "  uv run main.py --list                              # 查看可用技能\n"
            "  uv run main.py --skill file-processing              # 交互式执行\n"
            '  uv run main.py --skill file-processing --request "分析数据"  # 直接执行\n'
        ),
    )

    parser.add_argument(
        "--list", action="store_true",
        help="列出所有可用技能",
    )
    parser.add_argument(
        "--skill", type=str, default=None,
        help="要执行的技能名称",
    )
    parser.add_argument(
        "--request", type=str, default=None,
        help="传给技能的用户请求（不指定则进入交互模式）",
    )
    parser.add_argument(
        "--skills-dir", type=str, default=None,
        help=f"技能目录路径（默认读取 SKILLS_DIR 环境变量，否则 ./skills）",
    )
    parser.add_argument(
        "-v", "--verbose", action="store_true",
        help="启用详细日志输出",
    )

    args = parser.parse_args()

    # 配置日志
    setup_logging(args.verbose)

    # 解析技能目录：命令行 > 环境变量 > 默认值
    skills_dir = args.skills_dir or get_skills_dir()

    # 启动时扫描并打印所有已发现的技能元数据
    _print_discovered_skills(skills_dir)

    # 分发子命令
    if args.list:
        cmd_list(skills_dir)
        return

    if args.skill:
        # 如果未通过命令行指定请求，则进入交互式输入
        request = args.request
        if not request:
            print(f"\n>> 已选择技能: {args.skill}")
            request = input("请输入你的执行请求 > ").strip()
            if not request:
                print("❌ 请求不能为空")
                sys.exit(1)

        cmd_run(args.skill, request, skills_dir)
        return

    # 未指定任何操作时，显示帮助
    parser.print_help()


if __name__ == "__main__":
    main()
