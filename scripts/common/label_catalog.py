"""通用 YOLO 标签类别配置工具。

本模块把“品牌”“纸尿裤”“本地目录单类别”“S3 单类别”等历史入口统一为
同一套标签类别模型。其它脚本只需要关心 ``LabelClass``，不再把类别名称写死
在 Makefile 或控制台菜单里。
"""

# pylint: disable=line-too-long,too-many-locals,too-many-branches,duplicate-code

from __future__ import annotations

import json
import re
from dataclasses import dataclass
from html import escape
from pathlib import Path
from typing import Any

# 项目根目录，用于给默认配置文件提供稳定位置。
PROJECT_ROOT = Path(__file__).resolve().parents[2]
# 新的通用类别配置，属于可提交 Git 的结果配置。
DEFAULT_LABEL_CATALOG = PROJECT_ROOT / "config" / "label_categories.json"
# 旧品牌库路径；仅用于兼容历史文件或首次迁移。
LEGACY_BRAND_LIBRARY = PROJECT_ROOT / "config" / "brand_keywords.json"
# Label Studio 标签颜色池，多类别时按顺序循环使用。
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
class LabelClass:
    """一个可训练/可标注的 YOLO 类别。"""

    class_id: int
    name: str
    class_name: str
    aliases: tuple[str, ...]
    enabled: bool = True
    description: str = ""

    @property
    def display_name(self) -> str:
        """兼容历史品牌工具中使用的 display_name 字段。"""
        return self.name


@dataclass(frozen=True)
class LabelSet:
    """一组可被命令或控制台选择的标签类别。"""

    name: str
    display_name: str
    description: str
    task_type: str
    classes: tuple[LabelClass, ...]


def normalize_key(text: str) -> str:
    """把用户输入、类别名、别名归一化为可比较 key。"""
    return re.sub(r"[^a-z0-9一-鿿]+", "", str(text).lower())


def class_name_from_label(text: str) -> str:
    """把显示名转换成适合 YOLO YAML 的类别名。"""
    ascii_slug = re.sub(r"[^a-z0-9]+", "_", str(text).strip().lower()).strip("_")
    if ascii_slug:
        return ascii_slug
    unicode_slug = re.sub(r"[^0-9a-zA-Z一-鿿]+", "_", str(text).strip()).strip("_")
    return unicode_slug or "label"


def dataset_slug(text: str) -> str:
    """把类别集合或多选类别转换成稳定的数据集目录片段。"""
    return class_name_from_label(text).replace("__", "_") or "dataset"


def is_usable_label(text: str) -> bool:
    """过滤空值、纯数字和纯符号，避免无意义类别进入训练配置。"""
    value = str(text).strip()
    if not value or value.isdigit():
        return False
    return bool(normalize_key(value))


def unique_preserve_order(values: list[str]) -> list[str]:
    """按归一化 key 去重，并保持用户配置顺序。"""
    seen: set[str] = set()
    result: list[str] = []
    for value in values:
        text = str(value).strip()
        if not is_usable_label(text):
            continue
        key = normalize_key(text)
        if key in seen:
            continue
        seen.add(key)
        result.append(text)
    return result


def parse_label_filters(raw_value: str | list[str] | tuple[str, ...] | None) -> list[str]:
    """解析 LABELS 参数，支持逗号、换行和重复传入。"""
    if raw_value is None:
        return []
    if isinstance(raw_value, (list, tuple)):
        parts: list[str] = []
        for item in raw_value:
            parts.extend(parse_label_filters(str(item)))
        return parts
    return [part.strip() for part in re.split(r"[,\n]", str(raw_value)) if part.strip()]


def _raw_sets(payload: Any) -> list[dict[str, Any]]:
    """兼容对象、列表和旧品牌库对象，统一取出类别集合定义。"""
    if isinstance(payload, dict) and isinstance(payload.get("sets"), list):
        return [item for item in payload["sets"] if isinstance(item, dict)]
    if isinstance(payload, dict) and isinstance(payload.get("brands"), list):
        return [
            {
                "name": "brands",
                "display_name": "品牌包装",
                "description": payload.get("description", "历史品牌类别库"),
                "task_type": "detection",
                "classes": payload["brands"],
            }
        ]
    if isinstance(payload, list):
        return [
            {
                "name": "default",
                "display_name": "默认类别",
                "description": "纯列表类别配置",
                "task_type": "detection",
                "classes": payload,
            }
        ]
    raise ValueError("类别配置必须是包含 sets/brands 的对象，或类别列表。")


def _raw_class_items(raw_classes: Any) -> list[dict[str, Any]]:
    """兼容字符串类别和对象类别。"""
    if not isinstance(raw_classes, list):
        raise ValueError("类别集合中的 classes 必须是列表。")
    items: list[dict[str, Any]] = []
    for item in raw_classes:
        if isinstance(item, str):
            items.append({"name": item, "aliases": []})
        elif isinstance(item, dict):
            items.append(item)
    return items


def _load_payload(path: Path) -> Any:
    """读取 JSON 配置并返回原始对象。"""
    if not path.is_file():
        raise FileNotFoundError(f"类别配置不存在：{path}")
    return json.loads(path.read_text(encoding="utf-8"))


def _build_label_classes(raw_classes: Any) -> tuple[LabelClass, ...]:
    """把 JSON 类别条目转换成带稳定 class_id 的 LabelClass 列表。"""
    pending: list[dict[str, Any]] = []
    seen_keys: set[str] = set()
    used_class_names: set[str] = set()
    for item in _raw_class_items(raw_classes):
        if item.get("enabled", True) is False:
            continue
        name = str(item.get("name", item.get("display_name", ""))).strip()
        if not is_usable_label(name):
            continue
        key = normalize_key(name)
        if key in seen_keys:
            continue
        seen_keys.add(key)
        aliases_value = item.get("aliases", [])
        aliases = unique_preserve_order([str(alias) for alias in aliases_value]) if isinstance(aliases_value, list) else []
        class_name = str(item.get("class_name") or item.get("slug") or class_name_from_label(name)).strip()
        class_name = class_name_from_label(class_name)
        if class_name in used_class_names:
            suffix = 2
            candidate = f"{class_name}_{suffix}"
            while candidate in used_class_names:
                suffix += 1
                candidate = f"{class_name}_{suffix}"
            class_name = candidate
        used_class_names.add(class_name)
        pending.append(
            {
                "name": name,
                "class_name": class_name,
                "aliases": aliases,
                "class_id": item.get("class_id"),
                "description": str(item.get("description", "")),
            }
        )

    if not pending:
        raise ValueError("类别集合没有可用类别。")

    explicit_ids: set[int] = set()
    for item in pending:
        class_id = item.get("class_id")
        if class_id is None:
            continue
        if not isinstance(class_id, int) or class_id < 0:
            raise ValueError(f"类别 {item['name']} 的 class_id 必须是非负整数。")
        if class_id in explicit_ids:
            raise ValueError(f"类别配置 class_id 重复：{class_id}")
        explicit_ids.add(class_id)

    next_id = 0
    classes: list[LabelClass] = []
    for item in pending:
        class_id = item.get("class_id")
        if class_id is None:
            while next_id in explicit_ids:
                next_id += 1
            class_id = next_id
            next_id += 1
        classes.append(
            LabelClass(
                class_id=class_id,
                name=item["name"],
                class_name=item["class_name"],
                aliases=tuple(item["aliases"]),
                description=item["description"],
            )
        )
    return tuple(sorted(classes, key=lambda label: label.class_id))


def load_label_sets(path: Path = DEFAULT_LABEL_CATALOG) -> list[LabelSet]:
    """读取通用类别配置；如果新文件不存在，则兼容读取旧品牌库。"""
    source_path = path if path.is_file() else LEGACY_BRAND_LIBRARY
    payload = _load_payload(source_path)
    label_sets: list[LabelSet] = []
    seen_sets: set[str] = set()
    for raw_set in _raw_sets(payload):
        name = dataset_slug(str(raw_set.get("name", "default")))
        if not name or name in seen_sets:
            continue
        seen_sets.add(name)
        classes = _build_label_classes(raw_set.get("classes", []))
        label_sets.append(
            LabelSet(
                name=name,
                display_name=str(raw_set.get("display_name") or raw_set.get("title") or name),
                description=str(raw_set.get("description", "")),
                task_type=str(raw_set.get("task_type", "detection")),
                classes=classes,
            )
        )
    if not label_sets:
        raise ValueError(f"类别配置没有可用类别集合：{source_path}")
    return label_sets


def find_label_set(label_sets: list[LabelSet], name: str) -> LabelSet:
    """按集合名或显示名查找类别集合。"""
    key = normalize_key(name or "")
    for label_set in label_sets:
        if normalize_key(label_set.name) == key or normalize_key(label_set.display_name) == key:
            return label_set
    available = ", ".join(item.name for item in label_sets)
    raise ValueError(f"未知类别列表：{name}。可选值：{available}")


def _selected_filters_cover_all_classes(label_set: LabelSet, selected: list[LabelClass]) -> bool:
    """判断显式多选结果是否已经覆盖当前类别集合的全部启用类别。"""
    return len(selected) == len(label_set.classes)


def select_label_classes(label_set: LabelSet, labels: str | list[str] | None, compact_class_ids: bool = False) -> list[LabelClass]:
    """按 LABELS 多选过滤类别；空值、历史 all 或显式全选代表全量启用类别。"""
    filters = parse_label_filters(labels)
    explicit_all = not filters or any(item.lower() == "all" for item in filters)
    if explicit_all:
        selected = list(label_set.classes)
    else:
        allowed = {normalize_key(item) for item in filters if normalize_key(item)}
        selected = [
            label
            for label in label_set.classes
            if normalize_key(label.name) in allowed
            or normalize_key(label.class_name) in allowed
            or any(normalize_key(alias) in allowed for alias in label.aliases)
        ]
    if not selected:
        raise ValueError(f"类别过滤后没有可用类别：{labels}")
    if explicit_all or _selected_filters_cover_all_classes(label_set, selected) or not compact_class_ids:
        return selected
    return [
        LabelClass(
            class_id=index,
            name=label.name,
            class_name=label.class_name,
            aliases=label.aliases,
            enabled=label.enabled,
            description=label.description,
        )
        for index, label in enumerate(selected)
    ]


def dataset_name_for_selection(label_set: LabelSet, labels: str | list[str] | None) -> str:
    """为类别集合和多选类别生成默认数据集名称。"""
    filters = parse_label_filters(labels)
    if not filters or any(item.lower() == "all" for item in filters):
        return f"{label_set.name}_all"
    selected = select_label_classes(label_set, labels, compact_class_ids=False)
    if _selected_filters_cover_all_classes(label_set, selected):
        return f"{label_set.name}_all"
    if len(filters) == 1:
        return dataset_slug(filters[0])
    joined = "_".join(dataset_slug(item) for item in filters[:4])
    suffix = "" if len(filters) <= 4 else f"_{len(filters)}classes"
    return f"{label_set.name}_{joined}{suffix}"


def display_name_map(classes: list[LabelClass]) -> dict[str, LabelClass]:
    """构造 display/class/alias 到类别对象的查找表。"""
    mapping: dict[str, LabelClass] = {}
    for label in classes:
        mapping[normalize_key(label.name)] = label
        mapping[normalize_key(label.class_name)] = label
        for alias in label.aliases:
            mapping[normalize_key(alias)] = label
    return mapping


def class_id_map(classes: list[LabelClass]) -> dict[int, LabelClass]:
    """构造 class_id 到类别对象的查找表。"""
    return {label.class_id: label for label in classes}


def yolo_names(classes: list[LabelClass]) -> dict[int, str]:
    """生成 Ultralytics YAML 的 names 字典。"""
    return {label.class_id: label.class_name for label in classes}


def yolo_yaml_text(dataset_root: str, classes: list[LabelClass]) -> str:
    """生成 Ultralytics 检测数据集 YAML 文本。"""
    lines = [
        f"path: {dataset_root}",
        "train: images/train",
        "val: images/val",
        "test: images/test",
        "",
        "names:",
    ]
    for label in classes:
        lines.append(f"  {label.class_id}: {label.class_name}")
    return "\n".join(lines) + "\n"


def label_config_xml(classes: list[LabelClass], source_fields: bool = True) -> str:
    """根据类别生成 Label Studio 矩形框 XML 配置。"""
    labels = []
    for index, label in enumerate(classes):
        color = LABEL_COLORS[index % len(LABEL_COLORS)]
        labels.append(f'    <Label value="{escape(label.name, quote=True)}" background="{color}"/>')
    field_lines = ""
    if source_fields:
        field_lines = "\n  <Header value=\"来源：$row_number $image_name\"/>\n  <Text name=\"source_url\" value=\"$source_url\"/>"
    return f"""
<View>
  <Image name="image" value="$image"/>
  <RectangleLabels name="bbox" toName="image">
{chr(10).join(labels)}
  </RectangleLabels>{field_lines}
</View>
""".strip()


def catalog_to_jsonable(label_sets: list[LabelSet]) -> dict[str, object]:
    """把内存对象转换为控制台 API 可返回的 JSON 结构。"""
    return {
        "sets": [
            {
                "name": label_set.name,
                "display_name": label_set.display_name,
                "description": label_set.description,
                "task_type": label_set.task_type,
                "classes": [
                    {
                        "class_id": label.class_id,
                        "name": label.name,
                        "class_name": label.class_name,
                        "aliases": list(label.aliases),
                        "enabled": label.enabled,
                        "description": label.description,
                    }
                    for label in label_set.classes
                ],
            }
            for label_set in label_sets
        ]
    }
