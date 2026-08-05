from __future__ import annotations

import argparse
import csv
import json
import re
import shutil
from dataclasses import dataclass
from pathlib import Path

from rapidfuzz import fuzz

PROJECT_ROOT = Path(__file__).resolve().parents[1]
DEFAULT_RAW_DIR = PROJECT_ROOT / "datasets" / "softcare" / "raw" / "images"
DEFAULT_OUTPUT_DIR = PROJECT_ROOT / "datasets" / "softcare" / "ocr"
DEFAULT_KEYWORDS = ["softcare", "soft care"]
IMAGE_SUFFIXES = {".bmp", ".jpeg", ".jpg", ".png", ".tif", ".tiff", ".webp"}


@dataclass(frozen=True)
class OcrText:
    text: str
    confidence: float
    box: list[list[float]]


@dataclass(frozen=True)
class OcrResult:
    image: str
    candidate_image: str
    matched: bool
    score: float
    keyword: str
    matched_text: str
    texts: list[OcrText]


def normalize_text(text: str) -> str:
    return re.sub(r"[^a-z0-9]+", "", text.lower())


def list_images(raw_dir: Path, limit: int | None) -> list[Path]:
    images = sorted(path for path in raw_dir.rglob("*") if path.suffix.lower() in IMAGE_SUFFIXES)
    return images[:limit] if limit is not None else images


def build_reader(engine: str, languages: list[str], gpu: bool):
    if engine == "rapidocr":
        from rapidocr_onnxruntime import RapidOCR

        return RapidOCR()

    import easyocr

    return easyocr.Reader(languages, gpu=gpu, verbose=False)


def read_rapidocr(reader, image_path: Path, min_confidence: float) -> list[OcrText]:
    detections, _ = reader(image_path)
    texts: list[OcrText] = []
    for detection in detections or []:
        box, text, confidence = detection
        confidence = float(confidence)
        if confidence < min_confidence:
            continue
        texts.append(
            OcrText(
                text=str(text),
                confidence=round(confidence, 4),
                box=[[round(float(x), 2), round(float(y), 2)] for x, y in box],
            )
        )
    return texts


def read_easyocr(reader, image_path: Path, min_confidence: float) -> list[OcrText]:
    detections = reader.readtext(str(image_path), detail=1, paragraph=False)
    texts: list[OcrText] = []
    for box, text, confidence in detections:
        confidence = float(confidence)
        if confidence < min_confidence:
            continue
        texts.append(
            OcrText(
                text=str(text),
                confidence=round(confidence, 4),
                box=[[round(float(x), 2), round(float(y), 2)] for x, y in box],
            )
        )
    return texts


def read_ocr(reader, engine: str, image_path: Path, min_confidence: float) -> list[OcrText]:
    if engine == "rapidocr":
        return read_rapidocr(reader, image_path, min_confidence)
    return read_easyocr(reader, image_path, min_confidence)


def match_keywords(texts: list[OcrText], keywords: list[str], fuzzy_threshold: int) -> tuple[bool, float, str, str]:
    best_score = 0.0
    best_keyword = ""
    best_text = ""
    normalized_keywords = [(keyword, normalize_text(keyword)) for keyword in keywords]

    for item in texts:
        normalized_text = normalize_text(item.text)
        if not normalized_text:
            continue
        for keyword, normalized_keyword in normalized_keywords:
            score = 0.0
            if normalized_keyword and normalized_keyword in normalized_text:
                score = 100.0
            else:
                score = float(fuzz.partial_ratio(normalized_keyword, normalized_text))
            weighted_score = score * max(item.confidence, 0.01)
            if weighted_score > best_score:
                best_score = weighted_score
                best_keyword = keyword
                best_text = item.text

    return best_score >= fuzzy_threshold, round(best_score, 2), best_keyword, best_text


def write_reports(results: list[OcrResult], output_dir: Path) -> None:
    metadata_dir = output_dir / "metadata"
    metadata_dir.mkdir(parents=True, exist_ok=True)
    json_path = metadata_dir / "ocr_softcare_report.json"
    csv_path = metadata_dir / "ocr_softcare_report.csv"
    candidates_path = metadata_dir / "ocr_candidates.txt"

    rows = []
    for result in results:
        row = {
            "image": result.image,
            "candidate_image": result.candidate_image,
            "matched": result.matched,
            "score": result.score,
            "keyword": result.keyword,
            "matched_text": result.matched_text,
            "texts": [text.__dict__ for text in result.texts],
        }
        rows.append(row)

    json_path.write_text(json.dumps(rows, ensure_ascii=False, indent=2), encoding="utf-8")
    with csv_path.open("w", encoding="utf-8", newline="") as file:
        writer = csv.DictWriter(
            file,
            fieldnames=["image", "candidate_image", "matched", "score", "keyword", "matched_text", "text_count"],
        )
        writer.writeheader()
        for result in results:
            writer.writerow(
                {
                    "image": result.image,
                    "candidate_image": result.candidate_image,
                    "matched": result.matched,
                    "score": result.score,
                    "keyword": result.keyword,
                    "matched_text": result.matched_text,
                    "text_count": len(result.texts),
                }
            )

    candidate_images = [result.candidate_image for result in results if result.matched and result.candidate_image]
    candidates_path.write_text("\n".join(candidate_images) + ("\n" if candidate_images else ""), encoding="utf-8")


def main() -> None:
    parser = argparse.ArgumentParser(description="用 OCR 筛选疑似包含 Softcare 字样的原始图片。")
    parser.add_argument("--raw-dir", type=Path, default=DEFAULT_RAW_DIR, help="未标注原图目录")
    parser.add_argument("--output-dir", type=Path, default=DEFAULT_OUTPUT_DIR, help="OCR 输出目录")
    parser.add_argument("--keyword", action="append", dest="keywords", help="关键词，可重复传入")
    parser.add_argument("--engine", choices=["rapidocr", "easyocr"], default="rapidocr", help="OCR 引擎；默认 rapidocr，速度快且无需下载 EasyOCR 检测模型")
    parser.add_argument("--languages", nargs="+", default=["en"], help="EasyOCR 语言列表，仅 --engine easyocr 时使用")
    parser.add_argument("--gpu", action="store_true", help="是否启用 EasyOCR GPU，仅 --engine easyocr 时使用；Mac MPS 通常保持关闭")
    parser.add_argument("--min-confidence", type=float, default=0.2, help="OCR 文本最低置信度")
    parser.add_argument("--fuzzy-threshold", type=int, default=60, help="关键词模糊匹配阈值，0-100")
    parser.add_argument("--limit", type=int, default=None, help="只处理前 N 张图片，便于试跑")
    parser.add_argument("--copy-candidates", action="store_true", help="是否复制命中图片到 ocr/candidates")
    args = parser.parse_args()

    if not args.raw_dir.is_dir():
        raise SystemExit(f"原图目录不存在：{args.raw_dir}")
    if not 0.0 <= args.min_confidence <= 1.0:
        raise SystemExit("--min-confidence 必须位于 0 到 1 之间。")
    if not 0 <= args.fuzzy_threshold <= 100:
        raise SystemExit("--fuzzy-threshold 必须位于 0 到 100 之间。")

    keywords = args.keywords or DEFAULT_KEYWORDS
    images = list_images(args.raw_dir, args.limit)
    if not images:
        raise SystemExit(f"原图目录没有图片：{args.raw_dir}")

    candidate_dir = args.output_dir / "candidates"
    metadata_dir = args.output_dir / "metadata"
    candidate_dir.mkdir(parents=True, exist_ok=True)
    metadata_dir.mkdir(parents=True, exist_ok=True)

    reader = build_reader(args.engine, args.languages, args.gpu)
    results: list[OcrResult] = []
    for index, image_path in enumerate(images, start=1):
        texts = read_ocr(reader, args.engine, image_path, args.min_confidence)
        matched, score, keyword, matched_text = match_keywords(texts, keywords, args.fuzzy_threshold)
        candidate_image = ""
        if matched:
            candidate_image = str(image_path.resolve())
            if args.copy_candidates:
                target = candidate_dir / image_path.name
                shutil.copy2(image_path, target)
                candidate_image = str(target.resolve())
        results.append(
            OcrResult(
                image=str(image_path.resolve()),
                candidate_image=candidate_image,
                matched=matched,
                score=score,
                keyword=keyword,
                matched_text=matched_text,
                texts=texts,
            )
        )
        status = "MATCH" if matched else "miss"
        print(f"[{index}/{len(images)}] {status} score={score} keyword={keyword or '-'} text={matched_text or '-'} image={image_path.name}")

    write_reports(results, args.output_dir)
    matched_count = sum(result.matched for result in results)
    print(f"完成：processed={len(results)}, matched={matched_count}")
    print(f"OCR 报告：{metadata_dir / 'ocr_softcare_report.csv'}")
    print(f"候选清单：{metadata_dir / 'ocr_candidates.txt'}")


if __name__ == "__main__":
    main()
