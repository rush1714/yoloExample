"""
YOLO-World 多模型 A/B 预标注对比脚本。

该脚本用于在同一批图片、同一组品牌提示词、同一组过滤参数下，依次运行多个
YOLO-World 权重，并生成可人工复核的对比报告。它不替代正式预标注流程，而是帮助
判断当前项目应该继续使用哪个开放词汇模型作为候选框生成器。
"""

from __future__ import annotations

import argparse
import csv
import json
import os
import re
import sys
import time
from dataclasses import asdict, dataclass
from datetime import datetime
from pathlib import Path
from typing import Any

# pylint: disable=wrong-import-position

PROJECT_ROOT = Path(__file__).resolve().parents[2]
# Matplotlib 和 Ultralytics 会在导入时写配置/缓存；统一放到项目内可写目录，避免污染用户目录。
MPLCONFIG_DIR = PROJECT_ROOT / ".tmp" / "matplotlib"
YOLO_CONFIG_DIR = PROJECT_ROOT / ".tmp" / "ultralytics"
for runtime_dir in (MPLCONFIG_DIR, YOLO_CONFIG_DIR, YOLO_CONFIG_DIR / "Ultralytics"):
    runtime_dir.mkdir(parents=True, exist_ok=True)
os.environ.setdefault("MPLCONFIGDIR", str(MPLCONFIG_DIR))
os.environ.setdefault("YOLO_CONFIG_DIR", str(YOLO_CONFIG_DIR))
SCRIPTS_ROOT = PROJECT_ROOT / "scripts"
if str(SCRIPTS_ROOT) not in sys.path:
    sys.path.insert(0, str(SCRIPTS_ROOT))

from common.brand_library import (  # type: ignore[import-not-found]
    DEFAULT_BRAND_LIBRARY,
    load_brand_classes,
    normalize_key,
    prompt_to_brand_map,
    select_brand_classes,
)
from common.ultralytics_config import (  # type: ignore[import-not-found]
    configure_ultralytics_weights_dir,
)
from PIL import Image, ImageDraw, ImageFont
from pseudo_label.generate_yolo_world import (  # type: ignore[import-not-found]
    DEFAULT_RAW_DIR,
    MODELS_DIR,
    PseudoBox,
    build_prompt_specs,
    list_images,
    predict_image,
    split_name,
)
from ultralytics import YOLO

# 默认对比模型：当前 s-world baseline + 两个 v2 候选模型。
DEFAULT_MODELS = [
    "models/yolov8s-world.pt",
    "yolov8m-worldv2.pt",
    "yolov8x-worldv2.pt",
]
# A/B 输出根目录；实际每次运行会再创建一个带时间戳的 run 目录。
DEFAULT_OUTPUT_ROOT = PROJECT_ROOT / "datasets" / "multibrand" / "ab_tests" / "yolo_world"
# 预览图最大边长，避免报告目录里保存过大的可视化图片。
PREVIEW_MAX_SIDE = 1600
# 绘制预览框时循环使用的颜色。
PREVIEW_COLORS = ["#00A5FF", "#FF4D4D", "#33CC66", "#CC66FF", "#FFB000", "#00CCB8"]


@dataclass(frozen=True)
class ModelSummary:  # pylint: disable=too-many-instance-attributes
    """单个模型的 A/B 汇总结果。"""

    model_name: str
    model_path: str
    image_count: int
    images_with_boxes: int
    total_boxes: int
    average_boxes_per_image: float
    confidence: dict[str, float]
    class_counts: dict[str, int]
    prompt_counts: dict[str, int]
    elapsed_seconds: float


@dataclass(frozen=True)
class RunContext:
    """一次 A/B 测试运行所需的共享上下文。"""

    image_paths: list[Path]
    prompts: list[str]
    prompt_map: dict[str, Any]
    output_dir: Path
    parameters: dict[str, object]


@dataclass(frozen=True)
class PredictConfig:  # pylint: disable=too-many-instance-attributes
    """YOLO-World 推理和候选框过滤参数。"""

    conf: float
    imgsz: int
    nms_iou: float
    containment_threshold: float
    max_area_ratio: float
    cross_brand_dedup: bool
    cross_brand_iou: float
    cross_brand_containment: float
    preview_limit: int


def sanitize_model_name(model_path: Path) -> str:
    """把模型路径转换为稳定、可读、可作为目录名的模型短名称。"""
    # Path.stem 能去掉 .pt 后缀；正则再把空格和特殊符号统一成短横线。
    slug = re.sub(r"[^A-Za-z0-9_.-]+", "-", model_path.stem).strip("-._")
    return slug or "model"


def confidence_quantiles(values: list[float]) -> dict[str, float]:
    """计算候选框置信度分位数，用于快速比较不同模型输出质量。"""
    if not values:
        return {"p50": 0.0, "p75": 0.0, "p90": 0.0, "max": 0.0}

    sorted_values = sorted(values)

    def percentile(percent: float) -> float:
        """用线性插值计算百分位，样本少时也能得到稳定数值。"""
        if len(sorted_values) == 1:
            return sorted_values[0]
        position = (len(sorted_values) - 1) * percent
        lower_index = int(position)
        upper_index = min(lower_index + 1, len(sorted_values) - 1)
        weight = position - lower_index
        return sorted_values[lower_index] * (1 - weight) + sorted_values[upper_index] * weight

    return {
        "p50": round(percentile(0.50), 4),
        "p75": round(percentile(0.75), 4),
        "p90": round(percentile(0.90), 4),
        "max": round(max(sorted_values), 4),
    }


def increment_counter(counter: dict[str, int], key: str) -> None:
    """累加计数字典；空 key 归入 unknown，避免报告中丢失异常数据。"""
    normalized_key = key or "unknown"
    counter[normalized_key] = counter.get(normalized_key, 0) + 1


def summarize_prediction_rows(
    model_name: str,
    model_path: Path,
    rows: list[dict[str, Any]],
    elapsed_seconds: float,
) -> ModelSummary:
    """把逐图预测明细汇总成报告表格使用的指标。"""
    class_counts: dict[str, int] = {}
    prompt_counts: dict[str, int] = {}
    confidences: list[float] = []
    total_boxes = 0
    images_with_boxes = 0

    for row in rows:
        boxes = row.get("boxes", [])
        if boxes:
            images_with_boxes += 1
        total_boxes += int(row.get("box_count", len(boxes)))
        for box in boxes:
            increment_counter(class_counts, str(box.get("class_name", "unknown")))
            increment_counter(prompt_counts, str(box.get("prompt", "unknown")))
            confidences.append(float(box.get("confidence", 0.0)))

    image_count = len(rows)
    average_boxes = total_boxes / image_count if image_count else 0.0
    return ModelSummary(
        model_name=model_name,
        model_path=str(model_path),
        image_count=image_count,
        images_with_boxes=images_with_boxes,
        total_boxes=total_boxes,
        average_boxes_per_image=round(average_boxes, 4),
        confidence=confidence_quantiles(confidences),
        class_counts=dict(sorted(class_counts.items())),
        prompt_counts=dict(sorted(prompt_counts.items())),
        elapsed_seconds=round(elapsed_seconds, 2),
    )


def top_items(counter: dict[str, int], limit: int = 10) -> str:
    """把计数字典转换成 Markdown 中紧凑的 Top-N 文本。"""
    if not counter:
        return "无"
    items = sorted(counter.items(), key=lambda item: (-item[1], item[0]))[:limit]
    return ", ".join(f"{key}: {value}" for key, value in items)


def write_json_atomic(path: Path, payload: object) -> None:
    """原子写 JSON，避免脚本中断时留下半截报告。"""
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary_path = path.with_suffix(path.suffix + ".tmp")
    temporary_path.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
    os.replace(temporary_path, path)


def write_csv_report(path: Path, rows: list[dict[str, object]]) -> None:
    """写入单模型逐图 CSV，方便后续用表格筛选异常图片。"""
    path.parent.mkdir(parents=True, exist_ok=True)
    fieldnames = ["image", "label", "preview", "split", "box_count"]
    with path.open("w", encoding="utf-8", newline="") as file:
        writer = csv.DictWriter(file, fieldnames=fieldnames)
        writer.writeheader()
        for row in rows:
            writer.writerow({key: row.get(key, "") for key in fieldnames})


def write_markdown_report(
    report_path: Path,
    summary_path: Path,
    summaries: list[ModelSummary],
    image_paths: list[Path],
    parameters: dict[str, object],
) -> None:
    """生成 A/B Markdown 对比报告和机器可读 JSON 摘要。"""
    report_path.parent.mkdir(parents=True, exist_ok=True)
    write_json_atomic(summary_path, [asdict(summary) for summary in summaries])

    lines = [
        "# YOLO-World A/B 预标注对比报告",
        "",
        f"生成时间：{datetime.now().strftime('%Y-%m-%d %H:%M:%S')}",
        "",
        "## 1. 测试范围",
        "",
        f"- 图片数量：{len(image_paths)}",
        f"- 图片来源示例：{image_paths[0] if image_paths else '无'}",
        f"- JSON 摘要：`{summary_path}`",
        "",
        "## 2. 关键参数",
        "",
        "| 参数 | 值 |",
        "|---|---|",
    ]
    for key, value in parameters.items():
        lines.append(f"| `{key}` | `{value}` |")

    lines.extend(
        [
            "",
            "## 3. 模型汇总",
            "",
            "| 模型 | 图片数 | 有框图片 | 候选框 | 平均框/图 | conf P50 | conf P75 | conf P90 | conf Max | 耗时秒 |",
            "|---|---:|---:|---:|---:|---:|---:|---:|---:|---:|",
        ]
    )
    for summary in summaries:
        confidence = summary.confidence
        lines.append(
            "| "
            f"{summary.model_name} | {summary.image_count} | {summary.images_with_boxes} | "
            f"{summary.total_boxes} | {summary.average_boxes_per_image:.4f} | "
            f"{confidence['p50']:.4f} | {confidence['p75']:.4f} | "
            f"{confidence['p90']:.4f} | {confidence['max']:.4f} | "
            f"{summary.elapsed_seconds:.2f} |"
        )

    lines.extend(["", "## 4. 类别与提示词分布", ""])
    for summary in summaries:
        lines.extend(
            [
                f"### {summary.model_name}",
                "",
                f"- Top 类别：{top_items(summary.class_counts)}",
                f"- Top 提示词：{top_items(summary.prompt_counts)}",
                "",
            ]
        )

    lines.extend(
        [
            "## 5. 人工复核建议",
            "",
            "请不要只看候选框数量或置信度，建议用同一批图片人工抽检以下指标：",
            "",
            "1. 有效框率：候选框是否真的框住目标品牌包装。",
            "2. 漏检数：真实包装中还有多少没有被任何模型框出。",
            "3. 重复框：同一包装是否被多个提示词或多个品牌重复框选。",
            "4. 修框耗时：哪一个模型导入 Label Studio 后最省人工时间。",
            "5. 品牌混淆：同一位置是否被错误品牌提示词命中。",
            "",
            "建议优先选择“漏检少、明显误框少、人工修正最快”的模型，而不是只选候选框最多的模型。",
            "",
        ]
    )
    report_path.write_text("\n".join(lines), encoding="utf-8")


def resolve_model_for_yolo(model_path: Path) -> str:
    """解析传给 Ultralytics 的模型参数，兼顾本地权重和自动下载。"""
    # 明确存在的路径直接使用，确保当前 baseline 走项目内权重。
    if model_path.exists():
        return str(model_path)
    # 对默认官方权重，传裸文件名可让 Ultralytics 按已配置 weights_dir 下载到 models/。
    if model_path.parent in {Path("."), Path("models"), MODELS_DIR}:
        return model_path.name
    # 用户传了其它不存在路径时保留原路径，让 Ultralytics 报出清晰错误。
    return str(model_path)


def resolve_model_path(raw_model: str) -> Path:
    """把命令行模型参数规范化为报告里使用的路径。"""
    model_path = Path(raw_model)
    if model_path.is_absolute():
        return model_path
    if model_path.parent == Path("."):
        candidate = MODELS_DIR / model_path.name
        return candidate if candidate.exists() else model_path
    if model_path.parts and model_path.parts[0] == "models":
        return PROJECT_ROOT / model_path
    return PROJECT_ROOT / model_path


def parse_model_args(values: list[str] | None) -> list[Path]:
    """解析 --model 参数；支持重复传参，也支持逗号分隔。"""
    raw_values = values or DEFAULT_MODELS
    models: list[Path] = []
    for value in raw_values:
        for item in value.split(","):
            stripped = item.strip()
            if stripped:
                models.append(resolve_model_path(stripped))
    # 保留顺序去重，避免同一权重重复跑浪费时间。
    deduplicated: list[Path] = []
    seen: set[str] = set()
    for model in models:
        key = str(model)
        if key not in seen:
            seen.add(key)
            deduplicated.append(model)
    return deduplicated


def draw_preview(  # pylint: disable=too-many-locals
    image_path: Path,
    boxes: list[PseudoBox],
    output_path: Path,
) -> None:
    """保存带候选框的预览图，方便快速肉眼比较不同模型输出。"""
    output_path.parent.mkdir(parents=True, exist_ok=True)
    with Image.open(image_path) as image:
        preview = image.convert("RGB")
        preview.thumbnail((PREVIEW_MAX_SIDE, PREVIEW_MAX_SIDE))
        scale_x = preview.width / image.width
        scale_y = preview.height / image.height
        draw = ImageDraw.Draw(preview)
        font = ImageFont.load_default()
        for index, box in enumerate(boxes):
            color = PREVIEW_COLORS[index % len(PREVIEW_COLORS)]
            x1, y1, x2, y2 = box.xyxy
            rectangle = [x1 * scale_x, y1 * scale_y, x2 * scale_x, y2 * scale_y]
            label = f"{box.class_name} {box.confidence:.2f}"
            draw.rectangle(rectangle, outline=color, width=3)
            label_position = (rectangle[0], max(0, rectangle[1] - 12))
            draw.text(label_position, label, fill=color, font=font)
        preview.save(output_path, quality=90)


def write_yolo_label(path: Path, boxes: list[PseudoBox]) -> None:
    """把候选框写成 YOLO txt，便于需要时导入现有人工复核工具。"""
    path.parent.mkdir(parents=True, exist_ok=True)
    label_lines = [
        f"{box.class_id} " + " ".join(f"{value:.6f}" for value in box.yolo)
        for box in boxes
    ]
    temporary_path = path.with_suffix(".txt.tmp")
    temporary_path.write_text(
        "\n".join(label_lines) + ("\n" if label_lines else ""),
        encoding="utf-8",
    )
    os.replace(temporary_path, path)


def run_single_model(  # pylint: disable=too-many-locals
    model_path: Path,
    context: RunContext,
    config: PredictConfig,
) -> ModelSummary:
    """运行单个 YOLO-World 模型，并写出逐图明细、标签和预览图。"""
    model_name = sanitize_model_name(model_path)
    model_output_dir = context.output_dir / model_name
    metadata_dir = model_output_dir / "metadata"
    labels_dir = model_output_dir / "labels"
    previews_dir = model_output_dir / "previews"
    metadata_dir.mkdir(parents=True, exist_ok=True)

    print(f"\n开始模型：{model_name} -> {model_path}")
    model = YOLO(resolve_model_for_yolo(model_path))
    model.set_classes(context.prompts)

    start_time = time.perf_counter()
    rows: list[dict[str, object]] = []
    for index, image_path in enumerate(context.image_paths):
        split = split_name(index, len(context.image_paths))
        boxes = predict_image(
            model=model,
            image_path=image_path,
            prompt_map=context.prompt_map,
            confidence=config.conf,
            imgsz=config.imgsz,
            nms_iou=config.nms_iou,
            containment_threshold=config.containment_threshold,
            max_area_ratio=config.max_area_ratio,
            cross_brand_dedup=config.cross_brand_dedup,
            cross_iou_threshold=config.cross_brand_iou,
            cross_containment_threshold=config.cross_brand_containment,
        )
        label_path = labels_dir / split / image_path.with_suffix(".txt").name
        preview_path = previews_dir / f"{image_path.stem}.jpg"
        write_yolo_label(label_path, boxes)
        if index < config.preview_limit:
            draw_preview(image_path, boxes, preview_path)
        row = {
            "image": str(image_path),
            "label": str(label_path),
            "preview": str(preview_path) if index < config.preview_limit else "",
            "split": split,
            "box_count": len(boxes),
            "boxes": [asdict(box) for box in boxes],
        }
        rows.append(row)
        class_summary: dict[str, int] = {}
        for box in boxes:
            increment_counter(class_summary, box.class_name)
        print(
            f"[{index + 1}/{len(context.image_paths)}] {model_name} "
            f"{image_path.name}: {len(boxes)} boxes {class_summary}"
        )

    elapsed_seconds = time.perf_counter() - start_time
    report_json_path = metadata_dir / "prediction_rows.json"
    report_csv_path = metadata_dir / "prediction_rows.csv"
    write_json_atomic(report_json_path, rows)
    write_csv_report(report_csv_path, rows)
    summary = summarize_prediction_rows(model_name, model_path, rows, elapsed_seconds)
    write_json_atomic(metadata_dir / "summary.json", asdict(summary))
    print(f"模型完成：{model_name}，候选框 {summary.total_boxes} 个，耗时 {summary.elapsed_seconds:.2f} 秒。")
    return summary


def validate_ratio(name: str, value: float, allow_zero: bool = True) -> None:
    """校验 0-1 区间参数，尽早给出中文错误。"""
    lower_ok = value >= 0.0 if allow_zero else value > 0.0
    if not lower_ok or value > 1.0:
        operator = "0 到 1" if allow_zero else "0 到 1 且大于 0"
        raise SystemExit(f"--{name} 必须位于 {operator} 之间。")


def build_run_context(args: argparse.Namespace) -> RunContext:
    """准备图片清单、品牌提示词和输出目录，确保所有模型共用同一批输入。"""
    if not args.raw_dir.is_dir():
        raise SystemExit(f"原图目录不存在：{args.raw_dir}")
    images = list_images(args.raw_dir, args.limit, args.candidates_file)
    if not images:
        source = f"候选清单 {args.candidates_file}" if args.candidates_file else f"原图目录 {args.raw_dir}"
        raise SystemExit(f"没有可处理的图片：{source}")

    try:
        all_classes = load_brand_classes(args.brand_library)
    except (FileNotFoundError, ValueError) as exc:
        raise SystemExit(str(exc)) from exc
    selected_classes = select_brand_classes(all_classes, args.brand_filter, args.compact_class_ids)
    if not selected_classes:
        raise SystemExit(f"品牌过滤后没有可用类别：{args.brand_filter}")

    prompt_specs = build_prompt_specs(
        classes=selected_classes,
        include_brand_package_prompts=args.include_brand_package_prompts,
        cli_prompts=args.prompts,
    )
    prompts = [item.prompt for item in prompt_specs]
    prompt_map = prompt_to_brand_map(selected_classes, args.include_brand_package_prompts)
    for item in prompt_specs:
        prompt_map[normalize_key(item.prompt)] = item.brand

    run_name = args.run_name or datetime.now().strftime("%Y%m%d_%H%M%S")
    output_dir = args.output_root / run_name
    output_dir.mkdir(parents=True, exist_ok=True)

    parameters = {
        "raw_dir": str(args.raw_dir),
        "candidates_file": str(args.candidates_file) if args.candidates_file else "",
        "brand_library": str(args.brand_library),
        "brand_filter": ",".join(args.brand_filter or []) or "all",
        "prompt_count": len(prompts),
        "conf": args.conf,
        "imgsz": args.imgsz,
        "nms_iou": args.nms_iou,
        "containment_threshold": args.containment_threshold,
        "max_area_ratio": args.max_area_ratio,
        "cross_brand_dedup": args.cross_brand_dedup,
        "cross_brand_iou": args.cross_brand_iou,
        "cross_brand_containment": args.cross_brand_containment,
        "preview_limit": args.preview_limit,
    }
    write_json_atomic(
        output_dir / "metadata" / "sample_images.json",
        [str(path) for path in images],
    )
    write_json_atomic(output_dir / "metadata" / "parameters.json", parameters)
    print(f"本次 A/B 图片数量：{len(images)}")
    print(f"本次 A/B 品牌：{', '.join(brand.display_name for brand in selected_classes)}")
    print(f"本次 A/B 提示词数量：{len(prompts)}")
    print(f"输出目录：{output_dir}")
    return RunContext(
        image_paths=images,
        prompts=prompts,
        prompt_map=prompt_map,
        output_dir=output_dir,
        parameters=parameters,
    )


def parse_args() -> argparse.Namespace:
    """解析命令行参数。"""
    parser = argparse.ArgumentParser(
        description="用同一批图片对比多个 YOLO-World 模型的预标注效果。"
    )
    parser.add_argument("--raw-dir", type=Path, default=DEFAULT_RAW_DIR, help="未标注原图目录")
    parser.add_argument(
        "--output-root",
        type=Path,
        default=DEFAULT_OUTPUT_ROOT,
        help="A/B 测试输出根目录",
    )
    parser.add_argument("--run-name", help="本次运行目录名；默认使用时间戳")
    parser.add_argument(
        "--model",
        action="append",
        dest="models",
        help="要对比的模型；可重复传入，也可用逗号分隔",
    )
    parser.add_argument(
        "--prompt",
        action="append",
        dest="prompts",
        help="额外提示词模板；多类别建议使用 {brand} 占位符",
    )
    parser.add_argument(
        "--brand-library",
        type=Path,
        default=DEFAULT_BRAND_LIBRARY,
        help="品牌标识库 JSON/TXT",
    )
    parser.add_argument(
        "--brand-filter",
        action="append",
        dest="brand_filter",
        help="只对比指定品牌，可重复传入；默认不过滤",
    )
    parser.add_argument(
        "--compact-class-ids",
        action="store_true",
        help="将所选品牌重编号为连续类别 ID",
    )
    parser.add_argument(
        "--include-brand-package-prompts",
        action=argparse.BooleanOptionalAction,
        default=True,
        help="是否加入 '<brand> diaper package' 和 '<brand> package' 扩展提示词",
    )
    parser.add_argument("--nms-iou", type=float, default=0.45, help="同类别重复框去重 IoU 阈值")
    parser.add_argument(
        "--containment-threshold",
        type=float,
        default=0.85,
        help="大框覆盖小框过滤阈值",
    )
    parser.add_argument(
        "--max-area-ratio",
        type=float,
        default=0.45,
        help="丢弃占整图面积超过该比例的大框",
    )
    parser.add_argument(
        "--cross-brand-dedup",
        action=argparse.BooleanOptionalAction,
        default=True,
        help="是否启用跨品牌重叠框去重",
    )
    parser.add_argument("--cross-brand-iou", type=float, default=0.35, help="跨品牌重复框去重 IoU 阈值")
    parser.add_argument(
        "--cross-brand-containment",
        type=float,
        default=0.80,
        help="跨品牌覆盖过滤阈值",
    )
    parser.add_argument("--conf", type=float, default=0.03, help="候选框置信度阈值")
    parser.add_argument("--imgsz", type=int, default=960, help="推理图片边长")
    parser.add_argument("--limit", type=int, default=50, help="只处理前 N 张图片；默认 50，避免 A/B 首跑过慢")
    parser.add_argument("--preview-limit", type=int, default=30, help="每个模型最多保存多少张带框预览图")
    parser.add_argument(
        "--candidates-file",
        type=Path,
        default=None,
        help="OCR 候选图片清单；提供后只处理清单中的图片",
    )
    args = parser.parse_args()

    args.models = parse_model_args(args.models)
    validate_ratio("conf", args.conf)
    validate_ratio("nms-iou", args.nms_iou)
    validate_ratio("containment-threshold", args.containment_threshold)
    validate_ratio("max-area-ratio", args.max_area_ratio, allow_zero=False)
    validate_ratio("cross-brand-iou", args.cross_brand_iou)
    validate_ratio("cross-brand-containment", args.cross_brand_containment)
    if args.imgsz <= 0:
        raise SystemExit("--imgsz 必须大于 0。")
    if args.limit is not None and args.limit <= 0:
        raise SystemExit("--limit 必须大于 0；如需全量请传空或修改 Makefile。")
    if args.preview_limit < 0:
        raise SystemExit("--preview-limit 不能小于 0。")
    if not args.models:
        raise SystemExit("至少需要一个模型用于 A/B 测试。")
    return args


def main() -> None:
    """脚本主入口。"""
    configure_ultralytics_weights_dir()
    args = parse_args()
    context = build_run_context(args)
    config = PredictConfig(
        conf=args.conf,
        imgsz=args.imgsz,
        nms_iou=args.nms_iou,
        containment_threshold=args.containment_threshold,
        max_area_ratio=args.max_area_ratio,
        cross_brand_dedup=args.cross_brand_dedup,
        cross_brand_iou=args.cross_brand_iou,
        cross_brand_containment=args.cross_brand_containment,
        preview_limit=args.preview_limit,
    )

    summaries = [run_single_model(model_path, context, config) for model_path in args.models]
    write_markdown_report(
        report_path=context.output_dir / "yolo_world_ab_report.md",
        summary_path=context.output_dir / "metadata" / "model_summary.json",
        summaries=summaries,
        image_paths=context.image_paths,
        parameters=context.parameters | {"models": ", ".join(str(model) for model in args.models)},
    )
    print("\nA/B 测试报告已生成：")
    print(context.output_dir / "yolo_world_ab_report.md")
    print("重要：该报告只反映候选框分布，最终模型选择仍需人工抽检有效框率、漏检数和修框耗时。")


if __name__ == "__main__":
    main()
