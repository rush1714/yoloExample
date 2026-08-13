"""品牌 visual prompt 参考图导入脚本的纯逻辑单元测试。"""

from __future__ import annotations

import csv
import json
import tempfile
import unittest
from pathlib import Path

from openpyxl import Workbook

from data_import.import_visual_prompts_from_excel import (
    VisualPromptDownloadResult,
    VisualPromptImageRecord,
    completed_download_results,
    make_filename,
    read_visual_prompt_records,
    sanitize_brand_dir_name,
    target_path_for_record,
    write_reports,
)


class VisualPromptImportHelpersTest(unittest.TestCase):
    """验证 Excel 品牌参考图导入脚本中不依赖网络的核心逻辑。"""

    def test_sanitize_brand_dir_name_keeps_safe_brand_name(self) -> None:
        """品牌目录名应去除首尾空白，并保留字母、数字、下划线和连字符。"""
        self.assertEqual(sanitize_brand_dir_name(" softcare "), "softcare")
        self.assertEqual(sanitize_brand_dir_name("T-GUARD"), "T-GUARD")
        self.assertEqual(sanitize_brand_dir_name("SOFT CARE/2026"), "SOFT_CARE_2026")

    def test_sanitize_brand_dir_name_rejects_empty_value(self) -> None:
        """空品牌无法形成目录，应直接报错，避免图片落到不可追踪目录。"""
        with self.assertRaises(ValueError):
            sanitize_brand_dir_name("   ")

    def test_read_visual_prompt_records_splits_urls_and_deduplicates_globally(self) -> None:
        """读取 Excel 时应按 brand/attach_file 生成记录，并对重复 URL 做全局去重。"""
        with tempfile.TemporaryDirectory() as directory:
            excel_path = Path(directory) / "brands.xlsx"
            workbook = Workbook()
            sheet = workbook.active
            sheet.append(["brand", "attach_file", "remark"])
            sheet.append(
                [" softcare ", "https://example.com/a.png\nhttps://example.com/b.jpg", "two urls"]
            )
            sheet.append(
                [
                    "SOFT CARE/2026",
                    "https://example.com/a.png, https://example.com/c.webp",
                    "dedupe",
                ]
            )
            sheet.append(["", "https://example.com/ignored.png", "empty brand"])
            sheet.append(["maya", "not-a-url", "invalid url"])
            workbook.save(excel_path)

            records = read_visual_prompt_records(excel_path, "brand", "attach_file")

            self.assertEqual(
                records,
                [
                    VisualPromptImageRecord(2, 1, "softcare", "https://example.com/a.png"),
                    VisualPromptImageRecord(2, 2, "softcare", "https://example.com/b.jpg"),
                    VisualPromptImageRecord(3, 2, "SOFT_CARE_2026", "https://example.com/c.webp"),
                ],
            )

    def test_target_path_for_record_uses_brand_directory_and_url_index(self) -> None:
        """目标文件应落入 visual_prompts/<品牌>/，并用行号和 URL 序号避免同一行重名。"""
        record = VisualPromptImageRecord(
            row_number=12,
            url_index=2,
            brand="softcare",
            url="https://example.com/path/Z-1.png?token=abc",
        )

        self.assertEqual(make_filename(record, ".png"), "row00012_02_Z-1.png")
        self.assertEqual(
            target_path_for_record(record, Path("visual_prompts"), ".png"),
            Path("visual_prompts") / "softcare" / "row00012_02_Z-1.png",
        )

    def test_completed_download_results_detects_all_existing_images(self) -> None:
        """当 Excel 中所有参考图均已存在时，应返回 skipped 报告并避免再次联网。"""
        with tempfile.TemporaryDirectory() as directory:
            output_root = Path(directory) / "visual_prompts"
            brand_dir = output_root / "softcare"
            brand_dir.mkdir(parents=True)
            existing = brand_dir / "row00002_01_Z-1.png"
            existing.write_bytes(b"already exists")
            records = [VisualPromptImageRecord(2, 1, "softcare", "https://example.com/Z-1.png")]

            results = completed_download_results(records, output_root)

            self.assertEqual(
                results,
                [
                    VisualPromptDownloadResult(
                        row_number=2,
                        url_index=1,
                        brand="softcare",
                        url="https://example.com/Z-1.png",
                        status="skipped",
                        path=str(existing),
                    )
                ],
            )

    def test_completed_download_results_returns_none_when_any_image_missing(self) -> None:
        """只要仍有缺失文件，就应返回 None，让主流程进入下载阶段。"""
        with tempfile.TemporaryDirectory() as directory:
            output_root = Path(directory) / "visual_prompts"
            records = [VisualPromptImageRecord(2, 1, "softcare", "https://example.com/Z-1.png")]

            self.assertIsNone(completed_download_results(records, output_root))

    def test_write_reports_outputs_json_and_csv_with_brand_fields(self) -> None:
        """下载报告应同时写 JSON/CSV，并包含品牌、URL 序号、路径和错误信息。"""
        with tempfile.TemporaryDirectory() as directory:
            metadata_dir = Path(directory) / "metadata"
            results = [
                VisualPromptDownloadResult(
                    2,
                    1,
                    "softcare",
                    "https://example.com/a.png",
                    "downloaded",
                    "a.png",
                ),
                VisualPromptDownloadResult(
                    3,
                    1,
                    "maya",
                    "https://example.com/b.png",
                    "failed",
                    error="HTTP 404",
                ),
            ]

            write_reports(results, metadata_dir)

            json_rows = json.loads(
                (metadata_dir / "download_report.json").read_text(encoding="utf-8")
            )
            self.assertEqual(json_rows[0]["brand"], "softcare")
            self.assertEqual(json_rows[0]["url_index"], 1)
            with (metadata_dir / "download_report.csv").open(encoding="utf-8", newline="") as file:
                csv_rows = list(csv.DictReader(file))
            self.assertEqual(csv_rows[1]["error"], "HTTP 404")
            self.assertEqual(
                list(csv_rows[0].keys()),
                ["row_number", "url_index", "brand", "url", "status", "path", "error"],
            )


if __name__ == "__main__":
    unittest.main()
