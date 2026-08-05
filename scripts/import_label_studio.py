from __future__ import annotations

import argparse
import csv
import json
from pathlib import Path
from uuid import uuid4

from PIL import Image

PROJECT_ROOT = Path(__file__).resolve().parents[1]
DEFAULT_RAW_REPORT = PROJECT_ROOT / "datasets" / "softcare" / "raw" / "metadata" / "download_report.csv"
DEFAULT_PSEUDO_ROOT = PROJECT_ROOT / "datasets" / "softcare" / "pseudo"
DEFAULT_OUTPUT = PROJECT_ROOT / "datasets" / "softcare" / "label_studio" / "softcare_label_studio_import.json"
DEFAULT_LABEL = "softcare_diaper"
LABEL_CONFIG = """
<View>
  <Image name="image" value="$image"/>
  <RectangleLabels name="bbox" toName="image">
    <Label value="softcare_diaper" background="#FFA500"/>
  </RectangleLabels>
  <Header value="来源行：$row_number"/>
  <Text name="source_url" value="$source_url"/>
</View>
""".strip()

IMAGE_SUFFIXES = {".bmp", ".jpeg", ".jpg", ".png", ".tif", ".tiff", ".webp"}


def load_raw_records(report_path: Path) -> dict[str, dict[str, str]]:
    records: dict[str, dict[str, str]] = {}
    with report_path.open(encoding="utf-8") as file:
        for row in csv.DictReader(file):
            if row.get("status") != "downloaded" or not row.get("path"):
                continue
            path = Path(row["path"]).resolve()
            records[path.name] = {
                "image": row["url"],
                "source_url": row["url"],
                "local_path": str(path),
                "row_number": row.get("row_number", ""),
            }
    return records


def label_path_for_image(image_name: str, pseudo_root: Path) -> Path | None:
    stem = Path(image_name).stem
    for split in ("train", "val", "test"):
        label_path = pseudo_root / "labels" / split / f"{stem}.txt"
        if label_path.is_file():
            return label_path
    return None


def image_size(local_path: str) -> tuple[int, int]:
    with Image.open(local_path) as image:
        return image.size


def yolo_line_to_label_studio(line: str, width: int, height: int, label: str) -> dict[str, object] | None:
    values = line.split()
    if len(values) != 5:
        return None
    class_id, center_x, center_y, box_width, box_height = values
    if class_id != "0":
        return None
    cx, cy, bw, bh = map(float, [center_x, center_y, box_width, box_height])
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
            "rectanglelabels": [label],
        },
    }


def load_prediction_results(image_name: str, local_path: str, pseudo_root: Path, label: str) -> list[dict[str, object]]:
    label_path = label_path_for_image(image_name, pseudo_root)
    if label_path is None:
        return []
    width, height = image_size(local_path)
    results = []
    for line in label_path.read_text(encoding="utf-8").splitlines():
        if not line.strip():
            continue
        result = yolo_line_to_label_studio(line, width, height, label)
        if result is not None:
            results.append(result)
    return results


def build_tasks(raw_report: Path, pseudo_root: Path, label: str, limit: int | None) -> list[dict[str, object]]:
    records = load_raw_records(raw_report)
    tasks: list[dict[str, object]] = []
    for image_name in sorted(records):
        record = records[image_name]
        predictions = load_prediction_results(image_name, record["local_path"], pseudo_root, label)
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
                    "model_version": "yolo-world-pseudo-label",
                    "score": 0.5,
                    "result": predictions,
                }
            ]
        tasks.append(task)
        if limit is not None and len(tasks) >= limit:
            break
    return tasks


def write_import_file(tasks: list[dict[str, object]], output_path: Path) -> None:
    output_path.parent.mkdir(parents=True, exist_ok=True)
    output_path.write_text(json.dumps(tasks, ensure_ascii=False, indent=2), encoding="utf-8")


def main() -> None:
    parser = argparse.ArgumentParser(description="生成 Label Studio 图片检测任务导入 JSON。")
    parser.add_argument("--raw-report", type=Path, default=DEFAULT_RAW_REPORT, help="Excel 图片下载报告 CSV")
    parser.add_argument("--pseudo-root", type=Path, default=DEFAULT_PSEUDO_ROOT, help="YOLO 伪标注数据根目录")
    parser.add_argument("--output", type=Path, default=DEFAULT_OUTPUT, help="Label Studio 导入 JSON 输出路径")
    parser.add_argument("--label", default=DEFAULT_LABEL, help="Label Studio 矩形框标签名")
    parser.add_argument("--limit", type=int, default=None, help="仅生成前 N 个任务，便于试跑")
    args = parser.parse_args()

    tasks = build_tasks(args.raw_report, args.pseudo_root, args.label, args.limit)
    write_import_file(tasks, args.output)
    prediction_tasks = sum(1 for task in tasks if task.get("predictions"))
    prediction_boxes = sum(
        len(prediction["result"])
        for task in tasks
        for prediction in task.get("predictions", [])
    )
    print(f"Label Studio 导入 JSON：{args.output}")
    print(f"tasks={len(tasks)}, tasks_with_predictions={prediction_tasks}, prediction_boxes={prediction_boxes}")


if __name__ == "__main__":
    main()
