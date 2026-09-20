"""由已生成的 YOLO 训练集和 S3 上传清单生成 EC2 下载清单。

适用场景：图片先以本地文件形式导入 Label Studio，人工标注后已经通过
``label-to-yolo`` 生成了 ``images/{train,val,test}`` 和
``labels/{train,val,test}``。此时只需要上传这些训练图片到 S3，而不是上传
``raw/images`` 全量原图；本脚本负责把训练图片与 S3 上传清单匹配起来，生成
EC2 下载训练图片所需的 ``ec2_image_manifest.json|csv``。
"""

# pylint: disable=line-too-long,too-many-locals

from __future__ import annotations

import argparse
import csv
import json
import sys
from dataclasses import dataclass
from pathlib import Path
from typing import Any

import yaml

PROJECT_ROOT = Path(__file__).resolve().parents[2]
SCRIPTS_ROOT = PROJECT_ROOT / "scripts"
if str(SCRIPTS_ROOT) not in sys.path:
    sys.path.insert(0, str(SCRIPTS_ROOT))

from s3.brand_s3_config import load_manifest_records  # type: ignore[import-not-found]  # pylint: disable=wrong-import-position

IMAGE_SUFFIXES = {".bmp", ".jpeg", ".jpg", ".png", ".tif", ".tiff", ".webp"}
SPLITS = ("train", "val", "test")
UPLOADED_STATUSES = {"uploaded", "skipped_existing", "s3_existing"}


@dataclass(frozen=True)
class TrainingImage:
    """一张已经进入 YOLO 训练集的图片及其标签文件。"""

    split: str
    image_path: Path
    label_path: Path
    relative_path: str
    training_image_name: str


@dataclass(frozen=True)
class ManifestMatch:
    """训练图片匹配到的一条 S3 上传记录。"""

    record: dict[str, Any]
    match_mode: str


def resolve_project_path(value: Path) -> Path:
    """把命令行传入路径解析成绝对路径。"""
    path = value.expanduser()
    if not path.is_absolute():
        path = PROJECT_ROOT / path
    return path.resolve()


def load_yolo_names(data_yaml: Path) -> dict[str, str]:
    """读取 YOLO YAML 中的类别 ID 到类别名映射，读取失败时返回空映射。"""
    if not data_yaml.is_file():
        return {}
    payload = yaml.safe_load(data_yaml.read_text(encoding="utf-8")) or {}
    names = payload.get("names") if isinstance(payload, dict) else None
    if isinstance(names, dict):
        return {str(key): str(value) for key, value in names.items()}
    if isinstance(names, list):
        return {str(index): str(value) for index, value in enumerate(names)}
    return {}


def iter_training_images(dataset_root: Path) -> list[TrainingImage]:
    """扫描 ``images/{train,val,test}``，并推导对应 label 文件路径。"""
    images_root = dataset_root / "images"
    labels_root = dataset_root / "labels"
    items: list[TrainingImage] = []
    for split in SPLITS:
        split_images_root = images_root / split
        if not split_images_root.is_dir():
            continue
        image_paths = [path for path in split_images_root.rglob("*") if path.is_file() and path.suffix.lower() in IMAGE_SUFFIXES]
        image_paths = sorted(image_paths, key=lambda item, root=split_images_root: item.relative_to(root).as_posix().lower())
        for image_path in image_paths:
            image_name_in_split = image_path.relative_to(split_images_root).as_posix()
            relative_path = f"{split}/{image_name_in_split}"
            label_path = labels_root / split / Path(image_name_in_split).with_suffix(".txt")
            items.append(
                TrainingImage(
                    split=split,
                    image_path=image_path,
                    label_path=label_path,
                    relative_path=relative_path,
                    training_image_name=image_name_in_split,
                )
            )
    return items


def normalized_path_key(path: str | Path | None) -> str:
    """把本地路径归一化成可比较 key。"""
    text = str(path or "").strip()
    return str(Path(text).expanduser().resolve()) if text else ""


def add_unique(index: dict[str, dict[str, Any] | None], key: str, record: dict[str, Any]) -> None:
    """建立唯一索引；重复 key 置空，避免文件名重复时误匹配。"""
    if not key:
        return
    if key in index:
        index[key] = None
        return
    index[key] = record


def is_uploaded_record(record: dict[str, Any]) -> bool:
    """判断一条 S3 清单记录是否代表可用于训练下载的已上传对象。"""
    status = str(record.get("status") or "")
    return (record.get("uploaded") is True or status in UPLOADED_STATUSES) and bool(record.get("s3_bucket")) and bool(
        record.get("s3_key")
    )


def build_manifest_indexes(records: list[dict[str, Any]]) -> tuple[
    dict[str, dict[str, Any] | None],
    dict[str, dict[str, Any] | None],
    dict[str, dict[str, Any] | None],
]:
    """为 S3 上传清单建立 relative_path、local_path、image_name 三层索引。"""
    by_relative_path: dict[str, dict[str, Any] | None] = {}
    by_local_path: dict[str, dict[str, Any] | None] = {}
    by_image_name: dict[str, dict[str, Any] | None] = {}
    for record in records:
        if not is_uploaded_record(record):
            continue
        relative_path = str(record.get("relative_path") or "").strip().strip("/")
        local_path = normalized_path_key(str(record.get("local_path") or ""))
        image_name = str(record.get("image_name") or Path(relative_path).name)
        add_unique(by_relative_path, relative_path, record)
        add_unique(by_local_path, local_path, record)
        add_unique(by_image_name, image_name, record)
    return by_relative_path, by_local_path, by_image_name


def match_training_image(
    image: TrainingImage,
    indexes: tuple[
        dict[str, dict[str, Any] | None],
        dict[str, dict[str, Any] | None],
        dict[str, dict[str, Any] | None],
    ],
) -> ManifestMatch | None:
    """把训练图片匹配到 S3 上传记录。"""
    by_relative_path, by_local_path, by_image_name = indexes
    local_key = normalized_path_key(image.image_path)
    candidates = [
        (image.relative_path, by_relative_path, "relative_path"),
        (local_key, by_local_path, "local_path"),
        (image.image_path.name, by_image_name, "image_name"),
    ]
    for key, index, mode in candidates:
        if key and key in index and index[key] is not None:
            return ManifestMatch(record=index[key] or {}, match_mode=mode)
    return None


def count_label_file(label_path: Path, id_to_name: dict[str, str]) -> tuple[int, dict[str, int]]:
    """统计一个 YOLO label 文件中的框数量和类别数量。"""
    if not label_path.is_file():
        return 0, {}
    box_count = 0
    class_counts: dict[str, int] = {}
    for raw_line in label_path.read_text(encoding="utf-8").splitlines():
        line = raw_line.strip()
        if not line:
            continue
        class_id = line.split()[0]
        class_name = id_to_name.get(class_id, class_id)
        class_counts[class_name] = class_counts.get(class_name, 0) + 1
        box_count += 1
    return box_count, class_counts


def build_ec2_manifest_items(
    dataset_root: Path,
    manifest_records: list[dict[str, Any]],
    data_yaml: Path,
    skip_empty_labels: bool,
) -> tuple[list[dict[str, Any]], list[str]]:
    """构建 EC2 manifest items，并返回 warning 列表。"""
    id_to_name = load_yolo_names(data_yaml)
    indexes = build_manifest_indexes(manifest_records)
    items: list[dict[str, Any]] = []
    warnings: list[str] = []
    for image in iter_training_images(dataset_root):
        if not image.label_path.is_file():
            warnings.append(f"训练图片缺少对应标签，已跳过：{image.relative_path} -> {image.label_path}")
            continue
        box_count, class_counts = count_label_file(image.label_path, id_to_name)
        if box_count == 0 and skip_empty_labels:
            warnings.append(f"训练图片标签为空，已跳过：{image.relative_path}")
            continue
        match = match_training_image(image, indexes)
        if match is None:
            warnings.append(f"训练图片无法匹配 S3 上传清单，已跳过：{image.relative_path}")
            continue
        record = match.record
        items.append(
            {
                "image": str(image.image_path),
                "label": str(image.label_path),
                "split": image.split,
                "box_count": box_count,
                "class_counts": class_counts,
                "source_task_id": "",
                "relative_path": image.relative_path,
                "training_image_name": image.training_image_name,
                "s3_bucket": str(record.get("s3_bucket") or ""),
                "s3_key": str(record.get("s3_key") or ""),
                "s3_uri": str(record.get("s3_uri") or ""),
                "source_url": str(record.get("https_url") or record.get("source_url") or record.get("s3_uri") or ""),
                "match_mode": match.match_mode,
            }
        )
    if not items:
        warnings.append("没有生成任何 EC2 manifest item；请检查 images/labels 与 s3_images.json 是否匹配。")
    return items, warnings


def write_outputs(items: list[dict[str, Any]], warnings: list[str], report: Path, ec2_json: Path, ec2_csv: Path) -> None:
    """写 EC2 manifest JSON/CSV 和排查报告。"""
    report.parent.mkdir(parents=True, exist_ok=True)
    ec2_json.parent.mkdir(parents=True, exist_ok=True)
    ec2_csv.parent.mkdir(parents=True, exist_ok=True)
    payload = {"items": items}
    ec2_json.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
    fieldnames = [
        "split",
        "image_name",
        "relative_path",
        "training_image_name",
        "s3_bucket",
        "s3_key",
        "s3_uri",
        "label_path",
        "box_count",
        "class_counts",
    ]
    with ec2_csv.open("w", encoding="utf-8", newline="") as file:
        writer = csv.DictWriter(file, fieldnames=fieldnames)
        writer.writeheader()
        for item in items:
            writer.writerow(
                {
                    "split": item["split"],
                    "image_name": Path(str(item["image"])).name,
                    "relative_path": item["relative_path"],
                    "training_image_name": item["training_image_name"],
                    "s3_bucket": item["s3_bucket"],
                    "s3_key": item["s3_key"],
                    "s3_uri": item["s3_uri"],
                    "label_path": item["label"],
                    "box_count": item["box_count"],
                    "class_counts": json.dumps(item["class_counts"], ensure_ascii=False),
                }
            )
    report.write_text(
        json.dumps(
            {
                "converted_count": len(items),
                "box_count": sum(int(item.get("box_count") or 0) for item in items),
                "warnings": warnings,
                "items": items,
            },
            ensure_ascii=False,
            indent=2,
        ),
        encoding="utf-8",
    )


def parse_args() -> argparse.Namespace:
    """解析命令行参数。"""
    parser = argparse.ArgumentParser(description="由 YOLO images/labels 和 S3 上传清单生成 EC2 图片下载清单。")
    parser.add_argument("--dataset-root", type=Path, required=True, help="YOLO 数据集根目录")
    parser.add_argument("--s3-manifest", type=Path, required=True, help="S3 上传清单 s3_images.json")
    parser.add_argument("--data-yaml", type=Path, required=True, help="YOLO 数据集 YAML，用于读取类别名")
    parser.add_argument("--ec2-manifest-json", type=Path, required=True, help="输出 EC2 JSON 清单")
    parser.add_argument("--ec2-manifest-csv", type=Path, required=True, help="输出 EC2 CSV 清单")
    parser.add_argument("--report", type=Path, required=True, help="转换报告 JSON 输出路径")
    parser.add_argument("--skip-empty-labels", action="store_true", help="跳过空标签图片；默认保留为空标签负样本")
    return parser.parse_args()


def main() -> None:
    """脚本入口。"""
    args = parse_args()
    dataset_root = resolve_project_path(args.dataset_root)
    s3_manifest = resolve_project_path(args.s3_manifest)
    data_yaml = resolve_project_path(args.data_yaml)
    if not (dataset_root / "images").is_dir():
        raise SystemExit(f"YOLO images 目录不存在：{dataset_root / 'images'}")
    if not (dataset_root / "labels").is_dir():
        raise SystemExit(f"YOLO labels 目录不存在：{dataset_root / 'labels'}")
    if not s3_manifest.is_file():
        raise SystemExit(f"S3 上传清单不存在：{s3_manifest}")
    items, warnings = build_ec2_manifest_items(
        dataset_root,
        load_manifest_records(s3_manifest),
        data_yaml,
        args.skip_empty_labels,
    )
    write_outputs(
        items,
        warnings,
        resolve_project_path(args.report),
        resolve_project_path(args.ec2_manifest_json),
        resolve_project_path(args.ec2_manifest_csv),
    )
    print(f"YOLO 数据集目录：{dataset_root}")
    print(f"S3 上传清单：{s3_manifest}")
    print(f"EC2 图片清单 JSON：{resolve_project_path(args.ec2_manifest_json)}")
    print(f"EC2 图片清单 CSV：{resolve_project_path(args.ec2_manifest_csv)}")
    print(f"转换报告：{resolve_project_path(args.report)}")
    print(f"items={len(items)}, warnings={len(warnings)}")
    if not items:
        raise SystemExit("没有生成任何 EC2 manifest item，已停止。")


if __name__ == "__main__":
    main()
