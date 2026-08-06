"""
品牌标识库工具模块。

该模块是 OCR、YOLO-World 预标注、Label Studio 导入/导出和 YOLO YAML
生成的共同类别来源，确保多品牌多类别流程中 class_id、class_name、显示名一致。
"""

from __future__ import annotations

import json
import re
from dataclasses import dataclass
from pathlib import Path
from typing import Any

# 项目根目录
PROJECT_ROOT = Path(__file__).resolve().parents[2]
# 默认品牌标识库
DEFAULT_BRAND_LIBRARY = PROJECT_ROOT / "data" / "brand_keywords.json"
# Label Studio 标签颜色：循环使用，避免所有品牌同色。
LABEL_COLORS = [
    "#FFA500",
    "#1E90FF",
    "#2ECC71",
    "#E74C3C",
    "#9B59B6",
    "#F1C40F",
    "#16A085",
    "#E67E22",
    "#34495E",
    "#FF69B4",
    "#00CED1",
    "#8B4513",
]


@dataclass(frozen=True)
class BrandClass:
    """单个品牌类别定义。"""

    class_id: int
    class_name: str
    display_name: str
    aliases: tuple[str, ...]


def normalize_key(text: str) -> str:
    """标准化文本，用于品牌去重和映射查找。"""
    return re.sub(r"[^a-z0-9]+", "", str(text).lower())


def class_name_from_brand(text: str) -> str:
    """将品牌显示名转换为 YOLO 友好的类别名。"""
    normalized = re.sub(r"[^a-z0-9]+", "_", str(text).strip().lower()).strip("_")
    return normalized or "brand"


def is_usable_brand(text: str) -> bool:
    """判断品牌名或别名是否可用于文本匹配/类别生成。"""
    value = str(text).strip()
    if not value or value.isdigit():
        return False
    # 纯符号（例如 ★）不生成类别。
    return bool(normalize_key(value))


def unique_preserve_order(values: list[str]) -> list[str]:
    """按规范化 key 去重并保留顺序。"""
    seen: set[str] = set()
    result: list[str] = []
    for value in values:
        text = str(value).strip()
        if not is_usable_brand(text):
            continue
        key = normalize_key(text)
        if key in seen:
            continue
        seen.add(key)
        result.append(text)
    return result


def _raw_brand_items(payload: Any) -> list[dict[str, Any]]:
    """兼容 JSON 对象、JSON 列表和纯字符串列表。"""
    if isinstance(payload, dict):
        brands = payload.get("brands", [])
        if not isinstance(brands, list):
            raise ValueError("品牌标识库 JSON 的 brands 必须是列表。")
        items: list[dict[str, Any]] = []
        for item in brands:
            if isinstance(item, str):
                items.append({"name": item, "aliases": []})
            elif isinstance(item, dict):
                items.append(item)
        return items
    if isinstance(payload, list):
        return [{"name": str(item), "aliases": []} for item in payload]
    raise ValueError("品牌标识库 JSON 必须是对象或列表。")


def load_brand_classes(path: Path = DEFAULT_BRAND_LIBRARY) -> list[BrandClass]:
    """从 JSON 或文本品牌库加载启用的品牌类别。"""
    if not path.is_file():
        raise FileNotFoundError(f"品牌标识库不存在：{path}")

    if path.suffix.lower() == ".json":
        payload = json.loads(path.read_text(encoding="utf-8"))
        raw_items = _raw_brand_items(payload)
    else:
        raw_items = [{"name": line, "aliases": []} for line in path.read_text(encoding="utf-8").splitlines()]

    pending: list[dict[str, Any]] = []
    seen_keys: set[str] = set()
    used_class_names: set[str] = set()
    for item in raw_items:
        if item.get("enabled", True) is False:
            continue
        name = str(item.get("name", "")).strip()
        if not is_usable_brand(name):
            continue
        key = normalize_key(name)
        if key in seen_keys:
            continue
        seen_keys.add(key)

        aliases_value = item.get("aliases", [])
        aliases = unique_preserve_order([str(alias) for alias in aliases_value]) if isinstance(aliases_value, list) else []
        class_name = class_name_from_brand(name)
        if class_name in used_class_names:
            suffix = 2
            candidate = f"{class_name}_{suffix}"
            while candidate in used_class_names:
                suffix += 1
                candidate = f"{class_name}_{suffix}"
            class_name = candidate
        used_class_names.add(class_name)
        pending.append({"name": name, "aliases": aliases, "class_name": class_name, "class_id": item.get("class_id")})

    if not pending:
        raise ValueError(f"品牌标识库没有可用品牌：{path}")

    explicit_ids: set[int] = set()
    for item in pending:
        class_id = item.get("class_id")
        if class_id is None:
            continue
        if not isinstance(class_id, int) or class_id < 0:
            raise ValueError(f"品牌 {item['name']} 的 class_id 必须是非负整数。")
        if class_id in explicit_ids:
            raise ValueError(f"品牌标识库 class_id 重复：{class_id}")
        explicit_ids.add(class_id)

    next_id = 0
    classes: list[BrandClass] = []
    for item in pending:
        class_id = item.get("class_id")
        if class_id is None:
            while next_id in explicit_ids:
                next_id += 1
            class_id = next_id
            next_id += 1
        classes.append(
            BrandClass(
                class_id=class_id,
                class_name=item["class_name"],
                display_name=item["name"],
                aliases=tuple(item["aliases"]),
            )
        )
    return sorted(classes, key=lambda brand: brand.class_id)


def filter_brand_classes(classes: list[BrandClass], filters: list[str] | None) -> list[BrandClass]:
    """按品牌名/class_name/别名过滤类别；filters 为空时返回全部类别。"""
    if not filters:
        return classes
    allowed = {normalize_key(item) for item in filters if normalize_key(item)}
    return [
        brand
        for brand in classes
        if normalize_key(brand.display_name) in allowed
        or normalize_key(brand.class_name) in allowed
        or any(normalize_key(alias) in allowed for alias in brand.aliases)
    ]


def yolo_names(classes: list[BrandClass]) -> dict[int, str]:
    """生成 Ultralytics YAML 所需 names 映射。"""
    return {brand.class_id: brand.class_name for brand in classes}


def display_name_map(classes: list[BrandClass]) -> dict[str, BrandClass]:
    """Label Studio display_name -> BrandClass 映射，大小写无关。"""
    mapping: dict[str, BrandClass] = {}
    for brand in classes:
        mapping[normalize_key(brand.display_name)] = brand
        mapping[normalize_key(brand.class_name)] = brand
        for alias in brand.aliases:
            mapping[normalize_key(alias)] = brand
    return mapping


def class_id_map(classes: list[BrandClass]) -> dict[int, BrandClass]:
    """class_id -> BrandClass 映射。"""
    return {brand.class_id: brand for brand in classes}


def prompt_to_brand_map(classes: list[BrandClass], include_package_prompts: bool) -> dict[str, BrandClass]:
    """生成 YOLO-World prompt -> BrandClass 映射。"""
    mapping: dict[str, BrandClass] = {}
    for brand in classes:
        prompt_values = [brand.display_name, brand.class_name, *brand.aliases]
        if include_package_prompts:
            prompt_values.extend(f"{value} diaper package" for value in [brand.display_name, *brand.aliases])
            prompt_values.extend(f"{value} package" for value in [brand.display_name, *brand.aliases])
        for prompt in prompt_values:
            if is_usable_brand(prompt):
                mapping[normalize_key(prompt)] = brand
    return mapping


def label_config_xml(classes: list[BrandClass]) -> str:
    """根据品牌类别生成 Label Studio 多标签配置。"""
    labels = []
    for index, brand in enumerate(classes):
        color = LABEL_COLORS[index % len(LABEL_COLORS)]
        labels.append(f'    <Label value="{brand.display_name}" background="{color}"/>')
    labels_text = "\n".join(labels)
    return f"""
<View>
  <Image name="image" value="$image"/>
  <RectangleLabels name="bbox" toName="image">
{labels_text}
  </RectangleLabels>
  <Header value="来源行：$row_number"/>
  <Text name="source_url" value="$source_url"/>
</View>
""".strip()


def yaml_text(dataset_root: str, classes: list[BrandClass]) -> str:
    """生成 YOLO 数据集 YAML 文本。"""
    lines = [
        f"path: {dataset_root}",
        "train: images/train",
        "val: images/val",
        "test: images/test",
        "",
        "names:",
    ]
    for brand in classes:
        lines.append(f"  {brand.class_id}: {brand.class_name}")
    return "\n".join(lines) + "\n"
