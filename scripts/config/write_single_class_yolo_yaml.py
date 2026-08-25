"""生成单类别 YOLO 数据集 YAML。"""

from __future__ import annotations

import argparse
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[2]
DEFAULT_OUTPUT = PROJECT_ROOT / "config" / "generated" / "diaper_category_default.yaml"


def yaml_text(dataset_root: str, class_name: str) -> str:
    """生成 Ultralytics 单类别数据集 YAML 文本。"""
    return "\n".join(
        [
            f"path: {dataset_root}",
            "train: images/train",
            "val: images/val",
            "test: images/test",
            "",
            "names:",
            f"  0: {class_name}",
            "",
        ]
    )


def main() -> None:
    """命令行入口。"""
    parser = argparse.ArgumentParser(description="生成单类别 YOLO 数据集 YAML。")
    parser.add_argument("--output", type=Path, default=DEFAULT_OUTPUT, help="YAML 输出路径")
    parser.add_argument("--dataset-root", required=True, help="YAML 中的 path 值")
    parser.add_argument("--class-name", default="纸尿裤", help="YOLO 类别名，默认纸尿裤")
    args = parser.parse_args()

    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(yaml_text(args.dataset_root, args.class_name), encoding="utf-8")
    print(f"单类别 YAML：{args.output}")
    print(f"类别：0 -> {args.class_name}")


if __name__ == "__main__":
    main()
