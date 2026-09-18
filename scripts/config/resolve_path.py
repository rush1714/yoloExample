"""把用户传入路径解析为绝对路径，供 Makefile 避免内联 python -c。"""

from __future__ import annotations

import argparse
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[2]


def resolve_path(value: str) -> Path:
    """按项目根目录解析相对路径，并展开用户主目录。"""
    path = Path(value).expanduser()
    if not path.is_absolute():
        path = PROJECT_ROOT / path
    return path.resolve()


def main() -> None:
    """命令行入口。"""
    parser = argparse.ArgumentParser(description="解析项目相对路径或用户路径为绝对路径。")
    parser.add_argument("path", help="待解析路径")
    args = parser.parse_args()
    print(resolve_path(args.path))


if __name__ == "__main__":
    main()
