"""根据品牌标识库生成多品牌 YOLO 数据集 YAML。"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[2]
SCRIPTS_ROOT = PROJECT_ROOT / "scripts"
if str(SCRIPTS_ROOT) not in sys.path:
    sys.path.insert(0, str(SCRIPTS_ROOT))

# 动态添加 scripts 目录到 sys.path，IDE 静态分析无法识别，运行时可正常导入
from common.brand_library import DEFAULT_BRAND_LIBRARY, load_brand_classes, yaml_text  # type: ignore[import-not-found]

DEFAULT_DATA_YAML = PROJECT_ROOT / "data" / "multibrand.yaml"
DEFAULT_PSEUDO_YAML = PROJECT_ROOT / "data" / "multibrand_pseudo.yaml"


def main() -> None:
    """命令行入口。"""
    parser = argparse.ArgumentParser(description="根据品牌库生成正式数据集和伪标注数据集 YAML。")
    parser.add_argument("--brand-library", type=Path, default=DEFAULT_BRAND_LIBRARY, help="品牌标识库 JSON/TXT")
    parser.add_argument("--data-yaml", type=Path, default=DEFAULT_DATA_YAML, help="正式训练数据 YAML 输出路径")
    parser.add_argument("--pseudo-yaml", type=Path, default=DEFAULT_PSEUDO_YAML, help="伪标注数据 YAML 输出路径")
    args = parser.parse_args()

    classes = load_brand_classes(args.brand_library)
    args.data_yaml.write_text(yaml_text("../datasets/multibrand", classes), encoding="utf-8")
    args.pseudo_yaml.write_text(yaml_text("../datasets/multibrand/pseudo", classes), encoding="utf-8")
    print(f"品牌类别数：{len(classes)}")
    print(f"正式数据集 YAML：{args.data_yaml}")
    print(f"伪标注 YAML：{args.pseudo_yaml}")


if __name__ == "__main__":
    main()
