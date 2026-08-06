"""
Label Studio 导入 JSON 生成脚本。

该脚本生成 Label Studio 导入所需的 JSON 文件，用于人工复核流程：
- 从 Excel 下载报告的图片作为待复核任务
- 将 YOLO-World 伪标注结果转换为 Label Studio predictions 格式
- 使用本地文件服务路径，避免远程 CDN CORS 问题
- 支持限制任务数量（便于试跑）
"""

from __future__ import annotations

import argparse
import csv
import json
from pathlib import Path
from urllib.parse import quote
from uuid import uuid4

from PIL import Image

# 项目根目录
PROJECT_ROOT = Path(__file__).resolve().parents[1]
# 默认下载报告 CSV 路径
DEFAULT_RAW_REPORT = PROJECT_ROOT / "datasets" / "softcare" / "raw" / "metadata" / "download_report.csv"
# 默认伪标注数据根目录
DEFAULT_PSEUDO_ROOT = PROJECT_ROOT / "datasets" / "softcare" / "pseudo"
# 默认 Label Studio 导入 JSON 输出路径
DEFAULT_OUTPUT = PROJECT_ROOT / "datasets" / "softcare" / "label_studio" / "softcare_label_studio_import.json"
# 默认标签名称
DEFAULT_LABEL = "softcare_diaper"
# Label Studio 标签配置 XML
LABEL_CONFIG = """
<View>
  <Image name="image" value="$image"/>
  <RectangleLabels name="bbox" toName="image">
    <Label value="softcare_diaper" background="#FFA500"/>
  </RectangleLabels>
  <Header value="来源行：$row_number"/>
  <Text name="source_url" value="$source_url"/>
</View>
""".strip()

# 支持的图片格式后缀
IMAGE_SUFFIXES = {".bmp", ".jpeg", ".jpg", ".png", ".tif", ".tiff", ".webp"}


def load_raw_records(report_path: Path) -> dict[str, dict[str, str]]:
    """
    从下载报告 CSV 中加载成功下载的图片记录。
    
    Args:
        report_path: 下载报告 CSV 路径
    
    Returns:
        图片记录字典，键为文件名，值为包含图片信息的字典
    """
    records: dict[str, dict[str, str]] = {}
    with report_path.open(encoding="utf-8") as file:
        for row in csv.DictReader(file):
            # 只处理成功下载的记录
            if row.get("status") != "downloaded" or not row.get("path"):
                continue
            path = Path(row["path"]).resolve()
            # 使用 Label Studio 本地文件服务路径，避免远程 CDN CORS 问题
            local_file_url = f"/data/local-files/?d={quote(str(path))}"
            records[path.name] = {
                "image": local_file_url,
                "source_url": row["url"],
                "local_path": str(path),
                "row_number": row.get("row_number", ""),
            }
    return records


def label_path_for_image(image_name: str, pseudo_root: Path) -> Path | None:
    """
    查找图片对应的伪标注标签文件。
    
    在 train/val/test 三个分割中查找，返回第一个找到的标签文件。
    
    Args:
        image_name: 图片文件名
        pseudo_root: 伪标注数据根目录
    
    Returns:
        标签文件路径，如果不存在则返回 None
    """
    stem = Path(image_name).stem
    # 在三个分割中查找
    for split in ("train", "val", "test"):
        label_path = pseudo_root / "labels" / split / f"{stem}.txt"
        if label_path.is_file():
            return label_path
    return None


def image_size(local_path: str) -> tuple[int, int]:
    """
    获取图片尺寸。
    
    Args:
        local_path: 图片本地路径
    
    Returns:
        图片尺寸元组 (width, height)
    """
    with Image.open(local_path) as image:
        return image.size


def yolo_line_to_label_studio(line: str, width: int, height: int, label: str) -> dict[str, object] | None:
    """
    将 YOLO 格式的标签行转换为 Label Studio 格式。
    
    YOLO 格式：class_id center_x center_y box_width box_height（归一化值）
    Label Studio 格式：x y width height（百分比值，0-100）
    
    Args:
        line: YOLO 格式的标签行
        width: 图片宽度（像素）
        height: 图片高度（像素）
        label: 标签名称
    
    Returns:
        Label Studio 格式的标注字典，如果转换失败则返回 None
    """
    values = line.split()
    if len(values) != 5:
        return None
    class_id, center_x, center_y, box_width, box_height = values
    # 只处理类别 0（softcare_diaper）
    if class_id != "0":
        return None
    # 解析归一化坐标
    cx, cy, bw, bh = map(float, [center_x, center_y, box_width, box_height])
    # 转换为百分比坐标（0-100）
    x = max(0.0, min(100.0, (cx - bw / 2) * 100))
    y = max(0.0, min(100.0, (cy - bh / 2) * 100))
    w = max(0.0, min(100.0 - x, bw * 100))
    h = max(0.0, min(100.0 - y, bh * 100))
    if w <= 0 or h <= 0:
        return None
    # 构建 Label Studio 格式的标注
    return {
        "id": uuid4().hex[:10],
        "from_name": "bbox",
        "to_name": "image",
        "type": "rectanglelabels",
        "original_width": width,
        "original_height": height,
        "image_rotation": 0,
        "value": {
            "x": round(x, 6),
            "y": round(y, 6),
            "width": round(w, 6),
            "height": round(h, 6),
            "rotation": 0,
            "rectanglelabels": [label],
        },
    }


def load_prediction_results(image_name: str, local_path: str, pseudo_root: Path, label: str) -> list[dict[str, object]]:
    """
    加载图片的伪标注结果并转换为 Label Studio predictions 格式。
    
    Args:
        image_name: 图片文件名
        local_path: 图片本地路径
        pseudo_root: 伪标注数据根目录
        label: 标签名称
    
    Returns:
        Label Studio 格式的标注结果列表
    """
    # 查找对应的标签文件
    label_path = label_path_for_image(image_name, pseudo_root)
    if label_path is None:
        return []
    # 获取图片尺寸
    width, height = image_size(local_path)
    results = []
    # 解析标签文件中的每一行
    for line in label_path.read_text(encoding="utf-8").splitlines():
        if not line.strip():
            continue
        result = yolo_line_to_label_studio(line, width, height, label)
        if result is not None:
            results.append(result)
    return results


def build_tasks(raw_report: Path, pseudo_root: Path, label: str, limit: int | None) -> list[dict[str, object]]:
    """
    构建 Label Studio 导入任务列表。
    
    Args:
        raw_report: 下载报告 CSV 路径
        pseudo_root: 伪标注数据根目录
        label: 标签名称
        limit: 限制任务数量（用于试跑）
    
    Returns:
        Label Studio 任务列表
    """
    # 加载图片记录
    records = load_raw_records(raw_report)
    tasks: list[dict[str, object]] = []
    # 遍历每张图片构建任务
    for image_name in sorted(records):
        record = records[image_name]
        # 加载伪标注结果
        predictions = load_prediction_results(image_name, record["local_path"], pseudo_root, label)
        # 构建任务字典
        task: dict[str, object] = {
            "data": {
                "image": record["image"],
                "source_url": record["source_url"],
                "local_path": record["local_path"],
                "row_number": record["row_number"],
            },
            "meta": {
                "source": "softcare-yolo-demo",
                "image_name": image_name,
                "has_pseudo_label": bool(label_path_for_image(image_name, pseudo_root)),
            },
        }
        # 如果有伪标注，添加到 predictions 字段
        if predictions:
            task["predictions"] = [
                {
                    "model_version": "yolo-world-pseudo-label",
                    "score": 0.5,
                    "result": predictions,
                }
            ]
        tasks.append(task)
        # 检查是否达到限制
        if limit is not None and len(tasks) >= limit:
            break
    return tasks


def write_import_file(tasks: list[dict[str, object]], output_path: Path) -> None:
    """
    将任务列表写入 Label Studio 导入 JSON 文件。
    
    Args:
        tasks: 任务列表
        output_path: 输出文件路径
    """
    output_path.parent.mkdir(parents=True, exist_ok=True)
    output_path.write_text(json.dumps(tasks, ensure_ascii=False, indent=2), encoding="utf-8")


def main() -> None:
    """Label Studio 导入 JSON 生成脚本主入口。"""
    parser = argparse.ArgumentParser(description="生成 Label Studio 图片检测任务导入 JSON。")
    parser.add_argument("--raw-report", type=Path, default=DEFAULT_RAW_REPORT, help="Excel 图片下载报告 CSV")
    parser.add_argument("--pseudo-root", type=Path, default=DEFAULT_PSEUDO_ROOT, help="YOLO 伪标注数据根目录")
    parser.add_argument("--output", type=Path, default=DEFAULT_OUTPUT, help="Label Studio 导入 JSON 输出路径")
    parser.add_argument("--label", default=DEFAULT_LABEL, help="Label Studio 矩形框标签名")
    parser.add_argument("--limit", type=int, default=None, help="仅生成前 N 个任务，便于试跑")
    args = parser.parse_args()

    # 构建任务列表
    tasks = build_tasks(args.raw_report, args.pseudo_root, args.label, args.limit)
    # 写入导入文件
    write_import_file(tasks, args.output)
    # 统计信息
    prediction_tasks = sum(1 for task in tasks if task.get("predictions"))
    prediction_boxes = sum(
        len(prediction["result"])
        for task in tasks
        for prediction in task.get("predictions", [])
    )
    print(f"Label Studio 导入 JSON：{args.output}")
    print(f"tasks={len(tasks)}, tasks_with_predictions={prediction_tasks}, prediction_boxes={prediction_boxes}")


if __name__ == "__main__":
    main()
