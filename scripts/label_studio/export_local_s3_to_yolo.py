"""将本地地址 Label Studio 导出结合 S3 上传清单转换为 EC2 训练输入。

该脚本服务于一种补充流程：图片最初以本地文件地址导入 Label Studio，
人工标注并导出 JSON 后，用户又把同一批图片上传到了 S3。此时 Label
Studio 导出里没有 s3_bucket/s3_key，但 S3 上传清单 `s3_images.json`
里有本地图片路径与 S3 key 的对应关系。本脚本负责把两者匹配起来，
生成 EC2 从 S3 下载训练图片所需的 manifest，同时只在本地写 YOLO labels，
不复制 images 大文件。
"""

# pylint: disable=line-too-long,import-error,too-many-locals,too-many-arguments,too-many-positional-arguments

from __future__ import annotations

import argparse
import sys
from pathlib import Path
from typing import Any

PROJECT_ROOT = Path(__file__).resolve().parents[2]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from scripts.label_studio.export_s3_single_class_to_yolo import (  # pylint: disable=wrong-import-position
    S3ConvertedTask,
    prepare_output_dirs,
    safe_label_stem,
    write_reports,
    write_single_class_yaml,
)
from scripts.label_studio.export_single_class_to_yolo import (  # pylint: disable=wrong-import-position
    annotation_to_yolo_lines,
    load_export_tasks,
    select_annotation,
    split_by_index,
    task_image_path,
)
from scripts.s3.brand_s3_config import (  # pylint: disable=wrong-import-position
    DEFAULT_CONFIG_PATH,
    load_config,
    load_manifest_records,
)


def normalized_path_key(path: Path | str | None) -> str:
    """把本地路径归一化为可比较的 key；空路径返回空字符串。"""
    if path is None:
        return ""
    text = str(path).strip()
    if not text:
        return ""
    return str(Path(text).expanduser().resolve())


def task_relative_path(task: dict[str, Any], local_images_dir: Path | None) -> str:
    """从本地 LS 任务里推导相对路径，用于匹配 S3 上传清单。"""
    data = task.get("data")
    if not isinstance(data, dict):
        return ""
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


def task_image_name(task: dict[str, Any]) -> str:
    """从本地 LS 任务获取图片文件名，作为最后兜底匹配条件。"""
    data = task.get("data")
    if isinstance(data, dict):
        image_name = str(data.get("image_name") or "").strip()
        if image_name:
            return image_name
    image_path = task_image_path(task)
    return image_path.name if image_path is not None else str(task.get("id", "image"))


def task_image_value(task: dict[str, Any]) -> str:
    """返回 Label Studio 任务里的原始 image 字段，用于转换报告追溯。"""
    data = task.get("data")
    if not isinstance(data, dict):
        return ""
    return str(data.get("image") or "")


def manifest_identity(record: dict[str, Any]) -> tuple[str, str, str]:
    """从 S3 上传清单记录提取 bucket/key/uri。"""
    bucket = str(record.get("s3_bucket") or "")
    key = str(record.get("s3_key") or "")
    uri = str(record.get("s3_uri") or "")
    if bucket and key and not uri:
        uri = f"s3://{bucket}/{key}"
    return bucket, key, uri


def usable_manifest_records(records: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """过滤出已上传且包含 S3 bucket/key 的清单记录。"""
    usable: list[dict[str, Any]] = []
    for record in records:
        bucket, key, _uri = manifest_identity(record)
        status = str(record.get("status") or "")
        uploaded = record.get("uploaded") is True or status in {"uploaded", "skipped_existing", "s3_existing"}
        if bucket and key and uploaded:
            usable.append(record)
    return usable


def add_unique(index: dict[str, dict[str, Any] | None], key: str, record: dict[str, Any]) -> None:
    """构建唯一索引；重复 key 置为 None，避免按文件名误匹配。"""
    if not key:
        return
    if key in index:
        index[key] = None
    else:
        index[key] = record


def build_manifest_indexes(records: list[dict[str, Any]]) -> tuple[dict[str, dict[str, Any] | None], dict[str, dict[str, Any] | None], dict[str, dict[str, Any] | None]]:
    """按 local_path、relative_path、image_name 建立三层 S3 清单匹配索引。"""
    by_local_path: dict[str, dict[str, Any] | None] = {}
    by_relative_path: dict[str, dict[str, Any] | None] = {}
    by_image_name: dict[str, dict[str, Any] | None] = {}
    for record in records:
        add_unique(by_local_path, normalized_path_key(str(record.get("local_path") or "")), record)
        add_unique(by_relative_path, str(record.get("relative_path") or "").strip().strip("/"), record)
        image_name = str(record.get("image_name") or Path(str(record.get("relative_path") or "")).name).strip()
        add_unique(by_image_name, image_name, record)
    return by_local_path, by_relative_path, by_image_name


def match_manifest_record(
    task: dict[str, Any],
    indexes: tuple[dict[str, dict[str, Any] | None], dict[str, dict[str, Any] | None], dict[str, dict[str, Any] | None]],
    local_images_dir: Path | None,
) -> tuple[dict[str, Any] | None, str]:
    """按本地路径、相对路径、文件名顺序匹配 S3 上传清单记录。"""
    by_local_path, by_relative_path, by_image_name = indexes
    image_path = task_image_path(task)
    path_key = normalized_path_key(image_path)
    if path_key and path_key in by_local_path:
        return by_local_path[path_key], "local_path"
    relative_path = task_relative_path(task, local_images_dir)
    if relative_path and relative_path in by_relative_path:
        return by_relative_path[relative_path], "relative_path"
    image_name = task_image_name(task)
    if image_name and image_name in by_image_name:
        return by_image_name[image_name], "image_name"
    return None, "not_found"


def convert_local_tasks_with_s3_manifest(
    tasks: list[dict[str, Any]],
    manifest_records: list[dict[str, Any]],
    output_root: Path,
    label_name: str,
    annotation_index: str,
    include_empty_annotations: bool,
    local_images_dir: Path | None = None,
) -> tuple[list[S3ConvertedTask], list[str]]:
    """将本地 LS 导出任务和 S3 上传清单合并为 YOLO labels 与 EC2 manifest 记录。"""
    warnings: list[str] = []
    usable_records = usable_manifest_records(manifest_records)
    indexes = build_manifest_indexes(usable_records)
    annotated_items: list[tuple[dict[str, Any], dict[str, Any], dict[str, Any], str]] = []
    for task in tasks:
        image_name = task_image_name(task)
        record, match_mode = match_manifest_record(task, indexes, local_images_dir)
        if record is None:
            warnings.append(f"任务 {task.get('id', '-')} / {image_name} 无法唯一匹配 S3 上传清单，匹配方式={match_mode}，已跳过。")
            continue
        annotation = select_annotation(task, annotation_index)
        if annotation is None:
            warnings.append(f"图片 {image_name} 没有有效 annotation，已跳过。")
            continue
        annotated_items.append((task, annotation, record, match_mode))

    converted: list[S3ConvertedTask] = []
    for index, (task, annotation, record, _match_mode) in enumerate(annotated_items):
        bucket, key, uri = manifest_identity(record)
        image_name = task_image_name(task)
        relative_path = str(record.get("relative_path") or task_relative_path(task, local_images_dir) or image_name)
        lines = annotation_to_yolo_lines(annotation, label_name)
        if not lines and not include_empty_annotations:
            warnings.append(f"图片 {image_name} annotation 中没有 {label_name} 框，已跳过。")
            continue
        split = split_by_index(index, len(annotated_items))
        label_name_stem = safe_label_stem(relative_path, image_name)
        image_suffix = Path(image_name).suffix or Path(str(record.get("image_name") or "")).suffix or Path(key).suffix
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
                source_url=str(record.get("https_url") or task_image_value(task) or uri),
                training_image_name=f"{label_name_stem}{image_suffix}",
            )
        )
    return converted, warnings


def parse_args() -> argparse.Namespace:
    """解析命令行参数。"""
    parser = argparse.ArgumentParser(description="将本地地址 LS 导出结合 S3 上传清单转换为 EC2 下载训练清单。")
    parser.add_argument("--config", type=Path, default=DEFAULT_CONFIG_PATH, help="S3 工作流 YAML 配置路径")
    parser.add_argument("--input", type=Path, required=True, help="本地地址 Label Studio JSON 导出文件")
    parser.add_argument("--s3-manifest", type=Path, default=None, help="S3 上传清单 JSON，默认 metadata/s3_images.json")
    parser.add_argument("--output-root", type=Path, default=None, help="S3 YOLO 数据集根目录")
    parser.add_argument("--dataset-name", default="", help="S3 数据集短名称")
    parser.add_argument("--label-name", default="", help="单类别标签名")
    parser.add_argument("--local-images-dir", type=Path, default=None, help="原始本地图片目录，用于从绝对路径推导 relative_path")
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
    config = load_config(
        args.config,
        dataset_name=args.dataset_name,
        label_name=args.label_name,
        local_images_dir=args.local_images_dir or "",
        dataset_root=args.output_root or "",
        data_yaml=args.data_yaml or "",
        ec2_manifest_json=args.ec2_manifest_json or "",
        ec2_manifest_csv=args.ec2_manifest_csv or "",
    )
    input_path = args.input.resolve()
    manifest_path = args.s3_manifest or config.manifest_json
    output_root = (args.output_root or config.dataset_root).resolve()
    report_path = args.report or config.yolo_report_json
    data_yaml = args.data_yaml or config.data_yaml
    ec2_manifest_json = args.ec2_manifest_json or config.ec2_manifest_json
    ec2_manifest_csv = args.ec2_manifest_csv or config.ec2_manifest_csv
    if not input_path.is_file():
        raise SystemExit(f"Label Studio 导出文件不存在：{input_path}")
    if not manifest_path.is_file():
        raise SystemExit(f"S3 上传清单不存在：{manifest_path}；请先执行 brand-s3-upload-images 或 brand-s3-sync-manifest-from-s3。")
    prepare_output_dirs(output_root, args.clear_output)
    converted, warnings = convert_local_tasks_with_s3_manifest(
        tasks=load_export_tasks(input_path),
        manifest_records=load_manifest_records(manifest_path),
        output_root=output_root,
        label_name=config.label_name,
        annotation_index=args.annotation_index,
        include_empty_annotations=not args.skip_empty_annotations,
        local_images_dir=config.local_images_dir,
    )
    write_single_class_yaml(data_yaml, output_root, config.label_name)
    write_reports(converted, warnings, report_path, ec2_manifest_json, ec2_manifest_csv, config.dataset_name)
    print(f"转换完成：labels={len(converted)}, boxes={sum(item.box_count for item in converted)}")
    print(f"S3 上传清单：{manifest_path}")
    print(f"YOLO 标签目录：{output_root / 'labels'}")
    print(f"EC2 图片清单：{ec2_manifest_json}")
    print(f"EC2 图片 CSV：{ec2_manifest_csv}")
    print(f"YOLO YAML：{data_yaml}")
    print(f"转换报告：{report_path}")
    if warnings:
        print(f"警告：{len(warnings)} 条，详情见转换报告。")


if __name__ == "__main__":
    main()
