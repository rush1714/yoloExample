"""按通用标签类别生成 Label Studio 导入 JSON。

脚本统一支持三类图片来源：
1. Excel 下载报告（raw-report）：读取 download_report.csv 中的本地图片路径。
2. 本地图片目录（local-dir）：直接扫描本机目录，适合手机回流或人工整理样本。
3. S3 上传清单（s3-manifest）：读取 s3_images.json，使用 https/proxy/nginx/s3 地址导入。

类别来自 ``config/label_categories.json``，因此不再需要为品牌、纸尿裤或其它单独
品类复制一套导入脚本。
"""

# pylint: disable=line-too-long,wrong-import-position

from __future__ import annotations

import argparse
import csv
import json
import sys
from pathlib import Path
from typing import Any
from urllib.parse import quote

PROJECT_ROOT = Path(__file__).resolve().parents[2]
SCRIPTS_ROOT = PROJECT_ROOT / "scripts"
if str(SCRIPTS_ROOT) not in sys.path:
    sys.path.insert(0, str(SCRIPTS_ROOT))

from common.label_catalog import (  # type: ignore[import-not-found]
    DEFAULT_LABEL_CATALOG,
    class_id_map,
    find_label_set,
    label_config_xml,
    load_label_sets,
    select_label_classes,
)
from label_studio.generate_import import (  # type: ignore[import-not-found]
    load_prediction_results,
)
from s3.brand_s3_config import (  # type: ignore[import-not-found]
    load_manifest_records,
    nginx_url_for_object,
    proxy_url_for_object,
)

IMAGE_SUFFIXES = {".bmp", ".jpeg", ".jpg", ".png", ".tif", ".tiff", ".webp"}


def local_file_url(image_path: Path) -> str:
    """生成 Label Studio 本地文件服务 URL。"""
    return f"/data/local-files/?d={quote(str(image_path.resolve()))}"


def iter_image_files(input_dir: Path, recursive: bool) -> list[Path]:
    """按稳定顺序扫描本地图片文件。"""
    pattern = "**/*" if recursive else "*"
    resolved_dir = input_dir.expanduser().resolve()
    files = [
        path.resolve()
        for path in resolved_dir.glob(pattern)
        if path.is_file() and path.suffix.lower() in IMAGE_SUFFIXES
    ]
    return sorted(files, key=lambda item: item.relative_to(resolved_dir).as_posix().lower())


def records_from_local_dir(input_dir: Path, recursive: bool, limit: int | None) -> list[dict[str, str]]:
    """把本地图片目录转换成通用导入记录。"""
    resolved_dir = input_dir.expanduser().resolve()
    image_paths = iter_image_files(resolved_dir, recursive)
    if not image_paths:
        supported = ", ".join(sorted(IMAGE_SUFFIXES))
        raise SystemExit(f"目录中没有支持的图片：{resolved_dir}；支持后缀：{supported}")
    selected = image_paths[:limit] if limit is not None else image_paths
    records: list[dict[str, str]] = []
    for index, image_path in enumerate(selected, start=1):
        relative_path = image_path.relative_to(resolved_dir).as_posix()
        records.append(
            {
                "image": local_file_url(image_path),
                "source_url": "",
                "local_path": str(image_path),
                "row_number": str(index),
                "image_name": image_path.name,
                "relative_path": relative_path,
            }
        )
    return records


def records_from_raw_report(raw_report: Path, limit: int | None) -> list[dict[str, str]]:
    """从 Excel 下载报告中读取已下载或已存在图片记录。"""
    if not raw_report.is_file():
        raise SystemExit(f"下载报告不存在：{raw_report}")
    records: list[dict[str, str]] = []
    with raw_report.open(encoding="utf-8") as file:
        for row in csv.DictReader(file):
            if row.get("status") not in {"downloaded", "skipped"} or not row.get("path"):
                continue
            image_path = Path(str(row["path"])).resolve()
            if not image_path.is_file() or image_path.suffix.lower() not in IMAGE_SUFFIXES:
                continue
            records.append(
                {
                    "image": local_file_url(image_path),
                    "source_url": str(row.get("url", "")),
                    "local_path": str(image_path),
                    "row_number": str(row.get("row_number", "")),
                    "image_name": image_path.name,
                    "relative_path": image_path.name,
                }
            )
            if limit is not None and len(records) >= limit:
                break
    if not records:
        raise SystemExit(f"下载报告中没有可导入图片：{raw_report}")
    return sorted(records, key=lambda item: item["relative_path"].lower())


def image_url_from_s3_record(record: dict[str, Any], image_url_mode: str, proxy_base_url: str) -> str:
    """根据用户选择的地址模式返回 Label Studio 可加载的图片 URL。"""
    dataset_name = str(record.get("dataset_name") or "dataset")
    key = str(record.get("s3_key") or "")
    if image_url_mode == "nginx":
        return nginx_url_for_object(proxy_base_url, dataset_name, key)
    if image_url_mode == "proxy":
        return proxy_url_for_object(proxy_base_url, dataset_name, key)
    if image_url_mode == "s3":
        return str(record.get("s3_uri") or "")
    return str(record.get("https_url") or record.get("source_url") or record.get("s3_uri") or "")


def records_from_s3_manifest(manifest_path: Path, image_url_mode: str, proxy_base_url: str, limit: int | None) -> list[dict[str, str]]:
    """把 S3 上传清单转换成通用导入记录。"""
    if not manifest_path.is_file():
        raise SystemExit(f"S3 图片清单不存在：{manifest_path}")
    records: list[dict[str, str]] = []
    for index, record in enumerate(load_manifest_records(manifest_path), start=1):
        image_url = image_url_from_s3_record(record, image_url_mode, proxy_base_url)
        if not image_url:
            continue
        image_name = str(record.get("image_name") or Path(str(record.get("s3_key") or "image")).name)
        records.append(
            {
                "image": image_url,
                "source_url": str(record.get("https_url") or record.get("source_url") or record.get("s3_uri") or image_url),
                "local_path": str(record.get("local_path") or ""),
                "row_number": str(index),
                "image_name": image_name,
                "relative_path": str(record.get("relative_path") or image_name),
                "s3_bucket": str(record.get("s3_bucket") or ""),
                "s3_key": str(record.get("s3_key") or ""),
                "s3_uri": str(record.get("s3_uri") or ""),
            }
        )
        if limit is not None and len(records) >= limit:
            break
    if not records:
        raise SystemExit(f"S3 图片清单中没有可导入图片：{manifest_path}")
    return records


def build_tasks(
    records: list[dict[str, str]],
    dataset_name: str,
    source: str,
    pseudo_root: Path | None,
    id_to_label: dict[int, object],
) -> list[dict[str, object]]:
    """把通用图片记录转换成 Label Studio 任务。"""
    tasks: list[dict[str, object]] = []
    for record in records:
        data = {
            "image": record["image"],
            "source_url": record.get("source_url", ""),
            "local_path": record.get("local_path", ""),
            "row_number": record.get("row_number", ""),
            "image_name": record.get("image_name", ""),
            "relative_path": record.get("relative_path", ""),
        }
        if record.get("s3_bucket"):
            data.update(
                {
                    "s3_bucket": record.get("s3_bucket", ""),
                    "s3_key": record.get("s3_key", ""),
                    "s3_uri": record.get("s3_uri", ""),
                }
            )
        task: dict[str, object] = {
            "data": data,
            "meta": {
                "source": source,
                "dataset_name": dataset_name,
                "image_name": record.get("image_name", ""),
                "relative_path": record.get("relative_path", ""),
                "has_pseudo_label": False,
            },
        }
        if pseudo_root is not None and record.get("local_path"):
            predictions = load_prediction_results(record["image_name"], record["local_path"], pseudo_root, id_to_label)
            if predictions:
                task["predictions"] = [{"model_version": "yolo-pseudo-label", "score": 0.5, "result": predictions}]
                task["meta"]["has_pseudo_label"] = True  # type: ignore[index]
        tasks.append(task)
    return tasks


def parse_args() -> argparse.Namespace:
    """解析命令行参数。"""
    parser = argparse.ArgumentParser(description="按通用标签类别生成 Label Studio 导入 JSON。")
    parser.add_argument("--source", choices=["local-dir", "raw-report", "s3-manifest"], required=True, help="图片来源类型")
    parser.add_argument("--catalog", type=Path, default=DEFAULT_LABEL_CATALOG, help="通用类别配置 JSON")
    parser.add_argument("--label-set", default="general", help="类别列表名称，默认使用通用自定义类别集合")
    parser.add_argument("--labels", default="", help="类别多选，逗号分隔；空值表示全部启用类别，all 仅作历史兼容")
    parser.add_argument("--compact-class-ids", action="store_true", help="将所选类别重编号为连续类别 ID")
    parser.add_argument("--dataset-name", default="dataset", help="写入 task meta 的数据集名称")
    parser.add_argument("--input-dir", type=Path, default=None, help="local-dir 来源图片目录")
    parser.add_argument("--raw-report", type=Path, default=None, help="raw-report 来源下载报告 CSV")
    parser.add_argument("--s3-manifest", type=Path, default=None, help="s3-manifest 来源图片清单 JSON")
    parser.add_argument("--image-url-mode", choices=["nginx", "proxy", "https", "s3"], default="nginx", help="S3 图片地址模式")
    parser.add_argument("--proxy-base-url", default="http://127.0.0.1:3010", help="S3 本地代理 Base URL")
    parser.add_argument("--output", type=Path, required=True, help="Label Studio 导入 JSON 输出路径")
    parser.add_argument("--label-config-output", type=Path, required=True, help="Label Studio XML 标签配置输出路径")
    parser.add_argument("--pseudo-root", type=Path, default=None, help="可选伪标注目录；存在时写入 predictions")
    parser.add_argument("--limit", type=int, default=None, help="最多生成多少个任务")
    parser.add_argument("--recursive", dest="recursive", action="store_true", default=True, help="local-dir 递归扫描，默认开启")
    parser.add_argument("--no-recursive", dest="recursive", action="store_false", help="local-dir 只扫描当前层")
    return parser.parse_args()


def main() -> None:
    """脚本入口。"""
    args = parse_args()
    label_set = find_label_set(load_label_sets(args.catalog), args.label_set)
    classes = select_label_classes(label_set, args.labels, args.compact_class_ids)
    id_to_label = class_id_map(classes)
    if args.source == "local-dir":
        if args.input_dir is None:
            raise SystemExit("local-dir 来源必须传 --input-dir。")
        records = records_from_local_dir(args.input_dir, args.recursive, args.limit)
    elif args.source == "raw-report":
        if args.raw_report is None:
            raise SystemExit("raw-report 来源必须传 --raw-report。")
        records = records_from_raw_report(args.raw_report, args.limit)
    else:
        if args.s3_manifest is None:
            raise SystemExit("s3-manifest 来源必须传 --s3-manifest。")
        records = records_from_s3_manifest(args.s3_manifest, args.image_url_mode, args.proxy_base_url, args.limit)

    tasks = build_tasks(records, args.dataset_name, args.source, args.pseudo_root, id_to_label)
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(tasks, ensure_ascii=False, indent=2), encoding="utf-8")
    args.label_config_output.parent.mkdir(parents=True, exist_ok=True)
    args.label_config_output.write_text(label_config_xml(classes), encoding="utf-8")
    prediction_tasks = sum(1 for task in tasks if task.get("predictions"))
    prediction_boxes = sum(len(prediction["result"]) for task in tasks for prediction in task.get("predictions", []))
    print(f"类别列表：{label_set.name}")
    print(f"类别数：{len(classes)}")
    print(f"Label Studio 导入 JSON：{args.output}")
    print(f"Label Studio 标签配置：{args.label_config_output}")
    print(f"tasks={len(tasks)}, tasks_with_predictions={prediction_tasks}, prediction_boxes={prediction_boxes}")


if __name__ == "__main__":
    main()
