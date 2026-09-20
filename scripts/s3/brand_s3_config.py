"""S3 训练图片工作流的配置、路径和清单公共工具。

本模块只包含纯逻辑和轻量文件读取，不直接访问 AWS。这样上传、Label
Studio 导入、图片代理和 EC2 编排脚本可以复用同一套路径规则，也方便
单元测试在没有 AWS 凭证的本地环境中验证关键行为。
"""

# pylint: disable=line-too-long,too-many-instance-attributes,too-many-locals

from __future__ import annotations

import json
import os
from dataclasses import dataclass
from hashlib import sha256
from pathlib import Path
from typing import Any
from urllib.parse import quote, urlencode

import yaml

PROJECT_ROOT = Path(__file__).resolve().parents[2]
IMAGE_SUFFIXES = {".bmp", ".jpeg", ".jpg", ".png", ".tif", ".tiff", ".webp"}
DEFAULT_CONFIG_PATH = PROJECT_ROOT / "config" / "brand_s3_ec2.local.yaml"


@dataclass(frozen=True)
class BrandS3Config:
    """归一化后的 S3 图片工作流配置。

    字段分为三类：本地数据集路径、S3 访问参数、Label Studio/EC2 衔接
    参数。脚本入口可以从 YAML、环境变量和命令行覆盖值合并出该对象。
    """

    dataset_name: str
    label_name: str
    local_images_dir: Path
    dataset_root: Path
    bucket: str
    prefix: str
    region: str
    profile: str
    endpoint_url: str
    public_base_url: str
    image_url_mode: str
    proxy_base_url: str
    proxy_allowed_origin: str
    manifest_json: Path
    manifest_csv: Path
    urls_txt: Path
    label_studio_import_json: Path
    label_config_xml: Path
    label_studio_export_path: Path
    yolo_report_json: Path
    ec2_manifest_json: Path
    ec2_manifest_csv: Path
    data_yaml: Path


def s3_metadata_dir(dataset_root: Path) -> Path:
    """返回标准数据集下保存 S3/EC2 清单的目录。"""
    return dataset_root / "s3" / "metadata"


def _read_config_file(config_path: Path | None) -> dict[str, Any]:
    """读取 YAML 配置；路径为空或文件不存在时返回空配置。

    默认配置文件是本地私有文件，首次使用时通常不存在。这里不强制报错，
    允许用户完全通过 Make 变量传入桶、前缀等参数。
    """
    if config_path is None or not config_path.is_file():
        return {}
    payload = yaml.safe_load(config_path.read_text(encoding="utf-8")) or {}
    if not isinstance(payload, dict):
        raise ValueError(f"S3 配置文件必须是 YAML 对象：{config_path}")
    return payload


def _nested_get(payload: dict[str, Any], dotted_key: str, default: str = "") -> str:
    """按 `a.b.c` 路径从配置字典读取字符串值。"""
    current: Any = payload
    for key in dotted_key.split("."):
        if not isinstance(current, dict) or key not in current:
            return default
        current = current[key]
    if current is None:
        return default
    return str(current)


def _first_text(*values: object, default: str = "") -> str:
    """返回第一个非空字符串，用于命令行、环境变量、配置文件优先级合并。"""
    for value in values:
        text = str(value).strip() if value is not None else ""
        if text:
            return text
    return default


def resolve_project_path(value: str | Path, default: Path) -> Path:
    """把用户传入路径归一化为绝对路径。

    相对路径按项目根目录解析，`~` 会展开到用户主目录。这样 Makefile 中的
    `datasets/demo` 和命令行里的绝对路径能得到一致行为。
    """
    text = str(value).strip() if value is not None else ""
    if not text:
        return default.resolve()
    path = Path(text).expanduser()
    if not path.is_absolute():
        path = PROJECT_ROOT / path
    return path.resolve()


def normalize_s3_prefix(prefix: str) -> str:
    """清理 S3 prefix 两端斜杠，避免生成 `//` 或空 key 段。"""
    return "/".join(part for part in prefix.strip("/").split("/") if part)


def normalize_training_prefix(prefix: str, dataset_name: str) -> str:
    """把业务前缀统一归入 yolo-training 根目录。

    用户在 Make/Web/配置中填写的 `S3_PREFIX` 只表示业务子目录，例如
    `ci_20260916_01`。最终写入 S3 的完整 prefix 必须稳定落在
    `yolo-training/<业务子目录>` 下。如果用户已经显式传入
    `yolo-training/...`，则保持原样，避免重复拼接。
    """
    clean_prefix = normalize_s3_prefix(prefix)
    if not clean_prefix:
        clean_prefix = normalize_s3_prefix(dataset_name)
    if clean_prefix == "yolo-training" or clean_prefix.startswith("yolo-training/"):
        return clean_prefix
    return normalize_s3_prefix(f"yolo-training/{clean_prefix}")


def s3_key_for_relative_path(prefix: str, relative_path: str) -> str:
    """根据数据集 prefix 和图片相对路径生成稳定 S3 key。

    相对路径只接受普通文件路径，不允许 `..` 或绝对路径，防止配置错误把
    对象写到预期目录之外。S3 key 始终使用 POSIX `/` 分隔。
    """
    normalized_relative = Path(relative_path).as_posix().lstrip("/")
    parts = [part for part in normalized_relative.split("/") if part not in {"", "."}]
    if not parts or ".." in parts:
        raise ValueError(f"非法图片相对路径：{relative_path}")
    clean_prefix = normalize_s3_prefix(prefix)
    return f"{clean_prefix}/{'/'.join(parts)}" if clean_prefix else "/".join(parts)


def https_url_for_object(bucket: str, key: str, region: str, public_base_url: str = "") -> str:
    """生成可记录到清单中的 HTTPS 形式对象地址。

    该地址不代表对象一定公开可访问；它主要用于下载清单、排查和未来切换
    直连模式。私有桶仍然通过 boto3 或本地代理读取。
    """
    encoded_key = quote(key, safe="/")
    if public_base_url:
        return f"{public_base_url.rstrip('/')}/{encoded_key}"
    if region and region != "us-east-1":
        return f"https://{bucket}.s3.{region}.amazonaws.com/{encoded_key}"
    return f"https://{bucket}.s3.amazonaws.com/{encoded_key}"


def proxy_url_for_object(proxy_base_url: str, dataset_name: str, key: str) -> str:
    """生成本地 S3 图片代理 URL，用于规避 Label Studio 访问 S3 的 CORS 限制。"""
    query = urlencode({"dataset": dataset_name, "key": key})
    return f"{proxy_base_url.rstrip('/')}/image?{query}"


def nginx_url_for_object(proxy_base_url: str, dataset_name: str, key: str) -> str:
    """生成本地 Nginx 图片代理 URL。

    Nginx 代理会把该短路径映射到真实 S3 HTTPS 或预签名 URL。这里不直接把
    S3 key 暴露到浏览器 URL 中，避免超长对象 key 影响 Label Studio 前端渲染，
    也减少路径中空格、中文等字符对 Nginx location 匹配的影响。
    """
    digest = sha256(f"{dataset_name}\0{key}".encode("utf-8")).hexdigest()[:24]
    suffix = Path(key).suffix.lower()
    safe_dataset = "".join(
        char if ord(char) < 128 and (char.isalnum() or char in "._-") else "_"
        for char in (dataset_name.strip() or "dataset")
    )
    return f"{proxy_base_url.rstrip('/')}/image/{safe_dataset}/{digest}{suffix}"


def iter_image_files(input_dir: Path, recursive: bool) -> list[Path]:
    """扫描图片目录并按相对路径稳定排序。"""
    pattern = "**/*" if recursive else "*"
    resolved_input_dir = input_dir.expanduser().resolve()
    files = [
        path.resolve()
        for path in resolved_input_dir.glob(pattern)
        if path.is_file() and path.suffix.lower() in IMAGE_SUFFIXES
    ]
    return sorted(files, key=lambda item: item.relative_to(resolved_input_dir).as_posix().lower())


def load_manifest_records(manifest_path: Path) -> list[dict[str, Any]]:
    """读取 JSON 清单，兼容列表或包含 `items` 字段的对象。"""
    payload = json.loads(manifest_path.read_text(encoding="utf-8"))
    if isinstance(payload, list):
        return [item for item in payload if isinstance(item, dict)]
    if isinstance(payload, dict) and isinstance(payload.get("items"), list):
        return [item for item in payload["items"] if isinstance(item, dict)]
    raise ValueError(f"S3 清单必须是列表或包含 items 列表的对象：{manifest_path}")


def load_config(config_path: Path | None = DEFAULT_CONFIG_PATH, **overrides: object) -> BrandS3Config:
    """从 YAML 配置和覆盖值合并出 `BrandS3Config`。

    覆盖值通常来自 argparse 或 Make 变量，优先级最高；配置文件次之；默认值
    最后兜底。该函数不校验桶名是否为空，因为某些 dry-run 或测试只需要纯
    本地路径信息，真正访问 S3 的脚本会在执行前检查。
    """
    payload = _read_config_file(config_path)
    dataset_name = _first_text(overrides.get("dataset_name"), _nested_get(payload, "dataset_name"), default="dataset")
    label_name = _first_text(overrides.get("label_name"), _nested_get(payload, "label_name"), default="diaper")
    dataset_root = resolve_project_path(
        _first_text(overrides.get("dataset_root"), _nested_get(payload, "dataset_root")),
        PROJECT_ROOT / "datasets" / dataset_name,
    )
    local_images_dir = resolve_project_path(
        _first_text(overrides.get("local_images_dir"), _nested_get(payload, "local_images_dir")),
        PROJECT_ROOT / "data" / "local_import" / "images",
    )
    bucket = _first_text(overrides.get("bucket"), os.environ.get("S3_BUCKET"), _nested_get(payload, "s3.bucket"))
    prefix = normalize_training_prefix(
        _first_text(overrides.get("prefix"), _nested_get(payload, "s3.prefix")),
        dataset_name,
    )
    region = _first_text(overrides.get("region"), os.environ.get("AWS_REGION"), _nested_get(payload, "s3.region"),
                         default="ap-southeast-1")
    profile = _first_text(overrides.get("profile"), os.environ.get("AWS_PROFILE"), _nested_get(payload, "s3.profile"))
    endpoint_url = _first_text(overrides.get("endpoint_url"), _nested_get(payload, "s3.endpoint_url"))
    public_base_url = _first_text(overrides.get("public_base_url"), _nested_get(payload, "s3.public_base_url"))
    image_url_mode = _first_text(overrides.get("image_url_mode"), _nested_get(payload, "label_studio.image_url_mode"),
                                 default="nginx")
    proxy_base_url = _first_text(
        overrides.get("proxy_base_url"),
        _nested_get(payload, "label_studio.proxy_base_url"),
        default="http://127.0.0.1:3010",
    )
    proxy_allowed_origin = _first_text(
        overrides.get("proxy_allowed_origin"),
        _nested_get(payload, "label_studio.proxy_allowed_origin"),
        default="http://localhost:9001",
    )
    metadata_dir = s3_metadata_dir(dataset_root)
    label_studio_dir = dataset_root / "label_studio"
    return BrandS3Config(
        dataset_name=dataset_name,
        label_name=label_name,
        local_images_dir=local_images_dir,
        dataset_root=dataset_root,
        bucket=bucket,
        prefix=prefix,
        region=region,
        profile=profile,
        endpoint_url=endpoint_url,
        public_base_url=public_base_url,
        image_url_mode=image_url_mode,
        proxy_base_url=proxy_base_url,
        proxy_allowed_origin=proxy_allowed_origin,
        manifest_json=resolve_project_path(overrides.get("manifest_json") or "", metadata_dir / "s3_images.json"),
        manifest_csv=resolve_project_path(overrides.get("manifest_csv") or "", metadata_dir / "s3_images.csv"),
        urls_txt=resolve_project_path(overrides.get("urls_txt") or "", metadata_dir / "s3_download_urls.txt"),
        label_studio_import_json=resolve_project_path(
            overrides.get("label_studio_import_json") or "", label_studio_dir / "s3_label_studio_import.json"
        ),
        label_config_xml=resolve_project_path(overrides.get("label_config_xml") or "",
                                              label_studio_dir / "label_config.xml"),
        label_studio_export_path=resolve_project_path(
            overrides.get("label_studio_export_path") or "", label_studio_dir / "exports" / "label_studio_export.json"
        ),
        yolo_report_json=resolve_project_path(
            overrides.get("yolo_report_json") or "", metadata_dir / "label_studio_to_yolo_report.json"
        ),
        ec2_manifest_json=resolve_project_path(overrides.get("ec2_manifest_json") or "",
                                               metadata_dir / "ec2_image_manifest.json"),
        ec2_manifest_csv=resolve_project_path(overrides.get("ec2_manifest_csv") or "",
                                              metadata_dir / "ec2_image_manifest.csv"),
        data_yaml=resolve_project_path(
            overrides.get("data_yaml") or "", PROJECT_ROOT / "config" / "generated" / f"{dataset_name}.yaml"
        ),
    )
