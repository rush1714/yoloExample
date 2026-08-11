"""
多品牌包装检测模型训练脚本。

该脚本用于训练 YOLO 多品牌包装检测模型，支持：
- 数据集校验（训练前自动验证数据集完整性）
- 自定义训练参数（轮数、图片尺寸、批大小等）
- 训练完成后自动复制最佳模型到指定位置
"""

from __future__ import annotations

import argparse
import sys
import shutil
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[2]
SCRIPTS_ROOT = PROJECT_ROOT / "scripts"
if str(SCRIPTS_ROOT) not in sys.path:
    sys.path.insert(0, str(SCRIPTS_ROOT))

from ultralytics import YOLO

from common.ultralytics_config import configure_ultralytics_weights_dir  # type: ignore[import-not-found]
from training.validate_dataset import validate_dataset  # type: ignore[import-not-found]

# 项目根目录（scripts/ 的上一级目录）
# 模型目录，用于存放预训练权重和训练输出
MODELS_DIR = PROJECT_ROOT / "models"
# 默认数据集配置文件路径
DEFAULT_DATASET_YAML = PROJECT_ROOT / "config" / "generated" / "multibrand.yaml"
# 训练输出根目录
DEFAULT_PROJECT = MODELS_DIR / "train"
# 默认预训练模型路径
DEFAULT_BASE_MODEL = MODELS_DIR / "yolo26s.pt"
# 训练完成后最佳模型的保存路径
DEFAULT_FINAL_MODEL = MODELS_DIR / "multibrand-best.pt"


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
    # 如果是简单的文件名（如 yolo26s.pt），解析到 models 目录
    if model_path.parent == Path(".") and model_path.suffix == ".pt":
        return MODELS_DIR / model_path.name
    # 其他情况相对于项目根目录解析
    return PROJECT_ROOT / model_path


def main() -> None:
    """训练脚本主入口：解析参数、校验数据集、执行训练、保存最佳模型。"""
    parser = argparse.ArgumentParser(description="训练多品牌包装检测模型。")
    parser.add_argument("--data", type=Path, default=DEFAULT_DATASET_YAML, help="数据集 YAML 路径")
    parser.add_argument("--base-model", type=Path, default=DEFAULT_BASE_MODEL, help="预训练 YOLO 权重；默认使用 models/yolo26s.pt")
    parser.add_argument("--epochs", type=int, default=100, help="训练轮数")
    parser.add_argument("--imgsz", type=int, default=960, help="训练图片边长")
    parser.add_argument("--batch", type=int, default=-1, help="批大小；-1 表示 Ultralytics 自动选择")
    parser.add_argument("--device", default=None, help="设备，例如 cpu、mps、0")
    parser.add_argument("--project", type=Path, default=DEFAULT_PROJECT, help="训练输出目录；默认 models/train")
    parser.add_argument("--name", default="multibrand", help="本次训练名称")
    parser.add_argument("--export-model", type=Path, default=DEFAULT_FINAL_MODEL, help="训练完成后复制 best.pt 到该路径；默认 models/multibrand-best.pt")
    parser.add_argument("--resume", action="store_true", help="从 project/name/weights/last.pt 恢复中断训练")
    args = parser.parse_args()

    # 配置 Ultralytics 权重目录
    configure_ultralytics_weights_dir()

    # 解析模型路径
    args.base_model = resolve_model_path(args.base_model)
    args.export_model = resolve_model_path(args.export_model)

    # 解析并验证数据集配置文件
    data_path = args.data.resolve()
    if not data_path.is_file():
        raise SystemExit(f"数据集 YAML 不存在：{data_path}")

    # 训练前校验数据集完整性
    errors = validate_dataset(data_path)
    if errors:
        raise SystemExit("训练取消，数据集校验失败：\n- " + "\n- ".join(errors))

    last_model = args.project / args.name / "weights" / "last.pt"
    if args.resume:
        if not last_model.is_file():
            raise SystemExit(f"无法恢复：找不到训练检查点：{last_model}")
        model = YOLO(str(last_model))
        model.train(resume=True)
    else:
        model = YOLO(str(args.base_model))
        train_args = {
            "data": str(data_path),
            "epochs": args.epochs,
            "imgsz": args.imgsz,
            "project": str(args.project),
            "name": args.name,
            "batch": args.batch,
        }
        if args.device is not None:
            train_args["device"] = args.device
        model.train(**train_args)

    # 训练完成后，复制最佳模型到指定位置
    best_model = args.project / args.name / "weights" / "best.pt"
    if best_model.is_file() and args.export_model:
        args.export_model.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(best_model, args.export_model)
        print(f"训练完成。推理模型：{args.export_model}")
        print(f"训练原始权重：{best_model}")
    else:
        print(f"训练完成。推理模型：{best_model}")


if __name__ == "__main__":
    main()
