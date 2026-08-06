"""
多品牌 YOLO 检测推理脚本。

支持：
- 本地图片路径或 HTTP(S) URL 输入。
- 自定义置信度阈值和图片尺寸。
- 输出带框图片和 JSON 检测结果。
- 对多品牌模型按 class_name 汇总计数。
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path
from urllib.parse import urlparse

from ultralytics import YOLO

PROJECT_ROOT = Path(__file__).resolve().parents[2]
SCRIPTS_ROOT = PROJECT_ROOT / "scripts"
if str(SCRIPTS_ROOT) not in sys.path:
    sys.path.insert(0, str(SCRIPTS_ROOT))

from common.ultralytics_config import configure_ultralytics_weights_dir  # type: ignore[import-not-found]

MODELS_DIR = PROJECT_ROOT / "models"
DEFAULT_MODEL = MODELS_DIR / "multibrand-best.pt"
DEFAULT_OUTPUT_DIR = PROJECT_ROOT / "outputs" / "predict"


def resolve_model_path(model_path: Path) -> Path:
    """解析模型路径，支持绝对路径、models/ 裸文件名和项目相对路径。"""
    if model_path.is_absolute():
        return model_path
    if model_path.parent == Path(".") and model_path.suffix == ".pt":
        return MODELS_DIR / model_path.name
    return PROJECT_ROOT / model_path


def validate_source(source: str) -> str:
    """验证输入图片来源，支持本地文件路径和 HTTP(S) URL。"""
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
    """推理入口。"""
    parser = argparse.ArgumentParser(description="识别并统计图片中的多品牌包装。")
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
        raise SystemExit(f"模型不存在：{args.model}\n请先完成标注和训练，或通过 --model 指向具体权重文件。")

    source = validate_source(args.source)
    model = YOLO(args.model)
    result = model.predict(source=source, conf=args.conf, imgsz=args.imgsz, verbose=False)[0]

    output_dir = args.output_dir.resolve()
    output_dir.mkdir(parents=True, exist_ok=True)
    source_name = Path(urlparse(source).path).stem or "prediction"
    annotated_path = output_dir / f"{source_name}-annotated.jpg"
    json_path = output_dir / f"{source_name}.json"

    detections = []
    brand_counts: dict[str, int] = {}
    for box in result.boxes:
        class_id = int(box.cls.item())
        class_name = result.names[class_id]
        x1, y1, x2, y2 = (round(float(value), 2) for value in box.xyxy[0].tolist())
        brand_counts[class_name] = brand_counts.get(class_name, 0) + 1
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
        "brand_counts": brand_counts,
        "total_count": len(detections),
        "detections": detections,
        "annotated_image": str(annotated_path),
    }
    json_path.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
    print(json.dumps(payload, ensure_ascii=False, indent=2))
    print(f"JSON 结果：{json_path}")


if __name__ == "__main__":
    main()
