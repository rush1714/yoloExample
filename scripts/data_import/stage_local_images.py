"""把本机图片目录沉淀到标准数据集 ``raw/images`` 目录。

通用标注流程允许用户从任意本地目录导入图片。为了让 Excel、本地目录、
S3 衔接训练都落到同一套数据集结构，本脚本会把本地源图片按相对路径
复制到 ``datasets/<COUNTRY>/<DATA_VERSION>/<DATASET>/raw/images``，并写出
本次沉淀清单，后续 Label Studio 导入只读取标准 raw 目录。
"""

# pylint: disable=line-too-long,duplicate-code

from __future__ import annotations

import argparse
import csv
import json
import shutil
from pathlib import Path

IMAGE_SUFFIXES = {".bmp", ".jpeg", ".jpg", ".png", ".tif", ".tiff", ".webp"}


def iter_image_files(input_dir: Path, recursive: bool) -> list[Path]:
    """扫描源目录中的图片，并按相对路径排序以保证重复执行顺序稳定。"""
    resolved_dir = input_dir.expanduser().resolve()
    pattern = "**/*" if recursive else "*"
    files = [
        path.resolve()
        for path in resolved_dir.glob(pattern)
        if path.is_file() and path.suffix.lower() in IMAGE_SUFFIXES
    ]
    return sorted(files, key=lambda item: item.relative_to(resolved_dir).as_posix().lower())


def copy_or_keep_image(source_path: Path, target_path: Path) -> str:
    """复制图片到目标路径；源和目标相同时只记录为已存在。"""
    target_path.parent.mkdir(parents=True, exist_ok=True)
    try:
        if target_path.exists() and source_path.samefile(target_path):
            return "already_in_raw"
    except FileNotFoundError:
        # samefile 在目标不存在时会抛错；这种情况按正常复制处理。
        pass
    if target_path.exists() and target_path.stat().st_size == source_path.stat().st_size:
        return "skipped_existing"
    shutil.copy2(source_path, target_path)
    return "copied"


def stage_images(input_dir: Path, output_dir: Path, recursive: bool, limit: int | None) -> list[dict[str, object]]:
    """执行图片沉淀并返回清单记录。"""
    resolved_input_dir = input_dir.expanduser().resolve()
    resolved_output_dir = output_dir.expanduser().resolve()
    if not resolved_input_dir.is_dir():
        raise SystemExit(f"本地源图片目录不存在：{resolved_input_dir}")
    image_paths = iter_image_files(resolved_input_dir, recursive)
    # 如果用户误把数据集根目录作为源目录，而 raw/images 又位于该目录内，
    # 需要排除已有 raw 输出目录，避免重复执行时生成 raw/images/raw/images 嵌套副本。
    if resolved_output_dir != resolved_input_dir and resolved_output_dir.is_relative_to(resolved_input_dir):
        image_paths = [path for path in image_paths if not path.is_relative_to(resolved_output_dir)]
    if not image_paths:
        supported = ", ".join(sorted(IMAGE_SUFFIXES))
        raise SystemExit(f"目录中没有支持的图片：{resolved_input_dir}；支持后缀：{supported}")
    selected_paths = image_paths[:limit] if limit is not None else image_paths
    records: list[dict[str, object]] = []
    for image_path in selected_paths:
        relative_path = image_path.relative_to(resolved_input_dir).as_posix()
        target_path = resolved_output_dir / relative_path
        status = copy_or_keep_image(image_path, target_path)
        records.append(
            {
                "source_path": str(image_path),
                "path": str(target_path),
                "relative_path": relative_path,
                "image_name": image_path.name,
                "size_bytes": target_path.stat().st_size,
                "status": status,
            }
        )
    return records


def write_manifest(records: list[dict[str, object]], report_json: Path) -> None:
    """写 JSON 和同名 CSV 清单，方便排查本地图片沉淀结果。"""
    report_json.parent.mkdir(parents=True, exist_ok=True)
    report_json.write_text(json.dumps({"items": records}, ensure_ascii=False, indent=2), encoding="utf-8")
    report_csv = report_json.with_suffix(".csv")
    with report_csv.open("w", encoding="utf-8", newline="") as file:
        writer = csv.DictWriter(
            file,
            fieldnames=["source_path", "path", "relative_path", "image_name", "size_bytes", "status"],
            extrasaction="ignore",
        )
        writer.writeheader()
        writer.writerows(records)


def positive_int(value: str) -> int:
    """解析正整数参数。"""
    parsed = int(value)
    if parsed <= 0:
        raise argparse.ArgumentTypeError("必须是大于 0 的整数")
    return parsed


def parse_args() -> argparse.Namespace:
    """解析命令行参数。"""
    parser = argparse.ArgumentParser(description="把本机图片目录沉淀到标准数据集 raw/images 目录。")
    parser.add_argument("--input-dir", type=Path, required=True, help="源图片目录")
    parser.add_argument("--output-dir", type=Path, required=True, help="标准 raw/images 输出目录")
    parser.add_argument("--report", type=Path, required=True, help="沉淀清单 JSON 输出路径")
    parser.add_argument("--limit", type=positive_int, default=None, help="最多沉淀前 N 张图片")
    parser.add_argument("--recursive", dest="recursive", action="store_true", default=True, help="递归扫描，默认开启")
    parser.add_argument("--no-recursive", dest="recursive", action="store_false", help="只扫描当前层")
    return parser.parse_args()


def main() -> None:
    """脚本入口。"""
    args = parse_args()
    records = stage_images(args.input_dir, args.output_dir, args.recursive, args.limit)
    write_manifest(records, args.report)
    copied_count = sum(1 for item in records if item["status"] == "copied")
    skipped_count = len(records) - copied_count
    print(f"本地图片标准 raw 目录：{args.output_dir.expanduser().resolve()}")
    print(f"本地图片沉淀清单：{args.report.expanduser().resolve()}")
    print(f"images={len(records)}, copied={copied_count}, skipped={skipped_count}")


if __name__ == "__main__":
    main()
