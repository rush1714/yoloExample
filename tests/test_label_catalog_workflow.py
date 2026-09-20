"""通用标签类别配置、导入和转换测试。"""

# pylint: disable=import-error,wrong-import-position,line-too-long,duplicate-code

from __future__ import annotations

import tempfile
import unittest
from pathlib import Path

from scripts.common.label_catalog import (
    LabelClass,
    dataset_name_for_selection,
    find_label_set,
    label_config_xml,
    load_label_sets,
    display_name_map,
    select_label_classes,
    yolo_yaml_text,
)
from scripts.label_studio.export_labels_to_yolo import convert_local_tasks, convert_s3_tasks
from scripts.label_studio.generate_label_import import records_from_local_dir


class LabelCatalogWorkflowTest(unittest.TestCase):
    """验证通用类别配置和通用 LS/YOLO 流程。"""

    def test_load_catalog_and_select_multiple_labels(self) -> None:
        """类别配置应支持自定义列表和多选类别。"""
        label_sets = load_label_sets(Path("config/label_categories.json"))
        general = find_label_set(label_sets, "general")
        selected = select_label_classes(general, "diaper", compact_class_ids=True)

        self.assertEqual([item.class_id for item in selected], [0])
        self.assertEqual([item.class_name for item in selected], ["diaper"])
        self.assertEqual(dataset_name_for_selection(general, "diaper"), "diaper")

    def test_default_catalog_only_contains_general_custom_set(self) -> None:
        """默认类别配置只应暴露通用自定义类别集合。"""
        label_sets = load_label_sets(Path("config/label_categories.json"))

        self.assertEqual([item.name for item in label_sets], ["general"])
        self.assertNotIn("brands", [item.name for item in label_sets])

    def test_selecting_every_real_label_is_treated_as_all(self) -> None:
        """控制台全选真实类别时应等价于命令行空 LABELS 的全量选择。"""
        label_sets = load_label_sets(Path("config/label_categories.json"))
        general = find_label_set(label_sets, "general")
        selected = select_label_classes(general, "diaper,allround_purple", compact_class_ids=True)

        self.assertEqual([item.class_id for item in selected], [0, 1])
        self.assertEqual(dataset_name_for_selection(general, "diaper,allround_purple"), "general_all")

    def test_web_console_does_not_offer_all_as_label_option(self) -> None:
        """控制台 LABELS 多选框只能暴露真实类别，不再暴露 all 伪选项。"""
        console = Path("web-console/server.js").read_text(encoding="utf-8")

        self.assertNotIn("['all', ...Object.values(labelsBySet)", console)
        self.assertNotIn("labelsBySet[item.name] = ['all'", console)
        self.assertIn("paramDefinitions.LABELS.options = Object.values(labelsBySet).flat()", console)

    def test_yolo_yaml_and_label_config_are_generated_from_labels(self) -> None:
        """YOLO YAML 和 LS XML 都应来自同一组 LabelClass。"""
        classes = [
            LabelClass(class_id=0, name="diaper", class_name="diaper", aliases=("纸尿裤",)),
            LabelClass(class_id=1, name="allround_purple", class_name="allround_purple", aliases=()),
        ]

        yaml_text = yolo_yaml_text("datasets/local/GH/v1/demo", classes)
        xml = label_config_xml(classes)

        self.assertIn("path: datasets/local/GH/v1/demo", yaml_text)
        self.assertIn("  0: diaper", yaml_text)
        self.assertIn("  1: allround_purple", yaml_text)
        self.assertIn('Label value="diaper"', xml)
        self.assertIn('Label value="allround_purple"', xml)

    def test_local_import_records_use_stable_relative_paths(self) -> None:
        """本地目录导入应按相对路径稳定排序并保留路径元数据。"""
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory).resolve()
            nested = root / "nested"
            nested.mkdir()
            (nested / "b.jpg").write_bytes(b"image")
            (root / "a.jpg").write_bytes(b"image")

            records = records_from_local_dir(root, recursive=True, limit=None)

            self.assertEqual([item["relative_path"] for item in records], ["a.jpg", "nested/b.jpg"])
            self.assertIn("/data/local-files/?d=", records[0]["image"])

    def test_convert_local_tasks_supports_multiple_labels(self) -> None:
        """通用本地转换应支持同一任务多类别标签。"""
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory).resolve()
            image = root / "raw.jpg"
            image.write_bytes(b"image")
            classes = [
                LabelClass(class_id=0, name="diaper", class_name="diaper", aliases=("纸尿裤",)),
                LabelClass(class_id=1, name="allround_purple", class_name="allround_purple", aliases=()),
            ]
            task = {
                "id": 1,
                "data": {"local_path": str(image)},
                "annotations": [
                    {
                        "result": [
                            {"type": "rectanglelabels", "value": {"x": 0, "y": 0, "width": 10, "height": 20, "rectanglelabels": ["diaper"]}},
                            {"type": "rectanglelabels", "value": {"x": 10, "y": 20, "width": 30, "height": 40, "rectanglelabels": ["allround_purple"]}},
                        ]
                    }
                ],
            }
            output_root = root / "dataset"
            converted, warnings = convert_local_tasks([task], output_root, display_name_map(classes), "latest", True)

            self.assertFalse(warnings)
            self.assertEqual(converted[0].class_counts, {"diaper": 1, "allround_purple": 1})
            self.assertEqual(
                (output_root / "labels" / "train" / "raw.txt").read_text(encoding="utf-8"),
                "0 0.050000 0.100000 0.100000 0.200000\n1 0.250000 0.400000 0.300000 0.400000\n",
            )

    def test_convert_s3_tasks_writes_multiclass_manifest(self) -> None:
        """通用 S3 转换应写多类别 label 并保留 EC2 manifest 字段。"""
        classes = [
            LabelClass(class_id=0, name="diaper", class_name="diaper", aliases=()),
            LabelClass(class_id=1, name="allround_purple", class_name="allround_purple", aliases=()),
        ]
        task = {
            "id": 7,
            "data": {
                "image_name": "a.jpg",
                "relative_path": "nested/a.jpg",
                "s3_bucket": "bucket-a",
                "s3_key": "prefix/nested/a.jpg",
                "s3_uri": "s3://bucket-a/prefix/nested/a.jpg",
            },
            "annotations": [
                {"result": [{"type": "rectanglelabels", "value": {"x": 10, "y": 20, "width": 30, "height": 40, "rectanglelabels": ["allround_purple"]}}]}
            ],
        }
        with tempfile.TemporaryDirectory() as directory:
            output_root = Path(directory).resolve()

            converted, warnings = convert_s3_tasks([task], output_root, display_name_map(classes), "latest", True)

            self.assertFalse(warnings)
            self.assertEqual(converted[0].training_image_name, "nested__a.jpg")
            self.assertEqual(converted[0].class_counts, {"allround_purple": 1})
            self.assertEqual((output_root / "labels" / "train" / "nested__a.txt").read_text(encoding="utf-8"), "1 0.250000 0.400000 0.300000 0.400000\n")


if __name__ == "__main__":
    unittest.main()
