from __future__ import annotations

import argparse
import json
from pathlib import Path
from urllib.parse import urlparse

from ultralytics import YOLO

PROJECT_ROOT = Path(__file__).resolve().parents[1]
MODELS_DIR = PROJECT_ROOT / "models"
DEFAULT_MODEL = MODELS_DIR / "softcare-best.pt"
DEFAULT_OUTPUT_DIR = PROJECT_ROOT / "outputs" / "predict"
TARGET_CLASS = "softcare_diaper"


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


def validate_source(source: str) -> str:
    parsed = urlparse(source)
    if parsed.scheme:
        if parsed.scheme not in {"http", "https"} or not parsed.netloc:
            raise ValueError("图片地址必须是本地文件路径或完整的 HTTP(S) URL。")
        return source

    path = Path(source)
    if not path.is_file():
        raise FileNotFoundError(f"图片不存在：{path}")
    return str(path.resolve())


def main() -> None:
    parser = argparse.ArgumentParser(description="识别并统计图片中的 Softcare 纸尿裤包装。")
    parser.add_argument("source", help="本地图片路径或 HTTP(S) 图片 URL")
    parser.add_argument("--model", type=Path, default=DEFAULT_MODEL, help="训练完成的 best.pt 路径")
    parser.add_argument("--conf", type=float, default=0.35, help="最小置信度，范围 0 到 1")
    parser.add_argument("--imgsz", type=int, default=960, help="推理图片边长")
    parser.add_argument("--output-dir", type=Path, default=DEFAULT_OUTPUT_DIR, help="结果输出目录")
    args = parser.parse_args()

    configure_ultralytics_weights_dir()

    args.model = resolve_model_path(args.model)

    if not 0.0 <= args.conf <= 1.0:
        raise SystemExit("--conf 必须位于 0 到 1 之间。")
    if not args.model.is_file():
        raise SystemExit(
            f"Softcare 模型不存在：{args.model}\n"
            "请先完成标注和训练，再将 best.pt 复制到 models/softcare-best.pt，或通过 --model 指向具体权重文件。"
        )

    source = validate_source(args.source)
    model = YOLO(args.model)
    if TARGET_CLASS not in model.names.values():
        raise SystemExit(
            f"模型未包含类别 {TARGET_CLASS}，当前类别：{list(model.names.values())}\n"
            "请使用 Softcare 数据集训练生成的 best.pt。"
        )

    result = model.predict(source=source, conf=args.conf, imgsz=args.imgsz, verbose=False)[0]
    output_dir = args.output_dir.resolve()
    output_dir.mkdir(parents=True, exist_ok=True)
    source_name = Path(urlparse(source).path).stem or "prediction"
    annotated_path = output_dir / f"{source_name}-annotated.jpg"
    json_path = output_dir / f"{source_name}.json"

    detections = []
    for box in result.boxes:
        class_id = int(box.cls.item())
        class_name = result.names[class_id]
        if class_name != TARGET_CLASS:
            continue
        x1, y1, x2, y2 = (round(float(value), 2) for value in box.xyxy[0].tolist())
        detections.append(
            {
                "class_id": class_id,
                "class_name": class_name,
                "confidence": round(float(box.conf.item()), 4),
                "xyxy": [x1, y1, x2, y2],
            }
        )

    result.save(filename=str(annotated_path))
    payload = {
        "source": source,
        "model": str(args.model.resolve()),
        "softcare_count": len(detections),
        "detections": detections,
        "annotated_image": str(annotated_path),
    }
    json_path.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
    print(json.dumps(payload, ensure_ascii=False, indent=2))
    print(f"JSON 结果：{json_path}")


if __name__ == "__main__":
    main()
