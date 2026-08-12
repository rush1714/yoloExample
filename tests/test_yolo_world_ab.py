"""YOLO-World A/B 测试脚本的纯逻辑单元测试。"""

from __future__ import annotations

import json
import tempfile
import unittest
from pathlib import Path

from pseudo_label.ab_test_yolo_world import (
    ModelSummary,
    confidence_quantiles,
    sanitize_model_name,
    summarize_prediction_rows,
    write_markdown_report,
)


class YoloWorldAbHelpersTest(unittest.TestCase):
    """验证不依赖真实 YOLO 推理的报告辅助逻辑。"""

    def test_sanitize_model_name_keeps_readable_and_safe_slug(self) -> None:
        """模型路径应转成可读且适合作为输出目录名的短名称。"""
        self.assertEqual(sanitize_model_name(Path("models/yolov8m-worldv2.pt")), "yolov8m-worldv2")
        self.assertEqual(sanitize_model_name(Path(".tmp/custom model.pt")), "custom-model")
        self.assertEqual(sanitize_model_name(Path("???")), "model")

    def test_confidence_quantiles_handles_empty_and_sorted_values(self) -> None:
        """置信度分位数用于比较候选框质量，应能处理空列表和乱序输入。"""
        self.assertEqual(confidence_quantiles([]), {"p50": 0.0, "p75": 0.0, "p90": 0.0, "max": 0.0})
        self.assertEqual(
            confidence_quantiles([0.9, 0.1, 0.3, 0.5]),
            {"p50": 0.4, "p75": 0.6, "p90": 0.78, "max": 0.9},
        )

    def test_summarize_prediction_rows_counts_images_boxes_and_prompts(self) -> None:
        """汇总结果应覆盖图片数、候选框数、类别分布、提示词分布和置信度。"""
        rows = [
            {
                "image": ".tmp/a.jpg",
                "box_count": 2,
                "boxes": [
                    {"class_name": "softcare", "prompt": "SOFTCARE package", "confidence": 0.2},
                    {"class_name": "maya", "prompt": "MAYA package", "confidence": 0.8},
                ],
            },
            {"image": ".tmp/b.jpg", "box_count": 0, "boxes": []},
        ]
        summary = summarize_prediction_rows(
            "yolov8m-worldv2",
            Path("yolov8m-worldv2.pt"),
            rows,
            12.34,
        )
        self.assertEqual(summary.image_count, 2)
        self.assertEqual(summary.images_with_boxes, 1)
        self.assertEqual(summary.total_boxes, 2)
        self.assertEqual(summary.average_boxes_per_image, 1.0)
        self.assertEqual(summary.class_counts, {"maya": 1, "softcare": 1})
        self.assertEqual(summary.prompt_counts, {"MAYA package": 1, "SOFTCARE package": 1})
        self.assertEqual(summary.confidence, {"p50": 0.5, "p75": 0.65, "p90": 0.74, "max": 0.8})
        self.assertEqual(summary.elapsed_seconds, 12.34)

    def test_write_markdown_report_contains_model_table_and_manual_checklist(self) -> None:
        """Markdown 报告应能被人工复核直接使用，并附带 JSON 摘要。"""
        with tempfile.TemporaryDirectory() as directory:
            output_dir = Path(directory)
            summary = ModelSummary(
                model_name="yolov8m-worldv2",
                model_path="yolov8m-worldv2.pt",
                image_count=3,
                images_with_boxes=2,
                total_boxes=5,
                average_boxes_per_image=1.6667,
                confidence={"p50": 0.2, "p75": 0.3, "p90": 0.4, "max": 0.5},
                class_counts={"softcare": 4, "maya": 1},
                prompt_counts={"SOFTCARE package": 4, "MAYA package": 1},
                elapsed_seconds=7.0,
            )
            report_path = output_dir / "YOLO-World-A-B-测试-report.md"
            summary_path = output_dir / "summary.json"
            write_markdown_report(
                report_path=report_path,
                summary_path=summary_path,
                summaries=[summary],
                image_paths=[Path(".tmp/a.jpg"), Path(".tmp/b.jpg"), Path(".tmp/c.jpg")],
                parameters={"conf": 0.03, "imgsz": 960},
            )
            report_text = report_path.read_text(encoding="utf-8")
            self.assertIn("# YOLO-World A/B 预标注对比报告", report_text)
            self.assertIn("yolov8m-worldv2", report_text)
            self.assertIn("人工复核建议", report_text)
            summary_json = json.loads(summary_path.read_text(encoding="utf-8"))
            self.assertEqual(summary_json[0]["model_name"], "yolov8m-worldv2")


if __name__ == "__main__":
    unittest.main()
