"""
Label Studio 多品牌导入 JSON 生成脚本。

该脚本生成 Label Studio 导入所需的 JSON 文件：
- 从 Excel 下载报告读取本地图片。
- 将 YOLO-World 多品牌伪标注转换为 Label Studio predictions。
- 使用品牌库生成类别映射。
- 使用本地文件服务路径，避免远程 CDN CORS 问题。
"""

from __future__ import annotations

import argparse
import sys
import csv
import json
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[2]
SCRIPTS_ROOT = PROJECT_ROOT / "scripts"
if str(SCRIPTS_ROOT) not in sys.path:
    sys.path.insert(0, str(SCRIPTS_ROOT))
from urllib.parse import quote
from uuid import uuid4

from common.brand_library import DEFAULT_BRAND_LIBRARY, class_id_map, label_config_xml, load_brand_classes
from PIL import Image

DEFAULT_RAW_REPORT = PROJECT_ROOT / "datasets" / "multibrand" / "raw" / "metadata" / "download_report.csv"
DEFAULT_PSEUDO_ROOT = PROJECT_ROOT / "datasets" / "multibrand" / "pseudo"
DEFAULT_OUTPUT = PROJECT_ROOT / "datasets" / "multibrand" / "label_studio" / "multibrand_label_studio_import.json"
IMAGE_SUFFIXES = {".bmp", ".jpeg", ".jpg", ".png", ".tif", ".tiff", ".webp"}


def load_raw_records(report_path: Path) -> dict[str, dict[str, str]]:
    """从下载报告 CSV 中加载可导入的本地图片记录。"""
    records: dict[str, dict[str, str]] = {}
    with report_path.open(encoding="utf-8") as file:
        for row in csv.DictReader(file):
            # downloaded 表示本次新下载，skipped 表示图片已在本地存在；两者都有本地 path。
            if row.get("status") not in {"downloaded", "skipped"} or not row.get("path"):
                continue
            path = Path(row["path"]).resolve()
            if not path.is_file() or path.suffix.lower() not in IMAGE_SUFFIXES:
                continue
            local_file_url = f"/data/local-files/?d={quote(str(path))}"
            records[path.name] = {
                "image": local_file_url,
                "source_url": row["url"],
                "local_path": str(path),
                "row_number": row.get("row_number", ""),
            }
    return records


def label_path_for_image(image_name: str, pseudo_root: Path) -> Path | None:
    """查找图片对应的伪标注标签文件。"""
    stem = Path(image_name).stem
    for split in ("train", "val", "test"):
        label_path = pseudo_root / "labels" / split / f"{stem}.txt"
        if label_path.is_file():
            return label_path
    return None


def image_size(local_path: str) -> tuple[int, int]:
    """获取图片尺寸。"""
    with Image.open(local_path) as image:
        return image.size


def yolo_line_to_label_studio(
    line: str,
    width: int,
    height: int,
    id_to_brand: dict[int, object],
) -> dict[str, object] | None:
    """将多类别 YOLO 标签行转换为 Label Studio rectanglelabels 结果。"""
    values = line.split()
    if len(values) != 5:
        return None
    try:
        class_id = int(values[0])
        cx, cy, bw, bh = map(float, values[1:])
    except ValueError:
        return None
    brand = id_to_brand.get(class_id)
    if brand is None:
        return None

    x = max(0.0, min(100.0, (cx - bw / 2) * 100))
    y = max(0.0, min(100.0, (cy - bh / 2) * 100))
    w = max(0.0, min(100.0 - x, bw * 100))
    h = max(0.0, min(100.0 - y, bh * 100))
    if w <= 0 or h <= 0:
        return None
    return {
        "id": uuid4().hex[:10],
        "from_name": "bbox",
        "to_name": "image",
        "type": "rectanglelabels",
        "original_width": width,
        "original_height": height,
        "image_rotation": 0,
        "value": {
            "x": round(x, 6),
            "y": round(y, 6),
            "width": round(w, 6),
            "height": round(h, 6),
            "rotation": 0,
            "rectanglelabels": [brand.display_name],
        },
    }


def load_prediction_results(
    image_name: str,
    local_path: str,
    pseudo_root: Path,
    id_to_brand: dict[int, object],
) -> list[dict[str, object]]:
    """加载图片伪标注并转换为 Label Studio predictions。"""
    label_path = label_path_for_image(image_name, pseudo_root)
    if label_path is None:
        return []
    width, height = image_size(local_path)
    results = []
    for line in label_path.read_text(encoding="utf-8").splitlines():
        if not line.strip():
            continue
        result = yolo_line_to_label_studio(line, width, height, id_to_brand)
        if result is not None:
            results.append(result)
    return results


def build_tasks(
    raw_report: Path,
    pseudo_root: Path,
    id_to_brand: dict[int, object],
    limit: int | None,
) -> list[dict[str, object]]:
    """构建 Label Studio 导入任务列表。"""
    records = load_raw_records(raw_report)
    tasks: list[dict[str, object]] = []
    for image_name in sorted(records):
        record = records[image_name]
        predictions = load_prediction_results(image_name, record["local_path"], pseudo_root, id_to_brand)
        task: dict[str, object] = {
            "data": {
                "image": record["image"],
                "source_url": record["source_url"],
                "local_path": record["local_path"],
                "row_number": record["row_number"],
            },
            "meta": {
                "source": "softcare-yolo-demo",
                "image_name": image_name,
                "has_pseudo_label": bool(label_path_for_image(image_name, pseudo_root)),
            },
        }
        if predictions:
            task["predictions"] = [
                {
                    "model_version": "yolo-world-multibrand-pseudo-label",
                    "score": 0.5,
                    "result": predictions,
                }
            ]
        tasks.append(task)
        if limit is not None and len(tasks) >= limit:
            break
    return tasks


def write_import_file(tasks: list[dict[str, object]], output_path: Path) -> None:
    """将任务列表写入 JSON。"""
    output_path.parent.mkdir(parents=True, exist_ok=True)
    output_path.write_text(json.dumps(tasks, ensure_ascii=False, indent=2), encoding="utf-8")


def main() -> None:
    """命令行入口。"""
    parser = argparse.ArgumentParser(description="生成 Label Studio 多品牌图片检测任务导入 JSON。")
    parser.add_argument("--raw-report", type=Path, default=DEFAULT_RAW_REPORT, help="Excel 图片下载报告 CSV")
    parser.add_argument("--pseudo-root", type=Path, default=DEFAULT_PSEUDO_ROOT, help="YOLO 伪标注数据根目录")
    parser.add_argument("--output", type=Path, default=DEFAULT_OUTPUT, help="Label Studio 导入 JSON 输出路径")
    parser.add_argument("--brand-library", type=Path, default=DEFAULT_BRAND_LIBRARY, help="品牌标识库 JSON/TXT")
    parser.add_argument("--label-config-output", type=Path, default=None, help="可选：输出 Label Studio XML 标签配置")
    parser.add_argument("--limit", type=int, default=None, help="仅生成前 N 个任务，便于试跑")
    args = parser.parse_args()

    brand_classes = load_brand_classes(args.brand_library)
    id_to_brand = class_id_map(brand_classes)
    tasks = build_tasks(args.raw_report, args.pseudo_root, id_to_brand, args.limit)
    write_import_file(tasks, args.output)
    if args.label_config_output is not None:
        args.label_config_output.parent.mkdir(parents=True, exist_ok=True)
        args.label_config_output.write_text(label_config_xml(brand_classes), encoding="utf-8")

    prediction_tasks = sum(1 for task in tasks if task.get("predictions"))
    prediction_boxes = sum(len(prediction["result"]) for task in tasks for prediction in task.get("predictions", []))
    print(f"品牌类别数：{len(brand_classes)}")
    print(f"Label Studio 导入 JSON：{args.output}")
    print(f"tasks={len(tasks)}, tasks_with_predictions={prediction_tasks}, prediction_boxes={prediction_boxes}")


if __name__ == "__main__":
    main()
