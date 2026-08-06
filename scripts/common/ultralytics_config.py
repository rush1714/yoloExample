"""Ultralytics YOLO 框架配置工具。"""

from __future__ import annotations

from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[2]
MODELS_DIR = PROJECT_ROOT / "models"


def configure_ultralytics_weights_dir(models_dir: Path | None = None) -> None:
    """
    配置 Ultralytics 权重目录到项目本地 models/。

    将 Ultralytics 的默认权重目录从 ``~/.config/Ultralytics/downloads`` 重定向到
    项目内部的 ``models/`` 目录，确保训练/推理时下载的权重存放在项目范围内。

    Args:
        models_dir: 自定义权重目录，默认使用项目根目录下的 ``models/``。
    """
    import ultralytics.utils as ultralytics_utils
    from ultralytics.nn import text_model
    from ultralytics.utils import SETTINGS

    target_dir = models_dir or MODELS_DIR
    target_dir.mkdir(parents=True, exist_ok=True)
    SETTINGS["weights_dir"] = str(target_dir)
    ultralytics_utils.WEIGHTS_DIR = target_dir
    text_model.WEIGHTS_DIR = target_dir
