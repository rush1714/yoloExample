from __future__ import annotations

import argparse
import csv
import json
import shutil
from dataclasses import dataclass
from pathlib import Path

from PIL import Image
from ultralytics import YOLO

PROJECT_ROOT = Path(__file__).resolve().parents[1]
MODELS_DIR = PROJECT_ROOT / "models"
DEFAULT_RAW_DIR = PROJECT_ROOT / "datasets" / "softcare" / "raw" / "images"
DEFAULT_OUTPUT_ROOT = PROJECT_ROOT / "datasets" / "softcare" / "pseudo"
DEFAULT_MODEL = MODELS_DIR / "yolov8s-world.pt"
DEFAULT_PROMPTS = [
    "diaper package",
    "baby diaper package",
    "softcare diaper package",
    "softcare",
]
IMAGE_SUFFIXES = {".bmp", ".jpeg", ".jpg", ".png", ".tif", ".tiff", ".webp"}
SPLIT_RATIOS = (0.7, 0.2, 0.1)


def configure_ultralytics_weights_dir() -> None:
    import ultralytics.utils as ultralytics_utils
    from ultralytics.nn import text_model
    from ultralytics.utils import SETTINGS

    MODELS_DIR.mkdir(parents=True, exist_ok=True)
    SETTINGS["weights_dir"] = str(MODELS_DIR)
    ultralytics_utils.WEIGHTS_DIR = MODELS_DIR
    text_model.WEIGHTS_DIR = MODELS_DIR


def resolve_model_path(model_path: Path) -> Path:
    if model_path.is_absolute():
        return model_path
    if model_path.parent == Path(".") and model_path.suffix == ".pt":
        return MODELS_DIR / model_path.name
    return PROJECT_ROOT / model_path


@dataclass(frozen=True)
class PseudoBox:
    prompt: str
    confidence: float
    xyxy: list[float]
    yolo: list[float]


def list_images(raw_dir: Path, limit: int | None, candidates_file: Path | None = None) -> list[Path]:
    if candidates_file is not None:
        if not candidates_file.is_file():
            raise FileNotFoundError(f"候选清单不存在：{candidates_file}")
        images = [Path(line.strip()).resolve() for line in candidates_file.read_text(encoding="utf-8").splitlines() if line.strip()]
        images = [path for path in images if path.is_file() and path.suffix.lower() in IMAGE_SUFFIXES]
    else:
        images = sorted(path for path in raw_dir.rglob("*") if path.suffix.lower() in IMAGE_SUFFIXES)
    return images[:limit] if limit is not None else images


def split_name(index: int, total: int) -> str:
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


def predict_image(model: YOLO, image_path: Path, confidence: float, imgsz: int) -> list[PseudoBox]:
    with Image.open(image_path) as image:
        image_width, image_height = image.size

    result = model.predict(source=str(image_path), conf=confidence, imgsz=imgsz, verbose=False)[0]
    boxes: list[PseudoBox] = []
    for box in result.boxes:
        class_id = int(box.cls.item())
        prompt = result.names[class_id]
        xyxy = [float(value) for value in box.xyxy[0].tolist()]
        yolo = to_yolo_xywh(xyxy, image_width, image_height)
        if yolo[2] <= 0 or yolo[3] <= 0:
            continue
        boxes.append(
            PseudoBox(
                prompt=prompt,
                confidence=round(float(box.conf.item()), 4),
                xyxy=[round(value, 2) for value in xyxy],
                yolo=[round(value, 6) for value in yolo],
            )
        )
    return boxes


def prepare_output_dirs(output_root: Path) -> None:
    for split in ("train", "val", "test"):
        (output_root / "images" / split).mkdir(parents=True, exist_ok=True)
        (output_root / "labels" / split).mkdir(parents=True, exist_ok=True)
    (output_root / "metadata").mkdir(parents=True, exist_ok=True)


def main() -> None:
    parser = argparse.ArgumentParser(
        description="用 YOLO-World 对未标注图片生成 Softcare/纸尿裤候选框。生成结果必须人工复核。"
    )
    parser.add_argument("--raw-dir", type=Path, default=DEFAULT_RAW_DIR, help="未标注原图目录")
    parser.add_argument("--output-root", type=Path, default=DEFAULT_OUTPUT_ROOT, help="伪标注数据集输出根目录")
    parser.add_argument("--model", type=Path, default=DEFAULT_MODEL, help="YOLO-World 权重，例如 models/yolov8s-world.pt")
    parser.add_argument("--prompt", action="append", dest="prompts", help="开放词汇提示词，可重复传入")
    parser.add_argument("--conf", type=float, default=0.12, help="候选框置信度阈值；预标注建议低一些，人工复核再删除误检")
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

    prompts = args.prompts or DEFAULT_PROMPTS
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

        boxes = predict_image(model, image_path, args.conf, args.imgsz)
        label_lines = ["0 " + " ".join(f"{value:.6f}" for value in box.yolo) for box in boxes]
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
        print(f"[{index + 1}/{len(images)}] {split} {image_path.name}: {len(boxes)} boxes")

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
    print("重要：请用 CVAT/Label Studio 打开并人工复核这些标签，再用于训练。")


if __name__ == "__main__":
    main()
