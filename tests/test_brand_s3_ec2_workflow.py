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

from scripts.ec2.s3_workflow import download_images_command, validate_upload_inputs
from scripts.label_studio.export_local_s3_to_yolo import convert_local_tasks_with_s3_manifest
from scripts.label_studio.export_s3_single_class_to_yolo import convert_tasks as convert_s3_tasks
from scripts.label_studio.generate_s3_import import build_tasks as build_s3_import_tasks
from scripts.s3.brand_s3_config import (
    https_url_for_object,
    load_config,
    nginx_url_for_object,
    normalize_training_prefix,
    s3_key_for_relative_path,
)
from scripts.s3.render_nginx_image_proxy import render_config, render_map, upstream_url_for_record, write_nginx_files
from scripts.s3.upload_images_to_s3 import build_manifest_record, record_from_s3_object, upload_images, write_manifest


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

    def test_training_prefix_is_rooted_under_yolo_training(self) -> None:
        """用户业务前缀应自动归入 yolo-training 根目录。"""
        self.assertEqual(normalize_training_prefix("prefix/demo", "demo"), "yolo-training/prefix/demo")
        self.assertEqual(normalize_training_prefix("/yolo-training/demo/", "demo"), "yolo-training/demo")
        self.assertEqual(normalize_training_prefix("", "demo"), "yolo-training/demo")

    def test_manifest_record_contains_urls(self) -> None:
        """上传清单记录应同时包含 s3、https、nginx 和 proxy 地址。"""
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

            self.assertEqual(record["s3_uri"], "s3://bucket-a/yolo-training/prefix/demo/shelf 1.jpg")
            self.assertIn("bucket-a.s3.ap-southeast-1.amazonaws.com", record["https_url"])
            nginx_parsed = urlsplit(str(record["nginx_url"]))
            self.assertTrue(nginx_parsed.path.startswith("/image/demo/"))
            self.assertTrue(nginx_parsed.path.endswith(".jpg"))
            self.assertNotIn("yolo-training", nginx_parsed.path)
            parsed = urlsplit(str(record["proxy_url"]))
            self.assertEqual(parsed.path, "/image")
            self.assertEqual(parse_qs(parsed.query)["dataset"], ["demo"])
            self.assertEqual(parse_qs(parsed.query)["key"], ["yolo-training/prefix/demo/shelf 1.jpg"])

    def test_nginx_url_for_object_is_stable_short_path(self) -> None:
        """Nginx 本地 URL 应稳定、短路径化，并保留原图片扩展名。"""
        first = nginx_url_for_object("http://127.0.0.1:3010", "demo", "prefix/中文 shelf 1.jpg")
        second = nginx_url_for_object("http://127.0.0.1:3010", "demo", "prefix/中文 shelf 1.jpg")

        self.assertEqual(first, second)
        parsed = urlsplit(first)
        self.assertTrue(parsed.path.startswith("/image/demo/"))
        self.assertTrue(parsed.path.endswith(".jpg"))
        self.assertNotIn("中文", parsed.path)

    def test_upload_images_dry_run_resumes_from_existing_manifest(self) -> None:
        """dry-run 续传应跳过已有成功记录，仅计划未上传图片。"""
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory).resolve()
            image_a = root / "a.jpg"
            image_b = root / "nested" / "b.jpg"
            image_b.parent.mkdir()
            image_a.write_bytes(b"image-a")
            image_b.write_bytes(b"image-b")
            config = load_config(
                None,
                dataset_name="demo",
                local_images_dir=root,
                dataset_root=root / "dataset",
                bucket="bucket-a",
                prefix="prefix/demo",
                region="ap-southeast-1",
            )
            existing = build_manifest_record(
                config,
                image_a,
                "a.jpg",
                uploaded=True,
                extra={"status": "uploaded", "etag": "etag-a"},
            )
            write_manifest([existing], config)

            records = upload_images(config, recursive=True, limit=None, dry_run=True, workers=2)

            statuses = {str(item["relative_path"]): item["status"] for item in records}
            self.assertEqual(statuses["a.jpg"], "skipped_existing")
            self.assertEqual(statuses["nested/b.jpg"], "planned")
            self.assertTrue(records[0]["s3_key"].startswith("yolo-training/prefix/demo/"))

    def test_record_from_s3_object_marks_existing_uploaded(self) -> None:
        """从 S3 反建清单时，大小匹配的对象应被标记为已上传。"""
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory).resolve()
            image = root / "a.jpg"
            image.write_bytes(b"image-a")
            config = load_config(
                None,
                dataset_name="demo",
                local_images_dir=root,
                dataset_root=root / "dataset",
                bucket="bucket-a",
                prefix="prefix/demo",
                region="ap-southeast-1",
            )

            record = record_from_s3_object(config, image, "a.jpg", {"Size": image.stat().st_size, "ETag": '"etag"'})
            mismatch = record_from_s3_object(config, image, "a.jpg", {"Size": image.stat().st_size + 1})
            missing = record_from_s3_object(config, image, "a.jpg", None)

            self.assertTrue(record["uploaded"])
            self.assertEqual(record["status"], "s3_existing")
            self.assertFalse(mismatch["uploaded"])
            self.assertEqual(mismatch["status"], "size_mismatch")
            self.assertFalse(missing["uploaded"])
            self.assertEqual(missing["status"], "missing_on_s3")

    def test_s3_import_tasks_use_nginx_and_keep_s3_metadata(self) -> None:
        """Label Studio 任务可使用 Nginx URL，同时保留 S3 元数据供后续 EC2 使用。"""
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

        tasks = build_s3_import_tasks(records, "diaper", "nginx", "http://127.0.0.1:3010")

        self.assertEqual(len(tasks), 1)
        self.assertIn("http://127.0.0.1:3010/image/demo/", tasks[0]["data"]["image"])
        self.assertNotIn("prefix/a.jpg", tasks[0]["data"]["image"])
        self.assertEqual(tasks[0]["data"]["s3_uri"], "s3://bucket-a/prefix/a.jpg")
        self.assertEqual(tasks[0]["meta"]["source"], "s3")
        self.assertNotIn("predictions", tasks[0])

    def test_s3_import_tasks_still_support_python_proxy_mode(self) -> None:
        """旧 Python proxy 模式仍可生成 query-string 形式的图片地址。"""
        records = [
            {
                "dataset_name": "demo",
                "image_name": "a.jpg",
                "relative_path": "a.jpg",
                "s3_bucket": "bucket-a",
                "s3_key": "prefix/a.jpg",
                "s3_uri": "s3://bucket-a/prefix/a.jpg",
            }
        ]

        tasks = build_s3_import_tasks(records, "diaper", "proxy", "http://127.0.0.1:3010")

        parsed = urlsplit(str(tasks[0]["data"]["image"]))
        self.assertEqual(parsed.path, "/image")
        self.assertEqual(parse_qs(parsed.query)["key"], ["prefix/a.jpg"])

    def test_nginx_config_renderer_writes_cache_cors_and_map(self) -> None:
        """Nginx 配置应包含本地缓存、CORS 响应头和 URI 到 S3 的映射。"""
        records = [
            {
                "dataset_name": "demo",
                "s3_bucket": "bucket-a",
                "s3_key": "prefix/a.jpg",
                "https_url": "https://cdn.example.test/prefix/a.jpg",
            }
        ]
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory).resolve()
            config = load_config(None, dataset_name="demo", dataset_root=root, bucket="bucket-a", proxy_base_url="http://127.0.0.1:3010")
            routes = write_nginx_files(
                records,
                config,
                "direct",
                3600,
                "127.0.0.1",
                3010,
                root / "nginx.conf",
                root / "s3_image_map.conf",
                root / "cache",
                root / "nginx.pid",
            )

            self.assertEqual(len(routes), 1)
            self.assertEqual(upstream_url_for_record(records[0], config), "https://cdn.example.test/prefix/a.jpg")
            self.assertIn("proxy_cache_path", (root / "nginx.conf").read_text(encoding="utf-8"))
            self.assertIn("Access-Control-Allow-Origin", (root / "nginx.conf").read_text(encoding="utf-8"))
            self.assertIn("/image/demo/", (root / "s3_image_map.conf").read_text(encoding="utf-8"))
            self.assertIn("https://cdn.example.test/prefix/a.jpg", render_map(routes))
            self.assertIn("proxy_pass $s3_image_upstream", render_config("127.0.0.1", 3010, "*", root / "map.conf", root / "cache", root / "nginx.pid", root / "logs"))

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

    def test_local_ls_export_matches_s3_manifest_for_ec2_training(self) -> None:
        """本地地址 LS 导出应能通过 s3_images.json 匹配并生成 EC2 manifest 记录。"""
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory).resolve()
            image = root / "images" / "nested" / "a.jpg"
            image.parent.mkdir(parents=True)
            image.write_bytes(b"image")
            task = {
                "id": 9,
                "data": {
                    "image": f"/data/local-files/?d={image}",
                    "local_path": str(image),
                    "image_name": "a.jpg",
                    "relative_path": "nested/a.jpg",
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
            manifest_records = [
                {
                    "dataset_name": "demo",
                    "image_name": "a.jpg",
                    "relative_path": "nested/a.jpg",
                    "local_path": str(image),
                    "s3_bucket": "bucket-a",
                    "s3_key": "yolo-training/demo/nested/a.jpg",
                    "s3_uri": "s3://bucket-a/yolo-training/demo/nested/a.jpg",
                    "uploaded": True,
                }
            ]

            converted, warnings = convert_local_tasks_with_s3_manifest(
                [task], manifest_records, root / "dataset", "diaper", "latest", True, root / "images"
            )

            self.assertFalse(warnings)
            self.assertEqual(converted[0].s3_key, "yolo-training/demo/nested/a.jpg")
            self.assertEqual(converted[0].training_image_name, "nested__a.jpg")
            self.assertEqual((root / "dataset" / "labels" / "train" / "nested__a.txt").read_text(encoding="utf-8"), "0 0.250000 0.400000 0.300000 0.400000\n")

    def test_duplicate_image_name_does_not_match_ambiguously(self) -> None:
        """仅文件名重复时不能兜底匹配，避免把标注指向错误 S3 图片。"""
        task = {"id": 10, "data": {"image_name": "same.jpg"}, "annotations": [{"result": []}]}
        manifest_records = [
            {"image_name": "same.jpg", "relative_path": "a/same.jpg", "s3_bucket": "bucket-a", "s3_key": "a/same.jpg", "uploaded": True},
            {"image_name": "same.jpg", "relative_path": "b/same.jpg", "s3_bucket": "bucket-a", "s3_key": "b/same.jpg", "uploaded": True},
        ]

        converted, warnings = convert_local_tasks_with_s3_manifest([task], manifest_records, Path("/tmp/out"), "diaper", "latest", True)

        self.assertFalse(converted)
        self.assertIn("无法唯一匹配", warnings[0])

    def test_ec2_download_images_command_references_manifest(self) -> None:
        """EC2 dry-run 命令应包含 manifest 路径、字段校验和 boto3 下载逻辑。"""
        args = type(
            "Args",
            (),
            {
                "remote_manifest_json": "datasets/s3/demo/metadata/ec2_image_manifest.json",
                "remote_dataset_root": "datasets/s3/demo",
                "ec2_project_root": "/home/ec2-user/yoloExample",
                "python_cmd": "python3",
                "download_mode": "auto",
                "public_base_url": "https://cdn.example.test/base",
            },
        )()

        command = download_images_command(args)

        self.assertIn("ec2_image_manifest.json", command)
        self.assertIn("s3_images.json", command)
        self.assertIn("needs_boto3_identity", command)
        self.assertIn("urlretrieve", command)
        self.assertIn("https://cdn.example.test/base", command)
        self.assertIn("boto3", command)
        self.assertIn("download_file", command)
        self.assertIn("datasets/s3/demo", command)

    def test_ec2_public_download_mode_prefers_http_url(self) -> None:
        """public 模式应生成公共 URL 下载逻辑，不要求先具备 AWS credentials。"""
        args = type(
            "Args",
            (),
            {
                "remote_manifest_json": "datasets/s3/demo/metadata/ec2_image_manifest.json",
                "remote_dataset_root": "datasets/s3/demo",
                "ec2_project_root": "/home/ec2-user/yoloExample",
                "python_cmd": "python3",
                "download_mode": "public",
                "public_base_url": "https://cdn.example.test/base",
            },
        )()

        command = download_images_command(args)

        self.assertIn('download_mode = "public"', command)
        self.assertIn("urlretrieve", command)
        self.assertIn("source_url", command)
        self.assertIn("https_url", command)
        self.assertIn("public_base_url", command)

    def test_upload_manifest_hint_distinguishes_s3_and_ec2_manifests(self) -> None:
        """缺少 EC2 manifest 但存在上传清单时，应提示先生成标注后的 EC2 清单。"""
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory).resolve()
            dataset_root = root / "dataset"
            metadata_dir = dataset_root / "metadata"
            metadata_dir.mkdir(parents=True)
            (metadata_dir / "s3_images.json").write_text('{"items": []}', encoding="utf-8")
            args = type(
                "Args",
                (),
                {
                    "dataset_root": str(dataset_root),
                    "ec2_manifest_json": str(metadata_dir / "ec2_image_manifest.json"),
                    "ec2_manifest_csv": str(metadata_dir / "ec2_image_manifest.csv"),
                    "data_yaml": str(root / "config" / "generated" / "s3_demo.yaml"),
                },
            )()

            with self.assertRaises(SystemExit) as context:
                validate_upload_inputs(args)

            message = str(context.exception)
            self.assertIn("s3_images.json", message)
            self.assertIn("ec2_image_manifest.json", message)
            self.assertIn("2-brand-s3-workflow-after-ls", message)

    def test_makefile_contains_one_click_s3_ec2_training_target(self) -> None:
        """Makefile 应提供本地 LS 匹配 S3 清单和 S3 到 EC2 下载训练的一键入口。"""
        makefile = (PROJECT_ROOT / "makefiles" / "brand-s3-ec2" / "Makefile.mk").read_text(encoding="utf-8")

        self.assertIn("local-ls-s3-to-yolo:", makefile)
        self.assertIn("2-local-ls-s3-workflow-after-ls:", makefile)
        self.assertIn("3-brand-s3-workflow-ec2-train:", makefile)
        self.assertIn("brand-s3-ec2-upload-manifest brand-s3-ec2-download-images brand-s3-ec2-train", makefile)


if __name__ == "__main__":
    unittest.main()
