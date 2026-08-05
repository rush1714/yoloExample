from __future__ import annotations

import argparse
import shutil
from pathlib import Path

from ultralytics import YOLO

from validate_dataset import validate_dataset

PROJECT_ROOT = Path(__file__).resolve().parents[1]
MODELS_DIR = PROJECT_ROOT / "models"
DEFAULT_DATASET_YAML = PROJECT_ROOT / "data" / "softcare.yaml"
DEFAULT_PROJECT = MODELS_DIR / "train"
DEFAULT_BASE_MODEL = MODELS_DIR / "yolo26s.pt"
DEFAULT_FINAL_MODEL = MODELS_DIR / "softcare-best.pt"


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


def main() -> None:
    parser = argparse.ArgumentParser(description="训练 Softcare 纸尿裤检测模型。")
    parser.add_argument("--data", type=Path, default=DEFAULT_DATASET_YAML, help="数据集 YAML 路径")
    parser.add_argument("--base-model", type=Path, default=DEFAULT_BASE_MODEL, help="预训练 YOLO 权重；默认使用 models/yolo26s.pt")
    parser.add_argument("--epochs", type=int, default=100, help="训练轮数")
    parser.add_argument("--imgsz", type=int, default=960, help="训练图片边长")
    parser.add_argument("--batch", type=int, default=-1, help="批大小；-1 表示 Ultralytics 自动选择")
    parser.add_argument("--device", default=None, help="设备，例如 cpu、mps、0")
    parser.add_argument("--project", type=Path, default=DEFAULT_PROJECT, help="训练输出目录；默认 models/train")
    parser.add_argument("--name", default="softcare", help="本次训练名称")
    parser.add_argument("--export-model", type=Path, default=DEFAULT_FINAL_MODEL, help="训练完成后复制 best.pt 到该路径；默认 models/softcare-best.pt")
    args = parser.parse_args()

    configure_ultralytics_weights_dir()

    args.base_model = resolve_model_path(args.base_model)
    args.export_model = resolve_model_path(args.export_model)

    data_path = args.data.resolve()
    if not data_path.is_file():
        raise SystemExit(f"数据集 YAML 不存在：{data_path}")

    errors = validate_dataset(data_path)
    if errors:
        raise SystemExit("训练取消，数据集校验失败：\n- " + "\n- ".join(errors))

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
