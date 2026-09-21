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
    is_existing_file,
    parse_args,
    parse_s3_uri,
    positive_worker_count,
    public_url_for_s3_uri,
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

    def test_parse_args_defaults_source_download_timeout(self) -> None:
        """下载脚本默认使用 30 秒 HTTP 原图下载超时。"""
        original_argv = sys.argv
        try:
            sys.argv = [
                "download_predict_results.py",
                "--output-s3-uri",
                "s3://bucket/results/run1",
                "--uri-list-output",
                "uris.txt",
                "--result-root",
                "outputs/predict",
                "--source-image-root",
                "datasets/demo/predict/images",
                "--report-json",
                "report.json",
                "--report-csv",
                "report.csv",
            ]
            args = parse_args()
        finally:
            sys.argv = original_argv

        self.assertEqual(args.source_download_timeout, 30)
        self.assertEqual(args.workers, 8)

    def test_positive_worker_count_clamps_to_one(self) -> None:
        """下载并发数最小应归一化为 1。"""
        self.assertEqual(positive_worker_count(0), 1)
        self.assertEqual(positive_worker_count(16), 16)

    def test_public_url_for_s3_uri_uses_object_key(self) -> None:
        """配置 public base URL 后应按 S3 key 拼接 HTTP 下载地址。"""
        self.assertEqual(
            public_url_for_s3_uri(
                "s3://bucket-a/yolo-training/predict-results/summary.json",
                "https://bucket-a.s3.af-south-1.amazonaws.com",
            ),
            "https://bucket-a.s3.af-south-1.amazonaws.com/"
            "yolo-training/predict-results/summary.json",
        )

    def test_is_existing_file_skips_only_non_empty_files(self) -> None:
        """只有已存在且非空的目标文件才会被断点续传跳过。"""
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            missing = root / "missing.txt"
            empty = root / "empty.txt"
            ready = root / "ready.txt"
            empty.write_text("", encoding="utf-8")
            ready.write_text("ok", encoding="utf-8")

            self.assertFalse(is_existing_file(missing))
            self.assertFalse(is_existing_file(empty))
            self.assertTrue(is_existing_file(ready))


if __name__ == "__main__":
    unittest.main()
