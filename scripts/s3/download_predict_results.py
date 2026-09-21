"""下载 EC2 批量推理上传到 S3 的结果、记录文本和原始图片。

本脚本在本地 Mac 执行，用于把 EC2 推理完成后上传到 S3 的结果拉回
项目标准目录：

- S3 结果记录文本保存到数据集 ``s3/metadata`` 目录。
- summary/json/annotated 等推理结果保存到 ``outputs/ec2_predict`` 分层目录。
- 原始推理图片按 ``source_image_uris.txt`` 下载到数据集 ``predict/images`` 目录。
"""

# pylint: disable=line-too-long,too-many-locals,broad-exception-caught,too-many-arguments,too-many-positional-arguments

from __future__ import annotations

import argparse
import csv
import json
import shutil
from concurrent.futures import ThreadPoolExecutor, as_completed
from dataclasses import dataclass
from pathlib import Path
from typing import Any
from urllib.error import HTTPError, URLError
from urllib.parse import urlsplit
from urllib.request import urlopen


@dataclass(frozen=True)
class S3Location:
    """拆解后的 S3 地址。"""

    bucket: str
    key: str


IMAGE_SUFFIXES = {".bmp", ".jpeg", ".jpg", ".png", ".tif", ".tiff", ".webp"}


def parse_s3_uri(uri: str) -> S3Location:
    """解析 ``s3://bucket/key``，下载记录文本和结果文件时复用。"""
    parsed = urlsplit(uri)
    if parsed.scheme != "s3" or not parsed.netloc or not parsed.path.strip("/"):
        raise ValueError(f"S3 地址必须形如 s3://bucket/key_or_prefix：{uri}")
    return S3Location(bucket=parsed.netloc, key=parsed.path.lstrip("/"))


def s3_uri_join(base_uri: str, relative_path: str) -> str:
    """把 S3 目录和相对路径拼成完整对象 URI。"""
    base = parse_s3_uri(base_uri)
    key = f"{base.key.rstrip('/')}/{relative_path.lstrip('/')}"
    return f"s3://{base.bucket}/{key}"


def public_url_for_s3_uri(source_uri: str, public_base_url: str) -> str:
    """把 S3 URI 转成 public base URL 下的 HTTP(S) 地址。"""
    if not public_base_url:
        return ""
    location = parse_s3_uri(source_uri)
    from urllib.parse import quote  # pylint: disable=import-outside-toplevel

    return f"{public_base_url.rstrip('/')}/{quote(location.key, safe='/')}"


def is_existing_file(path: Path) -> bool:
    """判断目标文件是否已成功下载；空文件视为未完成。"""
    return path.is_file() and path.stat().st_size > 0


def build_s3_client(profile: str, region: str, endpoint_url: str) -> Any:
    """按本地 profile/region/endpoint 创建 boto3 S3 client。"""
    try:
        import boto3  # pylint: disable=import-outside-toplevel
    except ImportError as exc:
        raise SystemExit("缺少 boto3，请先执行 uv sync 安装项目依赖。") from exc
    session_kwargs: dict[str, str] = {}
    if profile:
        session_kwargs["profile_name"] = profile
    if region:
        session_kwargs["region_name"] = region
    session = boto3.session.Session(**session_kwargs)
    client_kwargs: dict[str, str] = {}
    if endpoint_url:
        client_kwargs["endpoint_url"] = endpoint_url
    return session.client("s3", **client_kwargs)


def download_s3_file(client: Any, source_uri: str, target: Path) -> None:
    """下载单个 S3 对象到本地文件。"""
    location = parse_s3_uri(source_uri)
    target.parent.mkdir(parents=True, exist_ok=True)
    client.download_file(location.bucket, location.key, str(target))


def download_http_file(source_url: str, target: Path, timeout: int) -> None:
    """带超时下载 HTTP(S) 图片到本地文件。"""
    target.parent.mkdir(parents=True, exist_ok=True)
    try:
        with urlopen(source_url, timeout=timeout) as response, target.open("wb") as file:  # noqa: S310 - URL 来自推理结果记录。
            shutil.copyfileobj(response, file)
    except (HTTPError, URLError, TimeoutError, OSError) as exc:
        raise RuntimeError(f"HTTP 下载失败：{source_url} -> {target}: {exc}") from exc


def read_uri_list(path: Path) -> list[str]:
    """读取 S3 URI 记录文本，忽略空行和注释。"""
    return [line.strip() for line in path.read_text(encoding="utf-8").splitlines() if line.strip() and not line.startswith("#")]


def local_result_path(result_root: Path, source_uri: str, output_s3_uri: str) -> Path:
    """把 S3 结果对象映射到本地结果目录下的相对路径。"""
    source = parse_s3_uri(source_uri)
    base = parse_s3_uri(output_s3_uri)
    prefix = base.key.rstrip("/") + "/"
    if source.bucket != base.bucket or not source.key.startswith(prefix):
        return result_root / Path(source.key).name
    relative = source.key[len(prefix):]
    return result_root / relative


def image_name_for_source(index: int, source: str) -> str:
    """根据图片来源生成稳定的本地文件名。"""
    parsed = urlsplit(source)
    name = Path(parsed.path or source).name or f"image_{index:06d}.jpg"
    suffix = Path(name).suffix.lower()
    if suffix not in IMAGE_SUFFIXES:
        name = f"{Path(name).stem or f'image_{index:06d}'}.jpg"
    return f"{index:06d}_{name}"


def positive_worker_count(workers: int) -> int:
    """归一化下载并发数，确保至少有一个 worker。"""
    return max(1, int(workers))


def download_s3_or_public_file(client: Any, source_uri: str, target: Path, public_base_url: str, timeout: int) -> str:
    """优先用 public URL 下载 S3 对象，失败后回退 boto3。"""
    if public_base_url:
        public_url = public_url_for_s3_uri(source_uri, public_base_url)
        try:
            download_http_file(public_url, target, timeout)
            return "public"
        except RuntimeError as exc:
            print(f"public download failed, fallback boto3 {public_url}: {exc}", flush=True)
    download_s3_file(client, source_uri, target)
    return "boto3"


def download_one_result_file(
    client: Any,
    index: int,
    total: int,
    uri: str,
    target: Path,
    public_base_url: str,
    timeout: int,
) -> dict[str, str]:
    """下载单个 S3 结果文件，供线程池并发调用。"""
    if is_existing_file(target):
        print(f"skip existing result file {index}/{total} {target}", flush=True)
        return {"source": uri, "target": str(target), "status": "skipped_existing", "error": ""}
    print(f"start result file {index}/{total} {uri} -> {target}", flush=True)
    try:
        mode = download_s3_or_public_file(client, uri, target, public_base_url, timeout)
        print(f"done result file {index}/{total} via {mode} {uri}", flush=True)
        return {"source": uri, "target": str(target), "status": "downloaded", "error": ""}
    except Exception as exc:  # pylint: disable=broad-exception-caught
        print(f"failed result file {index}/{total} {uri}: {exc}", flush=True)
        return {"source": uri, "target": str(target), "status": "failed", "error": str(exc)}


def download_result_files(
    client: Any,
    uris: list[str],
    result_root: Path,
    output_s3_uri: str,
    workers: int,
    public_base_url: str,
    timeout: int,
) -> list[dict[str, str]]:
    """并发下载 S3 推理结果文件。"""
    worker_count = positive_worker_count(workers)
    mode = "public+boto3-fallback" if public_base_url else "boto3"
    print(f"result files to download: {len(uris)}, workers={worker_count}, mode={mode}", flush=True)
    records: list[dict[str, str] | None] = [None] * len(uris)
    with ThreadPoolExecutor(max_workers=worker_count) as executor:
        futures = {}
        for index, uri in enumerate(uris, start=1):
            target = local_result_path(result_root, uri, output_s3_uri)
            future = executor.submit(
                download_one_result_file,
                client,
                index,
                len(uris),
                uri,
                target,
                public_base_url,
                timeout,
            )
            futures[future] = index - 1
        for future in as_completed(futures):
            records[futures[future]] = future.result()
    return [record for record in records if record is not None]


def download_one_source_image(
    client: Any,
    index: int,
    total: int,
    source: str,
    target: Path,
    timeout: int,
    public_base_url: str,
) -> dict[str, str]:
    """下载单张原始推理图片，供线程池并发调用。"""
    if is_existing_file(target):
        print(f"skip existing source image {index}/{total} {target}", flush=True)
        return {"source": source, "target": str(target), "status": "skipped_existing", "error": ""}
    print(f"start source image {index}/{total} {source} -> {target}", flush=True)
    try:
        scheme = urlsplit(source).scheme
        if scheme == "s3":
            mode = download_s3_or_public_file(client, source, target, public_base_url, timeout)
        elif scheme in {"http", "https"}:
            download_http_file(source, target, timeout)
            mode = "http"
        else:
            source_path = Path(source).expanduser()
            if not source_path.is_file():
                raise FileNotFoundError(f"源图片不存在：{source_path}")
            target.parent.mkdir(parents=True, exist_ok=True)
            target.write_bytes(source_path.read_bytes())
            mode = "local"
        print(f"done source image {index}/{total} via {mode} {source}", flush=True)
        return {"source": source, "target": str(target), "status": "downloaded", "error": ""}
    except Exception as exc:  # pylint: disable=broad-exception-caught
        print(f"failed source image {index}/{total} {source}: {exc}", flush=True)
        return {"source": source, "target": str(target), "status": "failed", "error": str(exc)}


def download_source_images(
    client: Any,
    source_list_path: Path,
    source_image_root: Path,
    timeout: int,
    workers: int,
    public_base_url: str,
) -> list[dict[str, str]]:
    """按 source_image_uris.txt 并发下载原始推理图片到本地数据集目录。"""
    if not source_list_path.is_file():
        print(f"source image list not found, skip: {source_list_path}", flush=True)
        return []
    sources = read_uri_list(source_list_path)
    worker_count = positive_worker_count(workers)
    print(f"source images to download: {len(sources)}, workers={worker_count}, timeout={timeout}s", flush=True)
    records: list[dict[str, str] | None] = [None] * len(sources)
    with ThreadPoolExecutor(max_workers=worker_count) as executor:
        futures = {}
        for index, source in enumerate(sources, start=1):
            target = source_image_root / image_name_for_source(index, source)
            future = executor.submit(
                download_one_source_image,
                client,
                index,
                len(sources),
                source,
                target,
                timeout,
                public_base_url,
            )
            futures[future] = index - 1
        for future in as_completed(futures):
            records[futures[future]] = future.result()
    return [record for record in records if record is not None]


def write_report(report_json: Path, report_csv: Path, result_records: list[dict[str, str]], source_records: list[dict[str, str]]) -> None:
    """写本地下载报告 JSON/CSV，便于控制台和排查查看。"""
    report_json.parent.mkdir(parents=True, exist_ok=True)
    payload = {
        "result_files": result_records,
        "source_images": source_records,
        "result_downloaded": sum(1 for item in result_records if item["status"] == "downloaded"),
        "source_downloaded": sum(1 for item in source_records if item["status"] == "downloaded"),
    }
    report_json.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
    with report_csv.open("w", encoding="utf-8", newline="") as file:
        writer = csv.DictWriter(file, fieldnames=["kind", "source", "target", "status", "error"])
        writer.writeheader()
        for item in result_records:
            writer.writerow({"kind": "result", **item})
        for item in source_records:
            writer.writerow({"kind": "source_image", **item})


def download_predict_results(args: argparse.Namespace) -> None:
    """下载推理结果记录文本、结果文件和可选原始图片。"""
    client = build_s3_client(args.profile, args.region, args.endpoint_url)
    result_root = args.result_root.expanduser().resolve()
    uri_list_output = args.uri_list_output.expanduser().resolve()
    source_image_root = args.source_image_root.expanduser().resolve()
    uri_list_s3 = s3_uri_join(args.output_s3_uri, "uploaded_s3_uris.txt")
    print(f"download uri list {uri_list_s3} -> {uri_list_output}", flush=True)
    if is_existing_file(uri_list_output):
        print(f"skip existing uri list {uri_list_output}", flush=True)
    else:
        download_s3_or_public_file(
            client,
            uri_list_s3,
            uri_list_output,
            args.public_base_url,
            args.source_download_timeout,
        )
    uris = read_uri_list(uri_list_output)
    result_records = download_result_files(
        client,
        uris,
        result_root,
        args.output_s3_uri,
        args.workers,
        args.public_base_url,
        args.source_download_timeout,
    )
    source_records: list[dict[str, str]] = []
    if args.download_source_images:
        source_list_path = result_root / "source_image_uris.txt"
        source_records = download_source_images(
            client,
            source_list_path,
            source_image_root,
            args.source_download_timeout,
            args.workers,
            args.public_base_url,
        )
    else:
        print("skip source images download", flush=True)
    write_report(args.report_json.expanduser().resolve(), args.report_csv.expanduser().resolve(), result_records, source_records)
    print(f"S3 结果记录文本：{uri_list_output}", flush=True)
    print(f"推理结果目录：{result_root}", flush=True)
    print(f"原始图片目录：{source_image_root}", flush=True)
    print(f"下载报告：{args.report_json}", flush=True)


def parse_args() -> argparse.Namespace:
    """解析命令行参数。"""
    parser = argparse.ArgumentParser(description="下载 EC2 批量推理 S3 结果到本地标准目录。")
    parser.add_argument("--output-s3-uri", required=True, help="EC2 推理结果 S3 目录，格式 s3://bucket/prefix")
    parser.add_argument("--uri-list-output", type=Path, required=True, help="本地保存 uploaded_s3_uris.txt 的路径")
    parser.add_argument("--result-root", type=Path, required=True, help="本地推理结果目录")
    parser.add_argument("--source-image-root", type=Path, required=True, help="本地原始推理图片下载目录")
    parser.add_argument("--report-json", type=Path, required=True, help="本地下载报告 JSON")
    parser.add_argument("--report-csv", type=Path, required=True, help="本地下载报告 CSV")
    parser.add_argument("--profile", default="", help="本地 AWS profile")
    parser.add_argument("--region", default="", help="AWS region")
    parser.add_argument("--endpoint-url", default="", help="兼容 S3 endpoint URL")
    parser.add_argument("--public-base-url", default="", help="公开 S3/CDN Base URL；非空时优先用 HTTP 下载 S3 对象")
    parser.add_argument("--download-source-images", action="store_true", help="同时下载原始推理图片")
    parser.add_argument("--source-download-timeout", type=int, default=30, help="HTTP(S) 原始图片下载超时秒数")
    parser.add_argument("--workers", type=int, default=8, help="结果文件和原始图片下载并发数")
    return parser.parse_args()


def main() -> None:
    """脚本入口。"""
    download_predict_results(parse_args())


if __name__ == "__main__":
    main()
