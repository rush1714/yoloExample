"""S3 图片上传、Label Studio 导入和 EC2 训练图管理测试。"""

# pylint: disable=import-error,wrong-import-position,line-too-long

from __future__ import annotations
import sys
import tempfile
import unittest
from pathlib import Path
from urllib.parse import parse_qs, urlsplit

PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from scripts.ec2.s3_workflow import download_images_command
from scripts.label_studio.export_s3_single_class_to_yolo import convert_tasks as convert_s3_tasks
from scripts.label_studio.generate_s3_import import build_tasks as build_s3_import_tasks
from scripts.s3.brand_s3_config import (
    https_url_for_object,
    load_config,
    s3_key_for_relative_path,
)
from scripts.s3.upload_images_to_s3 import build_manifest_record


class BrandS3Ec2WorkflowTest(unittest.TestCase):
    """验证 S3 训练图片工作流的纯逻辑。"""

    def test_s3_key_generation_normalizes_prefix_and_relative_path(self) -> None:
        """S3 key 应清理 prefix 两端斜杠并保留子目录结构。"""
        self.assertEqual(
            s3_key_for_relative_path("/training/demo/", "nested/a b.jpg"),
            "training/demo/nested/a b.jpg",
        )
        with self.assertRaises(ValueError):
            s3_key_for_relative_path("training/demo", "../bad.jpg")

    def test_manifest_record_contains_urls(self) -> None:
        """上传清单记录应同时包含 s3、https 和 proxy 地址。"""
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory).resolve()
            image = root / "shelf 1.jpg"
            image.write_bytes(b"image")
            config = load_config(
                None,
                dataset_name="demo",
                local_images_dir=root,
                bucket="bucket-a",
                prefix="prefix/demo",
                region="ap-southeast-1",
                proxy_base_url="http://127.0.0.1:3010",
            )

            record = build_manifest_record(config, image, "shelf 1.jpg", uploaded=False)

            self.assertEqual(record["s3_uri"], "s3://bucket-a/prefix/demo/shelf 1.jpg")
            self.assertIn("bucket-a.s3.ap-southeast-1.amazonaws.com", record["https_url"])
            parsed = urlsplit(str(record["proxy_url"]))
            self.assertEqual(parsed.path, "/image")
            self.assertEqual(parse_qs(parsed.query)["dataset"], ["demo"])
            self.assertEqual(parse_qs(parsed.query)["key"], ["prefix/demo/shelf 1.jpg"])

    def test_s3_import_tasks_use_proxy_and_keep_s3_metadata(self) -> None:
        """Label Studio 任务默认用 proxy URL，同时保留 S3 元数据供后续 EC2 使用。"""
        records = [
            {
                "dataset_name": "demo",
                "image_name": "a.jpg",
                "relative_path": "a.jpg",
                "s3_bucket": "bucket-a",
                "s3_key": "prefix/a.jpg",
                "s3_uri": "s3://bucket-a/prefix/a.jpg",
                "https_url": https_url_for_object("bucket-a", "prefix/a.jpg", "ap-southeast-1"),
            }
        ]

        tasks = build_s3_import_tasks(records, "diaper", "proxy", "http://127.0.0.1:3010")

        self.assertEqual(len(tasks), 1)
        self.assertIn("http://127.0.0.1:3010/image", tasks[0]["data"]["image"])
        self.assertEqual(tasks[0]["data"]["s3_uri"], "s3://bucket-a/prefix/a.jpg")
        self.assertEqual(tasks[0]["meta"]["source"], "s3")
        self.assertNotIn("predictions", tasks[0])

    def test_s3_export_writes_labels_without_local_images(self) -> None:
        """S3 导出转换不需要本地图片文件，只写 labels 和 EC2 manifest 元数据。"""
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
                {
                    "result": [
                        {
                            "type": "rectanglelabels",
                            "value": {"x": 10, "y": 20, "width": 30, "height": 40, "rectanglelabels": ["diaper"]},
                        }
                    ]
                }
            ],
        }
        with tempfile.TemporaryDirectory() as directory:
            output_root = Path(directory).resolve()

            converted, warnings = convert_s3_tasks([task], output_root, "diaper", "latest", True)

            self.assertFalse(warnings)
            self.assertEqual(converted[0].split, "train")
            self.assertEqual(converted[0].s3_uri, "s3://bucket-a/prefix/nested/a.jpg")
            self.assertEqual((output_root / "labels" / "train" / "nested__a.txt").read_text(encoding="utf-8"), "0 0.250000 0.400000 0.300000 0.400000\n")

    def test_ec2_download_images_command_references_manifest(self) -> None:
        """EC2 dry-run 命令应包含 manifest 路径和 boto3 下载逻辑。"""
        args = type(
            "Args",
            (),
            {
                "remote_manifest_json": "datasets/s3/demo/metadata/ec2_image_manifest.json",
                "remote_dataset_root": "datasets/s3/demo",
                "ec2_project_root": "/home/ec2-user/yoloExample",
                "python_cmd": "python3",
            },
        )()

        command = download_images_command(args)

        self.assertIn("ec2_image_manifest.json", command)
        self.assertIn("boto3", command)
        self.assertIn("download_file", command)
        self.assertIn("datasets/s3/demo", command)


if __name__ == "__main__":
    unittest.main()
