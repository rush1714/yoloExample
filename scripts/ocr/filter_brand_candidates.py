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

# OCR 脚本需要集中承载 CLI、模型初始化和单图处理逻辑；保留局部惰性导入以避免
# 未使用的 OCR 引擎在启动时强制加载模型。
# pylint: disable=import-outside-toplevel,too-many-arguments,too-many-positional-arguments
# pylint: disable=too-many-locals,too-many-statements

import argparse
import csv
import json
import os
import re
import shutil
import sys
import threading
import warnings
from typing import Any
from concurrent.futures import ThreadPoolExecutor, as_completed
from dataclasses import dataclass
from pathlib import Path

from rapidfuzz import fuzz

# OCR 文本过短时 partial_ratio 极易误召回，例如单个 K 命中 KLEESOFT。
MIN_OCR_MATCH_TEXT_LENGTH = 4
# 非别名品牌词要求 OCR 文本覆盖品牌长度的一定比例，避免 Viva 命中 LAVITA。
MIN_KEYWORD_COVERAGE = 0.70
# 高相似但低置信度的商标 Logo OCR 仍可作为候选，因此不再简单用 score * confidence。
LOW_CONFIDENCE_PENALTY = 0.85

# 全局抑制 PyTorch 的常见无害警告（MPS pin_memory 不支持、量化 API 弃用）
warnings.filterwarnings("ignore", message=".*pin_memory.*")
warnings.filterwarnings("ignore", message=".*quantize_per_tensor.*")
warnings.filterwarnings("ignore", message=".*quantize_per_channel.*")

# 项目根目录
PROJECT_ROOT = Path(__file__).resolve().parents[2]
SCRIPTS_ROOT = PROJECT_ROOT / "scripts"
if str(SCRIPTS_ROOT) not in sys.path:
    sys.path.insert(0, str(SCRIPTS_ROOT))
# 默认原始图片目录
DEFAULT_RAW_DIR = PROJECT_ROOT / "datasets" / "multibrand" / "raw" / "images"
# 默认 OCR 输出目录
DEFAULT_OUTPUT_DIR = PROJECT_ROOT / "datasets" / "multibrand" / "ocr"
# 默认品牌标识库路径
DEFAULT_BRAND_LIBRARY = PROJECT_ROOT / "config" / "brand_keywords.json"
from common.brand_library import load_brand_classes, select_brand_classes  # type: ignore[import-not-found]

# 默认关键词列表；如果品牌库存在，会优先使用品牌库。
DEFAULT_KEYWORDS = ["softcare", "soft care"]
# 支持的图片格式后缀
IMAGE_SUFFIXES = {".bmp", ".jpeg", ".jpg", ".png", ".tif", ".tiff", ".webp"}
# 每个工作线程保存一个独立 OCR reader，避免多个线程共享模型实例导致线程安全问题。
_THREAD_LOCAL = threading.local()


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


def load_brand_library(path: Path, brand_filters: list[str] | None = None) -> list[str]:
    """从品牌库加载所选品牌及其别名，供 OCR 文本匹配使用。"""
    classes = select_brand_classes(load_brand_classes(path), brand_filters)
    if not classes:
        raise ValueError(f"品牌过滤后没有可用类别：{brand_filters}")
    values = [value for brand in classes for value in [brand.display_name, *brand.aliases]]
    return unique_preserve_order(values)


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


def get_thread_reader(engine: str, languages: list[str], gpu: bool):
    """获取当前线程专用 OCR reader，首次调用时懒加载模型。"""
    cache_key = f"reader_{engine}_{'_'.join(languages)}_{int(gpu)}"
    reader = getattr(_THREAD_LOCAL, cache_key, None)
    if reader is None:
        reader = build_reader(engine, languages, gpu)
        setattr(_THREAD_LOCAL, cache_key, reader)
    return reader


def process_image(
    image_path: Path,
    engine: str,
    languages: list[str],
    gpu: bool,
    min_confidence: float,
    keywords: list[str],
    fuzzy_threshold: int,
    candidate_dir: Path,
    copy_candidates: bool,
) -> OcrResult:
    """处理单张图片：OCR 识别、关键词匹配，并按需复制候选图片。"""
    reader = get_thread_reader(engine, languages, gpu)
    texts = read_ocr(reader, engine, image_path, min_confidence)
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


def keyword_match_score(keyword: str, text: str, confidence: float) -> float:
    """计算单个 OCR 文本与品牌关键词的稳健匹配分数。"""
    normalized_keyword = normalize_text(keyword)
    normalized_text = normalize_text(text)
    if not normalized_keyword or not normalized_text:
        return 0.0
    # 过滤极短 OCR 文本，避免 K、iv 之类短文本误命中长品牌。
    if len(normalized_text) < MIN_OCR_MATCH_TEXT_LENGTH:
        return 0.0

    coverage = len(normalized_text) / len(normalized_keyword)
    reverse_coverage = len(normalized_keyword) / len(normalized_text)
    # OCR 文本比品牌短很多时，除非是显式别名，否则不允许 partial 子串高分误召回。
    if coverage < MIN_KEYWORD_COVERAGE and normalized_keyword not in normalized_text:
        return 0.0

    # 精确包含优先；短品牌包含长文本时也要避免整段货架文字误判。
    if normalized_keyword in normalized_text and reverse_coverage >= 0.45:
        score = 100.0
    else:
        ratio_score = float(fuzz.ratio(normalized_keyword, normalized_text))
        partial_score = float(fuzz.partial_ratio(normalized_keyword, normalized_text))
        wratio_score = float(fuzz.WRatio(normalized_keyword, normalized_text))
        # partial_ratio 对短文本过于乐观，这里只给较小权重。
        score = max(ratio_score, wratio_score, partial_score * 0.85)

    # 不再直接乘 confidence，避免 KLEESOFT Logo 低置信度相似文本被压没；
    # 但低置信度仍做轻微惩罚。
    if confidence < 0.35:
        score *= LOW_CONFIDENCE_PENALTY
    return score


def match_keywords(
    texts: list[OcrText], keywords: list[str], fuzzy_threshold: int
) -> tuple[bool, float, str, str]:
    """
    在 OCR 识别文本中匹配品牌关键词。

    匹配策略：
    - 过滤长度小于 4 的 OCR 文本，减少单字符误召回。
    - 不再简单使用 partial_ratio * confidence。
    - 使用 ratio / WRatio / 降权 partial_ratio 组合。
    - 低置信度但高相似的商标 Logo 文本仍保留为候选。
    """
    best_score = 0.0
    best_keyword = ""
    best_text = ""

    for item in texts:
        for keyword in keywords:
            score = keyword_match_score(keyword, item.text, item.confidence)
            if score > best_score:
                best_score = score
                best_keyword = keyword
                best_text = item.text

    return best_score >= fuzzy_threshold, round(best_score, 2), best_keyword, best_text


def report_row(result: OcrResult) -> dict[str, Any]:
    """将单张 OCR 结果转换为 JSON 详细报告行。"""
    return {
        "image": result.image,
        "candidate_image": result.candidate_image,
        "matched": result.matched,
        "score": result.score,
        "keyword": result.keyword,
        "matched_text": result.matched_text,
        "texts": [text.__dict__ for text in result.texts],
    }


class OcrReportWriter:
    """逐图写入 OCR JSON、CSV 和候选清单，确保中断后已有结果可读取。"""

    fieldnames = [
        "image",
        "candidate_image",
        "matched",
        "score",
        "keyword",
        "matched_text",
        "text_count",
    ]

    def __init__(self, output_dir: Path, resume: bool = False) -> None:
        self.metadata_dir = output_dir / "metadata"
        self.metadata_dir.mkdir(parents=True, exist_ok=True)
        self.json_path = self.metadata_dir / "ocr_softcare_report.json"
        self.csv_path = self.metadata_dir / "ocr_softcare_report.csv"
        self.candidates_path = self.metadata_dir / "ocr_candidates.txt"
        self.rows = self._load_rows() if resume else []
        self._write_json()
        self._rewrite_summary_files()

    def _load_rows(self) -> list[dict[str, Any]]:
        """加载已有完整 JSON 报告；损坏或格式错误时拒绝继续，避免遗漏图片。"""
        if not self.json_path.exists():
            return []
        try:
            payload = json.loads(self.json_path.read_text(encoding="utf-8"))
        except json.JSONDecodeError as exc:
            raise ValueError(f"无法恢复：OCR JSON 报告格式无效：{self.json_path}") from exc
        if not isinstance(payload, list) or not all(isinstance(row, dict) for row in payload):
            raise ValueError(f"无法恢复：OCR JSON 报告必须是对象列表：{self.json_path}")
        return payload

    def _rewrite_summary_files(self) -> None:
        """依据 JSON 重建 CSV 和候选清单，保持恢复时三份报告一致。"""
        with self.csv_path.open("w", encoding="utf-8", newline="") as file:
            writer = csv.DictWriter(file, fieldnames=self.fieldnames)
            writer.writeheader()
            for row in self.rows:
                writer.writerow(
                    {
                        "image": row.get("image", ""),
                        "candidate_image": row.get("candidate_image", ""),
                        "matched": row.get("matched", False),
                        "score": row.get("score", 0),
                        "keyword": row.get("keyword", ""),
                        "matched_text": row.get("matched_text", ""),
                        "text_count": len(row.get("texts", [])),
                    }
                )
        candidate_images = [
            str(row["candidate_image"])
            for row in self.rows
            if row.get("matched") and row.get("candidate_image")
        ]
        self.candidates_path.write_text(
            "\n".join(candidate_images) + ("\n" if candidate_images else ""), encoding="utf-8"
        )

    @property
    def completed_images(self) -> set[str]:
        """返回报告中已经成功处理过的绝对图片路径。"""
        return {str(row["image"]) for row in self.rows if isinstance(row.get("image"), str)}

    @property
    def matched_count(self) -> int:
        """返回报告中当前累计的命中数量。"""
        return sum(bool(row.get("matched")) for row in self.rows)

    def _write_json(self) -> None:
        """原子替换 JSON，读取方在每次更新期间都只能看到完整 JSON。"""
        temporary_path = self.json_path.with_suffix(".json.tmp")
        temporary_path.write_text(json.dumps(self.rows, ensure_ascii=False, indent=2), encoding="utf-8")
        os.replace(temporary_path, self.json_path)

    def record(self, result: OcrResult) -> None:
        """立即持久化一张已完成图片的 OCR 结果。"""
        self.rows.append(report_row(result))
        self._write_json()
        with self.csv_path.open("a", encoding="utf-8", newline="") as file:
            csv.DictWriter(file, fieldnames=self.fieldnames).writerow(
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
        if result.matched and result.candidate_image:
            with self.candidates_path.open("a", encoding="utf-8") as file:
                file.write(f"{result.candidate_image}\n")


def write_reports(results: list[OcrResult], output_dir: Path) -> None:
    """兼容批量调用，按输入顺序逐条写入报告。"""
    writer = OcrReportWriter(output_dir)
    for result in results:
        writer.record(result)


def main() -> None:
    """OCR 筛选脚本主入口。"""
    parser = argparse.ArgumentParser(description="用 OCR 筛选疑似包含 Softcare 字样的原始图片。")
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
    parser.add_argument("--brand-filter", action="append", dest="brand_filter", help="只匹配指定品牌，可重复传入")
    parser.add_argument(
        "--engine",
        choices=["rapidocr", "easyocr"],
        default="rapidocr",
        help="OCR 引擎；默认 rapidocr，速度快且无需下载 EasyOCR 检测模型",
    )
    parser.add_argument(
        "--languages", nargs="+", default=["en"], help="EasyOCR 语言列表，仅 --engine easyocr 时使用"
    )
    parser.add_argument(
        "--gpu", action="store_true", help="是否启用 EasyOCR GPU；Mac MPS 通常保持关闭"
    )
    parser.add_argument("--min-confidence", type=float, default=0.2, help="OCR 文本最低置信度")
    parser.add_argument("--fuzzy-threshold", type=int, default=60, help="关键词模糊匹配阈值，0-100")
    parser.add_argument("--limit", type=int, default=None, help="只处理前 N 张图片，便于试跑")
    parser.add_argument("--workers", type=int, default=4, help="并发 OCR 工作线程数；1 表示串行")
    parser.add_argument("--copy-candidates", action="store_true", help="是否复制命中图片到 ocr/candidates")
    parser.add_argument("--resume", action="store_true", help="从已有 OCR JSON 报告恢复，跳过已完成图片")
    args = parser.parse_args()

    # 验证参数
    if not args.raw_dir.is_dir():
        raise SystemExit(f"原图目录不存在：{args.raw_dir}")
    if not 0.0 <= args.min_confidence <= 1.0:
        raise SystemExit("--min-confidence 必须位于 0 到 1 之间。")
    if not 0 <= args.fuzzy_threshold <= 100:
        raise SystemExit("--fuzzy-threshold 必须位于 0 到 100 之间。")
    if args.workers < 1:
        raise SystemExit("--workers 必须大于 0。")

    # 获取 OCR 关键词：默认读取品牌库，同时允许命令行追加关键词。
    keywords: list[str] = []
    if not args.no_brand_library:
        if args.brand_library.is_file():
            keywords.extend(load_brand_library(args.brand_library, args.brand_filter))
        elif args.keywords:
            # 显式传了关键词时允许品牌库不存在，便于临时测试。
            pass
        else:
            raise SystemExit(f"品牌标识库不存在：{args.brand_library}")
    keywords.extend(args.keywords or [])
    keywords = unique_preserve_order(keywords or DEFAULT_KEYWORDS)
    print(f"OCR 关键词数量：{len(keywords)}，关键词：{', '.join(keywords)}")

    # 准备输出目录和恢复报告。
    candidate_dir = args.output_dir / "candidates"
    metadata_dir = args.output_dir / "metadata"
    candidate_dir.mkdir(parents=True, exist_ok=True)
    metadata_dir.mkdir(parents=True, exist_ok=True)
    try:
        report_writer = OcrReportWriter(args.output_dir, resume=args.resume)
    except ValueError as exc:
        raise SystemExit(str(exc)) from exc

    # 获取待处理的图片列表；恢复时依据已有 JSON 跳过成功完成的图片。
    all_images = list_images(args.raw_dir, args.limit)
    if not all_images:
        raise SystemExit(f"原图目录没有图片：{args.raw_dir}")
    images = [image for image in all_images if str(image.resolve()) not in report_writer.completed_images]
    skipped_count = len(all_images) - len(images)
    if args.resume:
        print(f"恢复模式：已完成={skipped_count}，待处理={len(images)}")
    if not images:
        print(f"已全部完成：processed={len(report_writer.rows)}, matched={report_writer.matched_count}")
        return

    # 多线程逐张图片进行 OCR 识别和关键词匹配。
    # 注意：每个线程会懒加载独立 OCR reader，避免多个线程共享模型实例。
    processed_count = 0
    matched_count = report_writer.matched_count
    with ThreadPoolExecutor(max_workers=args.workers) as executor:
        future_map = {
            executor.submit(
                process_image,
                image_path,
                args.engine,
                args.languages,
                args.gpu,
                args.min_confidence,
                keywords,
                args.fuzzy_threshold,
                candidate_dir,
                args.copy_candidates,
            ): image_path
            for image_path in images
        }
        for index, future in enumerate(as_completed(future_map), start=1):
            image_path = future_map[future]
            result = future.result()
            report_writer.record(result)
            processed_count += 1
            matched_count += int(result.matched)
            status = "MATCH" if result.matched else "miss"
            print(
                f"[{index}/{len(images)}] {status} score={result.score} "
                f"keyword={result.keyword or '-'} text={result.matched_text or '-'} "
                f"image={image_path.name}"
            )

    print(f"完成：processed={len(report_writer.rows)}, matched={matched_count}")
    print(f"OCR 报告：{metadata_dir / 'ocr_softcare_report.csv'}")
    print(f"候选清单：{metadata_dir / 'ocr_candidates.txt'}")


if __name__ == "__main__":
    main()
