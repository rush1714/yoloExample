"""EC2 S3 批量推理脚本的清单解析与输出路径测试。"""

# pylint: disable=import-error,wrong-import-position,duplicate-code

from __future__ import annotations

import json
import sys
import tempfile
import unittest
from pathlib import Path

from openpyxl import Workbook

PROJECT_ROOT = Path(__file__).resolve().parents[1]

if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from scripts.ec2.s3_batch_predict import (  # noqa: E402
    PredictionPaths,
    iter_result_files,
    load_manifest_items,
    parse_args,
    write_source_image_uris,
    parse_s3_uri,
    s3_key_for_output,
)


class S3BatchPredictTest(unittest.TestCase):
    """验证批量推理清单解析的纯逻辑。"""

    def test_parse_s3_uri_requires_bucket_and_key(self) -> None:
        """S3 输出地址必须包含 bucket 和 key/prefix。"""
        location = parse_s3_uri("s3://bucket-a/results/run1")

        self.assertEqual(location.bucket, "bucket-a")
        self.assertEqual(location.key, "results/run1")
        with self.assertRaises(ValueError):
            parse_s3_uri("s3://bucket-a")

    def test_load_txt_manifest_extracts_urls_and_skips_comments(self) -> None:
        """TXT 清单应按行提取图片地址，并忽略空行和注释。"""
        with tempfile.TemporaryDirectory() as directory:
            manifest = Path(directory) / "images.txt"
            manifest.write_text(
                "# comment\n"
                "s3://bucket-a/input/a.jpg\n"
                "说明 https://cdn.example.test/b.jpg 结束\n"
                "\n"
                "s3://bucket-a/input/a.jpg\n",
                encoding="utf-8",
            )

            items = load_manifest_items(manifest)

            self.assertEqual(
                [item.source for item in items],
                ["s3://bucket-a/input/a.jpg", "https://cdn.example.test/b.jpg"],
            )

    def test_load_json_manifest_supports_s3_bucket_key_records(self) -> None:
        """JSON 对象清单应支持 s3_bucket + s3_key 组合。"""
        with tempfile.TemporaryDirectory() as directory:
            manifest = Path(directory) / "images.json"
            manifest.write_text(
                json.dumps(
                    {
                        "items": [
                            {
                                "s3_bucket": "bucket-a",
                                "s3_key": "input/a.jpg",
                                "https_url": "https://cdn.example.test/a.jpg",
                            },
                            {"image_url": "https://cdn.example.test/b.jpg"},
                        ]
                    }
                ),
                encoding="utf-8",
            )

            items = load_manifest_items(manifest)

            self.assertEqual(
                [item.source for item in items],
                ["s3://bucket-a/input/a.jpg", "https://cdn.example.test/b.jpg"],
            )
            self.assertEqual(items[0].metadata["public_url"], "https://cdn.example.test/a.jpg")

    def test_load_csv_manifest_can_use_named_column(self) -> None:
        """CSV 清单传入列名时应只读取指定图片地址列。"""
        with tempfile.TemporaryDirectory() as directory:
            manifest = Path(directory) / "images.csv"
            manifest.write_text(
                "name,image_url,remark\n"
                "a,https://cdn.example.test/a.jpg,ignore\n"
                "b,s3://bucket-a/input/b.jpg,ignore\n",
                encoding="utf-8",
            )

            items = load_manifest_items(manifest, input_column="image_url")

            self.assertEqual(
                [item.source for item in items],
                ["https://cdn.example.test/a.jpg", "s3://bucket-a/input/b.jpg"],
            )

    def test_load_xlsx_manifest_can_use_named_column(self) -> None:
        """XLSX 清单传入列名时应读取该列的图片地址。"""
        with tempfile.TemporaryDirectory() as directory:
            manifest = Path(directory) / "images.xlsx"
            workbook = Workbook()
            sheet = workbook.active
            sheet.append(["name", "整改后图片URL"])
            sheet.append(["a", "https://cdn.example.test/a.jpg"])
            sheet.append(["b", "s3://bucket-a/input/b.jpg"])
            workbook.save(manifest)

            items = load_manifest_items(manifest, input_column="整改后图片URL")

            self.assertEqual(
                [item.source for item in items],
                ["https://cdn.example.test/a.jpg", "s3://bucket-a/input/b.jpg"],
            )

    def test_s3_key_for_output_preserves_relative_structure(self) -> None:
        """结果上传 key 应保留本地结果目录中的相对结构。"""
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            file_path = root / "annotated" / "a-annotated.jpg"
            file_path.parent.mkdir()
            file_path.write_bytes(b"image")

            key = s3_key_for_output("predict-results/run1", root, file_path)

            self.assertEqual(key, "predict-results/run1/annotated/a-annotated.jpg")

    def test_iter_result_files_excludes_downloaded_images(self) -> None:
        """上传结果时不应把 EC2 本地下载缓存的原图再次上传。"""
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            paths = PredictionPaths(
                root=root,
                manifest_dir=root / "manifest",
                image_dir=root / "images",
                json_dir=root / "json",
                annotated_dir=root / "annotated",
            )
            for path in (paths.manifest_dir, paths.image_dir, paths.json_dir, paths.annotated_dir):
                path.mkdir()
            (root / "summary.json").write_text("{}", encoding="utf-8")
            (root / "summary.csv").write_text("source,status\n", encoding="utf-8")
            (root / "source_image_uris.txt").write_text(
                "s3://bucket/source.jpg\n",
                encoding="utf-8",
            )
            (paths.image_dir / "downloaded.jpg").write_bytes(b"raw")
            (paths.json_dir / "a.json").write_text("{}", encoding="utf-8")
            (paths.annotated_dir / "a-annotated.jpg").write_bytes(b"annotated")

            uploaded = [path.relative_to(root).as_posix() for path in iter_result_files(paths)]

            self.assertEqual(
                uploaded,
                [
                    "summary.json",
                    "summary.csv",
                    "source_image_uris.txt",
                    "json/a.json",
                    "annotated/a-annotated.jpg",
                ],
            )

    def test_parse_args_allows_upload_existing_without_input_or_model(self) -> None:
        """补传已有结果模式不需要清单和模型参数。"""
        original_argv = sys.argv
        try:
            sys.argv = [
                "s3_batch_predict.py",
                "--upload-existing-only",
                "--output-s3-uri",
                "s3://bucket/results/run1",
            ]
            args = parse_args()
        finally:
            sys.argv = original_argv

        self.assertTrue(args.upload_existing_only)
        self.assertEqual(args.input, "")
        self.assertEqual(args.model, "")

    def test_write_source_image_uris_records_output_sources(self) -> None:
        """原始图片来源应写入 source_image_uris.txt 供本地下载命令使用。"""
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            paths = PredictionPaths(
                root=root,
                manifest_dir=root / "manifest",
                image_dir=root / "images",
                json_dir=root / "json",
                annotated_dir=root / "annotated",
            )

            output = write_source_image_uris(
                [
                    {"source": "s3://bucket/input/a.jpg"},
                    {"source": "https://cdn.example.test/b.jpg"},
                ],
                paths,
            )

            self.assertEqual(
                output.read_text(encoding="utf-8").splitlines(),
                ["s3://bucket/input/a.jpg", "https://cdn.example.test/b.jpg"],
            )


if __name__ == "__main__":
    unittest.main()
