"""Tests for generating Label Studio imports from local image directories."""

# pylint: disable=import-error,wrong-import-position

from __future__ import annotations

import sys
import tempfile
import unittest
from pathlib import Path
from urllib.parse import parse_qs, unquote, urlsplit

PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from scripts.label_studio.generate_local_dir_import import (
    build_tasks,
    iter_image_files,
    label_config_xml,
)


class LocalDirImportTest(unittest.TestCase):
    """Validate local-directory import task generation."""

    def test_label_config_escapes_label_name(self) -> None:
        """Label names containing XML characters should be escaped."""
        xml = label_config_xml("纸尿裤 & A")
        self.assertIn('Label value="纸尿裤 &amp; A"', xml)
        self.assertIn("RectangleLabels", xml)

    def test_iter_image_files_respects_recursive_flag(self) -> None:
        """Recursive mode should include nested images, while flat mode should not."""
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory).resolve()
            (root / "b.webp").write_bytes(b"image")
            (root / "ignore.txt").write_text("not image", encoding="utf-8")
            nested = root / "nested"
            nested.mkdir()
            (nested / "a.jpg").write_bytes(b"image")

            flat = [path.name for path in iter_image_files(root, recursive=False)]
            recursive = [
                path.relative_to(root).as_posix()
                for path in iter_image_files(root, recursive=True)
            ]

            self.assertEqual(flat, ["b.webp"])
            self.assertEqual(recursive, ["b.webp", "nested/a.jpg"])

    def test_build_tasks_contains_local_file_metadata(self) -> None:
        """Generated tasks should keep both local-file URL and original local path."""
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory).resolve()
            image = root / "shelf 1.jpg"
            image.write_bytes(b"image")

            tasks = build_tasks(root, [image], "demo_dataset", None)

            self.assertEqual(len(tasks), 1)
            task = tasks[0]
            data = task["data"]
            meta = task["meta"]
            self.assertEqual(data["local_path"], str(image))
            self.assertEqual(data["image_name"], "shelf 1.jpg")
            self.assertEqual(data["relative_path"], "shelf 1.jpg")
            self.assertEqual(meta["source"], "local-dir")
            self.assertEqual(meta["dataset_name"], "demo_dataset")
            parsed = urlsplit(data["image"])
            self.assertEqual(parsed.path, "/data/local-files/")
            self.assertEqual(unquote(parse_qs(parsed.query)["d"][0]), str(image))
            self.assertNotIn("predictions", task)

    def test_build_tasks_applies_limit(self) -> None:
        """Limit should keep only the requested number of tasks."""
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory).resolve()
            images = []
            for index in range(3):
                image = root / f"{index}.png"
                image.write_bytes(b"image")
                images.append(image)

            tasks = build_tasks(root, images, "demo_dataset", 2)

            self.assertEqual(len(tasks), 2)
            self.assertEqual(tasks[0]["data"]["row_number"], "1")
            self.assertEqual(tasks[1]["data"]["row_number"], "2")


if __name__ == "__main__":
    unittest.main()
