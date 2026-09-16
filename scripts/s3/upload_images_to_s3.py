"""将本地训练图片目录上传到 S3，并生成后续 LS/EC2 可复用的图片清单。"""

# pylint: disable=line-too-long,import-error,duplicate-code

from __future__ import annotations

import argparse
import csv
import json
import sys
from pathlib import Path
from typing import Any

# 允许直接执行 `python scripts/s3/upload_images_to_s3.py` 时导入项目模块。
PROJECT_ROOT = Path(__file__).resolve().parents[2]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from scripts.s3.brand_s3_config import (  # pylint: disable=wrong-import-position
    DEFAULT_CONFIG_PATH,
    BrandS3Config,
    https_url_for_object,
    iter_image_files,
    load_config,
    proxy_url_for_object,
    s3_key_for_relative_path,
)


def build_s3_client(config: BrandS3Config) -> Any:
    """按配置创建 boto3 S3 client。

    boto3 作为可选运行依赖延迟导入，使单元测试和无 AWS 环境下的 dry-run
    清单逻辑不受影响。真实上传时如果缺少依赖，会给出明确安装提示。
    """
    try:
        import boto3  # pylint: disable=import-outside-toplevel
    except ImportError as exc:
        raise SystemExit("缺少 boto3，请先执行：uv add boto3 或 uv sync 安装项目依赖。") from exc
    session_kwargs: dict[str, str] = {}
    if config.profile:
        session_kwargs["profile_name"] = config.profile
    if config.region:
        session_kwargs["region_name"] = config.region
    session = boto3.session.Session(**session_kwargs)
    client_kwargs: dict[str, str] = {}
    if config.endpoint_url:
        client_kwargs["endpoint_url"] = config.endpoint_url
    return session.client("s3", **client_kwargs)


def build_manifest_record(
    config: BrandS3Config,
    image_path: Path,
    relative_path: str,
    uploaded: bool,
    extra: dict[str, object] | None = None,
) -> dict[str, object]:
    """为一张图片生成 S3 清单记录。"""
    key = s3_key_for_relative_path(config.prefix, relative_path)
    record: dict[str, object] = {
        "dataset_name": config.dataset_name,
        "image_name": image_path.name,
        "relative_path": relative_path,
        "local_path": str(image_path),
        "s3_bucket": config.bucket,
        "s3_key": key,
        "s3_uri": f"s3://{config.bucket}/{key}",
        "https_url": https_url_for_object(config.bucket, key, config.region, config.public_base_url),
        "proxy_url": proxy_url_for_object(config.proxy_base_url, config.dataset_name, key),
        "size_bytes": image_path.stat().st_size,
        "uploaded": uploaded,
    }
    if extra:
        record.update({key_: value for key_, value in extra.items() if value is not None})
    return record


def upload_images(config: BrandS3Config, recursive: bool, limit: int | None, dry_run: bool) -> list[dict[str, object]]:
    """扫描图片、上传到 S3，并返回清单记录。"""
    if not config.bucket:
        raise SystemExit("S3 bucket 为空，请通过配置或 S3_BUCKET=<桶名> 传入。")
    if not config.local_images_dir.is_dir():
        raise SystemExit(f"本地图片目录不存在：{config.local_images_dir}")
    image_paths = iter_image_files(config.local_images_dir, recursive)
    if not image_paths:
        raise SystemExit(f"目录中没有支持的图片：{config.local_images_dir}")
    selected_paths = image_paths[:limit] if limit is not None else image_paths
    client = None if dry_run else build_s3_client(config)
    records: list[dict[str, object]] = []
    for image_path in selected_paths:
        relative_path = image_path.relative_to(config.local_images_dir).as_posix()
        key = s3_key_for_relative_path(config.prefix, relative_path)
        extra: dict[str, object] = {}
        if dry_run:
            print(f"[dry-run] upload {image_path} -> s3://{config.bucket}/{key}")
        else:
            client.upload_file(str(image_path), config.bucket, key)
            head = client.head_object(Bucket=config.bucket, Key=key)
            extra = {
                "etag": str(head.get("ETag", "")).strip('"'),
                "last_modified": head.get("LastModified"),
                "content_type": head.get("ContentType"),
            }
            print(f"uploaded {image_path} -> s3://{config.bucket}/{key}")
        records.append(build_manifest_record(config, image_path, relative_path, uploaded=not dry_run, extra=extra))
    return records


def write_manifest(records: list[dict[str, object]], config: BrandS3Config) -> None:
    """写 JSON、CSV 和纯 URL 下载清单。"""
    config.manifest_json.parent.mkdir(parents=True, exist_ok=True)
    payload = {
        "dataset_name": config.dataset_name,
        "label_name": config.label_name,
        "bucket": config.bucket,
        "prefix": config.prefix,
        "region": config.region,
        "image_url_mode": config.image_url_mode,
        "items": records,
    }
    config.manifest_json.write_text(json.dumps(payload, ensure_ascii=False, indent=2, default=str), encoding="utf-8")
    fieldnames = [
        "dataset_name",
        "image_name",
        "relative_path",
        "local_path",
        "s3_bucket",
        "s3_key",
        "s3_uri",
        "https_url",
        "proxy_url",
        "size_bytes",
        "uploaded",
        "etag",
        "last_modified",
        "content_type",
    ]
    config.manifest_csv.parent.mkdir(parents=True, exist_ok=True)
    with config.manifest_csv.open("w", encoding="utf-8", newline="") as file:
        writer = csv.DictWriter(file, fieldnames=fieldnames, extrasaction="ignore")
        writer.writeheader()
        writer.writerows(records)
    config.urls_txt.write_text("\n".join(str(item["https_url"]) for item in records) + "\n", encoding="utf-8")


def positive_int(value: str) -> int:
    """解析正整数参数。"""
    parsed = int(value)
    if parsed <= 0:
        raise argparse.ArgumentTypeError("必须是大于 0 的整数")
    return parsed


def parse_args() -> argparse.Namespace:
    """解析命令行参数。"""
    parser = argparse.ArgumentParser(description="上传本地图片目录到 S3 并生成训练图片清单。")
    parser.add_argument("--config", type=Path, default=DEFAULT_CONFIG_PATH, help="S3 工作流 YAML 配置路径")
    parser.add_argument("--dataset-name", default="", help="数据集短名称")
    parser.add_argument("--label-name", default="", help="单类别标签名")
    parser.add_argument("--input-dir", default="", help="本地图片目录")
    parser.add_argument("--dataset-root", default="", help="本地 S3 工作流输出根目录")
    parser.add_argument("--bucket", default="", help="S3 桶名")
    parser.add_argument("--prefix", default="", help="S3 对象前缀")
    parser.add_argument("--region", default="", help="S3 区域")
    parser.add_argument("--profile", default="", help="本机 AWS profile")
    parser.add_argument("--endpoint-url", default="", help="兼容 S3 服务 endpoint URL")
    parser.add_argument("--public-base-url", default="", help="自定义公开访问 base URL")
    parser.add_argument("--proxy-base-url", default="", help="本地 S3 图片代理 base URL")
    parser.add_argument("--limit", type=positive_int, default=None, help="仅处理前 N 张图片")
    parser.add_argument("--recursive", dest="recursive", action="store_true", default=True, help="递归扫描图片目录")
    parser.add_argument("--no-recursive", dest="recursive", action="store_false", help="只扫描当前目录")
    parser.add_argument("--dry-run", action="store_true", help="只生成清单并打印上传计划，不访问 S3")
    return parser.parse_args()


def main() -> None:
    """脚本入口。"""
    args = parse_args()
    config = load_config(
        args.config,
        dataset_name=args.dataset_name,
        label_name=args.label_name,
        local_images_dir=args.input_dir,
        dataset_root=args.dataset_root,
        bucket=args.bucket,
        prefix=args.prefix,
        region=args.region,
        profile=args.profile,
        endpoint_url=args.endpoint_url,
        public_base_url=args.public_base_url,
        proxy_base_url=args.proxy_base_url,
    )
    records = upload_images(config, recursive=args.recursive, limit=args.limit, dry_run=args.dry_run)
    write_manifest(records, config)
    print(f"S3 图片清单 JSON：{config.manifest_json}")
    print(f"S3 图片清单 CSV：{config.manifest_csv}")
    print(f"下载地址文件：{config.urls_txt}")
    print(f"images={len(records)}, dry_run={args.dry_run}")


if __name__ == "__main__":
    main()
