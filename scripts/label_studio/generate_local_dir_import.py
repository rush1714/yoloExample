"""Generate Label Studio import tasks from a local image directory.

This module is intentionally independent from the Excel download workflow. It is
used when images already exist on the local machine and should be sent directly
to Label Studio for manual single-class rectangle annotation.
"""

from __future__ import annotations

import argparse
import json
from html import escape
from pathlib import Path
from urllib.parse import quote

PROJECT_ROOT = Path(__file__).resolve().parents[2]
IMAGE_SUFFIXES = {".bmp", ".jpeg", ".jpg", ".png", ".tif", ".tiff", ".webp"}
DEFAULT_INPUT_DIR = PROJECT_ROOT / "data" / "local_import" / "images"
DEFAULT_OUTPUT = (
        PROJECT_ROOT
        / "datasets"
        / "dataset"
        / "label_studio"
        / "local_dir_label_studio_import.json"
)
DEFAULT_LABEL_CONFIG_OUTPUT = (
        PROJECT_ROOT / "datasets" / "dataset" / "label_studio" / "label_config.xml"
)


def label_config_xml(label_name: str) -> str:
    """Build a single-class rectangle Label Studio config.

    The value is escaped because users may pass labels containing characters that
    have meaning in XML. Label Studio still renders the original label text after
    XML parsing.
    """
    safe_label = escape(label_name, quote=True)
    return f"""
<View>
  <Image name="image" value="$image"/>
  <RectangleLabels name="bbox" toName="image">
    <Label value="{safe_label}" background="#1E90FF"/>
  </RectangleLabels>
  <Header value="文件：$image_name"/>
  <Text name="relative_path" value="$relative_path"/>
</View>
""".strip()


def iter_image_files(input_dir: Path, recursive: bool) -> list[Path]:
    """Return supported image files in a stable order.

    Stable ordering is useful because Label Studio task order and later YOLO
    train/val/test split should not change between repeated imports of the same
    directory.
    """
    pattern = "**/*" if recursive else "*"
    files = [
        path.resolve()
        for path in input_dir.glob(pattern)
        if path.is_file() and path.suffix.lower() in IMAGE_SUFFIXES
    ]
    resolved_input_dir = input_dir.resolve()
    return sorted(files, key=lambda item: str(item.relative_to(resolved_input_dir)).lower())


def build_tasks(
        input_dir: Path,
        image_paths: list[Path],
        dataset_name: str,
        limit: int | None,
) -> list[dict[str, object]]:
    """Build Label Studio tasks without predictions.

    The absolute local file URL enables Label Studio local-file serving, while
    `local_path` is kept for the later export-to-YOLO step to copy the original
    image into the training dataset.
    """
    tasks: list[dict[str, object]] = []
    resolved_input_dir = input_dir.resolve()
    selected_paths = image_paths[:limit] if limit is not None else image_paths
    for index, image_path in enumerate(selected_paths, start=1):
        relative_path = image_path.relative_to(resolved_input_dir).as_posix()
        tasks.append(
            {
                "data": {
                    "image": f"/data/local-files/?d={quote(str(image_path))}",
                    "local_path": str(image_path),
                    "image_name": image_path.name,
                    "relative_path": relative_path,
                    "row_number": str(index),
                    "source_url": "",
                },
                "meta": {
                    "source": "local-dir",
                    "dataset_name": dataset_name,
                    "image_name": image_path.name,
                    "relative_path": relative_path,
                    "has_pseudo_label": False,
                },
            }
        )
    return tasks


def positive_int(value: str) -> int:
    """Parse a positive integer argparse value."""
    parsed = int(value)
    if parsed <= 0:
        raise argparse.ArgumentTypeError("必须是大于 0 的整数")
    return parsed


def parse_args() -> argparse.Namespace:
    """Parse command-line arguments for local directory import generation."""
    parser = argparse.ArgumentParser(description="从本地图片目录生成 Label Studio 单类别导入 JSON。")
    parser.add_argument(
        "--input-dir",
        type=Path,
        default=DEFAULT_INPUT_DIR,
        help="本地图片目录",
    )
    parser.add_argument(
        "--output",
        type=Path,
        default=DEFAULT_OUTPUT,
        help="Label Studio 导入 JSON 输出路径",
    )
    parser.add_argument("--label-name", default="object", help="Label Studio 单类别标签名")
    parser.add_argument(
        "--label-config-output",
        type=Path,
        default=DEFAULT_LABEL_CONFIG_OUTPUT,
        help="Label Studio XML 标签配置输出路径",
    )
    parser.add_argument("--dataset-name", default="dataset", help="写入任务 meta 的数据集名称")
    parser.add_argument("--limit", type=positive_int, default=None, help="仅生成前 N 张图片任务")
    parser.add_argument(
        "--recursive",
        dest="recursive",
        action="store_true",
        default=True,
        help="递归扫描子目录，默认开启",
    )
    parser.add_argument(
        "--no-recursive",
        dest="recursive",
        action="store_false",
        help="只扫描当前目录，不递归子目录",
    )
    return parser.parse_args()


def main() -> None:
    """Generate import JSON and label config XML."""
    args = parse_args()
    input_dir = args.input_dir.expanduser().resolve()
    if not input_dir.is_dir():
        raise SystemExit(f"本地图片目录不存在：{input_dir}")

    image_paths = iter_image_files(input_dir, args.recursive)
    if not image_paths:
        supported = ", ".join(sorted(IMAGE_SUFFIXES))
        raise SystemExit(f"目录中没有支持的图片：{input_dir}；支持后缀：{supported}")

    tasks = build_tasks(input_dir, image_paths, args.dataset_name, args.limit)
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(tasks, ensure_ascii=False, indent=2), encoding="utf-8")

    if args.label_config_output is not None:
        args.label_config_output.parent.mkdir(parents=True, exist_ok=True)
        args.label_config_output.write_text(label_config_xml(args.label_name), encoding="utf-8")

    print(f"本地图片目录：{input_dir}")
    print(f"Label Studio 导入 JSON：{args.output}")
    print(f"Label Studio 标签配置：{args.label_config_output}")
    print(
        f"tasks={len(tasks)}, scanned_images={len(image_paths)}, "
        f"label={args.label_name}, recursive={args.recursive}"
    )


if __name__ == "__main__":
    main()
