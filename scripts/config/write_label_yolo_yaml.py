"""根据通用标签类别配置生成 YOLO 数据集 YAML。"""

# pylint: disable=line-too-long,wrong-import-position

from __future__ import annotations

import argparse
import sys
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[2]
SCRIPTS_ROOT = PROJECT_ROOT / "scripts"
if str(SCRIPTS_ROOT) not in sys.path:
    sys.path.insert(0, str(SCRIPTS_ROOT))

from common.label_catalog import (  # type: ignore[import-not-found]
    DEFAULT_LABEL_CATALOG,
    find_label_set,
    load_label_sets,
    select_label_classes,
    yolo_yaml_text,
)

DEFAULT_OUTPUT = PROJECT_ROOT / "config" / "generated" / "labels.yaml"


def main() -> None:
    """解析命令行参数并写入 YOLO YAML。"""
    parser = argparse.ArgumentParser(description="根据通用标签类别配置生成 YOLO 数据集 YAML。")
    parser.add_argument("--catalog", type=Path, default=DEFAULT_LABEL_CATALOG, help="通用类别配置 JSON")
    parser.add_argument("--label-set", default="general", help="类别列表名称，默认使用通用自定义类别集合")
    parser.add_argument("--labels", default="", help="类别多选，逗号分隔；空值表示全部启用类别，all 仅作历史兼容")
    parser.add_argument("--output", type=Path, default=DEFAULT_OUTPUT, help="正式训练 YAML 输出路径")
    parser.add_argument("--pseudo-output", type=Path, default=None, help="可选：伪标注 YAML 输出路径")
    parser.add_argument("--dataset-root", required=True, help="YAML 中的 path 值")
    parser.add_argument("--compact-class-ids", action="store_true", help="将所选类别重编号为连续类别 ID")
    args = parser.parse_args()

    try:
        label_set = find_label_set(load_label_sets(args.catalog), args.label_set)
        classes = select_label_classes(label_set, args.labels, args.compact_class_ids)
    except (FileNotFoundError, ValueError) as exc:
        raise SystemExit(str(exc)) from exc

    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(yolo_yaml_text(args.dataset_root, classes), encoding="utf-8")
    if args.pseudo_output is not None:
        args.pseudo_output.parent.mkdir(parents=True, exist_ok=True)
        args.pseudo_output.write_text(yolo_yaml_text(f"{args.dataset_root}/pseudo", classes), encoding="utf-8")
    print(f"类别列表：{label_set.name}")
    print(f"类别数：{len(classes)}")
    print(f"正式数据集 YAML：{args.output}")
    if args.pseudo_output is not None:
        print(f"伪标注 YAML：{args.pseudo_output}")


if __name__ == "__main__":
    main()
