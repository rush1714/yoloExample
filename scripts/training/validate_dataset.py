"""
YOLO 数据集校验脚本。

该脚本用于验证 YOLO 格式的数据集是否完整和正确，包括：
- 检查数据集 YAML 配置文件
- 验证图片目录和标签目录的存在性
- 检查每张图片是否有对应的标签文件
- 验证标签文件格式和内容（类别 ID、归一化坐标等）
- 检查是否有孤立的标签文件（没有对应图片）
"""

from __future__ import annotations

import argparse
from dataclasses import dataclass
from pathlib import Path

import yaml

# 支持的图片格式后缀
IMAGE_SUFFIXES = {".bmp", ".jpeg", ".jpg", ".png", ".tif", ".tiff", ".webp"}
# 项目根目录
PROJECT_ROOT = Path(__file__).resolve().parents[2]
# 默认数据集配置文件路径
DEFAULT_DATASET_YAML = PROJECT_ROOT / "config" / "generated" / "multibrand.yaml"


@dataclass(frozen=True)
class DatasetConfig:
    """数据集配置信息，包含根目录、各分割的图片目录和类别 ID 集合。"""
    root: Path  # 数据集根目录
    splits: dict[str, Path]  # 各分割（train/val/test）的图片目录路径
    class_ids: set[int]  # 数据集中定义的所有类别 ID


def resolve_path(value: str, base: Path) -> Path:
    """
    解析路径，支持相对路径和绝对路径。
    
    Args:
        value: 待解析的路径字符串
        base: 相对路径的基准目录
    
    Returns:
        解析后的绝对路径
    """
    path = Path(value)
    # 绝对路径直接返回，相对路径相对于 base 解析
    return path if path.is_absolute() else (base / path).resolve()


def load_config(dataset_yaml: Path) -> DatasetConfig:
    """
    加载并解析数据集 YAML 配置文件。
    
    Args:
        dataset_yaml: YAML 配置文件路径
    
    Returns:
        DatasetConfig 对象，包含解析后的配置信息
    
    Raises:
        ValueError: 配置文件格式不正确
    """
    config = yaml.safe_load(dataset_yaml.read_text(encoding="utf-8"))
    if not isinstance(config, dict):
        raise ValueError("数据集 YAML 必须是对象。")

    # 提取根目录和类别定义
    root_value = config.get("path")
    names = config.get("names")
    if not isinstance(root_value, str) or not isinstance(names, dict) or not names:
        raise ValueError("数据集 YAML 必须包含 path 和非空 names。")

    # 解析各分割（train/val/test）的图片目录路径
    splits: dict[str, Path] = {}
    for split in ("train", "val", "test"):
        value = config.get(split)
        if not isinstance(value, str):
            raise ValueError(f"数据集 YAML 缺少 {split} 图片目录。")
        splits[split] = resolve_path(value, resolve_path(root_value, dataset_yaml.parent))

    return DatasetConfig(
        root=resolve_path(root_value, dataset_yaml.parent),
        splits=splits,
        class_ids={int(class_id) for class_id in names},
    )


def label_path_for(image_path: Path, images_dir: Path, labels_dir: Path) -> Path:
    """
    根据图片路径计算对应的标签文件路径。
    
    Args:
        image_path: 图片文件路径
        images_dir: 图片目录根路径
        labels_dir: 标签目录根路径
    
    Returns:
        对应的标签文件路径
    """
    # 保持相对路径结构，只替换后缀为 .txt
    return labels_dir / image_path.relative_to(images_dir).with_suffix(".txt")


def validate_label(label_path: Path, image_path: Path, class_ids: set[int]) -> list[str]:
    """
    验证单个标签文件的内容格式。
    
    YOLO 标签格式：每行 5 列，分别为 class_id center_x center_y width height
    其中坐标必须是归一化值（0-1 之间）。
    
    Args:
        label_path: 标签文件路径
        image_path: 对应的图片路径（用于错误提示）
        class_ids: 有效的类别 ID 集合
    
    Returns:
        错误信息列表，空列表表示验证通过
    """
    errors: list[str] = []
    # 逐行解析标签文件
    for line_number, line in enumerate(label_path.read_text(encoding="utf-8").splitlines(), start=1):
        if not line.strip():
            continue
        values = line.split()
        prefix = f"{label_path}:{line_number}"
        # 检查列数是否正确
        if len(values) != 5:
            errors.append(f"{prefix}：每行必须有 5 列，当前为 {len(values)} 列。")
            continue
        try:
            class_id = int(values[0])
            coordinates = [float(value) for value in values[1:]]
        except ValueError:
            errors.append(f"{prefix}：类别 ID 必须为整数，坐标必须为数字。")
            continue
        # 检查类别 ID 是否有效
        if class_id not in class_ids:
            errors.append(f"{prefix}：未知类别 ID {class_id}。")
        # 检查坐标是否在归一化范围内
        if not all(0.0 <= value <= 1.0 for value in coordinates):
            errors.append(f"{prefix}：归一化坐标必须位于 [0, 1]。")
        # 检查框的宽度和高度是否大于 0
        if coordinates[2] == 0.0 or coordinates[3] == 0.0:
            errors.append(f"{prefix}：框的宽度和高度必须大于 0。")
    return errors


def validate_dataset(dataset_yaml: Path) -> list[str]:
    """
    完整验证数据集的完整性和正确性。
    
    检查项目：
    1. 各分割的图片目录和标签目录是否存在
    2. 每张图片是否有对应的标签文件
    3. 标签文件内容格式是否正确
    4. 是否有孤立的标签文件（没有对应图片）
    5. 数据集是否包含图片
    
    Args:
        dataset_yaml: 数据集配置文件路径
    
    Returns:
        错误信息列表，空列表表示验证通过
    """
    config = load_config(dataset_yaml)
    errors: list[str] = []
    image_count = 0

    # 遍历每个分割（train/val/test）
    for split, images_dir in config.splits.items():
        labels_dir = config.root / "labels" / split
        # 检查图片目录是否存在
        if not images_dir.is_dir():
            errors.append(f"{split} 图片目录不存在：{images_dir}")
            continue
        # 检查标签目录是否存在
        if not labels_dir.is_dir():
            errors.append(f"{split} 标签目录不存在：{labels_dir}")
            continue

        # 递归查找所有图片文件
        images = [path for path in images_dir.rglob("*") if path.suffix.lower() in IMAGE_SUFFIXES]
        image_count += len(images)
        # 验证每张图片的标签文件
        for image_path in images:
            label_path = label_path_for(image_path, images_dir, labels_dir)
            if not label_path.is_file():
                errors.append(f"缺少标签：图片 {image_path} 对应 {label_path}")
                continue
            errors.extend(validate_label(label_path, image_path, config.class_ids))

        # 检查是否有孤立的标签文件（没有对应图片）
        for label_path in labels_dir.rglob("*.txt"):
            matching_image = next(
                (
                    images_dir / label_path.relative_to(labels_dir).with_suffix(suffix)
                    for suffix in IMAGE_SUFFIXES
                    if (images_dir / label_path.relative_to(labels_dir).with_suffix(suffix)).is_file()
                ),
                None,
            )
            if matching_image is None:
                errors.append(f"标签没有对应图片：{label_path}")

    # 检查数据集是否为空
    if image_count == 0:
        errors.append("数据集没有图片；请先完成标注并放入 images/{train,val,test}。")
    return errors


def main() -> None:
    """数据集校验脚本主入口。"""
    parser = argparse.ArgumentParser(description="校验 YOLO 多品牌数据集。")
    parser.add_argument("--data", type=Path, default=DEFAULT_DATASET_YAML, help="数据集 YAML 路径")
    args = parser.parse_args()

    # 检查配置文件是否存在
    if not args.data.is_file():
        raise SystemExit(f"数据集 YAML 不存在：{args.data}")

    # 执行数据集校验
    errors = validate_dataset(args.data.resolve())
    if errors:
        raise SystemExit("数据集校验失败：\n- " + "\n- ".join(errors))
    print("数据集校验通过。")


if __name__ == "__main__":
    main()
