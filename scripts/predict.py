"""
Softcare 纸尿裤检测推理脚本。

该脚本用于使用训练好的 YOLO 模型对图片进行推理，检测图片中的 Softcare 纸尿裤包装，支持：
- 本地图片路径或 HTTP(S) URL 输入
- 自定义置信度阈值和图片尺寸
- 输出标注图片和 JSON 格式的检测结果
"""

from __future__ import annotations

import argparse
import json
from pathlib import Path
from urllib.parse import urlparse

from ultralytics import YOLO

# 项目根目录
PROJECT_ROOT = Path(__file__).resolve().parents[1]
# 模型目录
MODELS_DIR = PROJECT_ROOT / "models"
# 默认模型路径（训练完成后的最佳模型）
DEFAULT_MODEL = MODELS_DIR / "softcare-best.pt"
# 默认输出目录
DEFAULT_OUTPUT_DIR = PROJECT_ROOT / "outputs" / "predict"
# 目标检测类别名称
TARGET_CLASS = "softcare_diaper"


def configure_ultralytics_weights_dir() -> None:
    """
    配置 Ultralytics 的权重文件目录。
    
    将 Ultralytics 默认的 weights_dir 重定向到项目本地的 models 目录，
    避免下载模型到全局目录。
    """
    import ultralytics.utils as ultralytics_utils
    from ultralytics.nn import text_model
    from ultralytics.utils import SETTINGS

    # 确保 models 目录存在
    MODELS_DIR.mkdir(parents=True, exist_ok=True)
    # 更新 Ultralytics 的全局设置和常量
    SETTINGS["weights_dir"] = str(MODELS_DIR)
    ultralytics_utils.WEIGHTS_DIR = MODELS_DIR
    text_model.WEIGHTS_DIR = MODELS_DIR


def resolve_model_path(model_path: Path) -> Path:
    """
    解析模型路径，支持相对路径和绝对路径。
    
    规则：
    - 绝对路径：直接返回
    - 仅文件名（如 model.pt）：解析为 models/model.pt
    - 其他相对路径：相对于项目根目录解析
    """
    if model_path.is_absolute():
        return model_path
    # 如果是简单的文件名，解析到 models 目录
    if model_path.parent == Path(".") and model_path.suffix == ".pt":
        return MODELS_DIR / model_path.name
    # 其他情况相对于项目根目录解析
    return PROJECT_ROOT / model_path


def validate_source(source: str) -> str:
    """
    验证输入图片来源，支持本地文件路径和 HTTP(S) URL。
    
    Args:
        source: 图片路径或 URL
    
    Returns:
        解析后的有效路径或原始 URL
    
    Raises:
        ValueError: URL 格式不正确
        FileNotFoundError: 本地文件不存在
    """
    parsed = urlparse(source)
    # 如果是 URL，验证协议和域名
    if parsed.scheme:
        if parsed.scheme not in {"http", "https"} or not parsed.netloc:
            raise ValueError("图片地址必须是本地文件路径或完整的 HTTP(S) URL。")
        return source

    # 如果是本地路径，验证文件存在
    path = Path(source)
    if not path.is_file():
        raise FileNotFoundError(f"图片不存在：{path}")
    return str(path.resolve())


def main() -> None:
    """推理脚本主入口：加载模型、执行推理、保存标注图片和 JSON 结果。"""
    parser = argparse.ArgumentParser(description="识别并统计图片中的 Softcare 纸尿裤包装。")
    parser.add_argument("source", help="本地图片路径或 HTTP(S) 图片 URL")
    parser.add_argument("--model", type=Path, default=DEFAULT_MODEL, help="训练完成的 best.pt 路径")
    parser.add_argument("--conf", type=float, default=0.35, help="最小置信度，范围 0 到 1")
    parser.add_argument("--imgsz", type=int, default=960, help="推理图片边长")
    parser.add_argument("--output-dir", type=Path, default=DEFAULT_OUTPUT_DIR, help="结果输出目录")
    args = parser.parse_args()

    # 配置 Ultralytics 权重目录
    configure_ultralytics_weights_dir()

    # 解析模型路径
    args.model = resolve_model_path(args.model)

    # 验证参数
    if not 0.0 <= args.conf <= 1.0:
        raise SystemExit("--conf 必须位于 0 到 1 之间。")
    if not args.model.is_file():
        raise SystemExit(
            f"Softcare 模型不存在：{args.model}\n"
            "请先完成标注和训练，再将 best.pt 复制到 models/softcare-best.pt，或通过 --model 指向具体权重文件。"
        )

    # 验证输入源并加载模型
    source = validate_source(args.source)
    model = YOLO(args.model)
    # 检查模型是否包含目标类别
    if TARGET_CLASS not in model.names.values():
        raise SystemExit(
            f"模型未包含类别 {TARGET_CLASS}，当前类别：{list(model.names.values())}\n"
            "请使用 Softcare 数据集训练生成的 best.pt。"
        )

    # 执行推理
    result = model.predict(source=source, conf=args.conf, imgsz=args.imgsz, verbose=False)[0]
    # 准备输出路径
    output_dir = args.output_dir.resolve()
    output_dir.mkdir(parents=True, exist_ok=True)
    source_name = Path(urlparse(source).path).stem or "prediction"
    annotated_path = output_dir / f"{source_name}-annotated.jpg"
    json_path = output_dir / f"{source_name}.json"

    # 解析检测结果，过滤目标类别
    detections = []
    for box in result.boxes:
        class_id = int(box.cls.item())
        class_name = result.names[class_id]
        # 只保留目标类别的检测框
        if class_name != TARGET_CLASS:
            continue
        # 提取边界框坐标 (xyxy 格式)
        x1, y1, x2, y2 = (round(float(value), 2) for value in box.xyxy[0].tolist())
        detections.append(
            {
                "class_id": class_id,
                "class_name": class_name,
                "confidence": round(float(box.conf.item()), 4),
                "xyxy": [x1, y1, x2, y2],
            }
        )

    # 保存标注图片
    result.save(filename=str(annotated_path))
    # 构建 JSON 结果
    payload = {
        "source": source,
        "model": str(args.model.resolve()),
        "softcare_count": len(detections),
        "detections": detections,
        "annotated_image": str(annotated_path),
    }
    # 保存 JSON 文件并打印结果
    json_path.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
    print(json.dumps(payload, ensure_ascii=False, indent=2))
    print(f"JSON 结果：{json_path}")


if __name__ == "__main__":
    main()
