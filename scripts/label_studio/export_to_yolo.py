"""
将 Label Studio 多品牌 JSON 导出结果转换为正式 YOLO 训练数据集。

该脚本用于人工复核闭环的第 5 步：
- 从 Label Studio JSON 导出读取已完成人工复核的 annotations。
- 根据品牌库把 Label Studio 多标签显示名映射到 YOLO class_id。
- 将 Label Studio 百分比矩形框转换为 YOLO 归一化 xywh 标签。
- 将图片复制到 datasets/multibrand/images/{train,val,test}/。
- 将标签写入 datasets/multibrand/labels/{train,val,test}/。
"""

from __future__ import annotations

import argparse
import sys
import csv
import json
import shutil
from dataclasses import dataclass
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[2]
SCRIPTS_ROOT = PROJECT_ROOT / "scripts"
if str(SCRIPTS_ROOT) not in sys.path:
    sys.path.insert(0, str(SCRIPTS_ROOT))
from urllib.parse import parse_qs, unquote, urlsplit

from common.brand_library import DEFAULT_BRAND_LIBRARY, BrandClass, display_name_map, load_brand_classes

DEFAULT_INPUT = PROJECT_ROOT / "datasets" / "multibrand" / "label_studio" / "exports" / "label_studio_export.json"
DEFAULT_OUTPUT_ROOT = PROJECT_ROOT / "datasets" / "multibrand"
DEFAULT_PSEUDO_ROOT = PROJECT_ROOT / "datasets" / "multibrand" / "pseudo"
SPLIT_RATIOS = (0.7, 0.2, 0.1)
IMAGE_SUFFIXES = {".bmp", ".jpeg", ".jpg", ".png", ".tif", ".tiff", ".webp"}


@dataclass(frozen=True)
class ConvertedTask:
    """单个 Label Studio 任务转换后的结果。"""

    image_path: Path
    label_path: Path
    split: str
    box_count: int
    source_task_id: str
    class_counts: dict[str, int]


def load_export_tasks(export_path: Path) -> list[dict[str, object]]:
    """读取 Label Studio JSON 导出文件，并兼容常见导出结构。"""
    payload = json.loads(export_path.read_text(encoding="utf-8"))
    if isinstance(payload, list):
        return payload
    if isinstance(payload, dict) and isinstance(payload.get("tasks"), list):
        return payload["tasks"]
    raise ValueError("Label Studio 导出 JSON 必须是任务列表，或包含 tasks 列表的对象。")


def parse_local_file_url(value: str) -> Path | None:
    """从 /data/local-files/?d=<path> 形式的字段中解析本地文件路径。"""
    parsed = urlsplit(value)
    if parsed.path != "/data/local-files/":
        return None
    values = parse_qs(parsed.query).get("d")
    if not values:
        return None
    return Path(unquote(values[0])).resolve()


def task_image_path(task: dict[str, object]) -> Path | None:
    """从 Label Studio task.data 中获取本地图片路径。"""
    data = task.get("data")
    if not isinstance(data, dict):
        return None
    local_path = data.get("local_path")
    if isinstance(local_path, str) and local_path:
        return Path(local_path).resolve()
    image_value = data.get("image")
    if isinstance(image_value, str) and image_value:
        parsed_path = parse_local_file_url(image_value)
        if parsed_path is not None:
            return parsed_path
    return None


def select_annotation(task: dict[str, object], annotation_index: str) -> dict[str, object] | None:
    """选择一个有效 annotation；默认使用最后一个未取消的 annotation。"""
    annotations = task.get("annotations")
    if not isinstance(annotations, list):
        return None
    valid_annotations = [item for item in annotations if isinstance(item, dict) and not item.get("was_cancelled")]
    if not valid_annotations:
        return None
    if annotation_index == "first":
        return valid_annotations[0]
    return valid_annotations[-1]


def result_to_yolo_line(result: dict[str, object], label_to_brand: dict[str, BrandClass]) -> tuple[str, BrandClass] | None:
    """将 Label Studio rectanglelabels 结果转换为一行 YOLO 标签。"""
    if result.get("type") != "rectanglelabels":
        return None
    value = result.get("value")
    if not isinstance(value, dict):
        return None

    rectangle_labels = value.get("rectanglelabels")
    if not isinstance(rectangle_labels, list) or not rectangle_labels:
        return None
    brand = label_to_brand.get(str(rectangle_labels[0]).lower().replace(" ", ""))
    if brand is None:
        # display_name_map 的 key 是 normalize_key，延迟导入避免重复实现。
        from common.brand_library import normalize_key

        brand = label_to_brand.get(normalize_key(str(rectangle_labels[0])))
    if brand is None:
        return None

    try:
        x = float(value["x"])
        y = float(value["y"])
        width = float(value["width"])
        height = float(value["height"])
    except (KeyError, TypeError, ValueError):
        return None

    center_x = (x + width / 2.0) / 100.0
    center_y = (y + height / 2.0) / 100.0
    yolo_width = width / 100.0
    yolo_height = height / 100.0
    values = [center_x, center_y, yolo_width, yolo_height]
    if yolo_width <= 0 or yolo_height <= 0:
        return None
    if not all(0.0 <= item <= 1.0 for item in values):
        return None
    return f"{brand.class_id} " + " ".join(f"{item:.6f}" for item in values), brand


def annotation_to_yolo_lines(annotation: dict[str, object], label_to_brand: dict[str, BrandClass]) -> tuple[list[str], dict[str, int]]:
    """转换单个 annotation 中的全部矩形框。"""
    results = annotation.get("result")
    if not isinstance(results, list):
        return [], {}
    lines: list[str] = []
    class_counts: dict[str, int] = {}
    for result in results:
        if not isinstance(result, dict):
            continue
        converted = result_to_yolo_line(result, label_to_brand)
        if converted is None:
            continue
        line, brand = converted
        lines.append(line)
        class_counts[brand.class_name] = class_counts.get(brand.class_name, 0) + 1
    return lines, class_counts


def split_from_pseudo(image_path: Path, pseudo_root: Path) -> str | None:
    """根据伪标注标签所在目录推断 train/val/test 分割。"""
    stem = image_path.stem
    for split in ("train", "val", "test"):
        if (pseudo_root / "labels" / split / f"{stem}.txt").is_file():
            return split
    return None


def split_by_index(index: int, total: int) -> str:
    """当无法复用伪标注分割时，按稳定顺序做 70/20/10 划分。"""
    if total <= 1:
        return "train"
    train_cutoff = int(total * SPLIT_RATIOS[0])
    val_cutoff = int(total * (SPLIT_RATIOS[0] + SPLIT_RATIOS[1]))
    if index < train_cutoff:
        return "train"
    if index < val_cutoff:
        return "val"
    return "test"


def prepare_output_dirs(output_root: Path, clear_output: bool) -> None:
    """准备正式训练数据目录；可选清空旧图片和旧标签。"""
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
    pseudo_root: Path,
    label_to_brand: dict[str, BrandClass],
    annotation_index: str,
    include_empty_annotations: bool,
) -> tuple[list[ConvertedTask], list[str]]:
    """执行 Label Studio tasks 到 YOLO 数据集的转换。"""
    converted: list[ConvertedTask] = []
    warnings: list[str] = []
    annotated_items: list[tuple[dict[str, object], Path, dict[str, object]]] = []
    for task in tasks:
        image_path = task_image_path(task)
        if image_path is None:
            warnings.append(f"任务 {task.get('id', '-')} 缺少本地图片路径，已跳过。")
            continue
        if not image_path.is_file() or image_path.suffix.lower() not in IMAGE_SUFFIXES:
            warnings.append(f"图片不存在或格式不支持：{image_path}，已跳过。")
            continue
        annotation = select_annotation(task, annotation_index)
        if annotation is None:
            warnings.append(f"图片 {image_path.name} 没有有效 annotation，已跳过。")
            continue
        annotated_items.append((task, image_path, annotation))

    for index, (task, image_path, annotation) in enumerate(annotated_items):
        lines, class_counts = annotation_to_yolo_lines(annotation, label_to_brand)
        if not lines and not include_empty_annotations:
            warnings.append(f"图片 {image_path.name} annotation 中没有可导出的品牌框，已跳过。")
            continue
        split = split_from_pseudo(image_path, pseudo_root) or split_by_index(index, len(annotated_items))
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
                class_counts=class_counts,
            )
        )
    return converted, warnings


def write_report(converted: list[ConvertedTask], warnings: list[str], report_path: Path) -> None:
    """写入 JSON 与 CSV 转换报告。"""
    report_path.parent.mkdir(parents=True, exist_ok=True)
    total_class_counts: dict[str, int] = {}
    for item in converted:
        for class_name, count in item.class_counts.items():
            total_class_counts[class_name] = total_class_counts.get(class_name, 0) + count
    json_payload = {
        "converted_count": len(converted),
        "box_count": sum(item.box_count for item in converted),
        "class_counts": total_class_counts,
        "warnings": warnings,
        "items": [
            {
                "image": str(item.image_path),
                "label": str(item.label_path),
                "split": item.split,
                "box_count": item.box_count,
                "class_counts": item.class_counts,
                "source_task_id": item.source_task_id,
            }
            for item in converted
        ],
    }
    report_path.write_text(json.dumps(json_payload, ensure_ascii=False, indent=2), encoding="utf-8")

    csv_path = report_path.with_suffix(".csv")
    with csv_path.open("w", encoding="utf-8", newline="") as file:
        writer = csv.DictWriter(file, fieldnames=["image", "label", "split", "box_count", "source_task_id", "class_counts"])
        writer.writeheader()
        for item in converted:
            writer.writerow(
                {
                    "image": item.image_path,
                    "label": item.label_path,
                    "split": item.split,
                    "box_count": item.box_count,
                    "source_task_id": item.source_task_id,
                    "class_counts": json.dumps(item.class_counts, ensure_ascii=False),
                }
            )


def main() -> None:
    """命令行入口：解析参数并执行转换。"""
    parser = argparse.ArgumentParser(description="将 Label Studio JSON 导出转换为多品牌 YOLO 训练数据集。")
    parser.add_argument("--input", type=Path, default=DEFAULT_INPUT, help="Label Studio JSON 导出文件")
    parser.add_argument("--output-root", type=Path, default=DEFAULT_OUTPUT_ROOT, help="正式 YOLO 数据集根目录")
    parser.add_argument("--pseudo-root", type=Path, default=DEFAULT_PSEUDO_ROOT, help="伪标注目录，用于复用 train/val/test 分割")
    parser.add_argument("--brand-library", type=Path, default=DEFAULT_BRAND_LIBRARY, help="品牌标识库 JSON/TXT")
    parser.add_argument("--annotation-index", choices=["first", "latest"], default="latest", help="同一任务存在多个 annotation 时选择哪个")
    parser.add_argument("--skip-empty-annotations", action="store_true", help="跳过已完成但没有目标框的 annotation；默认保留为空标签负样本")
    parser.add_argument("--clear-output", action="store_true", help="转换前清空 images/labels 下旧文件；会保留 .gitkeep")
    parser.add_argument("--report", type=Path, default=None, help="转换报告 JSON 输出路径")
    args = parser.parse_args()

    if not args.input.is_file():
        raise SystemExit(f"Label Studio 导出文件不存在：{args.input}")
    output_root = args.output_root.resolve()
    pseudo_root = args.pseudo_root.resolve()
    report_path = args.report or (args.input.parent / f"{args.input.stem}_to_yolo_report.json")

    brand_classes = load_brand_classes(args.brand_library)
    label_to_brand = display_name_map(brand_classes)
    prepare_output_dirs(output_root, args.clear_output)
    tasks = load_export_tasks(args.input)
    converted, warnings = convert_tasks(
        tasks=tasks,
        output_root=output_root,
        pseudo_root=pseudo_root,
        label_to_brand=label_to_brand,
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
