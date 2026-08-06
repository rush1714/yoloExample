"""
YOLO-World 伪标注生成脚本。

该脚本使用 YOLO-World 模型对未标注的图片生成候选检测框，用于半自动标注流程：
- 支持开放词汇检测，通过文本提示词指定目标类别
- 将检测结果转换为 YOLO 格式的标签文件
- 自动划分训练集/验证集/测试集
- 生成详细的元数据报告（JSON 和 CSV）
- 生成的伪标注需要人工复核后再用于训练
"""

from __future__ import annotations

import argparse
import csv
import json
import shutil
from dataclasses import dataclass
from pathlib import Path

from PIL import Image
from ultralytics import YOLO

# 项目根目录
PROJECT_ROOT = Path(__file__).resolve().parents[1]
# 模型目录
MODELS_DIR = PROJECT_ROOT / "models"
# 默认原始图片目录（未标注）
DEFAULT_RAW_DIR = PROJECT_ROOT / "datasets" / "softcare" / "raw" / "images"
# 默认伪标注输出根目录
DEFAULT_OUTPUT_ROOT = PROJECT_ROOT / "datasets" / "softcare" / "pseudo"
# 默认 YOLO-World 模型路径
DEFAULT_MODEL = MODELS_DIR / "yolov8s-world.pt"
# 默认开放词汇提示词（用于检测纸尿裤包装）
DEFAULT_PROMPTS = [
    "diaper package",
    "baby diaper package",
    "softcare diaper package",
    "softcare",
]
# 支持的图片格式后缀
IMAGE_SUFFIXES = {".bmp", ".jpeg", ".jpg", ".png", ".tif", ".tiff", ".webp"}
# 数据集划分比例：训练集 70%，验证集 20%，测试集 10%
SPLIT_RATIOS = (0.7, 0.2, 0.1)


def configure_ultralytics_weights_dir() -> None:
    """
    配置 Ultralytics 的权重文件目录。
    
    将 Ultralytics 默认的 weights_dir 重定向到项目本地的 models 目录。
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


@dataclass(frozen=True)
class PseudoBox:
    """伪标注检测框数据类。"""
    prompt: str  # 触发该检测框的提示词
    confidence: float  # 检测置信度
    xyxy: list[float]  # 边界框坐标 [x1, y1, x2, y2]（像素值）
    yolo: list[float]  # YOLO 格式坐标 [center_x, center_y, width, height]（归一化值）


def list_images(raw_dir: Path, limit: int | None, candidates_file: Path | None = None) -> list[Path]:
    """
    获取待处理的图片列表。
    
    Args:
        raw_dir: 原始图片目录
        limit: 限制处理的图片数量（用于试跑）
        candidates_file: 候选图片清单文件（优先使用）
    
    Returns:
        图片路径列表
    
    Raises:
        FileNotFoundError: 候选清单文件不存在
    """
    if candidates_file is not None:
        # 从候选清单文件读取图片路径
        if not candidates_file.is_file():
            raise FileNotFoundError(f"候选清单不存在：{candidates_file}")
        images = [Path(line.strip()).resolve() for line in candidates_file.read_text(encoding="utf-8").splitlines() if line.strip()]
        images = [path for path in images if path.is_file() and path.suffix.lower() in IMAGE_SUFFIXES]
    else:
        # 递归查找目录中的所有图片
        images = sorted(path for path in raw_dir.rglob("*") if path.suffix.lower() in IMAGE_SUFFIXES)
    return images[:limit] if limit is not None else images


def split_name(index: int, total: int) -> str:
    """
    根据索引和总数确定图片所属的数据集分割。
    
    按照 SPLIT_RATIOS 比例划分：训练集 70%，验证集 20%，测试集 10%。
    
    Args:
        index: 图片索引（从 0 开始）
        total: 图片总数
    
    Returns:
        分割名称："train"、"val" 或 "test"
    """
    if total <= 1:
        return "train"
    # 计算各分割的切分点
    train_cutoff = int(total * SPLIT_RATIOS[0])
    val_cutoff = int(total * (SPLIT_RATIOS[0] + SPLIT_RATIOS[1]))
    if index < train_cutoff:
        return "train"
    if index < val_cutoff:
        return "val"
    return "test"


def to_yolo_xywh(xyxy: list[float], image_width: int, image_height: int) -> list[float]:
    """
    将边界框坐标从 xyxy 格式转换为 YOLO 格式的 xywh。
    
    Args:
        xyxy: 边界框坐标 [x1, y1, x2, y2]（像素值）
        image_width: 图片宽度
        image_height: 图片高度
    
    Returns:
        YOLO 格式坐标 [center_x, center_y, width, height]（归一化值）
    """
    x1, y1, x2, y2 = xyxy
    # 裁剪坐标到图片范围内
    x1 = max(0.0, min(float(image_width), x1))
    y1 = max(0.0, min(float(image_height), y1))
    x2 = max(0.0, min(float(image_width), x2))
    y2 = max(0.0, min(float(image_height), y2))
    # 计算宽度和高度
    width = max(0.0, x2 - x1)
    height = max(0.0, y2 - y1)
    # 计算中心点坐标
    center_x = x1 + width / 2
    center_y = y1 + height / 2
    # 返回归一化坐标
    return [
        center_x / image_width,
        center_y / image_height,
        width / image_width,
        height / image_height,
    ]


def predict_image(model: YOLO, image_path: Path, confidence: float, imgsz: int) -> list[PseudoBox]:
    """
    对单张图片执行 YOLO-World 推理。
    
    Args:
        model: YOLO-World 模型
        image_path: 图片路径
        confidence: 置信度阈值
        imgsz: 推理图片尺寸
    
    Returns:
        检测到的伪标注框列表
    """
    # 读取图片尺寸
    with Image.open(image_path) as image:
        image_width, image_height = image.size

    # 执行推理
    result = model.predict(source=str(image_path), conf=confidence, imgsz=imgsz, verbose=False)[0]
    boxes: list[PseudoBox] = []
    # 解析检测结果
    for box in result.boxes:
        class_id = int(box.cls.item())
        prompt = result.names[class_id]
        xyxy = [float(value) for value in box.xyxy[0].tolist()]
        # 转换为 YOLO 格式
        yolo = to_yolo_xywh(xyxy, image_width, image_height)
        # 过滤掉无效的框（宽度或高度为 0）
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
    """
    创建输出目录结构。
    
    目录结构：
    - output_root/images/{train,val,test}/
    - output_root/labels/{train,val,test}/
    - output_root/metadata/
    """
    # 创建各分割的图片和标签目录
    for split in ("train", "val", "test"):
        (output_root / "images" / split).mkdir(parents=True, exist_ok=True)
        (output_root / "labels" / split).mkdir(parents=True, exist_ok=True)
    # 创建元数据目录
    (output_root / "metadata").mkdir(parents=True, exist_ok=True)


def main() -> None:
    """伪标注生成脚本主入口。"""
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

    # 配置 Ultralytics 权重目录
    configure_ultralytics_weights_dir()

    # 解析模型路径
    args.model = resolve_model_path(args.model)

    # 验证参数
    if not args.raw_dir.is_dir():
        raise SystemExit(f"原图目录不存在：{args.raw_dir}")
    if not 0.0 <= args.conf <= 1.0:
        raise SystemExit("--conf 必须位于 0 到 1 之间。")

    # 获取待处理的图片列表
    prompts = args.prompts or DEFAULT_PROMPTS
    try:
        images = list_images(args.raw_dir, args.limit, args.candidates_file)
    except FileNotFoundError as exc:
        raise SystemExit(str(exc)) from exc
    if not images:
        source = f"候选清单 {args.candidates_file}" if args.candidates_file else f"原图目录 {args.raw_dir}"
        raise SystemExit(f"没有可处理的图片：{source}")

    # 准备输出目录
    prepare_output_dirs(args.output_root)
    # 加载 YOLO-World 模型并设置提示词
    model = YOLO(str(args.model))
    model.set_classes(prompts)

    # 逐张图片生成伪标注
    rows: list[dict[str, object]] = []
    for index, image_path in enumerate(images):
        # 确定数据集分割
        split = split_name(index, len(images))
        target_image = args.output_root / "images" / split / image_path.name
        target_label = args.output_root / "labels" / split / image_path.with_suffix(".txt").name
        # 复制图片到输出目录
        shutil.copy2(image_path, target_image)

        # 执行推理并生成伪标注
        boxes = predict_image(model, image_path, args.conf, args.imgsz)
        # 将检测结果转换为 YOLO 标签格式并写入文件
        label_lines = ["0 " + " ".join(f"{value:.6f}" for value in box.yolo) for box in boxes]
        target_label.write_text("\n".join(label_lines) + ("\n" if label_lines else ""), encoding="utf-8")
        # 记录元数据
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

    # 保存元数据报告（JSON 和 CSV）
    json_path = args.output_root / "metadata" / "pseudo_label_report.json"
    csv_path = args.output_root / "metadata" / "pseudo_label_report.csv"
    json_path.write_text(json.dumps(rows, ensure_ascii=False, indent=2), encoding="utf-8")
    with csv_path.open("w", encoding="utf-8", newline="") as file:
        writer = csv.DictWriter(file, fieldnames=["image", "label", "split", "box_count"])
        writer.writeheader()
        for row in rows:
            writer.writerow({key: row[key] for key in ["image", "label", "split", "box_count"]})

    # 打印统计信息
    print(f"完成：{len(images)} 张图片，候选框 {sum(int(row['box_count']) for row in rows)} 个。")
    print(f"伪标注目录：{args.output_root}")
    print("重要：请用 CVAT/Label Studio 打开并人工复核这些标签，再用于训练。")


if __name__ == "__main__":
    main()
