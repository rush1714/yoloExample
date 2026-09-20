"""在 Label Studio Django shell 中执行数据库迁移。

Makefile 只负责调用本脚本，不再在 Makefile 里内联 Python 代码，方便
维护、审查和 dry-run 输出。
"""

from __future__ import annotations

from django.core.management import call_command  # type: ignore[import-not-found]


def main() -> None:
    """执行 Django migration。"""
    call_command("migrate", "--no-color")


# label-studio shell 通过标准输入执行本文件，__name__ 不一定是 "__main__"，
# 因此这里直接调用 main()。
main()
