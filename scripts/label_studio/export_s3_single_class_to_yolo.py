"""将使用 S3 图片地址的单类别 Label Studio 导出转换为 YOLO 标签和 EC2 下载清单。"""

# pylint: disable=line-too-long,import-error,too-many-instance-attributes,too-many-locals,too-many-arguments,too-many-positional-arguments

from __future__ import annotations

import argparse
import csv
import json
import shutil
import sys
from dataclasses import dataclass
from pathlib import Path
from typing import Any

PROJECT_ROOT = Path(__file__).resolve().parents[2]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from scripts.label_studio.export_single_class_to_yolo import (  # pylint: disable=wrong-import-position
    annotation_to_yolo_lines,
    load_export_tasks,
    select_annotation,
    split_by_index,
)
from scripts.s3.brand_s3_config import DEFAULT_CONFIG_PATH, load_config  # pylint: disable=wrong-import-position


@dataclass(frozen=True)
class S3ConvertedTask:
    """一张 S3 图片的 YOLO 标签转换结果。"""

    label_path: Path
    split: str
    box_count: int
    source_task_id: str
    image_name: str
    relative_path: str
    s3_bucket: str
    s3_key: str
    s3_uri: str
    source_url: str
    training_image_name: str


def task_data(task: dict[str, Any]) -> dict[str, Any]:
    """安全获取 Label Studio task.data。"""
    data = task.get("data")
    return data if isinstance(data, dict) else {}


def s3_identity_from_task(task: dict[str, Any]) -> tuple[str, str, str]:
    """从任务中提取 bucket/key/uri；三者是 EC2 下载图片的最低信息。"""
    data = task_data(task)
    bucket = str(data.get("s3_bucket", ""))
    key = str(data.get("s3_key", ""))
    uri = str(data.get("s3_uri", ""))
    if uri.startswith("s3://") and (not bucket or not key):
        without_scheme = uri[len("s3://") :]
        bucket, _, key = without_scheme.partition("/")
    if bucket and key and not uri:
        uri = f"s3://{bucket}/{key}"
    return bucket, key, uri


def safe_label_stem(relative_path: str, fallback: str) -> str:
    """根据图片相对路径生成不会冲突的标签文件名。"""
    raw = relative_path.strip("/") or fallback
    stem = Path(raw).with_suffix("").as_posix().replace("/", "__")
    return stem or Path(fallback).stem


def prepare_output_dirs(output_root: Path, clear_output: bool) -> None:
    """准备 labels 目录；S3 流程不在本地生成 images 大文件。"""
    for split in ("train", "val", "test"):
        directory = output_root / "labels" / split
        directory.mkdir(parents=True, exist_ok=True)
        if clear_output:
            for path in directory.iterdir():
                if path.name == ".gitkeep":
                    continue
                if path.is_file() or path.is_symlink():
                    path.unlink()
                elif path.is_dir():
                    shutil.rmtree(path)


def convert_tasks(
    tasks: list[dict[str, Any]],
    output_root: Path,
    label_name: str,
    annotation_index: str,
    include_empty_annotations: bool,
) -> tuple[list[S3ConvertedTask], list[str]]:
    """把 Label Studio 导出转换为 YOLO labels 和 EC2 图片 manifest 记录。"""
    warnings: list[str] = []
    annotated_items: list[tuple[dict[str, Any], dict[str, Any]]] = []
    for task in tasks:
        bucket, key, _uri = s3_identity_from_task(task)
        image_name = str(task_data(task).get("image_name", task.get("id", "image")))
        if not bucket or not key:
            warnings.append(f"任务 {task.get('id', '-')} / {image_name} 缺少 s3_bucket/s3_key，已跳过。")
            continue
        annotation = select_annotation(task, annotation_index)
        if annotation is None:
            warnings.append(f"图片 {image_name} 没有有效 annotation，已跳过。")
            continue
        annotated_items.append((task, annotation))

    converted: list[S3ConvertedTask] = []
    for index, (task, annotation) in enumerate(annotated_items):
        data = task_data(task)
        bucket, key, uri = s3_identity_from_task(task)
        image_name = str(data.get("image_name") or Path(key).name)
        relative_path = str(data.get("relative_path") or image_name)
        lines = annotation_to_yolo_lines(annotation, label_name)
        if not lines and not include_empty_annotations:
            warnings.append(f"图片 {image_name} annotation 中没有 {label_name} 框，已跳过。")
            continue
        split = split_by_index(index, len(annotated_items))
        label_name_stem = safe_label_stem(relative_path, image_name)
        target_label = output_root / "labels" / split / f"{label_name_stem}.txt"
        target_label.parent.mkdir(parents=True, exist_ok=True)
        target_label.write_text("\n".join(lines) + ("\n" if lines else ""), encoding="utf-8")
        converted.append(
            S3ConvertedTask(
                label_path=target_label,
                split=split,
                box_count=len(lines),
                source_task_id=str(task.get("id", "")),
                image_name=image_name,
                relative_path=relative_path,
                s3_bucket=bucket,
                s3_key=key,
                s3_uri=uri,
                source_url=str(data.get("source_url") or data.get("image") or uri),
                training_image_name=f"{label_name_stem}{Path(image_name).suffix}",
            )
        )
    return converted, warnings


def write_single_class_yaml(output_path: Path, dataset_root: Path, label_name: str) -> None:
    """生成本地/远端都可理解的单类别 YOLO YAML。"""
    output_path.parent.mkdir(parents=True, exist_ok=True)
    text = "\n".join(
        [
            f"path: {dataset_root}",
            "train: images/train",
            "val: images/val",
            "test: images/test",
            "",
            "names:",
            f"  0: {label_name}",
            "",
        ]
    )
    output_path.write_text(text, encoding="utf-8")


def write_reports(
    converted: list[S3ConvertedTask],
    warnings: list[str],
    report_path: Path,
    manifest_json: Path,
    manifest_csv: Path,
    dataset_name: str,
) -> None:
    """写转换报告和 EC2 图片下载清单。"""
    report_path.parent.mkdir(parents=True, exist_ok=True)
    manifest_json.parent.mkdir(parents=True, exist_ok=True)
    items = [item.__dict__ | {"label_path": str(item.label_path)} for item in converted]
    report_payload = {
        "dataset_name": dataset_name,
        "converted_count": len(converted),
        "box_count": sum(item.box_count for item in converted),
        "class_counts": {"0": sum(item.box_count for item in converted)},
        "warnings": warnings,
        "items": items,
    }
    report_path.write_text(json.dumps(report_payload, ensure_ascii=False, indent=2, default=str), encoding="utf-8")
    manifest_payload = {"dataset_name": dataset_name, "items": items}
    manifest_json.write_text(json.dumps(manifest_payload, ensure_ascii=False, indent=2, default=str), encoding="utf-8")
    with report_path.with_suffix(".csv").open("w", encoding="utf-8", newline="") as file:
        writer = csv.DictWriter(file, fieldnames=["image", "label", "split", "box_count", "source_task_id", "s3_uri"])
        writer.writeheader()
        for item in converted:
            writer.writerow(
                {
                    "image": item.image_name,
                    "label": item.label_path,
                    "split": item.split,
                    "box_count": item.box_count,
                    "source_task_id": item.source_task_id,
                    "s3_uri": item.s3_uri,
                }
            )
    with manifest_csv.open("w", encoding="utf-8", newline="") as file:
        writer = csv.DictWriter(
            file,
            fieldnames=[
                "split",
                "image_name",
                "relative_path",
                "training_image_name",
                "s3_bucket",
                "s3_key",
                "s3_uri",
                "label_path",
                "box_count",
            ],
        )
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
                }
            )


def parse_args() -> argparse.Namespace:
    """解析命令行参数。"""
    parser = argparse.ArgumentParser(description="将 S3 图片 Label Studio 导出转换为 YOLO 标签和 EC2 下载清单。")
    parser.add_argument("--config", type=Path, default=DEFAULT_CONFIG_PATH, help="S3 工作流 YAML 配置路径")
    parser.add_argument("--input", type=Path, default=None, help="Label Studio JSON 导出文件")
    parser.add_argument("--output-root", type=Path, default=None, help="S3 YOLO 数据集根目录")
    parser.add_argument("--dataset-name", default="", help="数据集短名称")
    parser.add_argument("--label-name", default="", help="单类别标签名")
    parser.add_argument("--data-yaml", type=Path, default=None, help="YOLO YAML 输出路径")
    parser.add_argument("--annotation-index", choices=["first", "latest"], default="latest", help="选择 first/latest annotation")
    parser.add_argument("--skip-empty-annotations", action="store_true", help="跳过无框 annotation；默认保留为空标签负样本")
    parser.add_argument("--clear-output", action="store_true", help="转换前清空 labels 旧文件")
    parser.add_argument("--report", type=Path, default=None, help="转换报告 JSON 输出路径")
    parser.add_argument("--ec2-manifest-json", type=Path, default=None, help="EC2 图片下载 JSON 清单输出路径")
    parser.add_argument("--ec2-manifest-csv", type=Path, default=None, help="EC2 图片下载 CSV 清单输出路径")
    return parser.parse_args()


def main() -> None:
    """脚本入口。"""
    args = parse_args()
    config = load_config(args.config, dataset_name=args.dataset_name, label_name=args.label_name, data_yaml=args.data_yaml or "")
    input_path = args.input or config.label_studio_export_path
    output_root = (args.output_root or config.dataset_root).resolve()
    report_path = args.report or config.yolo_report_json
    ec2_manifest_json = args.ec2_manifest_json or config.ec2_manifest_json
    ec2_manifest_csv = args.ec2_manifest_csv or config.ec2_manifest_csv
    data_yaml = args.data_yaml or config.data_yaml
    if not input_path.is_file():
        raise SystemExit(f"Label Studio 导出文件不存在：{input_path}")
    prepare_output_dirs(output_root, args.clear_output)
    converted, warnings = convert_tasks(
        tasks=load_export_tasks(input_path),
        output_root=output_root,
        label_name=config.label_name,
        annotation_index=args.annotation_index,
        include_empty_annotations=not args.skip_empty_annotations,
    )
    write_single_class_yaml(data_yaml, output_root, config.label_name)
    write_reports(converted, warnings, report_path, ec2_manifest_json, ec2_manifest_csv, config.dataset_name)
    print(f"转换完成：labels={len(converted)}, boxes={sum(item.box_count for item in converted)}")
    print(f"YOLO 标签目录：{output_root / 'labels'}")
    print(f"EC2 图片清单：{ec2_manifest_json}")
    print(f"YOLO YAML：{data_yaml}")
    print(f"转换报告：{report_path}")
    if warnings:
        print(f"警告：{len(warnings)} 条，详情见转换报告。")


if __name__ == "__main__":
    main()
