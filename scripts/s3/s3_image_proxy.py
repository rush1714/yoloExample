"""本地只读 S3 图片代理，用于 Label Studio 无 S3 CORS 权限时加载图片。"""

# pylint: disable=line-too-long,import-error,arguments-differ

from __future__ import annotations

import argparse
import mimetypes
import sys
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from urllib.parse import parse_qs, unquote, urlsplit

PROJECT_ROOT = Path(__file__).resolve().parents[2]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from scripts.s3.brand_s3_config import DEFAULT_CONFIG_PATH, BrandS3Config, load_config  # pylint: disable=wrong-import-position
from scripts.s3.upload_images_to_s3 import build_s3_client  # pylint: disable=wrong-import-position


class S3ImageProxyHandler(BaseHTTPRequestHandler):
    """处理 `/image?key=<s3-key>` 请求并从 S3 返回图片内容。"""

    config: BrandS3Config
    s3_client: object

    def end_headers(self) -> None:
        """为 Label Studio 图片加载补充 CORS 响应头。"""
        self.send_header("Access-Control-Allow-Origin", self.config.proxy_allowed_origin)
        self.send_header("Access-Control-Allow-Methods", "GET, OPTIONS")
        self.send_header("Access-Control-Allow-Headers", "Content-Type")
        super().end_headers()

    def do_OPTIONS(self) -> None:  # pylint: disable=invalid-name
        """处理浏览器 CORS 预检请求。"""
        self.send_response(204)
        self.end_headers()

    def do_GET(self) -> None:  # pylint: disable=invalid-name
        """读取 S3 对象并作为图片响应返回。"""
        parsed = urlsplit(self.path)
        if parsed.path != "/image":
            self.send_error(404, "not found")
            return
        query = parse_qs(parsed.query)
        key_values = query.get("key")
        if not key_values:
            self.send_error(400, "missing key")
            return
        key = unquote(key_values[0])
        if ".." in key.split("/"):
            self.send_error(400, "invalid key")
            return
        try:
            response = self.s3_client.get_object(Bucket=self.config.bucket, Key=key)
            body = response["Body"].read()
        except Exception as exc:  # pylint: disable=broad-exception-caught
            self.send_error(502, f"failed to read s3 object: {exc}")
            return
        content_type = response.get("ContentType") or mimetypes.guess_type(key)[0] or "application/octet-stream"
        self.send_response(200)
        self.send_header("Content-Type", content_type)
        self.send_header("Cache-Control", "private, max-age=300")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def log_message(self, format_: str, *args: object) -> None:
        """保留标准访问日志，便于定位 Label Studio 图片加载问题。"""
        print(f"[{self.log_date_time_string()}] {format_ % args}")


def parse_args() -> argparse.Namespace:
    """解析命令行参数。"""
    parser = argparse.ArgumentParser(description="启动本地 S3 图片代理，给 Label Studio 加载私有桶图片。")
    parser.add_argument("--config", type=Path, default=DEFAULT_CONFIG_PATH, help="S3 工作流 YAML 配置路径")
    parser.add_argument("--bucket", default="", help="S3 桶名")
    parser.add_argument("--region", default="", help="S3 区域")
    parser.add_argument("--profile", default="", help="本机 AWS profile")
    parser.add_argument("--endpoint-url", default="", help="兼容 S3 服务 endpoint URL")
    parser.add_argument("--allowed-origin", default="", help="允许访问图片的 Label Studio origin")
    parser.add_argument("--host", default="127.0.0.1", help="代理监听地址")
    parser.add_argument("--port", type=int, default=3010, help="代理监听端口")
    return parser.parse_args()


def main() -> None:
    """启动 HTTP 服务。"""
    args = parse_args()
    config = load_config(
        args.config,
        bucket=args.bucket,
        region=args.region,
        profile=args.profile,
        endpoint_url=args.endpoint_url,
        proxy_allowed_origin=args.allowed_origin,
    )
    if not config.bucket:
        raise SystemExit("S3 bucket 为空，请通过配置或 S3_BUCKET=<桶名> 传入。")
    handler = S3ImageProxyHandler
    handler.config = config
    handler.s3_client = build_s3_client(config)
    server = ThreadingHTTPServer((args.host, args.port), handler)
    print(f"S3 图片代理已启动：http://{args.host}:{args.port}")
    print(f"bucket={config.bucket}, allowed_origin={config.proxy_allowed_origin}")
    server.serve_forever()


if __name__ == "__main__":
    main()
