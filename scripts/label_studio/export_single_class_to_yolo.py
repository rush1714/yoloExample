"""将单类别 Label Studio 导出转换为 YOLO 数据集。"""

from __future__ import annotations

import argparse
import csv
import json
import shutil
from dataclasses import dataclass
from pathlib import Path
from urllib.parse import parse_qs, unquote, urlsplit

PROJECT_ROOT = Path(__file__).resolve().parents[2]
DEFAULT_INPUT = PROJECT_ROOT / "datasets" / "diaper_category" / "default" / "v1" / "label_studio" / "exports" / "label_studio_export.json"
DEFAULT_OUTPUT_ROOT = PROJECT_ROOT / "datasets" / "diaper_category" / "default" / "v1"
SPLIT_RATIOS = (0.7, 0.2, 0.1)
IMAGE_SUFFIXES = {".bmp", ".jpeg", ".jpg", ".png", ".tif", ".tiff", ".webp"}


@dataclass(frozen=True)
class ConvertedTask:
    """单个 Label Studio 任务转换结果。"""

    image_path: Path
    label_path: Path
    split: str
    box_count: int
    source_task_id: str


def load_export_tasks(export_path: Path) -> list[dict[str, object]]:
    """读取 Label Studio JSON 导出。"""
    payload = json.loads(export_path.read_text(encoding="utf-8"))
    if isinstance(payload, list):
        return payload
    if isinstance(payload, dict) and isinstance(payload.get("tasks"), list):
        return payload["tasks"]
    raise ValueError("Label Studio 导出 JSON 必须是任务列表，或包含 tasks 列表的对象。")


def parse_local_file_url(value: str) -> Path | None:
    """解析 /data/local-files/?d=<path> 形式的本地图片路径。"""
    parsed = urlsplit(value)
    if parsed.path != "/data/local-files/":
        return None
    values = parse_qs(parsed.query).get("d")
    return Path(unquote(values[0])).resolve() if values else None


def task_image_path(task: dict[str, object]) -> Path | None:
    """从任务 data 中获取本地图片路径。"""
    data = task.get("data")
    if not isinstance(data, dict):
        return None
    local_path = data.get("local_path")
    if isinstance(local_path, str) and local_path:
        return Path(local_path).resolve()
    image_value = data.get("image")
    if isinstance(image_value, str) and image_value:
        return parse_local_file_url(image_value)
    return None


def select_annotation(task: dict[str, object], annotation_index: str) -> dict[str, object] | None:
    """选择有效 annotation。"""
    annotations = task.get("annotations")
    if not isinstance(annotations, list):
        return None
    valid = [item for item in annotations if isinstance(item, dict) and not item.get("was_cancelled")]
    if not valid:
        return None
    return valid[0] if annotation_index == "first" else valid[-1]


def result_to_yolo_line(result: dict[str, object], label_name: str) -> str | None:
    """将单个 rectanglelabels 结果转换为 class_id=0 的 YOLO 标签行。"""
    if result.get("type") != "rectanglelabels":
        return None
    value = result.get("value")
    if not isinstance(value, dict):
        return None
    labels = value.get("rectanglelabels")
    if not isinstance(labels, list) or label_name not in [str(item) for item in labels]:
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
    if yolo_width <= 0 or yolo_height <= 0:
        return None
    if not all(0.0 <= item <= 1.0 for item in values):
        return None
    return "0 " + " ".join(f"{item:.6f}" for item in values)


def annotation_to_yolo_lines(annotation: dict[str, object], label_name: str) -> list[str]:
    """转换一个 annotation 中全部纸尿裤框。"""
    results = annotation.get("result")
    if not isinstance(results, list):
        return []
    lines: list[str] = []
    for result in results:
        if not isinstance(result, dict):
            continue
        line = result_to_yolo_line(result, label_name)
        if line is not None:
            lines.append(line)
    return lines


def split_by_index(index: int, total: int) -> str:
    """按稳定顺序 70/20/10 划分。"""
    if total <= 1:
        return "train"
    train_cutoff = int(total * SPLIT_RATIOS[0])
    val_cutoff = int(total * (SPLIT_RATIOS[0] + SPLIT_RATIOS[1]))
    if index < train_cutoff:
        return "train"
    return "val" if index < val_cutoff else "test"


def prepare_output_dirs(output_root: Path, clear_output: bool) -> None:
    """准备 images/labels 目录，可选清空旧输出。"""
    for kind in ("images", "labels"):
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


def convert_tasks(
    tasks: list[dict[str, object]],
    output_root: Path,
    label_name: str,
    annotation_index: str,
    include_empty_annotations: bool,
) -> tuple[list[ConvertedTask], list[str]]:
    """执行单类别 Label Studio 导出到 YOLO 的转换。"""
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
        lines = annotation_to_yolo_lines(annotation, label_name)
        if not lines and not include_empty_annotations:
            warnings.append(f"图片 {image_path.name} annotation 中没有 {label_name} 框，已跳过。")
            continue
        split = split_by_index(index, len(annotated_items))
        target_image = output_root / "images" / split / image_path.name
        target_label = output_root / "labels" / split / image_path.with_suffix(".txt").name
        shutil.copy2(image_path, target_image)
        target_label.write_text("\n".join(lines) + ("\n" if lines else ""), encoding="utf-8")
        converted.append(
            ConvertedTask(
                image_path=target_image,
                label_path=target_label,
                split=split,
                box_count=len(lines),
                source_task_id=str(task.get("id", "")),
            )
        )
    return converted, warnings


def write_report(converted: list[ConvertedTask], warnings: list[str], report_path: Path) -> None:
    """写 JSON/CSV 转换报告。"""
    report_path.parent.mkdir(parents=True, exist_ok=True)
    payload = {
        "converted_count": len(converted),
        "box_count": sum(item.box_count for item in converted),
        "class_counts": {"0": sum(item.box_count for item in converted)},
        "warnings": warnings,
        "items": [item.__dict__ | {"image_path": str(item.image_path), "label_path": str(item.label_path)} for item in converted],
    }
    report_path.write_text(json.dumps(payload, ensure_ascii=False, indent=2, default=str), encoding="utf-8")
    with report_path.with_suffix(".csv").open("w", encoding="utf-8", newline="") as file:
        writer = csv.DictWriter(file, fieldnames=["image", "label", "split", "box_count", "source_task_id"])
        writer.writeheader()
        for item in converted:
            writer.writerow(
                {
                    "image": item.image_path,
                    "label": item.label_path,
                    "split": item.split,
                    "box_count": item.box_count,
                    "source_task_id": item.source_task_id,
                }
            )


def main() -> None:
    """命令行入口。"""
    parser = argparse.ArgumentParser(description="将纸尿裤大类 Label Studio JSON 导出转换为 YOLO 数据集。")
    parser.add_argument("--input", type=Path, default=DEFAULT_INPUT, help="Label Studio JSON 导出文件")
    parser.add_argument("--output-root", type=Path, default=DEFAULT_OUTPUT_ROOT, help="YOLO 数据集根目录")
    parser.add_argument("--label-name", default="纸尿裤", help="Label Studio 标签名")
    parser.add_argument("--annotation-index", choices=["first", "latest"], default="latest", help="选择 first/latest annotation")
    parser.add_argument("--skip-empty-annotations", action="store_true", help="跳过无框 annotation；默认保留为空标签负样本")
    parser.add_argument("--clear-output", action="store_true", help="转换前清空 images/labels 旧文件")
    parser.add_argument("--report", type=Path, default=None, help="转换报告 JSON 输出路径")
    args = parser.parse_args()

    if not args.input.is_file():
        raise SystemExit(f"Label Studio 导出文件不存在：{args.input}")
    output_root = args.output_root.resolve()
    report_path = args.report or (args.input.parent / f"{args.input.stem}_to_yolo_report.json")
    prepare_output_dirs(output_root, args.clear_output)
    converted, warnings = convert_tasks(
        tasks=load_export_tasks(args.input),
        output_root=output_root,
        label_name=args.label_name,
        annotation_index=args.annotation_index,
        include_empty_annotations=not args.skip_empty_annotations,
    )
    write_report(converted, warnings, report_path)
    print(f"转换完成：images={len(converted)}, boxes={sum(item.box_count for item in converted)}")
    print(f"正式图片目录：{output_root / 'images'}")
    print(f"正式标签目录：{output_root / 'labels'}")
    print(f"转换报告：{report_path}")
    if warnings:
        print(f"警告：{len(warnings)} 条，详情见转换报告。")


if __name__ == "__main__":
    main()
