"""Merge multiple Label Studio exports and keep only tasks with valid boxes."""

# pylint: disable=line-too-long,duplicate-code

from __future__ import annotations

import argparse
import csv
import json
from dataclasses import dataclass
from pathlib import Path


@dataclass(frozen=True)
class MergeInputSummary:
    """Summary for a single input export file."""

    path: str
    total_tasks: int
    kept_tasks: int
    skipped_without_box: int
    skipped_duplicate: int


def load_export_tasks(export_path: Path) -> list[dict[str, object]]:
    """Load Label Studio export tasks from a list or a dict containing tasks."""
    payload = json.loads(export_path.read_text(encoding="utf-8"))
    if isinstance(payload, list):
        return [item for item in payload if isinstance(item, dict)]
    if isinstance(payload, dict) and isinstance(payload.get("tasks"), list):
        return [item for item in payload["tasks"] if isinstance(item, dict)]
    raise ValueError(f"Label Studio 导出 JSON 格式不支持：{export_path}")


def select_annotation(task: dict[str, object], annotation_index: str) -> dict[str, object] | None:
    """Select the first or latest non-cancelled annotation from a task."""
    annotations = task.get("annotations")
    if not isinstance(annotations, list):
        return None
    valid = [
        item
        for item in annotations
        if isinstance(item, dict) and not item.get("was_cancelled")
    ]
    if not valid:
        return None
    return valid[0] if annotation_index == "first" else valid[-1]


def result_has_valid_box(result: dict[str, object], label_name: str | None) -> bool:
    """Return whether a result contains a rectangle label accepted by label filter."""
    if result.get("type") != "rectanglelabels":
        return False
    value = result.get("value")
    if not isinstance(value, dict):
        return False
    labels = value.get("rectanglelabels")
    if not isinstance(labels, list) or not labels:
        return False
    accepted_labels = {item.strip() for item in label_name.split(",") if item.strip()} if label_name else set()
    if accepted_labels and accepted_labels.isdisjoint({str(item) for item in labels}):
        return False
    try:
        width = float(value["width"])
        height = float(value["height"])
    except (KeyError, TypeError, ValueError):
        return False
    return width > 0 and height > 0


def task_has_valid_box(
    task: dict[str, object],
    label_name: str | None,
    annotation_index: str,
) -> bool:
    """Return whether the selected annotation has at least one valid rectangle box."""
    annotation = select_annotation(task, annotation_index)
    if annotation is None:
        return False
    results = annotation.get("result")
    if not isinstance(results, list):
        return False
    return any(
        isinstance(result, dict) and result_has_valid_box(result, label_name)
        for result in results
    )


def task_dedup_key(task: dict[str, object]) -> str:
    """Build a stable task key for cross-project deduplication."""
    data = task.get("data")
    if isinstance(data, dict):
        for key in ("local_path", "image"):
            value = data.get(key)
            if isinstance(value, str) and value:
                return f"data:{key}:{value}"
    meta = task.get("meta")
    if isinstance(meta, dict):
        value = meta.get("image_name") or meta.get("relative_path")
        if isinstance(value, str) and value:
            return f"meta:{value}"
    return f"id:{task.get('id', '')}"


def merge_tasks(
    input_paths: list[Path],
    label_name: str | None,
    annotation_index: str,
) -> tuple[list[dict[str, object]], list[MergeInputSummary]]:
    """Merge tasks from input exports, keeping valid boxed tasks and deduplicating."""
    merged: list[dict[str, object]] = []
    summaries: list[MergeInputSummary] = []
    seen_keys: set[str] = set()
    for input_path in input_paths:
        tasks = load_export_tasks(input_path)
        kept_count = 0
        skipped_without_box = 0
        skipped_duplicate = 0
        for task in tasks:
            if not task_has_valid_box(task, label_name, annotation_index):
                skipped_without_box += 1
                continue
            key = task_dedup_key(task)
            if key in seen_keys:
                skipped_duplicate += 1
                continue
            seen_keys.add(key)
            merged.append(task)
            kept_count += 1
        summaries.append(
            MergeInputSummary(
                path=str(input_path),
                total_tasks=len(tasks),
                kept_tasks=kept_count,
                skipped_without_box=skipped_without_box,
                skipped_duplicate=skipped_duplicate,
            )
        )
    return merged, summaries


def write_report(
    report_path: Path,
    input_summaries: list[MergeInputSummary],
    merged_count: int,
    label_name: str | None,
    annotation_index: str,
) -> None:
    """Write merge report as JSON and CSV."""
    report_path.parent.mkdir(parents=True, exist_ok=True)
    payload = {
        "merged_count": merged_count,
        "label_name": label_name or "",
        "annotation_index": annotation_index,
        "inputs": [summary.__dict__ for summary in input_summaries],
        "total_input_tasks": sum(summary.total_tasks for summary in input_summaries),
        "total_kept_tasks": sum(summary.kept_tasks for summary in input_summaries),
        "total_skipped_without_box": sum(
            summary.skipped_without_box for summary in input_summaries
        ),
        "total_skipped_duplicate": sum(summary.skipped_duplicate for summary in input_summaries),
    }
    report_path.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
    with report_path.with_suffix(".csv").open("w", encoding="utf-8", newline="") as file:
        writer = csv.DictWriter(
            file,
            fieldnames=[
                "path",
                "total_tasks",
                "kept_tasks",
                "skipped_without_box",
                "skipped_duplicate",
            ],
        )
        writer.writeheader()
        for summary in input_summaries:
            writer.writerow(summary.__dict__)


def parse_args() -> argparse.Namespace:
    """Parse command-line arguments."""
    parser = argparse.ArgumentParser(description="合并多个 Label Studio 导出，并仅保留有有效框的任务。")
    parser.add_argument(
        "--input",
        nargs="+",
        type=Path,
        required=True,
        help="一个或多个 Label Studio 导出 JSON",
    )
    parser.add_argument(
        "--output",
        type=Path,
        required=True,
        help="合并后的 Label Studio 导出 JSON",
    )
    parser.add_argument("--report", type=Path, required=True, help="合并报告 JSON 输出路径")
    parser.add_argument("--label-name", default="", help="可选：只保留包含该标签名的框")
    parser.add_argument(
        "--annotation-index",
        choices=["first", "latest"],
        default="latest",
        help="选择 first/latest annotation",
    )
    return parser.parse_args()


def main() -> None:
    """Merge Label Studio export files."""
    args = parse_args()
    input_paths = [path.resolve() for path in args.input]
    for path in input_paths:
        if not path.is_file():
            raise SystemExit(f"Label Studio 导出文件不存在：{path}")
    label_name = args.label_name.strip() or None
    merged, summaries = merge_tasks(input_paths, label_name, args.annotation_index)
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(merged, ensure_ascii=False, indent=2), encoding="utf-8")
    write_report(args.report, summaries, len(merged), label_name, args.annotation_index)
    print(f"合并完成：merged={len(merged)}")
    print(f"合并导出：{args.output}")
    print(f"合并报告：{args.report}")
    for summary in summaries:
        print(
            f"{Path(summary.path).name}: total={summary.total_tasks}, kept={summary.kept_tasks}, "
            f"no_box={summary.skipped_without_box}, duplicate={summary.skipped_duplicate}"
        )


if __name__ == "__main__":
    main()
