"""导出多个 Label Studio 项目并合并有效标注。

Makefile 只负责传入参数，具体的循环导出、路径拼接和合并逻辑放到本脚本，
避免在 Make 目标里嵌入过长 shell 脚本。
"""

# pylint: disable=line-too-long,wrong-import-position

from __future__ import annotations

import argparse
import os
import subprocess
import sys
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[2]
SCRIPTS_ROOT = PROJECT_ROOT / "scripts"
if str(SCRIPTS_ROOT) not in sys.path:
    sys.path.insert(0, str(SCRIPTS_ROOT))

from label_studio.merge_label_studio_exports import main as merge_main  # type: ignore[import-not-found]


def parse_project_ids(raw_value: str) -> list[str]:
    """解析逗号分隔的 Label Studio 项目 ID 列表。"""
    ids = [item.strip() for item in raw_value.split(",") if item.strip()]
    if not ids:
        raise argparse.ArgumentTypeError("至少需要一个项目 ID，例如 21,20")
    return ids


def export_project(project_id: str, export_path: Path, args: argparse.Namespace) -> None:
    """调用 label-studio CLI 导出单个项目。"""
    export_path.parent.mkdir(parents=True, exist_ok=True)
    command = [
        str(Path(args.venv_bin) / "label-studio"),
        "export",
        "--data-dir",
        str(args.ls_data_dir),
        "--export-path",
        str(export_path),
        project_id,
        args.export_format,
    ]
    env = os.environ.copy()
    env.update(
        {
            "PYTHONSAFEPATH": "1",
            "LABEL_STUDIO_LOCAL_FILES_SERVING_ENABLED": "true",
            "LABEL_STUDIO_LOCAL_FILES_DOCUMENT_ROOT": "/",
            "LABEL_STUDIO_BROWSER_OPEN": "false",
        }
    )
    print(f"导出 Label Studio 项目 {project_id} -> {export_path}")
    subprocess.run(command, cwd=args.ls_work_dir, env=env, check=True)


def run_merge(export_paths: list[Path], args: argparse.Namespace) -> None:
    """复用现有合并脚本执行纯文件合并。"""
    original_argv = sys.argv[:]
    sys.argv = [
        "merge_label_studio_exports.py",
        "--input",
        *[str(path) for path in export_paths],
        "--output",
        str(args.output),
        "--report",
        str(args.report),
        "--annotation-index",
        args.annotation_index,
    ]
    if args.label_name:
        sys.argv.extend(["--label-name", args.label_name])
    try:
        merge_main()
    finally:
        sys.argv = original_argv


def parse_args() -> argparse.Namespace:
    """解析命令行参数。"""
    parser = argparse.ArgumentParser(description="导出并合并多个 Label Studio 项目。")
    parser.add_argument("--project-ids", type=parse_project_ids, required=True, help="项目 ID，多个用英文逗号分隔")
    parser.add_argument("--output", type=Path, required=True, help="合并后的 Label Studio JSON")
    parser.add_argument("--report", type=Path, required=True, help="合并报告 JSON")
    parser.add_argument("--project-export-dir", type=Path, required=True, help="单项目导出临时目录")
    parser.add_argument("--label-name", default="", help="可选：只保留包含该标签名的有效框")
    parser.add_argument("--annotation-index", choices=["first", "latest"], default="latest", help="选择 first/latest annotation")
    parser.add_argument("--export-format", default="JSON", help="Label Studio 导出格式")
    parser.add_argument("--venv-bin", type=Path, default=PROJECT_ROOT / ".venv" / "bin", help="虚拟环境 bin 目录")
    parser.add_argument("--ls-work-dir", type=Path, default=PROJECT_ROOT / ".tmp" / "label-studio", help="Label Studio 工作目录")
    parser.add_argument("--ls-data-dir", type=Path, default=PROJECT_ROOT / ".label-studio-data", help="Label Studio 数据目录")
    return parser.parse_args()


def main() -> None:
    """导出所有项目并执行合并。"""
    args = parse_args()
    args.project_export_dir.mkdir(parents=True, exist_ok=True)
    export_paths = []
    for project_id in args.project_ids:
        export_path = args.project_export_dir / f"project_{project_id}.json"
        export_project(project_id, export_path, args)
        export_paths.append(export_path)
    run_merge(export_paths, args)


if __name__ == "__main__":
    main()
