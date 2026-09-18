"""按通用标签类别把 Label Studio 导出转换为 YOLO 数据。

该脚本替代历史的单类别/多品牌专用转换入口：
- ``--mode local``：从 LS 导出解析本地图片路径，复制 images 并写 labels。
- ``--mode s3``：LS 任务已包含 s3_bucket/s3_key，只写 labels 和 EC2 下载 manifest。
- ``--mode local-s3``：LS 任务是本地图片地址，结合 s3_images.json 匹配 S3 对象后写 manifest。
"""

# pylint: disable=line-too-long,too-many-locals,too-many-arguments,too-many-positional-arguments,wrong-import-position,too-many-instance-attributes,too-many-return-statements

from __future__ import annotations

import argparse
import csv
import json
import shutil
import sys
from dataclasses import dataclass
from pathlib import Path
from typing import Any
from urllib.parse import parse_qs, unquote, urlsplit

PROJECT_ROOT = Path(__file__).resolve().parents[2]
SCRIPTS_ROOT = PROJECT_ROOT / "scripts"
if str(SCRIPTS_ROOT) not in sys.path:
    sys.path.insert(0, str(SCRIPTS_ROOT))

from common.label_catalog import (  # type: ignore[import-not-found]
    DEFAULT_LABEL_CATALOG,
    LabelClass,
    display_name_map,
    find_label_set,
    load_label_sets,
    normalize_key,
    select_label_classes,
    yolo_yaml_text,
)
from s3.brand_s3_config import load_manifest_records  # type: ignore[import-not-found]

SPLIT_RATIOS = (0.7, 0.2, 0.1)
IMAGE_SUFFIXES = {".bmp", ".jpeg", ".jpg", ".png", ".tif", ".tiff", ".webp"}


@dataclass(frozen=True)
class ConvertedTask:
    """一张图片或一条 S3 训练记录的转换结果。"""

    label_path: Path
    split: str
    box_count: int
    source_task_id: str
    class_counts: dict[str, int]
    image_path: Path | None = None
    image_name: str = ""
    relative_path: str = ""
    s3_bucket: str = ""
    s3_key: str = ""
    s3_uri: str = ""
    source_url: str = ""
    training_image_name: str = ""


def load_export_tasks(export_path: Path) -> list[dict[str, object]]:
    """读取 Label Studio JSON 导出，兼容列表和包含 tasks 的对象。"""
    payload = json.loads(export_path.read_text(encoding="utf-8"))
    if isinstance(payload, list):
        return [item for item in payload if isinstance(item, dict)]
    if isinstance(payload, dict) and isinstance(payload.get("tasks"), list):
        return [item for item in payload["tasks"] if isinstance(item, dict)]
    raise ValueError("Label Studio 导出 JSON 必须是任务列表，或包含 tasks 列表的对象。")


def parse_local_file_url(value: str) -> Path | None:
    """解析 /data/local-files/?d=<path> 形式的本地图片路径。"""
    parsed = urlsplit(value)
    if parsed.path != "/data/local-files/":
        return None
    values = parse_qs(parsed.query).get("d")
    return Path(unquote(values[0])).resolve() if values else None


def task_data(task: dict[str, object]) -> dict[str, Any]:
    """安全获取 task.data 字典。"""
    data = task.get("data")
    return data if isinstance(data, dict) else {}


def task_image_path(task: dict[str, object]) -> Path | None:
    """从任务中解析本地图片路径。"""
    data = task_data(task)
    local_path = data.get("local_path")
    if isinstance(local_path, str) and local_path:
        return Path(local_path).resolve()
    image_value = data.get("image")
    if isinstance(image_value, str) and image_value:
        return parse_local_file_url(image_value)
    return None


def select_annotation(task: dict[str, object], annotation_index: str) -> dict[str, object] | None:
    """选择 first/latest 未取消 annotation。"""
    annotations = task.get("annotations")
    if not isinstance(annotations, list):
        return None
    valid = [item for item in annotations if isinstance(item, dict) and not item.get("was_cancelled")]
    if not valid:
        return None
    return valid[0] if annotation_index == "first" else valid[-1]


def result_to_yolo_line(result: dict[str, object], label_to_class: dict[str, LabelClass]) -> tuple[str, LabelClass] | None:
    """将单个 rectanglelabels 结果转换为 YOLO 行和类别。"""
    if result.get("type") != "rectanglelabels":
        return None
    value = result.get("value")
    if not isinstance(value, dict):
        return None
    labels = value.get("rectanglelabels")
    if not isinstance(labels, list) or not labels:
        return None
    label_class = label_to_class.get(normalize_key(str(labels[0])))
    if label_class is None:
        return None
    try:
        x_value = float(value["x"])
        y_value = float(value["y"])
        width = float(value["width"])
        height = float(value["height"])
    except (KeyError, TypeError, ValueError):
        return None
    center_x = (x_value + width / 2.0) / 100.0
    center_y = (y_value + height / 2.0) / 100.0
    yolo_width = width / 100.0
    yolo_height = height / 100.0
    values = [center_x, center_y, yolo_width, yolo_height]
    if yolo_width <= 0 or yolo_height <= 0 or not all(0.0 <= item <= 1.0 for item in values):
        return None
    return f"{label_class.class_id} " + " ".join(f"{item:.6f}" for item in values), label_class


def annotation_to_yolo_lines(annotation: dict[str, object], label_to_class: dict[str, LabelClass]) -> tuple[list[str], dict[str, int]]:
    """转换 annotation 中的全部矩形框。"""
    results = annotation.get("result")
    if not isinstance(results, list):
        return [], {}
    lines: list[str] = []
    class_counts: dict[str, int] = {}
    for result in results:
        if not isinstance(result, dict):
            continue
        converted = result_to_yolo_line(result, label_to_class)
        if converted is None:
            continue
        line, label_class = converted
        lines.append(line)
        class_counts[label_class.class_name] = class_counts.get(label_class.class_name, 0) + 1
    return lines, class_counts


def split_by_index(index: int, total: int) -> str:
    """按稳定顺序做 70/20/10 数据拆分。"""
    if total <= 1:
        return "train"
    train_cutoff = int(total * SPLIT_RATIOS[0])
    val_cutoff = int(total * (SPLIT_RATIOS[0] + SPLIT_RATIOS[1]))
    if index < train_cutoff:
        return "train"
    return "val" if index < val_cutoff else "test"


def prepare_output_dirs(output_root: Path, mode: str, clear_output: bool) -> None:
    """准备输出目录；S3 模式不复制 images 但仍保持 labels 结构。"""
    kinds = ("labels",) if mode in {"s3", "local-s3"} else ("images", "labels")
    for kind in kinds:
        for split in ("train", "val", "test"):
            directory = output_root / kind / split
            directory.mkdir(parents=True, exist_ok=True)
            if clear_output:
                for path in directory.iterdir():
                    if path.name == ".gitkeep":
                        continue
                    if path.is_file() or path.is_symlink():
                        path.unlink()
                    elif path.is_dir():
                        shutil.rmtree(path)


def safe_label_stem(relative_path: str, fallback: str) -> str:
    """根据相对路径生成不冲突的标签文件名。"""
    raw = relative_path.strip("/") or fallback
    stem = Path(raw).with_suffix("").as_posix().replace("/", "__")
    return stem or Path(fallback).stem


def s3_identity_from_task(task: dict[str, object]) -> tuple[str, str, str]:
    """从 S3 模式 LS 任务中提取 bucket/key/uri。"""
    data = task_data(task)
    bucket = str(data.get("s3_bucket", ""))
    key = str(data.get("s3_key", ""))
    uri = str(data.get("s3_uri", ""))
    if uri.startswith("s3://") and (not bucket or not key):
        bucket, _, key = uri[len("s3://") :].partition("/")
    if bucket and key and not uri:
        uri = f"s3://{bucket}/{key}"
    return bucket, key, uri


def normalized_path_key(path: Path | str | None) -> str:
    """把本地路径归一化成可比较字符串。"""
    if path is None:
        return ""
    text = str(path).strip()
    return str(Path(text).expanduser().resolve()) if text else ""


def task_relative_path(task: dict[str, object], local_images_dir: Path | None) -> str:
    """从任务中读取或推导图片相对路径。"""
    data = task_data(task)
    relative_path = str(data.get("relative_path") or "").strip().strip("/")
    if relative_path:
        return relative_path
    image_path = task_image_path(task)
    if image_path is None or local_images_dir is None:
        return ""
    try:
        return image_path.resolve().relative_to(local_images_dir.resolve()).as_posix()
    except ValueError:
        return ""


def task_image_name(task: dict[str, object]) -> str:
    """从任务中读取图片文件名。"""
    data = task_data(task)
    image_name = str(data.get("image_name") or "").strip()
    if image_name:
        return image_name
    image_path = task_image_path(task)
    return image_path.name if image_path is not None else str(task.get("id", "image"))


def add_unique(index: dict[str, dict[str, Any] | None], key: str, record: dict[str, Any]) -> None:
    """建立唯一索引；重复 key 置空，避免误匹配。"""
    if not key:
        return
    if key in index:
        index[key] = None
    else:
        index[key] = record


def build_manifest_indexes(records: list[dict[str, Any]]) -> tuple[dict[str, dict[str, Any] | None], dict[str, dict[str, Any] | None], dict[str, dict[str, Any] | None]]:
    """为 S3 上传清单建立 local_path、relative_path、image_name 三层索引。"""
    by_local_path: dict[str, dict[str, Any] | None] = {}
    by_relative_path: dict[str, dict[str, Any] | None] = {}
    by_image_name: dict[str, dict[str, Any] | None] = {}
    for record in records:
        status = str(record.get("status") or "")
        uploaded = record.get("uploaded") is True or status in {"uploaded", "skipped_existing", "s3_existing"}
        if not uploaded or not record.get("s3_bucket") or not record.get("s3_key"):
            continue
        add_unique(by_local_path, normalized_path_key(str(record.get("local_path") or "")), record)
        add_unique(by_relative_path, str(record.get("relative_path") or "").strip().strip("/"), record)
        add_unique(by_image_name, str(record.get("image_name") or Path(str(record.get("relative_path") or "")).name), record)
    return by_local_path, by_relative_path, by_image_name


def match_manifest_record(task: dict[str, object], indexes: tuple[dict[str, dict[str, Any] | None], dict[str, dict[str, Any] | None], dict[str, dict[str, Any] | None]], local_images_dir: Path | None) -> tuple[dict[str, Any] | None, str]:
    """把本地 LS 任务匹配到 S3 上传清单。"""
    by_local_path, by_relative_path, by_image_name = indexes
    path_key = normalized_path_key(task_image_path(task))
    if path_key and path_key in by_local_path:
        return by_local_path[path_key], "local_path"
    relative_path = task_relative_path(task, local_images_dir)
    if relative_path and relative_path in by_relative_path:
        return by_relative_path[relative_path], "relative_path"
    image_name = task_image_name(task)
    if image_name and image_name in by_image_name:
        return by_image_name[image_name], "image_name"
    return None, "not_found"


def convert_local_tasks(tasks: list[dict[str, object]], output_root: Path, label_to_class: dict[str, LabelClass], annotation_index: str, include_empty_annotations: bool) -> tuple[list[ConvertedTask], list[str]]:
    """转换本地图片任务，并复制图片到 YOLO images 目录。"""
    warnings: list[str] = []
    annotated_items: list[tuple[dict[str, object], Path, dict[str, object]]] = []
    for task in tasks:
        image_path = task_image_path(task)
        if image_path is None or not image_path.is_file() or image_path.suffix.lower() not in IMAGE_SUFFIXES:
            warnings.append(f"任务 {task.get('id', '-')} 缺少可用本地图片，已跳过。")
            continue
        annotation = select_annotation(task, annotation_index)
        if annotation is None:
            warnings.append(f"图片 {image_path.name} 没有有效 annotation，已跳过。")
            continue
        annotated_items.append((task, image_path, annotation))

    converted: list[ConvertedTask] = []
    for index, (task, image_path, annotation) in enumerate(annotated_items):
        lines, class_counts = annotation_to_yolo_lines(annotation, label_to_class)
        if not lines and not include_empty_annotations:
            warnings.append(f"图片 {image_path.name} annotation 中没有可导出的目标框，已跳过。")
            continue
        split = split_by_index(index, len(annotated_items))
        target_image = output_root / "images" / split / image_path.name
        target_label = output_root / "labels" / split / image_path.with_suffix(".txt").name
        target_image.parent.mkdir(parents=True, exist_ok=True)
        target_label.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(image_path, target_image)
        target_label.write_text("\n".join(lines) + ("\n" if lines else ""), encoding="utf-8")
        converted.append(
            ConvertedTask(
                image_path=target_image,
                label_path=target_label,
                split=split,
                box_count=len(lines),
                source_task_id=str(task.get("id", "")),
                class_counts=class_counts,
                image_name=image_path.name,
                relative_path=image_path.name,
            )
        )
    return converted, warnings


def convert_s3_tasks(tasks: list[dict[str, object]], output_root: Path, label_to_class: dict[str, LabelClass], annotation_index: str, include_empty_annotations: bool) -> tuple[list[ConvertedTask], list[str]]:
    """转换 S3 图片任务，只写 YOLO labels 和 manifest 元数据。"""
    warnings: list[str] = []
    annotated_items: list[tuple[dict[str, object], dict[str, object]]] = []
    for task in tasks:
        bucket, key, _uri = s3_identity_from_task(task)
        if not bucket or not key:
            warnings.append(f"任务 {task.get('id', '-')} / {task_image_name(task)} 缺少 s3_bucket/s3_key，已跳过。")
            continue
        annotation = select_annotation(task, annotation_index)
        if annotation is None:
            warnings.append(f"图片 {task_image_name(task)} 没有有效 annotation，已跳过。")
            continue
        annotated_items.append((task, annotation))

    converted: list[ConvertedTask] = []
    for index, (task, annotation) in enumerate(annotated_items):
        data = task_data(task)
        bucket, key, uri = s3_identity_from_task(task)
        image_name = task_image_name(task)
        relative_path = str(data.get("relative_path") or image_name)
        lines, class_counts = annotation_to_yolo_lines(annotation, label_to_class)
        if not lines and not include_empty_annotations:
            warnings.append(f"图片 {image_name} annotation 中没有可导出的目标框，已跳过。")
            continue
        split = split_by_index(index, len(annotated_items))
        label_stem = safe_label_stem(relative_path, image_name)
        target_label = output_root / "labels" / split / f"{label_stem}.txt"
        target_label.parent.mkdir(parents=True, exist_ok=True)
        target_label.write_text("\n".join(lines) + ("\n" if lines else ""), encoding="utf-8")
        converted.append(
            ConvertedTask(
                label_path=target_label,
                split=split,
                box_count=len(lines),
                source_task_id=str(task.get("id", "")),
                class_counts=class_counts,
                image_name=image_name,
                relative_path=relative_path,
                s3_bucket=bucket,
                s3_key=key,
                s3_uri=uri,
                source_url=str(data.get("source_url") or data.get("image") or uri),
                training_image_name=f"{label_stem}{Path(image_name).suffix}",
            )
        )
    return converted, warnings


def convert_local_s3_tasks(tasks: list[dict[str, object]], manifest_records: list[dict[str, Any]], output_root: Path, label_to_class: dict[str, LabelClass], annotation_index: str, include_empty_annotations: bool, local_images_dir: Path | None) -> tuple[list[ConvertedTask], list[str]]:
    """转换本地地址 LS 任务，并用 S3 上传清单补齐 EC2 下载字段。"""
    warnings: list[str] = []
    indexes = build_manifest_indexes(manifest_records)
    annotated_items: list[tuple[dict[str, object], dict[str, object], dict[str, Any]]] = []
    for task in tasks:
        record, match_mode = match_manifest_record(task, indexes, local_images_dir)
        if record is None:
            warnings.append(f"任务 {task.get('id', '-')} / {task_image_name(task)} 无法唯一匹配 S3 上传清单，匹配方式={match_mode}，已跳过。")
            continue
        annotation = select_annotation(task, annotation_index)
        if annotation is None:
            warnings.append(f"图片 {task_image_name(task)} 没有有效 annotation，已跳过。")
            continue
        annotated_items.append((task, annotation, record))

    converted: list[ConvertedTask] = []
    for index, (task, annotation, record) in enumerate(annotated_items):
        image_name = task_image_name(task)
        relative_path = str(record.get("relative_path") or task_relative_path(task, local_images_dir) or image_name)
        lines, class_counts = annotation_to_yolo_lines(annotation, label_to_class)
        if not lines and not include_empty_annotations:
            warnings.append(f"图片 {image_name} annotation 中没有可导出的目标框，已跳过。")
            continue
        split = split_by_index(index, len(annotated_items))
        label_stem = safe_label_stem(relative_path, image_name)
        image_suffix = Path(image_name).suffix or Path(str(record.get("image_name") or "")).suffix or Path(str(record.get("s3_key") or "")).suffix
        target_label = output_root / "labels" / split / f"{label_stem}.txt"
        target_label.parent.mkdir(parents=True, exist_ok=True)
        target_label.write_text("\n".join(lines) + ("\n" if lines else ""), encoding="utf-8")
        converted.append(
            ConvertedTask(
                label_path=target_label,
                split=split,
                box_count=len(lines),
                source_task_id=str(task.get("id", "")),
                class_counts=class_counts,
                image_name=image_name,
                relative_path=relative_path,
                s3_bucket=str(record.get("s3_bucket") or ""),
                s3_key=str(record.get("s3_key") or ""),
                s3_uri=str(record.get("s3_uri") or ""),
                source_url=str(record.get("https_url") or task_data(task).get("image") or record.get("s3_uri") or ""),
                training_image_name=f"{label_stem}{image_suffix}",
            )
        )
    return converted, warnings


def write_outputs(converted: list[ConvertedTask], warnings: list[str], report_path: Path, data_yaml: Path, dataset_root_for_yaml: str, classes: list[LabelClass], ec2_manifest_json: Path | None, ec2_manifest_csv: Path | None) -> None:
    """写转换报告、YOLO YAML 和可选 EC2 manifest。"""
    report_path.parent.mkdir(parents=True, exist_ok=True)
    total_class_counts: dict[str, int] = {}
    for item in converted:
        for class_name, count in item.class_counts.items():
            total_class_counts[class_name] = total_class_counts.get(class_name, 0) + count
    items = [
        {
            "image": str(item.image_path) if item.image_path else item.image_name,
            "label": str(item.label_path),
            "split": item.split,
            "box_count": item.box_count,
            "class_counts": item.class_counts,
            "source_task_id": item.source_task_id,
            "relative_path": item.relative_path,
            "training_image_name": item.training_image_name,
            "s3_bucket": item.s3_bucket,
            "s3_key": item.s3_key,
            "s3_uri": item.s3_uri,
            "source_url": item.source_url,
        }
        for item in converted
    ]
    report_path.write_text(
        json.dumps(
            {
                "converted_count": len(converted),
                "box_count": sum(item.box_count for item in converted),
                "class_counts": total_class_counts,
                "warnings": warnings,
                "items": items,
            },
            ensure_ascii=False,
            indent=2,
            default=str,
        ),
        encoding="utf-8",
    )
    with report_path.with_suffix(".csv").open("w", encoding="utf-8", newline="") as file:
        writer = csv.DictWriter(file, fieldnames=["image", "label", "split", "box_count", "source_task_id", "class_counts", "s3_uri"])
        writer.writeheader()
        for item in converted:
            writer.writerow(
                {
                    "image": item.image_path or item.image_name,
                    "label": item.label_path,
                    "split": item.split,
                    "box_count": item.box_count,
                    "source_task_id": item.source_task_id,
                    "class_counts": json.dumps(item.class_counts, ensure_ascii=False),
                    "s3_uri": item.s3_uri,
                }
            )
    data_yaml.parent.mkdir(parents=True, exist_ok=True)
    data_yaml.write_text(yolo_yaml_text(dataset_root_for_yaml, classes), encoding="utf-8")
    if ec2_manifest_json is not None:
        ec2_manifest_json.parent.mkdir(parents=True, exist_ok=True)
        ec2_manifest_json.write_text(json.dumps({"items": items}, ensure_ascii=False, indent=2, default=str), encoding="utf-8")
    if ec2_manifest_csv is not None:
        ec2_manifest_csv.parent.mkdir(parents=True, exist_ok=True)
        with ec2_manifest_csv.open("w", encoding="utf-8", newline="") as file:
            writer = csv.DictWriter(file, fieldnames=["split", "image_name", "relative_path", "training_image_name", "s3_bucket", "s3_key", "s3_uri", "label_path", "box_count", "class_counts"])
            writer.writeheader()
            for item in converted:
                writer.writerow(
                    {
                        "split": item.split,
                        "image_name": item.image_name,
                        "relative_path": item.relative_path,
                        "training_image_name": item.training_image_name,
                        "s3_bucket": item.s3_bucket,
                        "s3_key": item.s3_key,
                        "s3_uri": item.s3_uri,
                        "label_path": item.label_path,
                        "box_count": item.box_count,
                        "class_counts": json.dumps(item.class_counts, ensure_ascii=False),
                    }
                )


def parse_args() -> argparse.Namespace:
    """解析命令行参数。"""
    parser = argparse.ArgumentParser(description="按通用标签类别把 Label Studio 导出转换为 YOLO 数据。")
    parser.add_argument("--mode", choices=["local", "s3", "local-s3"], default="local", help="转换模式")
    parser.add_argument("--input", type=Path, required=True, help="Label Studio JSON 导出文件")
    parser.add_argument("--output-root", type=Path, required=True, help="YOLO 数据集输出根目录")
    parser.add_argument("--catalog", type=Path, default=DEFAULT_LABEL_CATALOG, help="通用类别配置 JSON")
    parser.add_argument("--label-set", default="brands", help="类别列表名称")
    parser.add_argument("--labels", default="all", help="类别多选，逗号分隔；all 表示全部启用类别")
    parser.add_argument("--compact-class-ids", action="store_true", help="将所选类别重编号为连续类别 ID")
    parser.add_argument("--annotation-index", choices=["first", "latest"], default="latest", help="选择 first/latest annotation")
    parser.add_argument("--skip-empty-annotations", action="store_true", help="跳过无框 annotation；默认保留为空标签负样本")
    parser.add_argument("--clear-output", action="store_true", help="转换前清空旧输出")
    parser.add_argument("--report", type=Path, required=True, help="转换报告 JSON 输出路径")
    parser.add_argument("--data-yaml", type=Path, required=True, help="YOLO YAML 输出路径")
    parser.add_argument("--dataset-root-for-yaml", default="", help="写入 YAML path 的路径；默认等于 output-root")
    parser.add_argument("--s3-manifest", type=Path, default=None, help="local-s3 模式使用的 S3 上传清单")
    parser.add_argument("--local-images-dir", type=Path, default=None, help="local-s3 模式用于推导相对路径的原图目录")
    parser.add_argument("--ec2-manifest-json", type=Path, default=None, help="S3/本地转 S3 模式下输出 EC2 JSON 清单")
    parser.add_argument("--ec2-manifest-csv", type=Path, default=None, help="S3/本地转 S3 模式下输出 EC2 CSV 清单")
    return parser.parse_args()


def main() -> None:
    """脚本入口。"""
    args = parse_args()
    if not args.input.is_file():
        raise SystemExit(f"Label Studio 导出文件不存在：{args.input}")
    label_set = find_label_set(load_label_sets(args.catalog), args.label_set)
    classes = select_label_classes(label_set, args.labels, args.compact_class_ids)
    label_to_class = display_name_map(classes)
    output_root = args.output_root.resolve()
    prepare_output_dirs(output_root, args.mode, args.clear_output)
    tasks = load_export_tasks(args.input)
    include_empty = not args.skip_empty_annotations
    if args.mode == "local":
        converted, warnings = convert_local_tasks(tasks, output_root, label_to_class, args.annotation_index, include_empty)
    elif args.mode == "s3":
        converted, warnings = convert_s3_tasks(tasks, output_root, label_to_class, args.annotation_index, include_empty)
    else:
        if args.s3_manifest is None or not args.s3_manifest.is_file():
            raise SystemExit(f"local-s3 模式必须传入已存在的 --s3-manifest：{args.s3_manifest}")
        converted, warnings = convert_local_s3_tasks(
            tasks,
            load_manifest_records(args.s3_manifest),
            output_root,
            label_to_class,
            args.annotation_index,
            include_empty,
            args.local_images_dir.resolve() if args.local_images_dir else None,
        )
    yaml_root = args.dataset_root_for_yaml or str(output_root)
    ec2_json = args.ec2_manifest_json if args.mode in {"s3", "local-s3"} else None
    ec2_csv = args.ec2_manifest_csv if args.mode in {"s3", "local-s3"} else None
    write_outputs(converted, warnings, args.report, args.data_yaml, yaml_root, classes, ec2_json, ec2_csv)
    print(f"类别列表：{label_set.name}")
    print(f"类别数：{len(classes)}")
    print(f"转换完成：items={len(converted)}, boxes={sum(item.box_count for item in converted)}")
    print(f"YOLO 数据集目录：{output_root}")
    print(f"YOLO YAML：{args.data_yaml}")
    print(f"转换报告：{args.report}")
    if ec2_json is not None:
        print(f"EC2 图片清单：{ec2_json}")
    if warnings:
        print(f"警告：{len(warnings)} 条，详情见转换报告。")


if __name__ == "__main__":
    main()
