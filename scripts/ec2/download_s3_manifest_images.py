"""在 EC2 上根据训练图片 manifest 从 S3 或公共 URL 下载图片。

该脚本替代旧的远端 ``python -c`` 内联代码，避免 dry-run 输出大段 Python
源码。调用方只需要把本脚本同步到 EC2 项目目录，然后用普通脚本参数执行。
"""

# pylint: disable=line-too-long

from __future__ import annotations

import argparse
import json
from pathlib import Path
from typing import Any
from urllib.error import HTTPError, URLError
from urllib.parse import quote, urlsplit
from urllib.request import urlretrieve


def public_url_for_item(item: dict[str, Any], public_base_url: str) -> str:
    """优先读取 manifest 中的公共 URL；没有时用 public_base_url + s3_key 拼出 URL。"""
    for field_name in ("source_url", "https_url", "public_url"):
        value = str(item.get(field_name) or "").strip()
        if value.startswith(("http://", "https://")):
            return value
    if public_base_url and item.get("s3_key"):
        parsed_base = urlsplit(public_base_url)
        safe_key = quote(str(item["s3_key"]).lstrip("/"), safe="/")
        if parsed_base.query:
            separator = "&" if not public_base_url.endswith(("?", "&")) else ""
            return f"{public_base_url}{separator}key={quote(str(item['s3_key']), safe='/')}"
        return f"{public_base_url.rstrip('/')}/{safe_key}"
    return ""


def download_public_url(url: str, target: Path) -> None:
    """通过公共 HTTP(S) URL 下载图片，不需要 EC2 配置 AWS credentials。"""
    try:
        urlretrieve(url, str(target))  # noqa: S310 - URL 来自受控训练清单或用户配置的 S3/CDN 地址。
    except (HTTPError, URLError, OSError) as exc:
        raise RuntimeError(f"公共 URL 下载失败：{url} -> {target}: {exc}") from exc


def s3_client() -> Any:
    """懒加载 boto3 client；public 模式成功时不会触发 AWS 凭证检查。"""
    try:
        import boto3  # pylint: disable=import-outside-toplevel
    except ImportError as exc:
        raise SystemExit("EC2 缺少 boto3，请先在远端环境安装 boto3，或使用 S3_EC2_DOWNLOAD_MODE=public。") from exc
    return boto3.client("s3")


def load_manifest_items(manifest_path: Path) -> list[dict[str, Any]]:
    """读取 EC2 图片下载清单，并校验基础结构。"""
    payload = json.loads(manifest_path.read_text(encoding="utf-8"))
    items = payload.get("items", payload if isinstance(payload, list) else [])
    if not isinstance(items, list) or not items:
        raise SystemExit("EC2 图片下载清单为空或格式不正确；请确认使用的是 ec2_image_manifest.json，而不是上传阶段的 s3_images.json。")
    valid_items: list[dict[str, Any]] = []
    for index, item in enumerate(items):
        if not isinstance(item, dict):
            raise SystemExit(f"EC2 图片下载清单第 {index} 项不是对象；请重新生成 ec2_image_manifest.json。")
        valid_items.append(item)
    return valid_items


def validate_item(item: dict[str, Any], index: int, download_mode: str, public_base_url: str) -> None:
    """校验单条 manifest 是否包含当前下载模式所需字段。"""
    missing = [field for field in ("split",) if not item.get(field)]
    needs_boto3_identity = download_mode == "boto3" or (download_mode == "auto" and not public_url_for_item(item, public_base_url))
    if needs_boto3_identity:
        missing.extend(field for field in ("s3_bucket", "s3_key") if not item.get(field))
    if download_mode == "public" and not public_url_for_item(item, public_base_url):
        missing.append("source_url/https_url/public_url 或 public_base_url+s3_key")
    if missing:
        raise SystemExit(
            f"EC2 图片下载清单第 {index} 项缺少字段：{', '.join(missing)}。"
            "请确认上传的是标注转换生成的 ec2_image_manifest.json；公共下载模式需要 manifest 中有公共 URL 或传入 S3_PUBLIC_BASE_URL。"
        )


def target_path_for_item(dataset_root: Path, item: dict[str, Any]) -> Path:
    """根据 split 和 training_image_name 计算远端训练图片路径。"""
    split = str(item["split"])
    image_name = item.get("training_image_name") or Path(
        str(item.get("relative_path") or item.get("image_name") or item.get("s3_key") or "image")
    ).name
    return dataset_root / "images" / split / str(image_name)


def download_items(items: list[dict[str, Any]], dataset_root: Path, download_mode: str, public_base_url: str) -> None:
    """逐条下载 manifest 中的训练图片。"""
    client = None
    for index, item in enumerate(items):
        validate_item(item, index, download_mode, public_base_url)
        target = target_path_for_item(dataset_root, item)
        target.parent.mkdir(parents=True, exist_ok=True)
        if target.exists() and target.stat().st_size > 0:
            print(f"skip existing {target}")
            continue
        public_url = public_url_for_item(item, public_base_url)
        if download_mode in {"auto", "public"} and public_url:
            print(f"download {public_url} -> {target}")
            try:
                download_public_url(public_url, target)
                continue
            except RuntimeError as exc:
                if download_mode == "public":
                    raise SystemExit(str(exc)) from exc
                print(f"公共 URL 下载失败，回退 boto3：{exc}")
        if client is None:
            client = s3_client()
        print(f"download s3://{item['s3_bucket']}/{item['s3_key']} -> {target}")
        client.download_file(str(item["s3_bucket"]), str(item["s3_key"]), str(target))


def parse_args() -> argparse.Namespace:
    """解析命令行参数。"""
    parser = argparse.ArgumentParser(description="根据 EC2 manifest 从 S3 或公共 URL 下载训练图片。")
    parser.add_argument("--manifest", type=Path, required=True, help="EC2 图片下载清单 JSON")
    parser.add_argument("--dataset-root", type=Path, required=True, help="EC2 数据集根目录")
    parser.add_argument("--download-mode", choices=["auto", "public", "boto3"], default="auto", help="下载模式")
    parser.add_argument("--public-base-url", default="", help="公共 S3/CDN Base URL")
    return parser.parse_args()


def main() -> None:
    """脚本入口。"""
    args = parse_args()
    items = load_manifest_items(args.manifest)
    download_items(items, args.dataset_root, args.download_mode, args.public_base_url.rstrip("/"))


if __name__ == "__main__":
    main()
