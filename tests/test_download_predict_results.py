"""EC2 批量推理结果下载脚本的纯逻辑测试。"""

# pylint: disable=import-error,wrong-import-position

from __future__ import annotations

import sys
import tempfile
import unittest
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from scripts.s3.download_predict_results import (  # noqa: E402
    image_name_for_source,
    local_result_path,
    parse_s3_uri,
    read_uri_list,
    s3_uri_join,
)


class DownloadPredictResultsTest(unittest.TestCase):
    """验证下载脚本的 S3 URI 和本地路径映射。"""

    def test_s3_uri_join_appends_relative_path(self) -> None:
        """S3 目录和相对路径应拼成完整对象地址。"""
        self.assertEqual(
            s3_uri_join("s3://bucket-a/results/run1", "json/a.json"),
            "s3://bucket-a/results/run1/json/a.json",
        )

    def test_local_result_path_keeps_prefix_relative_structure(self) -> None:
        """结果对象应按输出 S3 前缀的相对结构落到本地目录。"""
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            path = local_result_path(
                root,
                "s3://bucket-a/results/run1/annotated/a.jpg",
                "s3://bucket-a/results/run1",
            )

            self.assertEqual(path, root / "annotated" / "a.jpg")

    def test_image_name_for_source_preserves_image_suffix(self) -> None:
        """原始图片下载文件名应带序号并保留图片扩展名。"""
        self.assertEqual(image_name_for_source(3, "s3://bucket/input/a.webp"), "000003_a.webp")
        self.assertEqual(
            image_name_for_source(4, "https://cdn.example.test/file"),
            "000004_file.jpg",
        )

    def test_read_uri_list_skips_blank_and_comment_lines(self) -> None:
        """S3 记录文本读取时应忽略空行和注释。"""
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "uploaded_s3_uris.txt"
            path.write_text("# comment\n\ns3://bucket/a.json\n", encoding="utf-8")

            self.assertEqual(read_uri_list(path), ["s3://bucket/a.json"])

    def test_parse_s3_uri_rejects_missing_key(self) -> None:
        """S3 地址缺少 key 时应报错。"""
        self.assertEqual(parse_s3_uri("s3://bucket-a/a.txt").bucket, "bucket-a")
        with self.assertRaises(ValueError):
            parse_s3_uri("s3://bucket-a")


if __name__ == "__main__":
    unittest.main()
