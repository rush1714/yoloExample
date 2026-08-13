"""YOLOE visual prompt 预标注脚本的纯逻辑单元测试。"""

from __future__ import annotations

import json
import tempfile
import unittest
from pathlib import Path

from common.brand_library import BrandClass
from PIL import Image
from pseudo_label.generate_yoloe_visual import (
    MODELS_DIR,
    PseudoBox,
    brand_reference_keys,
    collect_reference_prompts,
    load_reference_bbox,
    resolve_model_path,
    write_yolo_label,
)


class YoloeVisualHelpersTest(unittest.TestCase):
    """验证不依赖真实 YOLOE 推理的 visual prompt 辅助逻辑。"""

    def test_resolve_model_path_prefers_models_dir_for_bare_pt_name(self) -> None:
        """裸权重文件名应自动解析到项目 models 目录，方便 Make 参数简写。"""
        self.assertEqual(
            resolve_model_path(Path("yoloe-26s-seg.pt")),
            MODELS_DIR / "yoloe-26s-seg.pt",
        )

    def test_brand_reference_keys_include_display_class_name_and_aliases(self) -> None:
        """参考图品牌目录可用显示名、类别名或别名，并统一做规范化匹配。"""
        brand = BrandClass(
            class_id=3,
            class_name="softcare",
            display_name="SOFTCARE",
            aliases=("SOFT CARE", "Soft-Care"),
        )
        self.assertEqual(brand_reference_keys(brand), {"softcare"})

    def test_load_reference_bbox_uses_whole_image_when_no_sidecar(self) -> None:
        """参考图没有同名 JSON 时，默认整张图就是目标包装 crop。"""
        with tempfile.TemporaryDirectory() as directory:
            image_path = Path(directory) / "ref.jpg"
            Image.new("RGB", (120, 80), "white").save(image_path)

            self.assertEqual(load_reference_bbox(image_path), [0.0, 0.0, 120.0, 80.0])

    def test_load_reference_bbox_supports_dict_and_list_sidecars(self) -> None:
        """同名 JSON 可用 {bbox: [...]} 或直接数组指定参考图中的包装位置。"""
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            dict_image = root / "dict.jpg"
            list_image = root / "list.jpg"
            Image.new("RGB", (120, 80), "white").save(dict_image)
            Image.new("RGB", (120, 80), "white").save(list_image)
            dict_image.with_suffix(".json").write_text(
                json.dumps({"bbox": [1, 2, 30, 40]}),
                encoding="utf-8",
            )
            list_image.with_suffix(".json").write_text(
                json.dumps([5, 6, 70, 75]),
                encoding="utf-8",
            )

            self.assertEqual(load_reference_bbox(dict_image), [1.0, 2.0, 30.0, 40.0])
            self.assertEqual(load_reference_bbox(list_image), [5.0, 6.0, 70.0, 75.0])

    def test_collect_reference_prompts_matches_brand_dirs_and_limits_per_brand(self) -> None:
        """多品牌参考图应按品牌目录收集，并对每个品牌单独应用数量上限。"""
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            softcare_dir = root / "SOFT CARE"
            maya_dir = root / "maya"
            softcare_dir.mkdir()
            maya_dir.mkdir()
            Image.new("RGB", (20, 10), "white").save(softcare_dir / "a.jpg")
            Image.new("RGB", (30, 10), "white").save(softcare_dir / "b.jpg")
            Image.new("RGB", (40, 10), "white").save(maya_dir / "a.jpg")
            brands = [
                BrandClass(0, "softcare", "SOFTCARE", ("SOFT CARE",)),
                BrandClass(1, "maya", "MAYA", ()),
            ]

            references = collect_reference_prompts(root, brands, reference_limit=1)

            self.assertEqual(len(references), 2)
            self.assertEqual(
                [(item.brand.display_name, item.image_path.name) for item in references],
                [("SOFTCARE", "a.jpg"), ("MAYA", "a.jpg")],
            )
            self.assertEqual(references[0].bbox_xyxy, [0.0, 0.0, 20.0, 10.0])

    def test_collect_reference_prompts_reports_missing_brand_in_chinese(self) -> None:
        """缺少品牌参考图时应明确提示需要补哪个品牌目录。"""
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            root.mkdir(exist_ok=True)
            brand = BrandClass(0, "softcare", "SOFTCARE", ())

            with self.assertRaises(FileNotFoundError) as context:
                collect_reference_prompts(root, [brand])

            self.assertIn("SOFTCARE", str(context.exception))
            self.assertIn("参考图", str(context.exception))

    def test_predict_config_accepts_mps_device(self) -> None:
        """YOLOE visual prompt 配置应保留用户指定的 MPS 推理设备。"""
        from pseudo_label.generate_yoloe_visual import PredictConfig

        config = PredictConfig(0.03, 960, "mps", 0.45, 0.85, 0.45, True, 0.35, 0.80)

        self.assertEqual(config.device, "mps")

    def test_write_yolo_label_writes_expected_txt_format(self) -> None:
        """YOLOE 分支应继续输出 Label Studio 导入脚本兼容的 YOLO txt。"""
        with tempfile.TemporaryDirectory() as directory:
            label_path = Path(directory) / "labels" / "image.txt"
            box = PseudoBox(
                class_id=2,
                class_name="maya",
                display_name="MAYA",
                prompt="visual:MAYA:ref.jpg",
                confidence=0.88,
                xyxy=[1.0, 2.0, 3.0, 4.0],
                yolo=[0.1, 0.2, 0.3, 0.4],
            )

            write_yolo_label(label_path, [box])

            self.assertEqual(
                label_path.read_text(encoding="utf-8"),
                "2 0.100000 0.200000 0.300000 0.400000\n",
            )


if __name__ == "__main__":
    unittest.main()
