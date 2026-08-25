"""纸尿裤大类与 EC2 工作流测试。"""

from __future__ import annotations

import json
import tempfile
import unittest
from pathlib import Path

from scripts.config.write_single_class_yolo_yaml import yaml_text
from scripts.label_studio.export_single_class_to_yolo import convert_tasks, result_to_yolo_line
from scripts.label_studio.generate_single_class_import import build_tasks, label_config_xml
from scripts.cloud.ec2_diaper_workflow import quote_cmd, rsync_ssh_arg, ssh_target


class DiaperCategoryWorkflowTest(unittest.TestCase):
    """验证纸尿裤大类流程的纯逻辑。"""

    def test_single_class_yaml_contains_chinese_label(self) -> None:
        """单类别 YAML 应只生成 class_id=0 的纸尿裤。"""
        text = yaml_text("../../datasets/diaper_category/ghana/v20260812", "纸尿裤")
        self.assertIn("path: ../../datasets/diaper_category/ghana/v20260812", text)
        self.assertIn("  0: 纸尿裤", text)

    def test_single_class_label_config_has_no_brand_dependency(self) -> None:
        """Label Studio 标签配置应直接使用纸尿裤标签。"""
        xml = label_config_xml("纸尿裤")
        self.assertIn('Label value="纸尿裤"', xml)
        self.assertIn("RectangleLabels", xml)

    def test_import_tasks_do_not_include_predictions(self) -> None:
        """新流程只导入原图，不应携带任何 pseudo-label predictions。"""
        records = [
            {
                "image": "/data/local-files/?d=/tmp/a.jpg",
                "source_url": "https://example.test/a.jpg",
                "local_path": "/tmp/a.jpg",
                "row_number": "2",
                "image_name": "a.jpg",
            }
        ]
        tasks = build_tasks(records, "diaper_category_ghana_v1", None)
        self.assertNotIn("predictions", tasks[0])
        self.assertFalse(tasks[0]["meta"]["has_pseudo_label"])

    def test_export_rectangle_to_yolo_class_zero(self) -> None:
        """纸尿裤矩形框应转为 class_id=0 的 YOLO 行。"""
        result = {
            "type": "rectanglelabels",
            "value": {"x": 10, "y": 20, "width": 30, "height": 40, "rectanglelabels": ["纸尿裤"]},
        }
        self.assertEqual(result_to_yolo_line(result, "纸尿裤"), "0 0.250000 0.400000 0.300000 0.400000")

    def test_convert_tasks_writes_images_and_labels(self) -> None:
        """LS 导出任务应被转换为 images/labels 训练数据。"""
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            image_path = root / "raw.jpg"
            image_path.write_bytes(b"image")
            task = {
                "id": 1,
                "data": {"local_path": str(image_path)},
                "annotations": [
                    {
                        "result": [
                            {
                                "type": "rectanglelabels",
                                "value": {"x": 0, "y": 0, "width": 10, "height": 20, "rectanglelabels": ["纸尿裤"]},
                            }
                        ]
                    }
                ],
            }
            output_root = root / "dataset"
            for kind in ("images", "labels"):
                for split in ("train", "val", "test"):
                    (output_root / kind / split).mkdir(parents=True)
            converted, warnings = convert_tasks([task], output_root, "纸尿裤", "latest", True)
            self.assertFalse(warnings)
            self.assertEqual(converted[0].box_count, 1)
            self.assertEqual((output_root / "labels" / "train" / "raw.txt").read_text(encoding="utf-8"), "0 0.050000 0.100000 0.100000 0.200000\n")

    def test_ec2_command_helpers_quote_connection_options(self) -> None:
        """EC2 dry-run 命令应正确拼接 SSH 目标和 rsync ssh 参数。"""
        self.assertEqual(ssh_target("ubuntu", "ec2.example"), "ubuntu@ec2.example")
        self.assertIn("-i", rsync_ssh_arg(2222, "~/key.pem"))
        self.assertEqual(quote_cmd(["ssh", "ubuntu@host", "echo ok"]), "ssh ubuntu@host 'echo ok'")


if __name__ == "__main__":
    unittest.main()
