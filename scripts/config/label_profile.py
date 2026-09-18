"""根据通用标签类别配置解析 Makefile 运行参数。"""

# pylint: disable=line-too-long,wrong-import-position

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[2]
SCRIPTS_ROOT = PROJECT_ROOT / "scripts"
if str(SCRIPTS_ROOT) not in sys.path:
    sys.path.insert(0, str(SCRIPTS_ROOT))

from common.label_catalog import (  # type: ignore[import-not-found]
    DEFAULT_LABEL_CATALOG,
    dataset_name_for_selection,
    find_label_set,
    load_label_sets,
    parse_label_filters,
    select_label_classes,
)


def profile(catalog_path: Path, label_set_name: str, labels: str, compact_class_ids: bool) -> dict[str, object]:
    """解析类别列表和多选类别，返回 Makefile 易读取的字段。"""
    label_sets = load_label_sets(catalog_path)
    label_set = find_label_set(label_sets, label_set_name)
    selected = select_label_classes(label_set, labels, compact_class_ids)
    raw_filters = parse_label_filters(labels)
    is_all = not raw_filters or any(item.lower() == "all" for item in raw_filters)
    return {
        "label_set": label_set.name,
        "label_set_display_name": label_set.display_name,
        "labels": "all" if is_all else ",".join(label.name for label in selected),
        "label_filter": "" if is_all else ",".join(label.name for label in selected),
        "dataset_name": dataset_name_for_selection(label_set, labels),
        "display_name": label_set.display_name if is_all else ", ".join(label.name for label in selected),
        "class_count": len(selected),
        "available_sets": [item.name for item in label_sets],
        "available_labels": [label.name for label in label_set.classes],
        "compact_class_ids": compact_class_ids,
    }


def main() -> None:
    """命令行入口，按字段输出，便于 Makefile 调用。"""
    parser = argparse.ArgumentParser(description="解析通用标签类别运行配置。")
    parser.add_argument("--catalog", type=Path, default=DEFAULT_LABEL_CATALOG, help="通用类别配置 JSON")
    parser.add_argument("--label-set", default="brands", help="类别列表名称，例如 brands/general")
    parser.add_argument("--labels", default="all", help="类别多选，逗号分隔；all 表示全部启用类别")
    parser.add_argument("--compact-class-ids", action="store_true", help="将所选类别重编号为从 0 开始的连续 ID")
    parser.add_argument(
        "--field",
        choices=[
            "dataset-name",
            "display-name",
            "label-filter",
            "class-count",
            "available-sets",
            "available-labels",
            "json",
        ],
        default="json",
        help="输出字段",
    )
    args = parser.parse_args()

    try:
        resolved = profile(args.catalog, args.label_set, args.labels, args.compact_class_ids)
    except (FileNotFoundError, ValueError) as exc:
        raise SystemExit(str(exc)) from exc

    fields = {
        "dataset-name": str(resolved["dataset_name"]),
        "display-name": str(resolved["display_name"]),
        "label-filter": str(resolved["label_filter"]),
        "class-count": str(resolved["class_count"]),
        "available-sets": "\n".join(resolved["available_sets"]),
        "available-labels": "\n".join(["all", *resolved["available_labels"]]),
        "json": json.dumps(resolved, ensure_ascii=False),
    }
    print(fields[args.field])


if __name__ == "__main__":
    main()
