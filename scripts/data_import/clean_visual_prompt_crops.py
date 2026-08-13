"""
清洗 YOLOE visual prompt 品牌参考包装图。

该脚本用于把品牌参考图目录中的商品包装图统一转换为“紧凑、干净、白底”的
单包装 crop，降低透明背景、镜面倒影和过大留白对 YOLOE visual prompt 的干扰。
默认会把原图备份到项目内 `.tmp/visual_prompt_backups/`，再原地覆盖目标目录。
"""

from __future__ import annotations

import argparse
import csv
import shutil
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path

import cv2
import numpy as np
from PIL import Image

# OpenCV 的 Python 扩展成员由运行时动态注入，pylint 无法静态识别。
# pylint: disable=no-member

PROJECT_ROOT = Path(__file__).resolve().parents[2]
DEFAULT_SOFTCARE_DIR = PROJECT_ROOT / "datasets" / "multibrand" / "visual_prompts" / "softcare"
DEFAULT_BACKUP_ROOT = PROJECT_ROOT / ".tmp" / "visual_prompt_backups"
IMAGE_SUFFIXES = {".jpg", ".jpeg", ".png", ".webp", ".bmp"}

# Softcare 原始参考图中，部分电商产品图底部带镜面倒影。
# 这里以文件名显式记录倒影裁切下边界，避免自动阈值误裁白色包装主体。
SOFTCARE_REFLECTION_BOTTOM_CUTS: dict[str, int] = {
    "row00013_01_Z-1.png": 1225,
    "row00014_01_Z-1.png": 1365,
    "row00015_01_Z-1.png": 1118,
    "row00019_01_Z-1.png": 590,
    "row00021_01_Z-1.png": 1578,
    "row00023_01_Z-1.png": 550,
    "row00025_01_Z-1.png": 508,
    "row00026_01_Z-1.png": 505,
    "row00027_01_Z-1.png": 560,
    "row00029_01_Z-1.png": 610,
    "row00032_01_Z-1.png": 1190,
    "row00039_01_Z-1.png": 675,
    "row00040_01_Z-1.png": 550,
}


@dataclass(frozen=True)
class CropResult:  # pylint: disable=too-many-instance-attributes
    """记录单张参考图清洗前后的关键尺寸与裁切信息。"""

    image_name: str
    original_width: int
    original_height: int
    output_width: int
    output_height: int
    content_box: tuple[int, int, int, int]
    reflection_cut_y: int | None
    backup_path: Path | None
    output_path: Path


def parse_args() -> argparse.Namespace:
    """解析命令行参数。"""
    parser = argparse.ArgumentParser(description="清洗 visual prompt 参考图为紧凑白底 crop。")
    parser.add_argument(
        "--source-dir",
        type=Path,
        default=DEFAULT_SOFTCARE_DIR,
        help="待清洗的品牌参考图目录，默认是 Softcare visual prompt 目录。",
    )
    parser.add_argument(
        "--output-dir",
        type=Path,
        default=None,
        help="输出目录；不传则原地覆盖 source-dir。",
    )
    parser.add_argument(
        "--backup-root",
        type=Path,
        default=DEFAULT_BACKUP_ROOT,
        help="原地覆盖时的原图备份根目录。",
    )
    parser.add_argument(
        "--margin-ratio",
        type=float,
        default=0.015,
        help="最终白底留边比例，按裁切后最长边计算。",
    )
    parser.add_argument(
        "--trim-padding-ratio",
        type=float,
        default=0.025,
        help="内容检测框向外扩展比例，防止商品边缘被裁掉。",
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="只输出将要处理的文件，不写入清洗结果。",
    )
    return parser.parse_args()


def list_images(source_dir: Path) -> list[Path]:
    """按文件名排序列出目录中的图片文件。"""
    return sorted(
        path
        for path in source_dir.iterdir()
        if path.is_file() and path.suffix.lower() in IMAGE_SUFFIXES
    )


def composite_on_white(image: Image.Image) -> Image.Image:
    """把透明或半透明背景合成到白底，避免预览和模型读取时出现黑底。"""
    rgba_image = image.convert("RGBA")
    white_canvas = Image.new("RGBA", rgba_image.size, (255, 255, 255, 255))
    white_canvas.alpha_composite(rgba_image)
    return white_canvas.convert("RGB")


def find_content_box(rgb_image: Image.Image) -> tuple[int, int, int, int]:
    """检测非纯白内容区域，返回适合进一步扩展的 xyxy 裁切框。

    参考图大多是白底商品照，且商品主体也可能包含大片白色包装。
    因此这里仅用较低阈值识别“不同于白底”的像素，并用轻微膨胀连接阴影、文字、
    包装边缘等弱信号；最终还会在调用方额外向外扩展，避免裁掉白色包装边缘。
    """
    pixel_array = np.asarray(rgb_image)
    # 使用离白色最远的通道差值作为“非背景”强度。
    white_delta = np.abs(pixel_array.astype(np.int16) - 255).max(axis=2)
    foreground_mask = white_delta > 4

    # 忽略极外侧一像素，避免下载图中的细边框或编码噪声撑大裁切框。
    if foreground_mask.shape[0] > 2 and foreground_mask.shape[1] > 2:
        foreground_mask[:1, :] = False
        foreground_mask[-1:, :] = False
        foreground_mask[:, :1] = False
        foreground_mask[:, -1:] = False

    # 膨胀一次把相邻弱边缘连接成连续主体，便于得到稳定外接框。
    kernel = np.ones((5, 5), dtype=np.uint8)
    foreground_mask = cv2.dilate(foreground_mask.astype(np.uint8), kernel, iterations=1) > 0
    y_indices, x_indices = np.where(foreground_mask)
    if len(x_indices) == 0 or len(y_indices) == 0:
        return (0, 0, rgb_image.width, rgb_image.height)

    return (
        int(x_indices.min()),
        int(y_indices.min()),
        int(x_indices.max() + 1),
        int(y_indices.max() + 1),
    )


def expand_box(
    box: tuple[int, int, int, int],
    image_size: tuple[int, int],
    padding_ratio: float,
) -> tuple[int, int, int, int]:
    """把内容框按比例外扩，并限制在图片边界内。"""
    image_width, image_height = image_size
    left, top, right, bottom = box
    box_width = right - left
    box_height = bottom - top
    padding = max(8, round(max(box_width, box_height) * padding_ratio))
    return (
        max(0, left - padding),
        max(0, top - padding),
        min(image_width, right + padding),
        min(image_height, bottom + padding),
    )


def add_white_margin(rgb_image: Image.Image, margin_ratio: float) -> Image.Image:
    """给最终 crop 增加很小的白边，避免 visual prompt 贴边导致缩放插值截断。"""
    margin = max(6, round(max(rgb_image.size) * margin_ratio))
    output_size = (
        rgb_image.width + 2 * margin,
        rgb_image.height + 2 * margin,
    )
    output = Image.new("RGB", output_size, "white")
    output.paste(rgb_image, (margin, margin))
    return output


def clean_one_image(
    image_path: Path,
    output_path: Path,
    margin_ratio: float,
    trim_padding_ratio: float,
) -> CropResult:
    """清洗单张商品参考图并写入输出路径。"""
    with Image.open(image_path) as source_image:
        rgb_image = composite_on_white(source_image)

    original_width, original_height = rgb_image.size
    reflection_cut_y = SOFTCARE_REFLECTION_BOTTOM_CUTS.get(image_path.name)
    if reflection_cut_y is not None:
        # 底部倒影只用于视觉展示，不应进入 YOLOE 的“单包装”参考框。
        safe_cut_y = max(1, min(reflection_cut_y, rgb_image.height))
        rgb_image = rgb_image.crop((0, 0, rgb_image.width, safe_cut_y))

    content_box = find_content_box(rgb_image)
    crop_box = expand_box(content_box, rgb_image.size, trim_padding_ratio)
    cropped_image = rgb_image.crop(crop_box)
    final_image = add_white_margin(cropped_image, margin_ratio)

    output_path.parent.mkdir(parents=True, exist_ok=True)
    final_image.save(output_path, optimize=True)
    return CropResult(
        image_name=image_path.name,
        original_width=original_width,
        original_height=original_height,
        output_width=final_image.width,
        output_height=final_image.height,
        content_box=crop_box,
        reflection_cut_y=reflection_cut_y,
        backup_path=None,
        output_path=output_path,
    )


def create_backup_dir(source_dir: Path, backup_root: Path) -> Path:
    """创建带时间戳的备份目录，目录名包含品牌目录名以便追溯。"""
    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    return backup_root / f"{source_dir.name}_{timestamp}"


def write_manifest(results: list[CropResult], manifest_path: Path) -> None:
    """写出清洗清单，记录每张图的备份、输出尺寸与裁切参数。"""
    manifest_path.parent.mkdir(parents=True, exist_ok=True)
    with manifest_path.open("w", newline="", encoding="utf-8") as file_obj:
        writer = csv.DictWriter(
            file_obj,
            fieldnames=[
                "image_name",
                "original_width",
                "original_height",
                "output_width",
                "output_height",
                "content_box_xyxy",
                "reflection_cut_y",
                "backup_path",
                "output_path",
            ],
        )
        writer.writeheader()
        for result in results:
            writer.writerow(
                {
                    "image_name": result.image_name,
                    "original_width": result.original_width,
                    "original_height": result.original_height,
                    "output_width": result.output_width,
                    "output_height": result.output_height,
                    "content_box_xyxy": list(result.content_box),
                    "reflection_cut_y": result.reflection_cut_y or "",
                    "backup_path": str(result.backup_path) if result.backup_path else "",
                    "output_path": str(result.output_path),
                }
            )


def clean_directory(args: argparse.Namespace) -> list[CropResult]:
    """批量清洗目录中的参考图。"""
    source_dir = args.source_dir.resolve()
    output_dir = (args.output_dir or args.source_dir).resolve()
    images = list_images(source_dir)
    if not images:
        raise FileNotFoundError(f"未在 {source_dir} 找到可处理图片。")

    inplace = source_dir == output_dir
    backup_dir: Path | None = None
    if inplace and not args.dry_run:
        backup_dir = create_backup_dir(source_dir, args.backup_root.resolve())
        backup_dir.mkdir(parents=True, exist_ok=True)

    results: list[CropResult] = []
    for image_path in images:
        output_path = output_dir / image_path.name
        backup_path: Path | None = None
        if backup_dir is not None:
            backup_path = backup_dir / image_path.name
            shutil.copy2(image_path, backup_path)

        if args.dry_run:
            print(f"dry-run: 将处理 {image_path} -> {output_path}")
            continue

        result = clean_one_image(
            image_path=image_path,
            output_path=output_path,
            margin_ratio=args.margin_ratio,
            trim_padding_ratio=args.trim_padding_ratio,
        )
        results.append(
            CropResult(
                image_name=result.image_name,
                original_width=result.original_width,
                original_height=result.original_height,
                output_width=result.output_width,
                output_height=result.output_height,
                content_box=result.content_box,
                reflection_cut_y=result.reflection_cut_y,
                backup_path=backup_path,
                output_path=result.output_path,
            )
        )
        print(
            f"已清洗 {image_path.name}: "
            f"{result.original_width}x{result.original_height} -> "
            f"{result.output_width}x{result.output_height}"
        )

    if not args.dry_run:
        manifest_dir = args.backup_root.resolve() / "metadata"
        manifest_path = manifest_dir / f"{source_dir.name}_clean_manifest.csv"
        write_manifest(results, manifest_path)
        print(f"清洗清单：{manifest_path}")
        if backup_dir is not None:
            print(f"原图备份：{backup_dir}")
    return results


def main() -> None:
    """脚本入口。"""
    clean_directory(parse_args())


if __name__ == "__main__":
    main()
