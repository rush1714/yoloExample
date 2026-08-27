"""汇总 Ultralytics 训练结果并归档关键产物。"""

from __future__ import annotations

import argparse
import csv
import shutil
from pathlib import Path
from typing import Any

PLOT_SUFFIXES = {".png", ".jpg", ".jpeg"}
REVIEW_CATEGORIES = (
    "false_positive",
    "false_negative",
    "wrong_class",
    "duplicate_box",
    "bad_image",
    "annotation_issue",
    "ok",
)


def copy_if_exists(source: Path, target: Path) -> bool:
    """如果源文件存在则复制到目标路径。"""
    if not source.is_file():
        return False
    target.parent.mkdir(parents=True, exist_ok=True)
    shutil.copy2(source, target)
    return True


def parse_float(value: str | None) -> float | None:
    """把 CSV 指标值解析为 float；空值或非法值返回 None。"""
    if value is None or value == "":
        return None
    try:
        return float(value)
    except ValueError:
        return None


def load_best_metrics(results_csv: Path) -> dict[str, Any]:
    """读取 Ultralytics results.csv，并按 mAP50-95 或 mAP50 选择最佳 epoch。"""
    if not results_csv.is_file():
        return {}
    with results_csv.open(encoding="utf-8") as file:
        rows = list(csv.DictReader(file))
    if not rows:
        return {}

    metric_keys = [
        "metrics/mAP50-95(B)",
        "metrics/mAP50(B)",
        "metrics/precision(B)",
        "metrics/recall(B)",
    ]

    def score(row: dict[str, str]) -> float:
        for key in metric_keys:
            value = parse_float(row.get(key))
            if value is not None:
                return value
        return -1.0

    best = max(rows, key=score)
    return {
        "rows": len(rows),
        "best_epoch": best.get("epoch", ""),
        "precision": best.get("metrics/precision(B)", ""),
        "recall": best.get("metrics/recall(B)", ""),
        "mAP50": best.get("metrics/mAP50(B)", ""),
        "mAP50_95": best.get("metrics/mAP50-95(B)", ""),
        "box_loss": best.get("train/box_loss", ""),
        "cls_loss": best.get("train/cls_loss", ""),
        "dfl_loss": best.get("train/dfl_loss", ""),
    }


def count_dataset_images(dataset_root: Path) -> dict[str, int]:
    """统计 train/val/test 图片数量。"""
    counts: dict[str, int] = {}
    for split in ("train", "val", "test"):
        image_dir = dataset_root / "images" / split
        counts[split] = sum(1 for path in image_dir.rglob("*") if path.is_file()) if image_dir.is_dir() else 0
    counts["total"] = sum(counts.values())
    return counts


def copy_training_artifacts(run_dir: Path, artifact_dir: Path) -> list[str]:
    """复制训练权重、指标表和图表到归档目录。"""
    copied: list[str] = []
    for name in ("best.pt", "last.pt"):
        if copy_if_exists(run_dir / "weights" / name, artifact_dir / "weights" / name):
            copied.append(f"weights/{name}")
    for name in ("results.csv", "args.yaml"):
        if copy_if_exists(run_dir / name, artifact_dir / "metrics" / name):
            copied.append(f"metrics/{name}")
    for path in run_dir.iterdir() if run_dir.is_dir() else []:
        if path.is_file() and path.suffix.lower() in PLOT_SUFFIXES:
            if copy_if_exists(path, artifact_dir / "plots" / path.name):
                copied.append(f"plots/{path.name}")
    return copied


def prepare_review_dirs(artifact_dir: Path) -> None:
    """创建人工复核问题类型目录。"""
    for category in REVIEW_CATEGORIES:
        (artifact_dir / "review" / category).mkdir(parents=True, exist_ok=True)


def write_summary(
    artifact_dir: Path,
    run_dir: Path,
    dataset_root: Path,
    dataset_yaml: Path,
    profile: str,
    model: str,
    imgsz: int,
    epochs: int,
    batch: str,
    device: str,
    copied: list[str],
    notes: str,
) -> None:
    """写 evaluation-summary.md。"""
    metrics = load_best_metrics(run_dir / "results.csv")
    counts = count_dataset_images(dataset_root)
    lines = [
        "# 纸尿裤大类训练评估摘要",
        "",
        "## 训练配置",
        "",
        f"- profile: `{profile}`",
        f"- model: `{model}`",
        f"- imgsz: `{imgsz}`",
        f"- epochs: `{epochs}`",
        f"- batch: `{batch}`",
        f"- device: `{device}`",
        f"- run_dir: `{run_dir}`",
        f"- dataset_yaml: `{dataset_yaml}`",
        f"- dataset_root: `{dataset_root}`",
        f"- dataset_images: train={counts['train']}, val={counts['val']}, test={counts['test']}, total={counts['total']}`",
        "",
        "## 最佳指标",
        "",
    ]
    if metrics:
        lines.extend(
            [
                f"- best_epoch: `{metrics.get('best_epoch', '')}`",
                f"- precision(B): `{metrics.get('precision', '')}`",
                f"- recall(B): `{metrics.get('recall', '')}`",
                f"- mAP50(B): `{metrics.get('mAP50', '')}`",
                f"- mAP50-95(B): `{metrics.get('mAP50_95', '')}`",
                f"- train/box_loss: `{metrics.get('box_loss', '')}`",
                f"- train/cls_loss: `{metrics.get('cls_loss', '')}`",
                f"- train/dfl_loss: `{metrics.get('dfl_loss', '')}`",
            ]
        )
    else:
        lines.append("- 未找到 `results.csv`，请确认训练是否完成或 run 目录是否正确。")
    lines.extend(
        [
            "",
            "## 已归档关键产物",
            "",
            *(f"- `{item}`" for item in copied),
            "",
            "## 人工复核问题分类",
            "",
            "请把预测可视化或人工复核样例复制到以下目录，按问题类型沉淀：",
            "",
            "- `review/false_positive/`：误检",
            "- `review/false_negative/`：漏检",
            "- `review/wrong_class/`：类别错误（当前单类通常较少）",
            "- `review/duplicate_box/`：重复框",
            "- `review/bad_image/`：图片质量问题",
            "- `review/annotation_issue/`：标注规范或标注错误",
            "- `review/ok/`：效果可接受样例",
            "",
            "## 备注",
            "",
            notes or "首轮 PoC 建议只使用 300~500 张有效标注图，先验证闭环、暴露标注规范/类别设计/图片质量问题，再扩大数据量。",
            "",
        ]
    )
    artifact_dir.mkdir(parents=True, exist_ok=True)
    (artifact_dir / "evaluation-summary.md").write_text("\n".join(lines), encoding="utf-8")


def main() -> None:
    """命令行入口。"""
    parser = argparse.ArgumentParser(description="汇总 YOLO 训练结果并归档关键产物。")
    parser.add_argument("--run-dir", type=Path, required=True, help="Ultralytics 训练 run 目录")
    parser.add_argument("--export-model", type=Path, default=None, help="可选：固定导出的 best.pt 路径，也归档到 weights")
    parser.add_argument("--dataset-root", type=Path, required=True, help="数据集根目录")
    parser.add_argument("--dataset-yaml", type=Path, required=True, help="数据集 YAML 路径")
    parser.add_argument("--artifact-dir", type=Path, required=True, help="归档输出目录")
    parser.add_argument("--profile", default="custom", help="训练档位：smoke/baseline/improve/custom")
    parser.add_argument("--model", default="", help="训练模型")
    parser.add_argument("--imgsz", type=int, default=960, help="训练尺寸")
    parser.add_argument("--epochs", type=int, default=100, help="训练轮数")
    parser.add_argument("--batch", default="", help="batch 大小")
    parser.add_argument("--device", default="", help="训练设备")
    parser.add_argument("--notes", default="", help="写入摘要的补充备注")
    args = parser.parse_args()

    artifact_dir = args.artifact_dir.resolve()
    copied = copy_training_artifacts(args.run_dir.resolve(), artifact_dir)
    if args.export_model is not None and copy_if_exists(args.export_model.resolve(), artifact_dir / "weights" / "exported-best.pt"):
        copied.append("weights/exported-best.pt")
    prepare_review_dirs(artifact_dir)
    write_summary(
        artifact_dir=artifact_dir,
        run_dir=args.run_dir.resolve(),
        dataset_root=args.dataset_root.resolve(),
        dataset_yaml=args.dataset_yaml,
        profile=args.profile,
        model=args.model,
        imgsz=args.imgsz,
        epochs=args.epochs,
        batch=args.batch,
        device=args.device,
        copied=copied,
        notes=args.notes,
    )
    print(f"评估摘要：{artifact_dir / 'evaluation-summary.md'}")
    print(f"归档目录：{artifact_dir}")


if __name__ == "__main__":
    main()
