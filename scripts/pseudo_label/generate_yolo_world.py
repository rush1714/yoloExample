"""
YOLO-World 多品牌伪标注生成脚本。

该脚本使用 YOLO-World 模型对未标注图片生成候选检测框，用于半自动标注流程：
- 从品牌标识库生成多品牌多类别提示词。
- 将每个品牌提示词映射到稳定的 YOLO class_id。
- 将检测结果转换为 YOLO 格式标签文件。
- 自动划分训练集/验证集/测试集。
- 对同一类别内的跨提示词结果做 NMS、大框覆盖过滤和整图大框过滤。
- 生成详细元数据报告，输出必须经 Label Studio 人工复核后才能用于训练。
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

from common.brand_library import (
    DEFAULT_BRAND_LIBRARY,
    BrandClass,
    filter_brand_classes,
    load_brand_classes,
    normalize_key,
    prompt_to_brand_map,
)
from PIL import Image
from ultralytics import YOLO

# 项目根目录
# 模型目录
MODELS_DIR = PROJECT_ROOT / "models"
# 默认原始图片目录（未标注）
DEFAULT_RAW_DIR = PROJECT_ROOT / "datasets" / "multibrand" / "raw" / "images"
# 默认伪标注输出根目录
DEFAULT_OUTPUT_ROOT = PROJECT_ROOT / "datasets" / "multibrand" / "pseudo"
# 默认 YOLO-World 模型路径
DEFAULT_MODEL = MODELS_DIR / "yolov8s-world.pt"
# 支持的图片格式后缀
IMAGE_SUFFIXES = {".bmp", ".jpeg", ".jpg", ".png", ".tif", ".tiff", ".webp"}
# 数据集划分比例：训练集 70%，验证集 20%，测试集 10%
SPLIT_RATIOS = (0.7, 0.2, 0.1)


@dataclass(frozen=True)
class PromptSpec:
    """YOLO-World 提示词及其对应品牌类别。"""

    prompt: str
    brand: BrandClass


@dataclass(frozen=True)
class PseudoBox:
    """伪标注检测框数据类。"""

    class_id: int  # YOLO 类别 ID
    class_name: str  # YOLO 类别名
    display_name: str  # Label Studio 显示名
    prompt: str  # 触发该检测框的提示词
    confidence: float  # 检测置信度
    xyxy: list[float]  # 边界框坐标 [x1, y1, x2, y2]（像素值）
    yolo: list[float]  # YOLO 格式坐标 [center_x, center_y, width, height]（归一化值）


def configure_ultralytics_weights_dir() -> None:
    """将 Ultralytics 默认权重目录重定向到项目本地 models/。"""
    import ultralytics.utils as ultralytics_utils
    from ultralytics.nn import text_model
    from ultralytics.utils import SETTINGS

    MODELS_DIR.mkdir(parents=True, exist_ok=True)
    SETTINGS["weights_dir"] = str(MODELS_DIR)
    ultralytics_utils.WEIGHTS_DIR = MODELS_DIR
    text_model.WEIGHTS_DIR = MODELS_DIR


def resolve_model_path(model_path: Path) -> Path:
    """解析模型路径，支持绝对路径、models/ 下裸文件名和项目相对路径。"""
    if model_path.is_absolute():
        return model_path
    if model_path.parent == Path(".") and model_path.suffix == ".pt":
        return MODELS_DIR / model_path.name
    return PROJECT_ROOT / model_path


def unique_prompt_specs(items: list[PromptSpec]) -> list[PromptSpec]:
    """按提示词规范化 key 去重，保留顺序和首个品牌映射。"""
    seen: set[str] = set()
    result: list[PromptSpec] = []
    for item in items:
        key = normalize_key(item.prompt)
        if not key or key in seen:
            continue
        seen.add(key)
        result.append(item)
    return result


def build_prompt_specs(
    classes: list[BrandClass],
    include_brand_package_prompts: bool,
    cli_prompts: list[str] | None,
) -> list[PromptSpec]:
    """根据品牌类别生成 YOLO-World 提示词，并保留 prompt -> class 映射。"""
    specs: list[PromptSpec] = []
    for brand in classes:
        # 品牌名和别名直接作为提示词，用于模型识别文字/包装品牌线索。
        base_prompts = [brand.display_name, *brand.aliases]
        if include_brand_package_prompts:
            # 包装组合提示词能提高商品包装召回。
            base_prompts.extend(f"{value} diaper package" for value in [brand.display_name, *brand.aliases])
            base_prompts.extend(f"{value} package" for value in [brand.display_name, *brand.aliases])
        # 命令行额外 prompt 只有在含有 {brand} 占位符时才能安全映射到多类别。
        for template in cli_prompts or []:
            if "{brand}" in template:
                base_prompts.append(template.format(brand=brand.display_name, class_name=brand.class_name))
        specs.extend(PromptSpec(prompt=prompt, brand=brand) for prompt in base_prompts)
    return unique_prompt_specs(specs)


def list_images(raw_dir: Path, limit: int | None, candidates_file: Path | None = None) -> list[Path]:
    """获取待处理图片列表；提供候选清单时优先读取候选清单。"""
    if candidates_file is not None:
        if not candidates_file.is_file():
            raise FileNotFoundError(f"候选清单不存在：{candidates_file}")
        images = [Path(line.strip()).resolve() for line in candidates_file.read_text(encoding="utf-8").splitlines() if line.strip()]
        images = [path for path in images if path.is_file() and path.suffix.lower() in IMAGE_SUFFIXES]
    else:
        images = sorted(path for path in raw_dir.rglob("*") if path.suffix.lower() in IMAGE_SUFFIXES)
    return images[:limit] if limit is not None else images


def split_name(index: int, total: int) -> str:
    """根据索引和总数确定 train/val/test 分割。"""
    if total <= 1:
        return "train"
    train_cutoff = int(total * SPLIT_RATIOS[0])
    val_cutoff = int(total * (SPLIT_RATIOS[0] + SPLIT_RATIOS[1]))
    if index < train_cutoff:
        return "train"
    if index < val_cutoff:
        return "val"
    return "test"


def to_yolo_xywh(xyxy: list[float], image_width: int, image_height: int) -> list[float]:
    """将 xyxy 像素框转换为 YOLO 归一化 xywh。"""
    x1, y1, x2, y2 = xyxy
    x1 = max(0.0, min(float(image_width), x1))
    y1 = max(0.0, min(float(image_height), y1))
    x2 = max(0.0, min(float(image_width), x2))
    y2 = max(0.0, min(float(image_height), y2))
    width = max(0.0, x2 - x1)
    height = max(0.0, y2 - y1)
    center_x = x1 + width / 2
    center_y = y1 + height / 2
    return [
        center_x / image_width,
        center_y / image_height,
        width / image_width,
        height / image_height,
    ]


def box_area(xyxy: list[float]) -> float:
    """计算像素框面积。"""
    return max(0.0, xyxy[2] - xyxy[0]) * max(0.0, xyxy[3] - xyxy[1])


def box_iou(left: list[float], right: list[float]) -> float:
    """计算两个 xyxy 像素框的 IoU。"""
    inter_x1 = max(left[0], right[0])
    inter_y1 = max(left[1], right[1])
    inter_x2 = min(left[2], right[2])
    inter_y2 = min(left[3], right[3])
    inter_area = max(0.0, inter_x2 - inter_x1) * max(0.0, inter_y2 - inter_y1)
    if inter_area <= 0:
        return 0.0
    union_area = box_area(left) + box_area(right) - inter_area
    return inter_area / union_area if union_area > 0 else 0.0


def covered_ratio(inner: list[float], outer: list[float]) -> float:
    """计算 inner 被 outer 覆盖的比例，用于删除覆盖小框的大框。"""
    inner_area = box_area(inner)
    if inner_area <= 0:
        return 0.0
    inter_x1 = max(inner[0], outer[0])
    inter_y1 = max(inner[1], outer[1])
    inter_x2 = min(inner[2], outer[2])
    inter_y2 = min(inner[3], outer[3])
    inter_area = max(0.0, inter_x2 - inter_x1) * max(0.0, inter_y2 - inter_y1)
    return inter_area / inner_area


def filter_boxes(
    boxes: list[PseudoBox],
    image_width: int,
    image_height: int,
    iou_threshold: float,
    containment_threshold: float,
    max_area_ratio: float,
) -> list[PseudoBox]:
    """按类别分别做去重和大框过滤，避免不同品牌互相误删。"""
    image_area = float(image_width * image_height)
    grouped: dict[int, list[PseudoBox]] = {}
    for box in boxes:
        if box_area(box.xyxy) / image_area > max_area_ratio:
            continue
        grouped.setdefault(box.class_id, []).append(box)

    kept_all: list[PseudoBox] = []
    for class_boxes in grouped.values():
        class_boxes.sort(key=lambda item: (item.confidence, -box_area(item.xyxy)), reverse=True)
        kept: list[PseudoBox] = []
        for candidate in class_boxes:
            candidate_area = box_area(candidate.xyxy)
            should_drop = False
            for kept_box in kept:
                kept_area = box_area(kept_box.xyxy)
                if box_iou(candidate.xyxy, kept_box.xyxy) >= iou_threshold:
                    should_drop = True
                    break
                if candidate_area > kept_area and covered_ratio(kept_box.xyxy, candidate.xyxy) >= containment_threshold:
                    should_drop = True
                    break
            if not should_drop:
                kept.append(candidate)
        kept_all.extend(kept)
    return sorted(kept_all, key=lambda item: (item.class_id, -item.confidence))


def predict_image(
    model: YOLO,
    image_path: Path,
    prompt_map: dict[str, BrandClass],
    confidence: float,
    imgsz: int,
    nms_iou: float,
    containment_threshold: float,
    max_area_ratio: float,
) -> list[PseudoBox]:
    """执行 YOLO-World 推理，并将 prompt 结果映射为品牌类别。"""
    with Image.open(image_path) as image:
        image_width, image_height = image.size

    result = model.predict(source=str(image_path), conf=confidence, imgsz=imgsz, verbose=False)[0]
    boxes: list[PseudoBox] = []
    for box in result.boxes:
        model_class_id = int(box.cls.item())
        prompt = result.names[model_class_id]
        brand = prompt_map.get(normalize_key(prompt))
        if brand is None:
            # 多类别训练不能安全使用没有品牌映射的泛化 prompt。
            continue
        xyxy = [float(value) for value in box.xyxy[0].tolist()]
        yolo = to_yolo_xywh(xyxy, image_width, image_height)
        if yolo[2] <= 0 or yolo[3] <= 0:
            continue
        boxes.append(
            PseudoBox(
                class_id=brand.class_id,
                class_name=brand.class_name,
                display_name=brand.display_name,
                prompt=prompt,
                confidence=round(float(box.conf.item()), 4),
                xyxy=[round(value, 2) for value in xyxy],
                yolo=[round(value, 6) for value in yolo],
            )
        )
    return filter_boxes(
        boxes=boxes,
        image_width=image_width,
        image_height=image_height,
        iou_threshold=nms_iou,
        containment_threshold=containment_threshold,
        max_area_ratio=max_area_ratio,
    )


def prepare_output_dirs(output_root: Path) -> None:
    """创建伪标注输出目录结构。"""
    for split in ("train", "val", "test"):
        (output_root / "images" / split).mkdir(parents=True, exist_ok=True)
        (output_root / "labels" / split).mkdir(parents=True, exist_ok=True)
    (output_root / "metadata").mkdir(parents=True, exist_ok=True)


def main() -> None:
    """伪标注生成脚本主入口。"""
    parser = argparse.ArgumentParser(description="用 YOLO-World 对未标注图片生成多品牌候选框。生成结果必须人工复核。")
    parser.add_argument("--raw-dir", type=Path, default=DEFAULT_RAW_DIR, help="未标注原图目录")
    parser.add_argument("--output-root", type=Path, default=DEFAULT_OUTPUT_ROOT, help="伪标注数据集输出根目录")
    parser.add_argument("--model", type=Path, default=DEFAULT_MODEL, help="YOLO-World 权重，例如 models/yolov8s-world.pt")
    parser.add_argument("--prompt", action="append", dest="prompts", help="额外提示词模板；多类别建议使用 {brand} 占位符")
    parser.add_argument("--brand-library", type=Path, default=DEFAULT_BRAND_LIBRARY, help="品牌标识库 JSON/TXT")
    parser.add_argument("--brand-filter", action="append", dest="brand_filter", help="只预标指定品牌，可重复传入；默认不过滤，即多品牌")
    parser.add_argument("--include-brand-package-prompts", action="store_true", help="为每个品牌额外生成 '<brand> diaper package' 和 '<brand> package' 提示词")
    parser.add_argument("--nms-iou", type=float, default=0.45, help="同类别重复框去重 IoU 阈值")
    parser.add_argument("--containment-threshold", type=float, default=0.85, help="大框覆盖已保留小框超过该比例时丢弃大框")
    parser.add_argument("--max-area-ratio", type=float, default=0.45, help="丢弃占整图面积超过该比例的大框")
    parser.add_argument("--conf", type=float, default=0.12, help="候选框置信度阈值")
    parser.add_argument("--imgsz", type=int, default=960, help="推理图片边长")
    parser.add_argument("--limit", type=int, default=None, help="只处理前 N 张图片，便于先试跑")
    parser.add_argument("--candidates-file", type=Path, default=None, help="OCR 候选图片清单；提供后只处理清单中的图片")
    args = parser.parse_args()

    configure_ultralytics_weights_dir()
    args.model = resolve_model_path(args.model)

    if not args.raw_dir.is_dir():
        raise SystemExit(f"原图目录不存在：{args.raw_dir}")
    if not 0.0 <= args.conf <= 1.0:
        raise SystemExit("--conf 必须位于 0 到 1 之间。")
    if not 0.0 <= args.nms_iou <= 1.0:
        raise SystemExit("--nms-iou 必须位于 0 到 1 之间。")
    if not 0.0 <= args.containment_threshold <= 1.0:
        raise SystemExit("--containment-threshold 必须位于 0 到 1 之间。")
    if not 0.0 < args.max_area_ratio <= 1.0:
        raise SystemExit("--max-area-ratio 必须位于 0 到 1 之间且大于 0。")

    try:
        all_classes = load_brand_classes(args.brand_library)
    except (FileNotFoundError, ValueError) as exc:
        raise SystemExit(str(exc)) from exc
    selected_classes = filter_brand_classes(all_classes, args.brand_filter)
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
    print(f"品牌类别数量：{len(all_classes)}，本次预标注品牌：{', '.join(brand.display_name for brand in selected_classes)}")
    print(f"YOLO-World 提示词数量：{len(prompts)}，提示词：{', '.join(prompts)}")

    try:
        images = list_images(args.raw_dir, args.limit, args.candidates_file)
    except FileNotFoundError as exc:
        raise SystemExit(str(exc)) from exc
    if not images:
        source = f"候选清单 {args.candidates_file}" if args.candidates_file else f"原图目录 {args.raw_dir}"
        raise SystemExit(f"没有可处理的图片：{source}")

    prepare_output_dirs(args.output_root)
    model = YOLO(str(args.model))
    model.set_classes(prompts)

    rows: list[dict[str, object]] = []
    for index, image_path in enumerate(images):
        split = split_name(index, len(images))
        target_image = args.output_root / "images" / split / image_path.name
        target_label = args.output_root / "labels" / split / image_path.with_suffix(".txt").name
        shutil.copy2(image_path, target_image)

        boxes = predict_image(
            model=model,
            image_path=image_path,
            prompt_map=prompt_map,
            confidence=args.conf,
            imgsz=args.imgsz,
            nms_iou=args.nms_iou,
            containment_threshold=args.containment_threshold,
            max_area_ratio=args.max_area_ratio,
        )
        label_lines = [f"{box.class_id} " + " ".join(f"{value:.6f}" for value in box.yolo) for box in boxes]
        target_label.write_text("\n".join(label_lines) + ("\n" if label_lines else ""), encoding="utf-8")
        rows.append(
            {
                "image": str(target_image),
                "label": str(target_label),
                "split": split,
                "box_count": len(boxes),
                "boxes": [box.__dict__ for box in boxes],
            }
        )
        class_summary: dict[str, int] = {}
        for box in boxes:
            class_summary[box.class_name] = class_summary.get(box.class_name, 0) + 1
        print(f"[{index + 1}/{len(images)}] {split} {image_path.name}: {len(boxes)} boxes {class_summary}")

    json_path = args.output_root / "metadata" / "pseudo_label_report.json"
    csv_path = args.output_root / "metadata" / "pseudo_label_report.csv"
    json_path.write_text(json.dumps(rows, ensure_ascii=False, indent=2), encoding="utf-8")
    with csv_path.open("w", encoding="utf-8", newline="") as file:
        writer = csv.DictWriter(file, fieldnames=["image", "label", "split", "box_count"])
        writer.writeheader()
        for row in rows:
            writer.writerow({key: row[key] for key in ["image", "label", "split", "box_count"]})

    print(f"完成：{len(images)} 张图片，候选框 {sum(int(row['box_count']) for row in rows)} 个。")
    print(f"伪标注目录：{args.output_root}")
    print("重要：请用 Label Studio 打开并人工复核这些标签，再用于训练。")


if __name__ == "__main__":
    main()
