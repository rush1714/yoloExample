"""根据品牌库解析全品牌或单品牌运行配置。"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[2]
SCRIPTS_ROOT = PROJECT_ROOT / "scripts"
if str(SCRIPTS_ROOT) not in sys.path:
    sys.path.insert(0, str(SCRIPTS_ROOT))

from common.brand_library import (  # type: ignore[import-not-found]
    DEFAULT_BRAND_LIBRARY,
    available_brand_names,
    filter_brand_classes,
    load_brand_classes,
)


def profile(brand_library: Path, brand: str) -> dict[str, object]:
    """解析品牌参数，生成 Makefile 和脚本共用的运行配置。"""
    classes = load_brand_classes(brand_library)
    normalized_brand = brand.strip()
    if not normalized_brand or normalized_brand.lower() == "all":
        return {
            "brand": "all",
            "dataset_name": "multibrand",
            "display_name": "全部品牌",
            "brand_filter": "",
            "compact_class_ids": False,
            "available_brands": available_brand_names(classes),
        }

    selected = filter_brand_classes(classes, [normalized_brand])
    if len(selected) != 1:
        available = ", ".join(available_brand_names(classes))
        raise ValueError(f"未知或不唯一的品牌：{brand}。可选值：all, {available}")
    selected_brand = selected[0]
    return {
        "brand": selected_brand.display_name,
        "dataset_name": selected_brand.class_name,
        "display_name": selected_brand.display_name,
        "brand_filter": selected_brand.display_name,
        "compact_class_ids": True,
        "available_brands": available_brand_names(classes),
    }


def main() -> None:
    """输出可供 Makefile 使用的品牌运行配置字段。"""
    parser = argparse.ArgumentParser(description="根据品牌库解析全品牌或单品牌运行配置。")
    parser.add_argument("--brand-library", type=Path, default=DEFAULT_BRAND_LIBRARY, help="品牌标识库 JSON/TXT")
    parser.add_argument("--brand", default="all", help="all 或品牌显示名、类别名、别名")
    parser.add_argument(
        "--field",
        choices=["dataset-name", "display-name", "brand-filter", "available-brands", "json"],
        default="json",
        help="输出字段",
    )
    args = parser.parse_args()

    try:
        resolved = profile(args.brand_library, args.brand)
    except (FileNotFoundError, ValueError) as exc:
        raise SystemExit(str(exc)) from exc

    fields = {
        "dataset-name": str(resolved["dataset_name"]),
        "display-name": str(resolved["display_name"]),
        "brand-filter": str(resolved["brand_filter"]),
        "available-brands": "\n".join(["all", *resolved["available_brands"]]),
        "json": json.dumps(resolved, ensure_ascii=False),
    }
    print(fields[args.field])


if __name__ == "__main__":
    main()
