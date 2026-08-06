"""
OCR 筛选脚本：通过文本识别筛选包含 Softcare 字样的图片。

该脚本使用 OCR 技术从原始图片中筛选包含 "Softcare" 或 "soft care" 等关键词的图片，
用于半自动数据收集流程：
- 支持 RapidOCR 和 EasyOCR 两种 OCR 引擎
- 支持关键词模糊匹配（基于编辑距离）
- 生成详细的 OCR 识别报告（JSON 和 CSV）
- 输出候选图片清单，供后续伪标注使用
"""

from __future__ import annotations

import argparse
import csv
import json
import re
import shutil
import warnings
from dataclasses import dataclass
from pathlib import Path

from rapidfuzz import fuzz

# 全局抑制 PyTorch 的常见无害警告（MPS pin_memory 不支持、量化 API 弃用）
warnings.filterwarnings("ignore", message=".*pin_memory.*")
warnings.filterwarnings("ignore", message=".*quantize_per_tensor.*")
warnings.filterwarnings("ignore", message=".*quantize_per_channel.*")

# 项目根目录
PROJECT_ROOT = Path(__file__).resolve().parents[2]
# 默认原始图片目录
DEFAULT_RAW_DIR = PROJECT_ROOT / "datasets" / "multibrand" / "raw" / "images"
# 默认 OCR 输出目录
DEFAULT_OUTPUT_DIR = PROJECT_ROOT / "datasets" / "multibrand" / "ocr"
# 默认品牌标识库路径
DEFAULT_BRAND_LIBRARY = PROJECT_ROOT / "data" / "brand_keywords.json"
# 默认关键词列表；如果品牌库存在，会优先使用品牌库。
DEFAULT_KEYWORDS = ["softcare", "soft care"]
# 支持的图片格式后缀
IMAGE_SUFFIXES = {".bmp", ".jpeg", ".jpg", ".png", ".tif", ".tiff", ".webp"}


@dataclass(frozen=True)
class OcrText:
    """OCR 识别的单条文本结果。"""
    text: str  # 识别的文本内容
    confidence: float  # 识别置信度
    box: list[list[float]]  # 文本框坐标点列表


@dataclass(frozen=True)
class OcrResult:
    """单张图片的 OCR 处理结果。"""
    image: str  # 原始图片路径
    candidate_image: str  # 候选图片路径（如果匹配关键词）
    matched: bool  # 是否匹配关键词
    score: float  # 匹配得分
    keyword: str  # 匹配的关键词
    matched_text: str  # 匹配的 OCR 文本
    texts: list[OcrText]  # 所有识别的文本


def normalize_text(text: str) -> str:
    """
    标准化文本：转换为小写并移除非字母数字字符。

    用于关键词匹配时的规范化处理。
    """
    return re.sub(r"[^a-z0-9]+", "", text.lower())


def is_usable_keyword(value: str) -> bool:
    """判断品牌库中的文本是否适合作为 OCR 关键词。"""
    text = str(value).strip()
    if not text:
        return False
    # 用户给出的列表中夹杂数字序号，这里统一忽略纯数字。
    if text.isdigit():
        return False
    # 星号这类纯符号不适合当前文本 OCR 模糊匹配，避免大量误召回。
    return bool(normalize_text(text))


def unique_preserve_order(values: list[str]) -> list[str]:
    """按大小写无关方式去重，同时保留原始顺序。"""
    seen: set[str] = set()
    result: list[str] = []
    for value in values:
        text = str(value).strip()
        if not is_usable_keyword(text):
            continue
        key = normalize_text(text)
        if key in seen:
            continue
        seen.add(key)
        result.append(text)
    return result


def load_brand_library(path: Path) -> list[str]:
    """从 JSON 或文本品牌库中加载 OCR 关键词，并忽略数字和重复项。"""
    if not path.is_file():
        raise FileNotFoundError(f"品牌标识库不存在：{path}")

    if path.suffix.lower() == ".json":
        payload = json.loads(path.read_text(encoding="utf-8"))
        raw_values: list[str] = []
        if isinstance(payload, dict):
            brands = payload.get("brands", [])
            if not isinstance(brands, list):
                raise ValueError("品牌标识库 JSON 的 brands 必须是列表。")
            for item in brands:
                if isinstance(item, str):
                    raw_values.append(item)
                    continue
                if not isinstance(item, dict):
                    continue
                if item.get("enabled", True) is False:
                    continue
                name = item.get("name")
                if isinstance(name, str):
                    raw_values.append(name)
                aliases = item.get("aliases", [])
                if isinstance(aliases, list):
                    raw_values.extend(str(alias) for alias in aliases)
        elif isinstance(payload, list):
            raw_values = [str(item) for item in payload]
        else:
            raise ValueError("品牌标识库 JSON 必须是对象或列表。")
        return unique_preserve_order(raw_values)

    raw_values = path.read_text(encoding="utf-8").splitlines()
    return unique_preserve_order(raw_values)


def list_images(raw_dir: Path, limit: int | None) -> list[Path]:
    """
    获取待处理的图片列表。
    
    Args:
        raw_dir: 原始图片目录
        limit: 限制处理的图片数量（用于试跑）
    
    Returns:
        图片路径列表
    """
    # 递归查找目录中的所有图片并排序
    images = sorted(path for path in raw_dir.rglob("*") if path.suffix.lower() in IMAGE_SUFFIXES)
    return images[:limit] if limit is not None else images


def build_reader(engine: str, languages: list[str], gpu: bool):
    """
    构建 OCR 引擎读取器。
    
    Args:
        engine: OCR 引擎类型（"rapidocr" 或 "easyocr"）
        languages: 语言列表（仅 EasyOCR 使用）
        gpu: 是否启用 GPU（仅 EasyOCR 使用）
    
    Returns:
        OCR 读取器实例
    """
    if engine == "rapidocr":
        # 使用 RapidOCR（速度快，无需下载检测模型）
        from rapidocr_onnxruntime import RapidOCR

        return RapidOCR()

    # 使用 EasyOCR
    import easyocr

    return easyocr.Reader(languages, gpu=gpu, verbose=False)


def read_rapidocr(reader, image_path: Path, min_confidence: float) -> list[OcrText]:
    """
    使用 RapidOCR 识别图片中的文本。
    
    Args:
        reader: RapidOCR 读取器实例
        image_path: 图片路径
        min_confidence: 最低置信度阈值
    
    Returns:
        识别的文本结果列表
    """
    detections, _ = reader(image_path)
    texts: list[OcrText] = []
    # 解析检测结果
    for detection in detections or []:
        box, text, confidence = detection
        confidence = float(confidence)
        # 过滤低置信度结果
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
    """
    使用 EasyOCR 识别图片中的文本。
    
    Args:
        reader: EasyOCR 读取器实例
        image_path: 图片路径
        min_confidence: 最低置信度阈值
    
    Returns:
        识别的文本结果列表
    """
    detections = reader.readtext(str(image_path), detail=1, paragraph=False)
    texts: list[OcrText] = []
    # 解析检测结果
    for box, text, confidence in detections:
        confidence = float(confidence)
        # 过滤低置信度结果
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
    """
    根据引擎类型调用相应的 OCR 识别函数。
    
    Args:
        reader: OCR 读取器实例
        engine: OCR 引擎类型
        image_path: 图片路径
        min_confidence: 最低置信度阈值
    
    Returns:
        识别的文本结果列表
    """
    if engine == "rapidocr":
        return read_rapidocr(reader, image_path, min_confidence)
    return read_easyocr(reader, image_path, min_confidence)


def match_keywords(texts: list[OcrText], keywords: list[str], fuzzy_threshold: int) -> tuple[bool, float, str, str]:
    """
    在 OCR 识别的文本中匹配关键词。
    
    支持精确匹配和模糊匹配（基于编辑距离），并考虑 OCR 置信度进行加权。
    
    Args:
        texts: OCR 识别的文本列表
        keywords: 关键词列表
        fuzzy_threshold: 模糊匹配阈值（0-100）
    
    Returns:
        元组：(是否匹配, 最佳得分, 匹配的关键词, 匹配的文本)
    """
    best_score = 0.0
    best_keyword = ""
    best_text = ""
    # 预处理关键词：标准化
    normalized_keywords = [(keyword, normalize_text(keyword)) for keyword in keywords]

    # 遍历所有识别的文本
    for item in texts:
        normalized_text = normalize_text(item.text)
        if not normalized_text:
            continue
        # 对每个关键词进行匹配
        for keyword, normalized_keyword in normalized_keywords:
            score = 0.0
            # 精确子串匹配得满分
            if normalized_keyword and normalized_keyword in normalized_text:
                score = 100.0
            else:
                # 模糊匹配：使用 partial_ratio 计算相似度
                score = float(fuzz.partial_ratio(normalized_keyword, normalized_text))
            # 加权得分：考虑 OCR 置信度
            weighted_score = score * max(item.confidence, 0.01)
            # 更新最佳匹配
            if weighted_score > best_score:
                best_score = weighted_score
                best_keyword = keyword
                best_text = item.text

    # 判断是否达到阈值
    return best_score >= fuzzy_threshold, round(best_score, 2), best_keyword, best_text


def write_reports(results: list[OcrResult], output_dir: Path) -> None:
    """
    生成 OCR 处理报告。
    
    生成三种报告文件：
    - JSON 详细报告（包含所有 OCR 识别结果）
    - CSV 摘要报告（便于查看和筛选）
    - 候选图片清单（匹配关键词的图片路径列表）
    
    Args:
        results: OCR 处理结果列表
        output_dir: 输出目录
    """
    metadata_dir = output_dir / "metadata"
    metadata_dir.mkdir(parents=True, exist_ok=True)
    json_path = metadata_dir / "ocr_softcare_report.json"
    csv_path = metadata_dir / "ocr_softcare_report.csv"
    candidates_path = metadata_dir / "ocr_candidates.txt"

    # 构建 JSON 报告数据
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

    # 保存 JSON 报告
    json_path.write_text(json.dumps(rows, ensure_ascii=False, indent=2), encoding="utf-8")
    # 保存 CSV 摘要报告
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

    # 保存候选图片清单（仅包含匹配的图片）
    candidate_images = [result.candidate_image for result in results if result.matched and result.candidate_image]
    candidates_path.write_text("\n".join(candidate_images) + ("\n" if candidate_images else ""), encoding="utf-8")


def main() -> None:
    """OCR 筛选脚本主入口。"""
    parser = argparse.ArgumentParser(description="用 OCR 筛选疑似包含 Softcare 字样的原始图片。")
    parser.add_argument("--raw-dir", type=Path, default=DEFAULT_RAW_DIR, help="未标注原图目录")
    parser.add_argument("--output-dir", type=Path, default=DEFAULT_OUTPUT_DIR, help="OCR 输出目录")
    parser.add_argument("--keyword", action="append", dest="keywords", help="关键词，可重复传入；会与品牌库合并")
    parser.add_argument("--brand-library", type=Path, default=DEFAULT_BRAND_LIBRARY, help="品牌标识库 JSON/TXT；会自动忽略数字行和重复项")
    parser.add_argument("--no-brand-library", action="store_true", help="不读取品牌标识库，仅使用 --keyword 或默认关键词")
    parser.add_argument("--engine", choices=["rapidocr", "easyocr"], default="rapidocr", help="OCR 引擎；默认 rapidocr，速度快且无需下载 EasyOCR 检测模型")
    parser.add_argument("--languages", nargs="+", default=["en"], help="EasyOCR 语言列表，仅 --engine easyocr 时使用")
    parser.add_argument("--gpu", action="store_true", help="是否启用 EasyOCR GPU，仅 --engine easyocr 时使用；Mac MPS 通常保持关闭")
    parser.add_argument("--min-confidence", type=float, default=0.2, help="OCR 文本最低置信度")
    parser.add_argument("--fuzzy-threshold", type=int, default=60, help="关键词模糊匹配阈值，0-100")
    parser.add_argument("--limit", type=int, default=None, help="只处理前 N 张图片，便于试跑")
    parser.add_argument("--copy-candidates", action="store_true", help="是否复制命中图片到 ocr/candidates")
    args = parser.parse_args()

    # 验证参数
    if not args.raw_dir.is_dir():
        raise SystemExit(f"原图目录不存在：{args.raw_dir}")
    if not 0.0 <= args.min_confidence <= 1.0:
        raise SystemExit("--min-confidence 必须位于 0 到 1 之间。")
    if not 0 <= args.fuzzy_threshold <= 100:
        raise SystemExit("--fuzzy-threshold 必须位于 0 到 100 之间。")

    # 获取 OCR 关键词：默认读取品牌库，同时允许命令行追加关键词。
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
    keywords = unique_preserve_order(keywords or DEFAULT_KEYWORDS)
    print(f"OCR 关键词数量：{len(keywords)}，关键词：{', '.join(keywords)}")

    # 获取待处理的图片列表
    images = list_images(args.raw_dir, args.limit)
    if not images:
        raise SystemExit(f"原图目录没有图片：{args.raw_dir}")

    # 准备输出目录
    candidate_dir = args.output_dir / "candidates"
    metadata_dir = args.output_dir / "metadata"
    candidate_dir.mkdir(parents=True, exist_ok=True)
    metadata_dir.mkdir(parents=True, exist_ok=True)

    # 初始化 OCR 引擎
    reader = build_reader(args.engine, args.languages, args.gpu)
    # 逐张图片进行 OCR 识别和关键词匹配
    results: list[OcrResult] = []
    for index, image_path in enumerate(images, start=1):
        # OCR 识别
        texts = read_ocr(reader, args.engine, image_path, args.min_confidence)
        # 关键词匹配
        matched, score, keyword, matched_text = match_keywords(texts, keywords, args.fuzzy_threshold)
        candidate_image = ""
        if matched:
            candidate_image = str(image_path.resolve())
            # 如果启用复制，将匹配的图片复制到候选目录
            if args.copy_candidates:
                target = candidate_dir / image_path.name
                shutil.copy2(image_path, target)
                candidate_image = str(target.resolve())
        # 记录结果
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

    # 生成报告
    write_reports(results, args.output_dir)
    # 打印统计信息
    matched_count = sum(result.matched for result in results)
    print(f"完成：processed={len(results)}, matched={matched_count}")
    print(f"OCR 报告：{metadata_dir / 'ocr_softcare_report.csv'}")
    print(f"候选清单：{metadata_dir / 'ocr_candidates.txt'}")


if __name__ == "__main__":
    main()
