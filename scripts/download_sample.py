from __future__ import annotations

import argparse
from pathlib import Path
from urllib.parse import urlparse
from urllib.request import Request, urlopen

from PIL import Image

DEFAULT_URL = (
    "https://uat-smdp4cust-cdn.globaltradecoo.com/CustomerComponent/"
    "67cfc8156160c2fd227aef004b771854.webp"
)
PROJECT_ROOT = Path(__file__).resolve().parents[1]
DEFAULT_OUTPUT = PROJECT_ROOT / "data" / "samples" / "softcare-shelf.webp"


def download_image(url: str, output: Path) -> None:
    parsed = urlparse(url)
    if parsed.scheme not in {"http", "https"} or not parsed.netloc:
        raise ValueError("图片地址必须是完整的 HTTP(S) URL。")

    request = Request(url, headers={"User-Agent": "softcare-yolo-demo/0.1"})
    with urlopen(request, timeout=30) as response:
        if response.status != 200:
            raise RuntimeError(f"图片下载失败，HTTP 状态码：{response.status}")
        content = response.read()

    if not content:
        raise RuntimeError("图片下载失败：响应内容为空。")

    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_bytes(content)

    try:
        with Image.open(output) as image:
            image.verify()
    except Exception:
        output.unlink(missing_ok=True)
        raise RuntimeError("下载内容不是有效图片。")


def main() -> None:
    parser = argparse.ArgumentParser(description="下载 Softcare 示例门店图片。")
    parser.add_argument("--url", default=DEFAULT_URL, help="待下载的 HTTP(S) 图片 URL")
    parser.add_argument("--output", type=Path, default=DEFAULT_OUTPUT, help="本地输出路径")
    args = parser.parse_args()

    download_image(args.url, args.output)
    print(f"图片已保存至：{args.output}")


if __name__ == "__main__":
    main()
