"""
Ollama 本地视觉大模型 OCR 筛选脚本。

该脚本把本地图片转换为 JPEG 后发送给 Ollama 视觉模型，让多模态大模型输出
图片中可见的品牌文字，再复用常规 OCR 脚本的品牌模糊匹配和报告格式：
- 输出 ocr_candidates.txt，供后续 YOLO-World 预标注继续使用。
- 输出 CSV/JSON 报告，便于和 RapidOCR/EasyOCR 结果对比。
- 支持少量并发请求；本地大模型通常建议 workers=1，避免显存/内存压力过大。
"""

from __future__ import annotations

# 该脚本是独立 CLI 工具，需要向 Ollama 传递较多运行参数；复用常规 OCR
# 报告/匹配逻辑会产生少量重复结构，保留以保持命令入口清晰。
# pylint: disable=wrong-import-position,too-many-arguments,too-many-positional-arguments
# pylint: disable=too-many-locals,duplicate-code

import argparse
import base64
import io
import json
import re
import shutil
import sys
from concurrent.futures import ThreadPoolExecutor, as_completed
from pathlib import Path
from typing import Any
from urllib.error import HTTPError, URLError
from urllib.request import Request, urlopen

from PIL import Image

PROJECT_ROOT = Path(__file__).resolve().parents[2]
SCRIPTS_ROOT = PROJECT_ROOT / "scripts"
if str(SCRIPTS_ROOT) not in sys.path:
    sys.path.insert(0, str(SCRIPTS_ROOT))

from ocr.filter_brand_candidates import (  # type: ignore[import-not-found]
    DEFAULT_BRAND_LIBRARY,
    DEFAULT_KEYWORDS,
    DEFAULT_OUTPUT_DIR,
    DEFAULT_RAW_DIR,
    IMAGE_SUFFIXES,
    OcrResult,
    OcrText,
    load_brand_library,
    match_keywords,
    unique_preserve_order,
    write_reports,
)

# 默认 Ollama 服务地址。
DEFAULT_OLLAMA_URL = "http://127.0.0.1:11434"
# 本机已验证 gemma3:12b 对样例货架图能稳定输出 Softcare 等英文品牌。
DEFAULT_MODEL = "gemma3:12b"
# 传给视觉模型前的默认最长边，避免原始大图导致请求过慢或内存占用过高。
DEFAULT_MAX_IMAGE_SIDE = 1280
# JPEG 转码质量；90 在文字细节和请求体大小之间较平衡。
DEFAULT_JPEG_QUALITY = 90
# 大模型 OCR 的提示词：要求尽量只输出 JSON，降低后处理复杂度。
OCR_PROMPT = """
你是门店货架图片 OCR 助手。请识别图片中所有可见的品牌名、包装正面英文单词、
中文品牌词、价签或货架文字中可能代表品牌的短语。

要求：
1. 只输出 JSON，不要解释。
2. JSON 格式必须是 {"texts": ["Softcare", "KLEESOFT"]}。
3. 如果没有可读文字，输出 {"texts": []}。
4. 不要输出商品数量、颜色、材质、货架描述。
""".strip()


def list_images(raw_dir: Path, limit: int | None) -> list[Path]:
    """递归获取待处理图片，并按路径排序保证结果稳定。"""
    images = sorted(path for path in raw_dir.rglob("*") if path.suffix.lower() in IMAGE_SUFFIXES)
    return images[:limit] if limit is not None else images


def encode_image_as_jpeg_base64(image_path: Path, max_side: int, jpeg_quality: int) -> str:
    """把任意本地图片转为 RGB JPEG 并返回 base64 字符串。"""
    with Image.open(image_path) as image:
        image = image.convert("RGB")
        if max_side > 0:
            image.thumbnail((max_side, max_side))
        buffer = io.BytesIO()
        image.save(buffer, format="JPEG", quality=jpeg_quality)
    return base64.b64encode(buffer.getvalue()).decode("ascii")


def parse_texts_from_response(response_text: str) -> list[str]:
    """从 Ollama 模型输出中解析 OCR 文本，兼容 JSON 和普通文本两种输出。"""
    text = response_text.strip()
    if not text:
        return []

    # 优先解析模型按提示词返回的 JSON 对象或 JSON 数组。
    json_text = extract_json_fragment(text)
    if json_text:
        try:
            payload = json.loads(json_text)
        except json.JSONDecodeError:
            payload = None
        if isinstance(payload, dict):
            values = payload.get("texts", [])
            if isinstance(values, list):
                return unique_preserve_order([str(item) for item in values])
        if isinstance(payload, list):
            return unique_preserve_order([str(item) for item in payload])

    # 兜底兼容逗号、顿号、分号、换行分隔的普通文本。
    cleaned = re.sub(r"^[\s`]*json", "", text, flags=re.IGNORECASE).strip("` \n\t")
    parts = re.split(r"[,，、;；\n]+", cleaned)
    return unique_preserve_order([part.strip(" -：:[]{}\"'") for part in parts])


def extract_json_fragment(text: str) -> str:
    """提取响应中的第一个 JSON 对象或数组片段。"""
    object_start = text.find("{")
    object_end = text.rfind("}")
    if object_start != -1 and object_end > object_start:
        return text[object_start : object_end + 1]

    array_start = text.find("[")
    array_end = text.rfind("]")
    if array_start != -1 and array_end > array_start:
        return text[array_start : array_end + 1]
    return ""


def call_ollama_ocr(
    image_path: Path,
    model: str,
    ollama_url: str,
    timeout: int,
    max_image_side: int,
    jpeg_quality: int,
) -> tuple[list[OcrText], str]:
    """调用 Ollama 视觉模型识别单张图片文字。"""
    image_base64 = encode_image_as_jpeg_base64(image_path, max_image_side, jpeg_quality)
    payload: dict[str, Any] = {
        "model": model,
        "prompt": OCR_PROMPT,
        "images": [image_base64],
        "stream": False,
        "options": {"temperature": 0},
    }
    endpoint = ollama_url.rstrip("/") + "/api/generate"
    request = Request(
        endpoint,
        data=json.dumps(payload).encode("utf-8"),
        headers={"Content-Type": "application/json"},
        method="POST",
    )
    with urlopen(request, timeout=timeout) as response:
        data = json.loads(response.read().decode("utf-8"))
    raw_text = str(data.get("response", ""))
    texts = [
        OcrText(text=value, confidence=1.0, box=[])
        for value in parse_texts_from_response(raw_text)
    ]
    return texts, raw_text


def process_image(
    image_path: Path,
    model: str,
    ollama_url: str,
    timeout: int,
    max_image_side: int,
    jpeg_quality: int,
    keywords: list[str],
    fuzzy_threshold: int,
    candidate_dir: Path,
    copy_candidates: bool,
) -> OcrResult:
    """处理单张图片：调用 LLM OCR、执行品牌匹配，并按需复制候选图。"""
    texts, _raw_text = call_ollama_ocr(
        image_path, model, ollama_url, timeout, max_image_side, jpeg_quality
    )
    matched, score, keyword, matched_text = match_keywords(texts, keywords, fuzzy_threshold)
    candidate_image = ""
    if matched:
        candidate_image = str(image_path.resolve())
        if copy_candidates:
            target = candidate_dir / image_path.name
            shutil.copy2(image_path, target)
            candidate_image = str(target.resolve())
    return OcrResult(
        image=str(image_path.resolve()),
        candidate_image=candidate_image,
        matched=matched,
        score=score,
        keyword=keyword,
        matched_text=matched_text,
        texts=texts,
    )


def load_keywords(args: argparse.Namespace) -> list[str]:
    """加载品牌库关键词，并合并命令行额外关键词。"""
    keywords: list[str] = []
    if not args.no_brand_library:
        if args.brand_library.is_file():
            keywords.extend(load_brand_library(args.brand_library))
        elif args.keywords:
            # 显式传了关键词时允许品牌库不存在，便于临时测试。
            pass
        else:
            raise SystemExit(f"品牌标识库不存在：{args.brand_library}")
    keywords.extend(args.keywords or [])
    return unique_preserve_order(keywords or DEFAULT_KEYWORDS)


def validate_args(args: argparse.Namespace) -> None:
    """校验命令行参数，尽早给出清晰错误。"""
    if not args.raw_dir.is_dir():
        raise SystemExit(f"原图目录不存在：{args.raw_dir}")
    if not 0 <= args.fuzzy_threshold <= 100:
        raise SystemExit("--fuzzy-threshold 必须位于 0 到 100 之间。")
    if args.timeout < 1:
        raise SystemExit("--timeout 必须大于 0。")
    if args.workers < 1:
        raise SystemExit("--workers 必须大于 0。")
    if args.max_image_side < 1:
        raise SystemExit("--max-image-side 必须大于 0。")
    if not 1 <= args.jpeg_quality <= 100:
        raise SystemExit("--jpeg-quality 必须位于 1 到 100 之间。")


def main() -> None:
    """Ollama 本地大模型 OCR 筛选脚本主入口。"""
    parser = argparse.ArgumentParser(description="用 Ollama 本地视觉大模型 OCR 筛选目标品牌图片。")
    parser.add_argument("--raw-dir", type=Path, default=DEFAULT_RAW_DIR, help="未标注原图目录")
    parser.add_argument("--output-dir", type=Path, default=DEFAULT_OUTPUT_DIR, help="OCR 输出目录")
    parser.add_argument(
        "--keyword", action="append", dest="keywords", help="关键词，可重复传入；会与品牌库合并"
    )
    parser.add_argument(
        "--brand-library",
        type=Path,
        default=DEFAULT_BRAND_LIBRARY,
        help="品牌标识库 JSON/TXT；会自动忽略数字行和重复项",
    )
    parser.add_argument(
        "--no-brand-library", action="store_true", help="不读取品牌库，仅使用 --keyword 或默认关键词"
    )
    parser.add_argument(
        "--model",
        default=DEFAULT_MODEL,
        help="Ollama 视觉模型名，例如 gemma3:12b、qwen3.6:latest、minicpm-v:latest",
    )
    parser.add_argument("--ollama-url", default=DEFAULT_OLLAMA_URL, help="Ollama 服务地址")
    parser.add_argument("--timeout", type=int, default=180, help="单图 Ollama 请求超时秒数")
    parser.add_argument("--workers", type=int, default=1, help="并发 Ollama 请求数；本地模型建议 1")
    parser.add_argument("--fuzzy-threshold", type=int, default=60, help="关键词模糊匹配阈值，0-100")
    parser.add_argument("--limit", type=int, default=None, help="只处理前 N 张图片，便于试跑")
    parser.add_argument(
        "--max-image-side", type=int, default=DEFAULT_MAX_IMAGE_SIDE, help="送入模型前最长边"
    )
    parser.add_argument(
        "--jpeg-quality", type=int, default=DEFAULT_JPEG_QUALITY, help="送入模型前 JPEG 质量，1-100"
    )
    parser.add_argument("--copy-candidates", action="store_true", help="是否复制命中图片到 ocr/candidates")
    args = parser.parse_args()

    validate_args(args)
    keywords = load_keywords(args)
    print(f"LLM OCR 模型：{args.model}，Ollama：{args.ollama_url}，并发：{args.workers}")
    print(f"OCR 关键词数量：{len(keywords)}，关键词：{', '.join(keywords)}")

    images = list_images(args.raw_dir, args.limit)
    if not images:
        raise SystemExit(f"原图目录没有图片：{args.raw_dir}")

    candidate_dir = args.output_dir / "candidates"
    metadata_dir = args.output_dir / "metadata"
    candidate_dir.mkdir(parents=True, exist_ok=True)
    metadata_dir.mkdir(parents=True, exist_ok=True)

    results: list[OcrResult] = []
    with ThreadPoolExecutor(max_workers=args.workers) as executor:
        future_map = {
            executor.submit(
                process_image,
                image_path,
                args.model,
                args.ollama_url,
                args.timeout,
                args.max_image_side,
                args.jpeg_quality,
                keywords,
                args.fuzzy_threshold,
                candidate_dir,
                args.copy_candidates,
            ): image_path
            for image_path in images
        }
        for index, future in enumerate(as_completed(future_map), start=1):
            image_path = future_map[future]
            try:
                result = future.result()
            except (HTTPError, URLError, TimeoutError) as exc:
                raise SystemExit(f"Ollama OCR 请求失败：image={image_path} error={exc}") from exc
            except Exception as exc:
                raise SystemExit(f"LLM OCR 处理失败：image={image_path} error={exc}") from exc
            results.append(result)
            status = "MATCH" if result.matched else "miss"
            joined_texts = " | ".join(item.text for item in result.texts) or "-"
            print(
                f"[{index}/{len(images)}] {status} score={result.score} "
                f"keyword={result.keyword or '-'} text={result.matched_text or '-'} "
                f"llm_texts={joined_texts} image={image_path.name}"
            )

    order = {
        str(image_path.resolve()): index
        for index, image_path in enumerate(images)
    }
    results.sort(key=lambda item: order.get(item.image, len(order)))
    write_reports(results, args.output_dir)

    matched_count = sum(result.matched for result in results)
    print(f"完成：processed={len(results)}, matched={matched_count}")
    print(f"OCR 报告：{metadata_dir / 'ocr_softcare_report.csv'}")
    print(f"候选清单：{metadata_dir / 'ocr_candidates.txt'}")


if __name__ == "__main__":
    main()
