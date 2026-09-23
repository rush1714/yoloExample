"""
YOLO 模型导出脚本。

支持将训练好的 YOLO 模型权重（如 best.pt）导出为各类目标格式，
特别针对手机移动端与边缘设备部署：
- iOS (iPhone / iPad): CoreML (支持 nms=True, half=True)
- Android: TFLite (支持 float32, int8, nms)
- 移动端极速推理: NCNN (.param, .bin)
- 通用跨平台: ONNX (支持 simplify, dynamic, nms)
- 服务端 GPU 加速: TensorRT (engine)
- 其他格式: OpenVINO, TorchScript 等
"""

from __future__ import annotations

import argparse
import shutil
import sys
from pathlib import Path
from typing import Any, Dict

from ultralytics import YOLO

PROJECT_ROOT = Path(__file__).resolve().parents[2]
SCRIPTS_ROOT = PROJECT_ROOT / "scripts"
if str(SCRIPTS_ROOT) not in sys.path:
    sys.path.insert(0, str(SCRIPTS_ROOT))

# pylint: disable=wrong-import-position
from common.ultralytics_config import (
    configure_ultralytics_weights_dir,
)

MODELS_DIR = PROJECT_ROOT / "models"
DEFAULT_MODEL = MODELS_DIR / "yolo26s.pt"


def resolve_model_path(model_path: Path) -> Path:
    """
    解析模型权重路径。

    支持：
    1. 绝对路径；
    2. models/ 下的裸文件名（如 yolo26s.pt）；
    3. 相对于项目根目录的相对路径。
    """
    if model_path.is_absolute():
        return model_path
    if model_path.parent == Path(".") and model_path.suffix == ".pt":
        candidate = MODELS_DIR / model_path.name
        if candidate.is_file():
            return candidate
    return (PROJECT_ROOT / model_path).resolve()


def resolve_output_dir(output_dir: Path | None) -> Path | None:
    """解析并创建目标输出目录。"""
    if output_dir is None:
        return None
    if output_dir.is_absolute():
        target = output_dir
    else:
        target = (PROJECT_ROOT / output_dir).resolve()
    target.mkdir(parents=True, exist_ok=True)
    return target


def parse_args() -> argparse.Namespace:
    """解析命令行参数。"""
    parser = argparse.ArgumentParser(
        description="导出 YOLO 模型至移动端（iOS CoreML / Android TFLite / NCNN）或通用 ONNX / TensorRT。"
    )
    parser.add_argument(
        "--model",
        "-m",
        type=Path,
        default=DEFAULT_MODEL,
        help="待导出的 YOLO 模型权重文件路径（.pt），支持相对路径或绝对路径（默认：models/yolo26s.pt）",
    )
    parser.add_argument(
        "--format",
        "-f",
        type=str,
        default="onnx",
        choices=[
            "coreml",
            "tflite",
            "ncnn",
            "onnx",
            "openvino",
            "engine",
            "torchscript",
            "saved_model",
            "pb",
            "paddle",
        ],
        help="目标格式：coreml(iOS首选), tflite(Android首选), ncnn(极速), onnx(通用), engine等",
    )
    parser.add_argument(
        "--imgsz",
        type=int,
        default=640,
        help="导出模型的输入分辨率边长（默认：640，手机端推荐 320、480 或 640）",
    )
    parser.add_argument(
        "--nms",
        action="store_true",
        default=False,
        help="是否将 NMS (非极大值抑制) 后处理集成进导出模型中（CoreML/ONNX 建议开启）",
    )
    parser.add_argument(
        "--half",
        action="store_true",
        default=False,
        help="是否使用 FP16 半精度导出（体积减半，加速 GPU/NPU 推理；iOS CoreML 推荐）",
    )
    parser.add_argument(
        "--int8",
        action="store_true",
        default=False,
        help="是否使用 INT8 量化（需配合 --data 指定校准数据集）",
    )
    parser.add_argument(
        "--data",
        type=str,
        default=None,
        help="INT8 量化校准时使用的数据集 YAML 路径",
    )
    parser.add_argument(
        "--device",
        type=str,
        default="cpu",
        help="导出运行设备，如 cpu, mps, cuda:0（默认：cpu）",
    )
    parser.add_argument(
        "--dynamic",
        action="store_true",
        default=False,
        help="是否启用动态输入尺寸（主要用于 ONNX）",
    )
    parser.add_argument(
        "--simplify",
        action="store_true",
        default=True,
        help="是否对 ONNX 模型使用 onnxsim 进行简化（默认开启）",
    )
    parser.add_argument(
        "--output-dir",
        "-o",
        type=Path,
        default=None,
        help="可选的目标输出目录。指定后会将导出的模型文件/目录移动或复制至该目录",
    )
    return parser.parse_args()


def print_platform_guidance(export_format: str, output_path: str) -> None:
    """输出对应平台的部署指引说明。"""
    print("\n" + "=" * 70)
    print("🎉 模型导出成功！产物位置：")
    print(f"   {output_path}")
    print("=" * 70)

    if export_format == "coreml":
        print("\n📱 【iOS (iPhone / iPad) 部署指引】")
        print("1. 将导出的 `.mlpackage` 目录直接拖入 Xcode 工程中；")
        print("2. Xcode 会自动生成 Swift 接口类；")
        print("3. 在 iOS 代码中使用 Vision 框架 (VNCoreMLRequest) 加载并对接摄像头实时视频流；")
        print("4. CoreML 会自动使用 Apple Neural Engine (NPU) 进行硬件加速。")
    elif export_format == "tflite":
        print("\n🤖 【Android (TFLite) 部署指引】")
        print("1. 将导出的 `.tflite` 文件拷贝至 Android 工程的 `app/src/main/assets/` 目录；")
        print("2. 使用 Android CameraX 捕获摄像头视频帧；")
        print("3. 使用 TensorFlow Lite Task Vision 或 Interpreter 进行推理并开启 GPU/NNAPI 加速；")
        print("4. 在自定义 View 上绘制检测框。")
    elif export_format == "ncnn":
        print("\n⚡ 【移动端极速推理 (NCNN) 部署指引】")
        print("1. 导出的目录中包含 `.param` (网络结构) 与 `.bin` (权重) 文件；")
        print("2. 可配合开源模板工程 (如 nihui/ncnn-android-yolo) 快速在 Android 端编译运行；")
        print("3. 适合追求极低延迟和对老旧机型兼容的场景。")
    elif export_format == "onnx":
        print("\n🌐 【通用跨平台 / Web 端 (ONNX) 部署指引】")
        print("1. 通用于 PC、服务端 (ONNXRuntime) 以及 Web 浏览器 (ONNX Runtime Web)；")
        print("2. Web 端可通过 H5 navigator.mediaDevices.getUserMedia 调用手机摄像头。")
    print("=" * 70 + "\n")


def build_export_kwargs(args: argparse.Namespace) -> Dict[str, Any]:
    """构建 Ultralytics export 参数字典。"""
    kwargs: Dict[str, Any] = {
        "format": args.format,
        "imgsz": args.imgsz,
        "device": args.device,
    }
    if args.nms:
        kwargs["nms"] = True
    if args.half:
        kwargs["half"] = True
    if args.int8:
        kwargs["int8"] = True
    if args.data:
        kwargs["data"] = args.data
    if args.format == "onnx":
        kwargs["dynamic"] = args.dynamic
        kwargs["simplify"] = args.simplify
    return kwargs


def relocate_artifact(exported_path: Path, output_dir: Path | None) -> Path:
    """若指定了 output-dir，将产物移动或复制到目标目录。"""
    target_out_dir = resolve_output_dir(output_dir)
    if not target_out_dir or target_out_dir == exported_path.parent:
        return exported_path

    dest_path = target_out_dir / exported_path.name
    print(f"正在将导出结果归档至目标目录: {dest_path} ...")
    if dest_path.exists():
        if dest_path.is_dir():
            shutil.rmtree(dest_path)
        else:
            dest_path.unlink()
    if exported_path.is_dir():
        shutil.copytree(exported_path, dest_path)
    else:
        shutil.copy2(exported_path, dest_path)
    return dest_path


def main() -> None:
    """导出主入口逻辑。"""
    args = parse_args()
    configure_ultralytics_weights_dir()

    model_path = resolve_model_path(args.model)
    if not model_path.is_file():
        print(f"❌ 错误：模型文件不存在：{model_path}", file=sys.stderr)
        sys.exit(1)

    print("=" * 70)
    print("🚀 开始导出 YOLO 模型...")
    print(f"📦 源模型路径: {model_path}")
    print(f"🎯 目标格式:   {args.format}")
    print(f"📐 输入尺寸:   {args.imgsz}")
    print(f"✂️  集成 NMS:   {'是' if args.nms else '否'}")
    print(f"⚡ 半精度FP16: {'是' if args.half else '否'}")
    print(f"💻 执行设备:   {args.device}")
    print("=" * 70)

    try:
        model = YOLO(str(model_path))
    except Exception as exc:  # pylint: disable=broad-except
        print(f"❌ 加载模型失败: {exc}", file=sys.stderr)
        sys.exit(1)

    export_kwargs = build_export_kwargs(args)
    try:
        exported_path_str = model.export(**export_kwargs)
    except Exception as exc:  # pylint: disable=broad-except
        print(f"\n❌ 模型导出失败: {exc}", file=sys.stderr)
        sys.exit(1)

    final_path = relocate_artifact(Path(exported_path_str).resolve(), args.output_dir)
    print_platform_guidance(args.format, str(final_path))


if __name__ == "__main__":
    main()
