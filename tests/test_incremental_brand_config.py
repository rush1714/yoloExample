"""品牌配置与增量报告写入测试。"""

from __future__ import annotations

import csv
import json
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[1]
SCRIPTS_ROOT = PROJECT_ROOT / "scripts"
if str(SCRIPTS_ROOT) not in sys.path:
    sys.path.insert(0, str(SCRIPTS_ROOT))

from common.brand_library import BrandClass, select_brand_classes  # type: ignore[import-not-found]
from config.brand_profile import profile  # type: ignore[import-not-found]
from ocr.filter_brand_candidates import OcrReportWriter, OcrResult, OcrText  # type: ignore[import-not-found]
from pseudo_label.generate_yolo_world import PseudoReportWriter  # type: ignore[import-not-found]


class BrandSelectionTest(unittest.TestCase):
    """验证单品牌模式的类别重编号。"""

    def test_compact_single_brand_class_id(self) -> None:
        classes = [
            BrandClass(0, "softcare", "SOFTCARE", ()),
            BrandClass(1, "kleesoft", "KLEESOFT", ()),
        ]
        selected = select_brand_classes(classes, ["KLEESOFT"], compact_class_ids=True)
        self.assertEqual([(item.class_id, item.class_name) for item in selected], [(0, "kleesoft")])

    def test_modified_library_changes_profile_and_yaml(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            directory_path = Path(directory)
            library_path = directory_path / "brands.json"
            library_path.write_text(
                json.dumps({"brands": [{"class_id": 8, "name": "TESTBRAND", "aliases": ["TEST BRAND"]}]}),
                encoding="utf-8",
            )
            resolved = profile(library_path, "TESTBRAND")
            self.assertEqual(resolved["dataset_name"], "testbrand")
            data_yaml = directory_path / "testbrand.yaml"
            pseudo_yaml = directory_path / "testbrand_pseudo.yaml"
            subprocess.run(
                [
                    sys.executable,
                    str(SCRIPTS_ROOT / "config" / "write_brand_yolo_yaml.py"),
                    "--brand-library",
                    str(library_path),
                    "--data-yaml",
                    str(data_yaml),
                    "--pseudo-yaml",
                    str(pseudo_yaml),
                    "--dataset-root",
                    "../../datasets/testbrand",
                    "--brand-filter",
                    "TESTBRAND",
                    "--compact-class-ids",
                ],
                check=True,
                capture_output=True,
                text=True,
            )
            self.assertIn("  0: testbrand", data_yaml.read_text(encoding="utf-8"))
            self.assertIn("../../datasets/testbrand/pseudo", pseudo_yaml.read_text(encoding="utf-8"))


class IncrementalReportWriterTest(unittest.TestCase):
    """验证每条结果写入后所有报告都可立即读取。"""

    def test_ocr_writer_persists_each_result(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            output_dir = Path(directory)
            writer = OcrReportWriter(output_dir)
            result = OcrResult(
                image="/raw/image.jpg",
                candidate_image="/raw/image.jpg",
                matched=True,
                score=99.0,
                keyword="SOFTCARE",
                matched_text="Softcare",
                texts=[OcrText("Softcare", 0.99, [])],
            )
            writer.record(result)
            metadata_dir = output_dir / "metadata"
            self.assertEqual(json.loads((metadata_dir / "ocr_softcare_report.json").read_text(encoding="utf-8"))[0]["image"], "/raw/image.jpg")
            with (metadata_dir / "ocr_softcare_report.csv").open(encoding="utf-8") as file:
                self.assertEqual(len(list(csv.DictReader(file))), 1)
            self.assertEqual((metadata_dir / "ocr_candidates.txt").read_text(encoding="utf-8"), "/raw/image.jpg\n")

    def test_ocr_writer_resumes_and_rebuilds_summary_files(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            output_dir = Path(directory)
            writer = OcrReportWriter(output_dir)
            writer.record(
                OcrResult(
                    image="/raw/processed.jpg",
                    candidate_image="/raw/processed.jpg",
                    matched=True,
                    score=99.0,
                    keyword="SOFTCARE",
                    matched_text="Softcare",
                    texts=[OcrText("Softcare", 0.99, [])],
                )
            )
            metadata_dir = output_dir / "metadata"
            (metadata_dir / "ocr_softcare_report.csv").write_text("invalid", encoding="utf-8")
            (metadata_dir / "ocr_candidates.txt").write_text("invalid\n", encoding="utf-8")
            resumed = OcrReportWriter(output_dir, resume=True)
            self.assertEqual(resumed.completed_images, {"/raw/processed.jpg"})
            self.assertEqual(resumed.matched_count, 1)
            with (metadata_dir / "ocr_softcare_report.csv").open(encoding="utf-8") as file:
                self.assertEqual(len(list(csv.DictReader(file))), 1)
            self.assertEqual((metadata_dir / "ocr_candidates.txt").read_text(encoding="utf-8"), "/raw/processed.jpg\n")
            resumed.record(
                OcrResult(
                    image="/raw/remaining.jpg",
                    candidate_image="",
                    matched=False,
                    score=0.0,
                    keyword="",
                    matched_text="",
                    texts=[],
                )
            )
            self.assertEqual(len(json.loads((metadata_dir / "ocr_softcare_report.json").read_text(encoding="utf-8"))), 2)

    def test_pseudo_writer_persists_each_result(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            output_root = Path(directory)
            (output_root / "metadata").mkdir()
            writer = PseudoReportWriter(output_root)
            writer.record(
                {
                    "image": "/pseudo/images/train/image.jpg",
                    "label": "/pseudo/labels/train/image.txt",
                    "split": "train",
                    "box_count": 1,
                    "boxes": [],
                }
            )
            metadata_dir = output_root / "metadata"
            self.assertEqual(json.loads((metadata_dir / "pseudo_label_report.json").read_text(encoding="utf-8"))[0]["box_count"], 1)
            with (metadata_dir / "pseudo_label_report.csv").open(encoding="utf-8") as file:
                self.assertEqual(len(list(csv.DictReader(file))), 1)


if __name__ == "__main__":
    unittest.main()
