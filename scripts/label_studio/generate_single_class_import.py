"""生成单类别 Label Studio 导入 JSON，不包含任何预标注。"""

from __future__ import annotations

import argparse
import csv
import json
from pathlib import Path
from urllib.parse import quote

PROJECT_ROOT = Path(__file__).resolve().parents[2]
DEFAULT_RAW_REPORT = PROJECT_ROOT / "datasets" / "diaper_category" / "default" / "v1" / "raw" / "metadata" / "download_report.csv"
DEFAULT_OUTPUT = PROJECT_ROOT / "datasets" / "diaper_category" / "default" / "v1" / "label_studio" / "diaper_category_label_studio_import.json"
IMAGE_SUFFIXES = {".bmp", ".jpeg", ".jpg", ".png", ".tif", ".tiff", ".webp"}


def label_config_xml(label_name: str) -> str:
    """生成单类别矩形框 Label Studio 配置。"""
    return f"""
<View>
  <Image name="image" value="$image"/>
  <RectangleLabels name="bbox" toName="image">
    <Label value="{label_name}" background="#1E90FF"/>
  </RectangleLabels>
  <Header value="来源行：$row_number"/>
  <Text name="source_url" value="$source_url"/>
</View>
""".strip()


def load_raw_records(report_path: Path) -> list[dict[str, str]]:
    """从下载报告读取已下载或已存在的图片。"""
    records: list[dict[str, str]] = []
    with report_path.open(encoding="utf-8") as file:
        for row in csv.DictReader(file):
            if row.get("status") not in {"downloaded", "skipped"} or not row.get("path"):
                continue
            path = Path(row["path"]).resolve()
            if not path.is_file() or path.suffix.lower() not in IMAGE_SUFFIXES:
                continue
            records.append(
                {
                    "image": f"/data/local-files/?d={quote(str(path))}",
                    "source_url": row.get("url", ""),
                    "local_path": str(path),
                    "row_number": row.get("row_number", ""),
                    "image_name": path.name,
                }
            )
    return records


def build_tasks(records: list[dict[str, str]], dataset_name: str, limit: int | None) -> list[dict[str, object]]:
    """构建不含 predictions 的 Label Studio 任务。"""
    tasks: list[dict[str, object]] = []
    for record in sorted(records, key=lambda item: item["image_name"]):
        tasks.append(
            {
                "data": {
                    "image": record["image"],
                    "source_url": record["source_url"],
                    "local_path": record["local_path"],
                    "row_number": record["row_number"],
                },
                "meta": {
                    "source": "diaper-category",
                    "dataset_name": dataset_name,
                    "image_name": record["image_name"],
                    "has_pseudo_label": False,
                },
            }
        )
        if limit is not None and len(tasks) >= limit:
            break
    return tasks


def main() -> None:
    """命令行入口。"""
    parser = argparse.ArgumentParser(description="生成纸尿裤大类 Label Studio 导入 JSON。")
    parser.add_argument("--raw-report", type=Path, default=DEFAULT_RAW_REPORT, help="下载报告 CSV")
    parser.add_argument("--output", type=Path, default=DEFAULT_OUTPUT, help="Label Studio 导入 JSON 输出路径")
    parser.add_argument("--label-name", default="纸尿裤", help="Label Studio 标签名")
    parser.add_argument("--label-config-output", type=Path, default=None, help="可选：输出 Label Studio XML 标签配置")
    parser.add_argument("--dataset-name", default="diaper_category", help="写入任务 meta 的数据集名称")
    parser.add_argument("--limit", type=int, default=None, help="仅生成前 N 个任务")
    args = parser.parse_args()

    if not args.raw_report.is_file():
        raise SystemExit(f"下载报告不存在：{args.raw_report}")
    records = load_raw_records(args.raw_report)
    if not records:
        raise SystemExit(f"下载报告中没有可导入图片：{args.raw_report}")
    tasks = build_tasks(records, args.dataset_name, args.limit)

    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(tasks, ensure_ascii=False, indent=2), encoding="utf-8")
    if args.label_config_output is not None:
        args.label_config_output.parent.mkdir(parents=True, exist_ok=True)
        args.label_config_output.write_text(label_config_xml(args.label_name), encoding="utf-8")
    print(f"Label Studio 导入 JSON：{args.output}")
    print(f"tasks={len(tasks)}, predictions=0, label={args.label_name}")


if __name__ == "__main__":
    main()
