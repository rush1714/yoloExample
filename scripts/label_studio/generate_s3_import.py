"""根据 S3 图片清单生成 Label Studio 单类别导入任务。"""

# pylint: disable=line-too-long,import-error,duplicate-code

from __future__ import annotations

import argparse
import json
import sys
from html import escape
from pathlib import Path
from typing import Any

PROJECT_ROOT = Path(__file__).resolve().parents[2]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from scripts.s3.brand_s3_config import (  # pylint: disable=wrong-import-position
    DEFAULT_CONFIG_PATH,
    https_url_for_object,
    load_config,
    load_manifest_records,
    proxy_url_for_object,
)


def label_config_xml(label_name: str) -> str:
    """构建单类别矩形框 Label Studio 配置。"""
    safe_label = escape(label_name, quote=True)
    return f"""
<View>
  <Image name="image" value="$image"/>
  <RectangleLabels name="bbox" toName="image">
    <Label value="{safe_label}" background="#1E90FF"/>
  </RectangleLabels>
  <Header value="文件：$image_name"/>
  <Text name="s3_uri" value="$s3_uri"/>
  <Text name="relative_path" value="$relative_path"/>
</View>
""".strip()


def image_value_for_record(record: dict[str, Any], image_url_mode: str) -> str:
    """根据 URL 模式选择 Label Studio 实际加载的图片地址。"""
    if image_url_mode == "https":
        return str(record.get("https_url", ""))
    if image_url_mode == "s3":
        return str(record.get("s3_uri", ""))
    return str(record.get("proxy_url", ""))


def enrich_manifest_record(record: dict[str, Any], proxy_base_url: str, image_url_mode: str) -> dict[str, Any]:
    """补齐旧清单或手写清单中可能缺少的 URL 字段。"""
    enriched = dict(record)
    bucket = str(enriched.get("s3_bucket", ""))
    key = str(enriched.get("s3_key", ""))
    dataset_name = str(enriched.get("dataset_name", "local_dataset"))
    region = str(enriched.get("region", ""))
    if bucket and key:
        enriched.setdefault("s3_uri", f"s3://{bucket}/{key}")
        enriched.setdefault("https_url", https_url_for_object(bucket, key, region))
        enriched["proxy_url"] = proxy_url_for_object(proxy_base_url, dataset_name, key)
    enriched["image"] = image_value_for_record(enriched, image_url_mode)
    return enriched


def build_tasks(records: list[dict[str, Any]], label_name: str, image_url_mode: str, proxy_base_url: str) -> list[dict[str, object]]:
    """把 S3 清单记录转换为 Label Studio 任务列表。"""
    tasks: list[dict[str, object]] = []
    for index, record in enumerate(records, start=1):
        enriched = enrich_manifest_record(record, proxy_base_url, image_url_mode)
        image_value = str(enriched.get("image", ""))
        if not image_value:
            raise ValueError(f"第 {index} 条 S3 清单缺少可用 image URL：{record}")
        dataset_name = str(enriched.get("dataset_name", "local_dataset"))
        image_name = str(enriched.get("image_name") or Path(str(enriched.get("relative_path", f"image_{index}"))).name)
        relative_path = str(enriched.get("relative_path") or image_name)
        s3_key = str(enriched.get("s3_key", ""))
        s3_uri = str(enriched.get("s3_uri", ""))
        tasks.append(
            {
                "data": {
                    "image": image_value,
                    "image_name": image_name,
                    "relative_path": relative_path,
                    "source_url": str(enriched.get("https_url", image_value)),
                    "s3_uri": s3_uri,
                    "s3_bucket": str(enriched.get("s3_bucket", "")),
                    "s3_key": s3_key,
                    "label_name": label_name,
                    "row_number": str(index),
                },
                "meta": {
                    "source": "s3",
                    "dataset_name": dataset_name,
                    "image_name": image_name,
                    "relative_path": relative_path,
                    "s3_uri": s3_uri,
                    "s3_key": s3_key,
                    "image_url_mode": image_url_mode,
                    "has_pseudo_label": False,
                },
            }
        )
    return tasks


def parse_args() -> argparse.Namespace:
    """解析命令行参数。"""
    parser = argparse.ArgumentParser(description="从 S3 图片清单生成 Label Studio 导入 JSON。")
    parser.add_argument("--config", type=Path, default=DEFAULT_CONFIG_PATH, help="S3 工作流 YAML 配置路径")
    parser.add_argument("--manifest", type=Path, default=None, help="S3 图片清单 JSON")
    parser.add_argument("--output", type=Path, default=None, help="Label Studio 导入 JSON 输出路径")
    parser.add_argument("--label-config-output", type=Path, default=None, help="Label Studio XML 标签配置输出路径")
    parser.add_argument("--dataset-name", default="", help="数据集短名称")
    parser.add_argument("--label-name", default="", help="单类别标签名")
    parser.add_argument("--dataset-root", default="", help="本地 S3 工作流输出根目录")
    parser.add_argument("--image-url-mode", choices=["proxy", "https", "s3"], default="", help="LS 图片地址模式")
    parser.add_argument("--proxy-base-url", default="", help="本地 S3 图片代理 base URL")
    return parser.parse_args()


def main() -> None:
    """脚本入口。"""
    args = parse_args()
    config = load_config(
        args.config,
        dataset_name=args.dataset_name,
        label_name=args.label_name,
        dataset_root=args.dataset_root,
        image_url_mode=args.image_url_mode,
        proxy_base_url=args.proxy_base_url,
    )
    manifest_path = args.manifest or config.manifest_json
    output_path = args.output or config.label_studio_import_json
    label_config_path = args.label_config_output or config.label_config_xml
    records = load_manifest_records(manifest_path)
    tasks = build_tasks(records, config.label_name, config.image_url_mode, config.proxy_base_url)
    output_path.parent.mkdir(parents=True, exist_ok=True)
    output_path.write_text(json.dumps(tasks, ensure_ascii=False, indent=2), encoding="utf-8")
    label_config_path.parent.mkdir(parents=True, exist_ok=True)
    label_config_path.write_text(label_config_xml(config.label_name), encoding="utf-8")
    print(f"S3 图片清单：{manifest_path}")
    print(f"Label Studio 导入 JSON：{output_path}")
    print(f"Label Studio 标签配置：{label_config_path}")
    print(f"tasks={len(tasks)}, label={config.label_name}, image_url_mode={config.image_url_mode}")


if __name__ == "__main__":
    main()
