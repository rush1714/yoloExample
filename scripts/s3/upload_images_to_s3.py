"""将本地训练图片目录上传到 S3，并生成后续 LS/EC2 可复用的图片清单。"""

# pylint: disable=line-too-long,import-error,duplicate-code,too-many-arguments,too-many-locals

from __future__ import annotations

import argparse
import csv
import json
import sys
from concurrent.futures import ThreadPoolExecutor, as_completed
from pathlib import Path
from threading import Lock
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


def load_existing_success_records(config: BrandS3Config) -> dict[str, dict[str, object]]:
    """读取已有成功上传清单，用于断点续传跳过已完成图片。"""
    if not config.manifest_json.is_file():
        return {}
    try:
        payload = json.loads(config.manifest_json.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return {}
    items = payload.get("items", []) if isinstance(payload, dict) else payload
    if not isinstance(items, list):
        return {}
    records: dict[str, dict[str, object]] = {}
    for item in items:
        if not isinstance(item, dict) or item.get("uploaded") is not True:
            continue
        relative_path = str(item.get("relative_path", ""))
        s3_key = str(item.get("s3_key", ""))
        try:
            size_bytes = int(item.get("size_bytes", -1))
        except (TypeError, ValueError):
            continue
        if relative_path and s3_key and size_bytes >= 0:
            records[f"{relative_path}|{s3_key}|{size_bytes}"] = item
    return records


def existing_success_record(
    existing_records: dict[str, dict[str, object]],
    relative_path: str,
    s3_key: str,
    size_bytes: int,
) -> dict[str, object] | None:
    """匹配已有成功记录；路径、key 和大小都一致才认为可跳过。"""
    return existing_records.get(f"{relative_path}|{s3_key}|{size_bytes}")


def upload_one_image(
    client: Any,
    config: BrandS3Config,
    image_path: Path,
    relative_path: str,
) -> dict[str, object]:
    """上传单张图片并返回清单记录；供线程池调用。"""
    key = s3_key_for_relative_path(config.prefix, relative_path)
    client.upload_file(str(image_path), config.bucket, key)
    head = client.head_object(Bucket=config.bucket, Key=key)
    extra = {
        "status": "uploaded",
        "etag": str(head.get("ETag", "")).strip('"'),
        "last_modified": head.get("LastModified"),
        "content_type": head.get("ContentType"),
    }
    print(f"uploaded {image_path} -> s3://{config.bucket}/{key}")
    return build_manifest_record(config, image_path, relative_path, uploaded=True, extra=extra)


def planned_record(config: BrandS3Config, image_path: Path, relative_path: str) -> dict[str, object]:
    """dry-run 下生成计划上传记录。"""
    key = s3_key_for_relative_path(config.prefix, relative_path)
    print(f"[dry-run] upload {image_path} -> s3://{config.bucket}/{key}")
    return build_manifest_record(config, image_path, relative_path, uploaded=False, extra={"status": "planned"})


def skipped_record(
    config: BrandS3Config,
    image_path: Path,
    relative_path: str,
    existing_record: dict[str, object],
) -> dict[str, object]:
    """把已有成功记录刷新为本轮跳过记录，保持清单统一完整。"""
    record = build_manifest_record(
        config,
        image_path,
        relative_path,
        uploaded=True,
        extra={
            "status": "skipped_existing",
            "etag": existing_record.get("etag"),
            "last_modified": existing_record.get("last_modified"),
            "content_type": existing_record.get("content_type"),
        },
    )
    print(f"skip existing {image_path} -> {record['s3_uri']}")
    return record


def failed_record(
    config: BrandS3Config,
    image_path: Path,
    relative_path: str,
    error: BaseException,
) -> dict[str, object]:
    """上传失败时也写入统一清单，方便下次续传定位。"""
    return build_manifest_record(
        config,
        image_path,
        relative_path,
        uploaded=False,
        extra={"status": "failed", "error": str(error)},
    )


def upload_images(
    config: BrandS3Config,
    recursive: bool,
    limit: int | None,
    dry_run: bool,
    workers: int,
) -> list[dict[str, object]]:
    """扫描图片、并发上传到 S3，并返回统一清单记录。"""
    if not config.bucket:
        raise SystemExit("S3 bucket 为空，请通过配置或 S3_BUCKET=<桶名> 传入。")
    if not config.local_images_dir.is_dir():
        raise SystemExit(f"本地图片目录不存在：{config.local_images_dir}")
    image_paths = iter_image_files(config.local_images_dir, recursive)
    if not image_paths:
        raise SystemExit(f"目录中没有支持的图片：{config.local_images_dir}")
    selected_paths = image_paths[:limit] if limit is not None else image_paths
    existing_records = load_existing_success_records(config)
    indexed_records: dict[str, dict[str, object]] = {}
    pending: list[tuple[Path, str]] = []
    for image_path in selected_paths:
        relative_path = image_path.relative_to(config.local_images_dir).as_posix()
        key = s3_key_for_relative_path(config.prefix, relative_path)
        existing_record = existing_success_record(existing_records, relative_path, key, image_path.stat().st_size)
        if existing_record:
            indexed_records[relative_path] = skipped_record(config, image_path, relative_path, existing_record)
        else:
            pending.append((image_path, relative_path))

    if dry_run:
        for image_path, relative_path in pending:
            indexed_records[relative_path] = planned_record(config, image_path, relative_path)
    elif pending:
        client = build_s3_client(config)
        upload_lock = Lock()
        worker_count = max(1, workers)
        with ThreadPoolExecutor(max_workers=worker_count) as executor:
            futures = {
                executor.submit(upload_one_image, client, config, image_path, relative_path): (image_path, relative_path)
                for image_path, relative_path in pending
            }
            for future in as_completed(futures):
                image_path, relative_path = futures[future]
                try:
                    record = future.result()
                except Exception as error:  # pylint: disable=broad-exception-caught
                    print(f"failed {image_path}: {error}")
                    record = failed_record(config, image_path, relative_path, error)
                with upload_lock:
                    indexed_records[relative_path] = record

    records = [indexed_records[path.relative_to(config.local_images_dir).as_posix()] for path in selected_paths]
    failed_count = sum(1 for item in records if item.get("status") == "failed")
    uploaded_count = sum(1 for item in records if item.get("status") == "uploaded")
    skipped_count = sum(1 for item in records if item.get("status") == "skipped_existing")
    planned_count = sum(1 for item in records if item.get("status") == "planned")
    print(
        f"summary total={len(records)} uploaded={uploaded_count} "
        f"skipped_existing={skipped_count} planned={planned_count} failed={failed_count}"
    )
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
        "s3_size_bytes",
        "status",
        "error",
    ]
    config.manifest_csv.parent.mkdir(parents=True, exist_ok=True)
    with config.manifest_csv.open("w", encoding="utf-8", newline="") as file:
        writer = csv.DictWriter(file, fieldnames=fieldnames, extrasaction="ignore")
        writer.writeheader()
        writer.writerows(records)
    config.urls_txt.write_text("\n".join(str(item["https_url"]) for item in records) + "\n", encoding="utf-8")



def list_s3_objects(config: BrandS3Config, client: Any) -> dict[str, dict[str, object]]:
    """列出目标 S3 prefix 下的对象，用于从远端反建本地上传清单。"""
    objects: dict[str, dict[str, object]] = {}
    paginator = client.get_paginator("list_objects_v2")
    list_prefix = f"{config.prefix.rstrip('/')}/" if config.prefix else ""
    for page in paginator.paginate(Bucket=config.bucket, Prefix=list_prefix):
        for item in page.get("Contents", []):
            key = str(item.get("Key", ""))
            if key:
                objects[key] = item
    return objects


def record_from_s3_object(
    config: BrandS3Config,
    image_path: Path,
    relative_path: str,
    s3_object: dict[str, object] | None,
) -> dict[str, object]:
    """根据 S3 对象列表和本地图片信息生成断点续传清单记录。"""
    if s3_object is None:
        return build_manifest_record(
            config,
            image_path,
            relative_path,
            uploaded=False,
            extra={"status": "missing_on_s3"},
        )
    local_size = image_path.stat().st_size
    remote_size = int(s3_object.get("Size", -1))
    uploaded = remote_size == local_size
    status = "s3_existing" if uploaded else "size_mismatch"
    return build_manifest_record(
        config,
        image_path,
        relative_path,
        uploaded=uploaded,
        extra={
            "status": status,
            "etag": str(s3_object.get("ETag", "")).strip('"'),
            "last_modified": s3_object.get("LastModified"),
            "s3_size_bytes": remote_size,
        },
    )


def sync_manifest_from_s3(
    config: BrandS3Config,
    recursive: bool,
    limit: int | None,
) -> list[dict[str, object]]:
    """查询 S3 目标目录，并结合本地目录生成可续传的上传清单。"""
    if not config.bucket:
        raise SystemExit("S3 bucket 为空，请通过配置或 S3_BUCKET=<桶名> 传入。")
    if not config.local_images_dir.is_dir():
        raise SystemExit(f"本地图片目录不存在：{config.local_images_dir}")
    image_paths = iter_image_files(config.local_images_dir, recursive)
    if not image_paths:
        raise SystemExit(f"目录中没有支持的图片：{config.local_images_dir}")
    selected_paths = image_paths[:limit] if limit is not None else image_paths
    client = build_s3_client(config)
    remote_objects = list_s3_objects(config, client)
    records = []
    for image_path in selected_paths:
        relative_path = image_path.relative_to(config.local_images_dir).as_posix()
        key = s3_key_for_relative_path(config.prefix, relative_path)
        records.append(record_from_s3_object(config, image_path, relative_path, remote_objects.get(key)))
    uploaded_count = sum(1 for item in records if item.get("uploaded") is True)
    missing_count = sum(1 for item in records if item.get("status") == "missing_on_s3")
    mismatch_count = sum(1 for item in records if item.get("status") == "size_mismatch")
    print(
        f"sync-from-s3 total={len(records)} s3_existing={uploaded_count} "
        f"missing_on_s3={missing_count} size_mismatch={mismatch_count}"
    )
    return records


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
    parser.add_argument("--workers", type=positive_int, default=8, help="并发上传线程数")
    parser.add_argument("--sync-from-s3", action="store_true", help="查询 S3 目标 prefix 并生成可续传清单")
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
    records: list[dict[str, object]] = []
    upload_error: RuntimeError | None = None
    try:
        if args.sync_from_s3:
            records = sync_manifest_from_s3(config, recursive=args.recursive, limit=args.limit)
        else:
            records = upload_images(
                config,
                recursive=args.recursive,
                limit=args.limit,
                dry_run=args.dry_run,
                workers=args.workers,
            )
    except RuntimeError as error:
        upload_error = error
    finally:
        if records:
            write_manifest(records, config)
    if upload_error is not None:
        raise upload_error
    failed_count = sum(1 for item in records if item.get("status") == "failed")
    if failed_count:
        raise RuntimeError(f"S3 上传失败 {failed_count} 张，已写入失败清单，下次可继续上传。")
    print(f"S3 图片清单 JSON：{config.manifest_json}")
    print(f"S3 图片清单 CSV：{config.manifest_csv}")
    print(f"下载地址文件：{config.urls_txt}")
    print(f"images={len(records)}, dry_run={args.dry_run}, workers={args.workers}")


if __name__ == "__main__":
    main()
