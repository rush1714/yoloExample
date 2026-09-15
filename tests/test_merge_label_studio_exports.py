"""Tests for merging Label Studio exports."""

# pylint: disable=import-error,wrong-import-position

from __future__ import annotations

import json
import sys
import tempfile
import unittest
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from scripts.label_studio.merge_label_studio_exports import load_export_tasks, merge_tasks


def rectangle_result(labels: list[str]) -> dict[str, object]:
    """Build a minimal rectangle label result."""
    return {
        "type": "rectanglelabels",
        "value": {"x": 1, "y": 2, "width": 30, "height": 40, "rectanglelabels": labels},
    }


def task(task_id: int, image: str, labels: list[str] | None) -> dict[str, object]:
    """Build a compact Label Studio task fixture."""
    result = []
    if labels is not None:
        result.append(rectangle_result(labels))
    return {
        "id": task_id,
        "data": {"image": image, "local_path": image},
        "annotations": [{"result": result}],
    }


class MergeLabelStudioExportsTest(unittest.TestCase):
    """Validate Label Studio export merge behavior."""

    def test_load_export_tasks_accepts_list_and_tasks_object(self) -> None:
        """The loader should support both common Label Studio export shapes."""
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            list_path = root / "list.json"
            object_path = root / "object.json"
            list_path.write_text(json.dumps([task(1, "/a.jpg", ["diaper"])]), encoding="utf-8")
            object_path.write_text(
                json.dumps({"tasks": [task(2, "/b.jpg", ["diaper"])]}),
                encoding="utf-8",
            )

            self.assertEqual(len(load_export_tasks(list_path)), 1)
            self.assertEqual(len(load_export_tasks(object_path)), 1)

    def test_merge_keeps_only_valid_label_boxes(self) -> None:
        """Only tasks with a matching rectangle label should be kept."""
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            export_path = root / "project.json"
            export_path.write_text(
                json.dumps(
                    [
                        task(1, "/a.jpg", ["diaper"]),
                        task(2, "/b.jpg", None),
                        task(3, "/c.jpg", ["other"]),
                    ]
                ),
                encoding="utf-8",
            )

            merged, summaries = merge_tasks([export_path], "diaper", "latest")

            self.assertEqual([item["id"] for item in merged], [1])
            self.assertEqual(summaries[0].total_tasks, 3)
            self.assertEqual(summaries[0].kept_tasks, 1)
            self.assertEqual(summaries[0].skipped_without_box, 2)

    def test_merge_deduplicates_by_input_order(self) -> None:
        """When duplicate images exist, the earlier export should win."""
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            first = root / "first.json"
            second = root / "second.json"
            first.write_text(json.dumps([task(1, "/same.jpg", ["diaper"])]), encoding="utf-8")
            second.write_text(
                json.dumps([
                    task(2, "/same.jpg", ["diaper"]),
                    task(3, "/new.jpg", ["diaper"]),
                ]),
                encoding="utf-8",
            )

            merged, summaries = merge_tasks([first, second], "diaper", "latest")

            self.assertEqual([item["id"] for item in merged], [1, 3])
            self.assertEqual(summaries[1].skipped_duplicate, 1)

    def test_merge_accepts_any_label_when_label_filter_is_empty(self) -> None:
        """Without label filter, any non-empty rectangle label should be valid."""
        with tempfile.TemporaryDirectory() as directory:
            export_path = Path(directory) / "project.json"
            export_path.write_text(json.dumps([task(1, "/a.jpg", ["other"])]), encoding="utf-8")

            merged, _summaries = merge_tasks([export_path], None, "latest")

            self.assertEqual(len(merged), 1)


if __name__ == "__main__":
    unittest.main()
