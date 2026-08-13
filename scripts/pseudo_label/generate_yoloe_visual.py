"""
YOLOE visual prompt 多品牌伪标注生成脚本。

该脚本用于把“品牌参考包装图”转换成 YOLOE visual prompt，再对原始门店图片
生成候选检测框。它与 YOLO-World 文本 prompt 脚本保持相同输出结构：
- pseudo/images/<split>/ 保存待复核图片副本；
- pseudo/labels/<split>/ 保存 YOLO bbox 标签；
- pseudo/metadata/ 保存逐图 JSON/CSV 与参考图清单。

参考图目录约定：reference_root/<品牌目录>/*.{jpg,png,webp...}。
品牌目录可以使用品牌显示名、class_name 或别名；脚本会用品牌库做规范化匹配。
如果参考图本身就是裁好的包装图，默认整张图作为 visual prompt 参考框；如果需要
在一张大图里指定包装位置，可放同名 JSON sidecar，例如 a.jpg + a.json：
{"bbox": [x1, y1, x2, y2]}。
"""

from __future__ import annotations

import argparse
import json
import os
import shutil
import sys
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Any

# pylint: disable=wrong-import-position

PROJECT_ROOT = Path(__file__).resolve().parents[2]
# Ultralytics/Matplotlib 在导入阶段可能写配置缓存；放到项目内，避免写用户目录失败。
MPLCONFIG_DIR = PROJECT_ROOT / ".tmp" / "matplotlib"
YOLO_CONFIG_DIR = PROJECT_ROOT / ".tmp" / "ultralytics"
for runtime_dir in (MPLCONFIG_DIR, YOLO_CONFIG_DIR, YOLO_CONFIG_DIR / "Ultralytics"):
    runtime_dir.mkdir(parents=True, exist_ok=True)
os.environ.setdefault("MPLCONFIGDIR", str(MPLCONFIG_DIR))
os.environ.setdefault("YOLO_CONFIG_DIR", str(YOLO_CONFIG_DIR))
SCRIPTS_ROOT = PROJECT_ROOT / "scripts"
if str(SCRIPTS_ROOT) not in sys.path:
    sys.path.insert(0, str(SCRIPTS_ROOT))

import numpy as np
from common.brand_library import (  # type: ignore[import-not-found]
    DEFAULT_BRAND_LIBRARY,
    BrandClass,
    load_brand_classes,
    normalize_key,
    select_brand_classes,
)
from common.ultralytics_config import (  # type: ignore[import-not-found]
    configure_ultralytics_weights_dir,
)
from PIL import Image
from pseudo_label.generate_yolo_world import (  # type: ignore[import-not-found]
    DEFAULT_RAW_DIR,
    IMAGE_SUFFIXES,
    MODELS_DIR,
    PseudoBox,
    PseudoReportWriter,
    filter_boxes,
    list_images,
    prepare_output_dirs,
    split_name,
    to_yolo_xywh,
)
from ultralytics import YOLOE
from ultralytics.models.yolo.yoloe import YOLOEVPSegPredictor

# 默认使用小模型先跑通 visual prompt 分支；效果评估时可切到 m/l。
DEFAULT_MODEL = MODELS_DIR / "yoloe-26s-seg.pt"
# 参考图默认集中放在共享多品牌数据池，避免单品牌重复复制参考包装图。
DEFAULT_REFERENCE_ROOT = PROJECT_ROOT / "datasets" / "multibrand" / "visual_prompts"
# 默认伪标注输出目录与既有 Label Studio 导入脚本兼容。
DEFAULT_OUTPUT_ROOT = PROJECT_ROOT / "datasets" / "multibrand" / "pseudo"


@dataclass(frozen=True)
class VisualPromptReference:
    """一张品牌参考包装图及其 visual prompt bbox。"""

    brand: BrandClass
    image_path: Path
    bbox_xyxy: list[float]

    @property
    def prompt_name(self) -> str:
        """生成写入元数据的提示词名称，便于回溯是哪张参考图触发的框。"""
        return f"visual:{self.brand.display_name}:{self.image_path.name}"


@dataclass(frozen=True)
class PredictConfig:  # pylint: disable=too-many-instance-attributes
    """YOLOE visual prompt 推理与候选框过滤参数。"""

    conf: float
    imgsz: int
    device: str | None
    nms_iou: float
    containment_threshold: float
    max_area_ratio: float
    cross_brand_dedup: bool
    cross_brand_iou: float
    cross_brand_containment: float


def resolve_model_path(model_path: Path) -> Path:
    """解析 YOLOE 权重路径，兼容绝对路径、裸文件名和项目相对路径。"""
    if model_path.is_absolute():
        return model_path
    if model_path.parent == Path(".") and model_path.suffix == ".pt":
        return MODELS_DIR / model_path.name
    return PROJECT_ROOT / model_path


def brand_reference_keys(brand: BrandClass) -> set[str]:
    """生成可匹配参考图品牌目录名的一组规范化 key。"""
    values = [brand.display_name, brand.class_name, *brand.aliases]
    return {normalize_key(value) for value in values if normalize_key(value)}


def load_reference_bbox(image_path: Path) -> list[float]:
    """
    读取参考图 bbox；默认整张参考图就是目标包装。

    如果存在同名 JSON sidecar，支持两种简洁写法：
    - [x1, y1, x2, y2]
    - {"bbox": [x1, y1, x2, y2]}
    """
    sidecar_path = image_path.with_suffix(".json")
    if sidecar_path.is_file():
        payload: Any = json.loads(sidecar_path.read_text(encoding="utf-8"))
        bbox_value = payload.get("bbox") if isinstance(payload, dict) else payload
        if not isinstance(bbox_value, list) or len(bbox_value) != 4:
            raise ValueError(f"参考图 bbox JSON 格式错误：{sidecar_path}")
        return [float(value) for value in bbox_value]

    with Image.open(image_path) as image:
        width, height = image.size
    return [0.0, 0.0, float(width), float(height)]


def validate_reference_bbox(image_path: Path, bbox_xyxy: list[float]) -> list[float]:
    """校验并裁剪参考框，避免 visual prompt 收到空框或越界框。"""
    with Image.open(image_path) as image:
        width, height = image.size
    x1, y1, x2, y2 = bbox_xyxy
    clipped = [
        max(0.0, min(float(width), x1)),
        max(0.0, min(float(height), y1)),
        max(0.0, min(float(width), x2)),
        max(0.0, min(float(height), y2)),
    ]
    if clipped[2] <= clipped[0] or clipped[3] <= clipped[1]:
        raise ValueError(f"参考图 bbox 为空或无效：{image_path} -> {bbox_xyxy}")
    return clipped


def index_reference_directories(reference_root: Path) -> dict[str, list[Path]]:
    """按规范化目录名索引一级参考图目录，支持同一品牌多个别名目录。"""
    directory_index: dict[str, list[Path]] = {}
    for child in sorted(path for path in reference_root.iterdir() if path.is_dir()):
        key = normalize_key(child.name)
        if key:
            directory_index.setdefault(key, []).append(child)
    return directory_index


def matching_reference_directories(
    directory_index: dict[str, list[Path]],
    brand: BrandClass,
) -> list[Path]:
    """找出某个品牌可使用的参考图目录，并避免别名目录重复加入。"""
    brand_dirs: list[Path] = []
    seen_dirs: set[Path] = set()
    for key in sorted(brand_reference_keys(brand)):
        for directory in directory_index.get(key, []):
            if directory in seen_dirs:
                continue
            seen_dirs.add(directory)
            brand_dirs.append(directory)
    return brand_dirs


def reference_images_for_brand(
    brand_dirs: list[Path],
    reference_limit: int | None,
) -> list[Path]:
    """从品牌目录递归收集参考图片，并应用每品牌参考图数量上限。"""
    brand_images: list[Path] = []
    for directory in brand_dirs:
        brand_images.extend(
            sorted(
                image_path
                for image_path in directory.rglob("*")
                if image_path.is_file() and image_path.suffix.lower() in IMAGE_SUFFIXES
            )
        )
    return brand_images[:reference_limit] if reference_limit is not None else brand_images


def build_reference(brand: BrandClass, image_path: Path) -> VisualPromptReference:
    """把单张参考图片转换成带品牌类别和参考框的 visual prompt 配置。"""
    bbox = validate_reference_bbox(image_path, load_reference_bbox(image_path))
    return VisualPromptReference(
        brand=brand,
        image_path=image_path,
        bbox_xyxy=[round(value, 2) for value in bbox],
    )


def collect_reference_prompts(
    reference_root: Path,
    brands: list[BrandClass],
    reference_limit: int | None = None,
) -> list[VisualPromptReference]:
    """按品牌目录收集参考包装图，多品牌时会从每个品牌目录分别取图。"""
    if not reference_root.is_dir():
        raise FileNotFoundError(f"参考图根目录不存在：{reference_root}")

    directory_index = index_reference_directories(reference_root)
    references: list[VisualPromptReference] = []
    missing_brands: list[str] = []
    for brand in brands:
        brand_dirs = matching_reference_directories(directory_index, brand)
        brand_images = reference_images_for_brand(brand_dirs, reference_limit)
        if not brand_images:
            missing_brands.append(brand.display_name)
            continue
        references.extend(build_reference(brand, image_path) for image_path in brand_images)

    if missing_brands:
        missing_text = ", ".join(missing_brands)
        raise FileNotFoundError(
            f"以下品牌没有可用参考图：{missing_text}。请放到 {reference_root}/<品牌名>/ 下。"
        )
    return references


def build_visual_prompt_payload(reference: VisualPromptReference) -> dict[str, np.ndarray]:
    """构造 Ultralytics YOLOE visual_prompts 参数。"""
    return {
        "bboxes": np.array([reference.bbox_xyxy], dtype=np.float32),
        # 每次只用一个品牌参考图，YOLOE 内部类别固定为 object0，之后映射回业务品牌。
        "cls": np.array([0], dtype=np.int64),
    }


def predict_with_reference(
    model: YOLOE,
    image_path: Path,
    reference: VisualPromptReference,
    config: PredictConfig,
) -> list[PseudoBox]:
    """用单张参考包装图对单张目标图片执行 YOLOE visual prompt 推理。"""
    with Image.open(image_path) as image:
        image_width, image_height = image.size

    result = model.predict(
        source=str(image_path),
        refer_image=str(reference.image_path),
        visual_prompts=build_visual_prompt_payload(reference),
        predictor=YOLOEVPSegPredictor,
        conf=config.conf,
        imgsz=config.imgsz,
        device=config.device,
        verbose=False,
    )[0]

    boxes: list[PseudoBox] = []
    for box in result.boxes:
        xyxy = [float(value) for value in box.xyxy[0].tolist()]
        yolo = to_yolo_xywh(xyxy, image_width, image_height)
        if yolo[2] <= 0 or yolo[3] <= 0:
            continue
        boxes.append(
            PseudoBox(
                class_id=reference.brand.class_id,
                class_name=reference.brand.class_name,
                display_name=reference.brand.display_name,
                prompt=reference.prompt_name,
                confidence=round(float(box.conf.item()), 4),
                xyxy=[round(value, 2) for value in xyxy],
                yolo=[round(value, 6) for value in yolo],
            )
        )
    return boxes


def predict_image(
    model: YOLOE,
    image_path: Path,
    references: list[VisualPromptReference],
    config: PredictConfig,
) -> list[PseudoBox]:
    """对单张图片依次运行所有品牌参考图，并合并、去重、过滤候选框。"""
    with Image.open(image_path) as image:
        image_width, image_height = image.size

    boxes: list[PseudoBox] = []
    for reference in references:
        boxes.extend(predict_with_reference(model, image_path, reference, config))

    return filter_boxes(
        boxes=boxes,
        image_width=image_width,
        image_height=image_height,
        iou_threshold=config.nms_iou,
        containment_threshold=config.containment_threshold,
        max_area_ratio=config.max_area_ratio,
        cross_brand_dedup=config.cross_brand_dedup,
        cross_iou_threshold=config.cross_brand_iou,
        cross_containment_threshold=config.cross_brand_containment,
    )


def write_json_atomic(path: Path, payload: object) -> None:
    """原子写 JSON 文件，避免中途中断留下半截文件。"""
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary_path = path.with_suffix(path.suffix + ".tmp")
    temporary_path.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
    os.replace(temporary_path, path)


def write_yolo_label(path: Path, boxes: list[PseudoBox]) -> None:
    """把候选框写成 YOLO txt 格式，供 Label Studio 预标注导入使用。"""
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


def class_count_summary(boxes: list[PseudoBox]) -> dict[str, int]:
    """汇总单张图的品牌候选框数量，用于命令行进度展示。"""
    summary: dict[str, int] = {}
    for box in boxes:
        summary[box.class_name] = summary.get(box.class_name, 0) + 1
    return summary


def validate_ratio(name: str, value: float, allow_zero: bool = True) -> None:
    """校验 0-1 区间参数，尽早给出中文错误。"""
    lower_ok = value >= 0.0 if allow_zero else value > 0.0
    if not lower_ok or value > 1.0:
        operator = "0 到 1" if allow_zero else "0 到 1 且大于 0"
        raise SystemExit(f"--{name} 必须位于 {operator} 之间。")


def parse_args() -> argparse.Namespace:
    """解析命令行参数。"""
    parser = argparse.ArgumentParser(
        description="使用 YOLOE visual prompt 和品牌参考图生成预标注。"
    )
    parser.add_argument("--raw-dir", type=Path, default=DEFAULT_RAW_DIR, help="未标注原图目录")
    parser.add_argument(
        "--output-root",
        type=Path,
        default=DEFAULT_OUTPUT_ROOT,
        help="伪标注输出目录，需与 Label Studio 导入流程保持一致",
    )
    parser.add_argument(
        "--reference-root",
        type=Path,
        default=DEFAULT_REFERENCE_ROOT,
        help="品牌参考图根目录，目录结构为 reference_root/<品牌名>/*.jpg",
    )
    parser.add_argument("--model", type=Path, default=DEFAULT_MODEL, help="YOLOE seg 权重路径")
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
        help="只预标指定品牌，可重复传入；默认使用全部品牌",
    )
    parser.add_argument("--compact-class-ids", action="store_true", help="将所选品牌重编号")
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
    parser.add_argument("--cross-brand-iou", type=float, default=0.35, help="跨品牌去重 IoU 阈值")
    parser.add_argument(
        "--cross-brand-containment",
        type=float,
        default=0.80,
        help="跨品牌覆盖过滤阈值",
    )
    parser.add_argument("--conf", type=float, default=0.05, help="YOLOE 候选框置信度阈值")
    parser.add_argument("--imgsz", type=int, default=960, help="推理图片边长")
    parser.add_argument("--device", default=None, help="推理设备，例如 mps、cpu、0；空值由 Ultralytics 自动选择")
    parser.add_argument("--limit", type=int, default=None, help="只处理前 N 张图片，便于先试跑")
    parser.add_argument(
        "--reference-limit",
        type=int,
        default=None,
        help="每个品牌最多使用多少张参考图；默认使用全部参考图",
    )
    parser.add_argument(
        "--candidates-file",
        type=Path,
        default=None,
        help="OCR 候选图片清单；提供后只处理清单中的图片",
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="只检查图片、品牌和参考图，不加载模型、不写伪标签",
    )
    args = parser.parse_args()

    args.model = resolve_model_path(args.model)
    validate_ratio("conf", args.conf)
    validate_ratio("nms-iou", args.nms_iou)
    validate_ratio("containment-threshold", args.containment_threshold)
    validate_ratio("max-area-ratio", args.max_area_ratio, allow_zero=False)
    validate_ratio("cross-brand-iou", args.cross_brand_iou)
    validate_ratio("cross-brand-containment", args.cross_brand_containment)
    if args.imgsz <= 0:
        raise SystemExit("--imgsz 必须大于 0。")
    if args.limit is not None and args.limit <= 0:
        raise SystemExit("--limit 必须大于 0。")
    if args.reference_limit is not None and args.reference_limit <= 0:
        raise SystemExit("--reference-limit 必须大于 0。")
    return args


def load_run_inputs(
    args: argparse.Namespace,
) -> tuple[list[BrandClass], list[Path], list[VisualPromptReference]]:
    """加载品牌、待处理图片和 visual prompt 参考图。"""
    if not args.raw_dir.is_dir():
        raise SystemExit(f"原图目录不存在：{args.raw_dir}")
    try:
        images = list_images(args.raw_dir, args.limit, args.candidates_file)
    except FileNotFoundError as exc:
        raise SystemExit(str(exc)) from exc
    if not images:
        source = (
            f"候选清单 {args.candidates_file}"
            if args.candidates_file
            else f"原图目录 {args.raw_dir}"
        )
        raise SystemExit(f"没有可处理的图片：{source}")

    try:
        all_classes = load_brand_classes(args.brand_library)
    except (FileNotFoundError, ValueError) as exc:
        raise SystemExit(str(exc)) from exc
    selected_classes = select_brand_classes(
        all_classes,
        args.brand_filter,
        args.compact_class_ids,
    )
    if not selected_classes:
        raise SystemExit(f"品牌过滤后没有可用类别：{args.brand_filter}")

    try:
        references = collect_reference_prompts(
            reference_root=args.reference_root,
            brands=selected_classes,
            reference_limit=args.reference_limit,
        )
    except (FileNotFoundError, ValueError) as exc:
        raise SystemExit(str(exc)) from exc
    return selected_classes, images, references


def write_reference_report(output_root: Path, references: list[VisualPromptReference]) -> None:
    """写出本次使用的参考图清单，便于排查误检来源。"""
    rows = [
        {
            "brand": reference.brand.display_name,
            "class_id": reference.brand.class_id,
            "class_name": reference.brand.class_name,
            "image": str(reference.image_path),
            "bbox_xyxy": reference.bbox_xyxy,
            "prompt": reference.prompt_name,
        }
        for reference in references
    ]
    write_json_atomic(output_root / "metadata" / "visual_prompt_references.json", rows)


def run_pseudo_label(args: argparse.Namespace) -> None:
    """执行完整 YOLOE visual prompt 预标注流程。"""
    selected_classes, images, references = load_run_inputs(args)
    print(
        "本次 YOLOE visual prompt 品牌："
        f"{', '.join(brand.display_name for brand in selected_classes)}"
    )
    print(f"目标图片数量：{len(images)}")
    print(f"参考图数量：{len(references)}")
    print(f"参考图根目录：{args.reference_root}")

    if args.dry_run:
        print("dry-run 完成：未加载模型，未写入伪标签。")
        return

    configure_ultralytics_weights_dir()
    prepare_output_dirs(args.output_root)
    write_reference_report(args.output_root, references)
    model = YOLOE(str(args.model))
    config = PredictConfig(
        conf=args.conf,
        imgsz=args.imgsz,
        device=args.device,
        nms_iou=args.nms_iou,
        containment_threshold=args.containment_threshold,
        max_area_ratio=args.max_area_ratio,
        cross_brand_dedup=args.cross_brand_dedup,
        cross_brand_iou=args.cross_brand_iou,
        cross_brand_containment=args.cross_brand_containment,
    )

    report_writer = PseudoReportWriter(args.output_root)
    total_boxes = 0
    for index, image_path in enumerate(images):
        split = split_name(index, len(images))
        target_image = args.output_root / "images" / split / image_path.name
        target_label = args.output_root / "labels" / split / image_path.with_suffix(".txt").name
        boxes = predict_image(model, image_path, references, config)
        shutil.copy2(image_path, target_image)
        write_yolo_label(target_label, boxes)
        row = {
            "image": str(target_image),
            "label": str(target_label),
            "split": split,
            "box_count": len(boxes),
            "boxes": [asdict(box) for box in boxes],
        }
        report_writer.record(row)
        total_boxes += len(boxes)
        print(
            f"[{index + 1}/{len(images)}] {split} {image_path.name}: "
            f"{len(boxes)} boxes {class_count_summary(boxes)}"
        )

    print(f"完成：{len(images)} 张图片，YOLOE visual prompt 候选框 {total_boxes} 个。")
    print(f"伪标注目录：{args.output_root}")
    print("重要：请用 Label Studio 打开并人工复核这些标签，再用于训练。")


def main() -> None:
    """脚本入口。"""
    run_pseudo_label(parse_args())


if __name__ == "__main__":
    main()
