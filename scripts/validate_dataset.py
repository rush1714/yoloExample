from __future__ import annotations

import argparse
from dataclasses import dataclass
from pathlib import Path

import yaml

IMAGE_SUFFIXES = {".bmp", ".jpeg", ".jpg", ".png", ".tif", ".tiff", ".webp"}
PROJECT_ROOT = Path(__file__).resolve().parents[1]
DEFAULT_DATASET_YAML = PROJECT_ROOT / "data" / "softcare.yaml"


@dataclass(frozen=True)
class DatasetConfig:
    root: Path
    splits: dict[str, Path]
    class_ids: set[int]


def resolve_path(value: str, base: Path) -> Path:
    path = Path(value)
    return path if path.is_absolute() else (base / path).resolve()


def load_config(dataset_yaml: Path) -> DatasetConfig:
    config = yaml.safe_load(dataset_yaml.read_text(encoding="utf-8"))
    if not isinstance(config, dict):
        raise ValueError("数据集 YAML 必须是对象。")

    root_value = config.get("path")
    names = config.get("names")
    if not isinstance(root_value, str) or not isinstance(names, dict) or not names:
        raise ValueError("数据集 YAML 必须包含 path 和非空 names。")

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
    return labels_dir / image_path.relative_to(images_dir).with_suffix(".txt")


def validate_label(label_path: Path, image_path: Path, class_ids: set[int]) -> list[str]:
    errors: list[str] = []
    for line_number, line in enumerate(label_path.read_text(encoding="utf-8").splitlines(), start=1):
        if not line.strip():
            continue
        values = line.split()
        prefix = f"{label_path}:{line_number}"
        if len(values) != 5:
            errors.append(f"{prefix}：每行必须有 5 列，当前为 {len(values)} 列。")
            continue
        try:
            class_id = int(values[0])
            coordinates = [float(value) for value in values[1:]]
        except ValueError:
            errors.append(f"{prefix}：类别 ID 必须为整数，坐标必须为数字。")
            continue
        if class_id not in class_ids:
            errors.append(f"{prefix}：未知类别 ID {class_id}。")
        if not all(0.0 <= value <= 1.0 for value in coordinates):
            errors.append(f"{prefix}：归一化坐标必须位于 [0, 1]。")
        if coordinates[2] == 0.0 or coordinates[3] == 0.0:
            errors.append(f"{prefix}：框的宽度和高度必须大于 0。")
    return errors


def validate_dataset(dataset_yaml: Path) -> list[str]:
    config = load_config(dataset_yaml)
    errors: list[str] = []
    image_count = 0

    for split, images_dir in config.splits.items():
        labels_dir = config.root / "labels" / split
        if not images_dir.is_dir():
            errors.append(f"{split} 图片目录不存在：{images_dir}")
            continue
        if not labels_dir.is_dir():
            errors.append(f"{split} 标签目录不存在：{labels_dir}")
            continue

        images = [path for path in images_dir.rglob("*") if path.suffix.lower() in IMAGE_SUFFIXES]
        image_count += len(images)
        for image_path in images:
            label_path = label_path_for(image_path, images_dir, labels_dir)
            if not label_path.is_file():
                errors.append(f"缺少标签：图片 {image_path} 对应 {label_path}")
                continue
            errors.extend(validate_label(label_path, image_path, config.class_ids))

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

    if image_count == 0:
        errors.append("数据集没有图片；请先完成标注并放入 images/{train,val,test}。")
    return errors


def main() -> None:
    parser = argparse.ArgumentParser(description="校验 YOLO Softcare 数据集。")
    parser.add_argument("--data", type=Path, default=DEFAULT_DATASET_YAML, help="数据集 YAML 路径")
    args = parser.parse_args()

    if not args.data.is_file():
        raise SystemExit(f"数据集 YAML 不存在：{args.data}")

    errors = validate_dataset(args.data.resolve())
    if errors:
        raise SystemExit("数据集校验失败：\n- " + "\n- ".join(errors))
    print("数据集校验通过。")


if __name__ == "__main__":
    main()
