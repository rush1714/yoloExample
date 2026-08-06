# 多品牌多类别 YOLO / Label Studio 改造计划

## 目标

把当前单类别 `softcare_diaper` 流程改造成基于 `data/brand_keywords.json` 的多品牌多类别流程：

1. 品牌库定义类别体系。
2. OCR 用全品牌库筛选候选图片。
3. YOLO-World 预标注为每个品牌生成对应类别 ID，而不是全部写成 `softcare_diaper`。
4. Label Studio 配置自动生成多个 `<Label>`。
5. Label Studio 导入 predictions 保留多品牌类别。
6. Label Studio 导出转 YOLO 时按多类别写标签。
7. `data/softcare.yaml` / `data/softcare_pseudo.yaml` 更新为多类别 names。
8. Make 参数和文档同步更新。
9. 完成编译、dry-run、小样本转换/预标注验证。

## 类别体系设计

### 品牌库作为唯一类别来源

继续使用：

```text
data/brand_keywords.json
```

启用的品牌按 `brands` 数组顺序生成类别 ID。`enabled: false` 的品牌（例如 `★`）不会生成类别。

### 类别命名规则

- `display_name`：用于 Label Studio 显示，保留原始品牌名，例如 `KLEESOFT`、`SOFTCARE`、`T-GUARD`、`DR.X`。
- `class_name`：用于 YOLO `names`、标签文件和内部映射，统一规范化为小写 snake 风格：
  - `KLEESOFT` -> `kleesoft`
  - `SOFTCARE` -> `softcare`
  - `T-GUARD` -> `t_guard`
  - `DR.X` -> `dr_x`
- `class_id`：按品牌库启用品牌顺序从 0 开始稳定生成。

这样可以避免 Label Studio 展示名和 YOLO 类别名混乱，同时保持可读、稳定。

## 代码改造

### 1. 新增共享品牌工具模块

新增：

```text
scripts/brand_library.py
```

职责：

- 加载 JSON/TXT 品牌库。
- 过滤纯数字、重复项、`enabled: false`、纯符号。
- 生成 `BrandClass`：`class_id`、`class_name`、`display_name`、`aliases`。
- 生成 YOLO `names` 映射。
- 生成 Label Studio XML 中的 `<Label>` 列表。
- 根据 YOLO-World prompt 反查类别 ID。

### 2. 改造 `scripts/pseudo_label_yolo_world.py`

当前问题：所有提示词结果都写成类别 `0`。

改造后：

- 默认加载品牌库的全部启用品牌，生成多类别。
- 为每个品牌生成提示词：
  - brand display name
  - aliases
  - `<brand> diaper package`
  - `<brand> package`
- 可继续用 `--brand-filter` 限制只预标部分品牌；默认 Make 将改为多品牌，不再只过滤 SOFTCARE。
- 每个 YOLO-World 检测结果根据 prompt 映射到对应 `class_id`。
- 输出 YOLO 行：`<brand_class_id> cx cy w h`。
- 元数据中记录 `class_id`、`class_name`、`display_name`、`prompt`、`confidence`。
- NMS / 大框过滤保留，并改为同类别内去重，避免不同品牌框互相误删。

### 3. 改造 `scripts/import_label_studio.py`

当前问题：Label Studio 配置和 prediction 只支持 `softcare_diaper`。

改造后：

- 从品牌库生成 `LABEL_CONFIG` 多 `<Label>`。
- 读取 `data/softcare_pseudo.yaml` 或品牌库 names，解析 YOLO `class_id` -> Label Studio `display_name`。
- prediction 的 `rectanglelabels` 写入对应品牌显示名，例如 `SOFTCARE`、`KLEESOFT`。
- 保留本地图片路径逻辑。

### 4. 改造 `scripts/apply_label_studio_import.py`

当前问题：Label Studio 项目 XML 写死单标签。

改造后：

- 从品牌库动态生成多标签 `LABEL_CONFIG`。
- 项目标题改为更通用，例如 `Multi Brand Package Review - 2026-08-06`，也支持环境变量覆盖。
- 继续创建 Local Files storage 和 task links。

### 5. 改造 `scripts/export_label_studio_to_yolo.py`

当前问题：只导出一个 `label/class_id`。

改造后：

- 从品牌库加载 `display_name` / `class_name` / `class_id` 映射。
- Label Studio annotation 中每个 rectangle 的 `rectanglelabels[0]` 映射到品牌 `class_id`。
- 写多类别 YOLO 标签。
- 报告记录每个类别的 box 数量。

### 6. 数据集 YAML 更新

更新：

```text
data/softcare.yaml
data/softcare_pseudo.yaml
```

从单类别：

```yaml
names:
  0: softcare_diaper
```

改为多品牌类别，例如：

```yaml
names:
  0: kleesoft
  1: softcare
  2: doffi
  ...
```

为避免手写维护错误，可新增脚本：

```text
scripts/write_brand_yolo_yaml.py
```

Make 目标 `brand-yaml` 自动从品牌库生成两个 YAML。

## Makefile 改造

### 参数调整

- `PSEUDO_BRAND_FILTER_ARGS` 默认从 `--brand-filter SOFTCARE` 改为空，表示多品牌预标注。
- 保留可覆盖方式：如果只想预标 Softcare，仍可执行：

```bash
make step-3-pseudo-label PSEUDO_BRAND_FILTER_ARGS="--brand-filter SOFTCARE"
```

- 新增/更新：
  - `BRAND_LIBRARY`
  - `BRAND_YAML_TARGETS`
  - `LABEL_STUDIO_PROJECT_TITLE`

### 流程调整

`workflow-to-ls` 前增加类别 YAML 生成：

```text
brand-yaml -> step-1 -> step-2 -> step-3 -> step-4
```

## 文档更新

同步更新：

- `README.md`
- `设计.md`
- `docs/reports/softcare-yolo-setup-2026-08-05.md`

说明：

- 多品牌类别 ID 由品牌库顺序决定。
- Label Studio 多标签来自品牌库。
- YOLO 输出多类别，不再是单类别 `softcare_diaper`。
- 如何只筛/只预标某个品牌。
- 训练与推理结果将按品牌类别输出。

## 测试计划

1. Python 编译：

```bash
.venv/bin/python -m compileall -q scripts
```

2. 品牌库加载测试：

- 类别数应为 20。
- `★` 不进入类别。
- `KLEESOFT`、`SOFTCARE` 等有稳定 class_id。

3. YAML 生成测试：

```bash
make brand-yaml
make data-validate
```

4. 预标注小样本测试：

```bash
make step-3-pseudo-label PSEUDO_LIMIT=1 PSEUDO_USE_OCR_CANDIDATES=0
```

检查输出标签 class_id 不再全是 0。

5. Label Studio JSON 生成测试：

```bash
make ls-import-json
```

验证：

- JSON 非空。
- predictions 中出现多个品牌 label。
- Label config 含多个品牌。

6. 导出转换脚本合成测试：

构造一个包含两个品牌 annotation 的小 JSON，验证输出 YOLO 标签 class_id 不同。

7. Make dry-run：

```bash
make -n workflow-to-ls
make -n workflow-after-ls LS_PROJECT_ID=1
make help
```

## 风险与注意事项

- 已有单类别 Label Studio 项目和旧标签不再与新多类别体系完全兼容；建议新建项目重新导入。
- 已有 `datasets/softcare/pseudo/labels` 中旧单类别标签可能需要重新生成。
- 已有正式训练集如果是单类别，需要重新从多类别 Label Studio 导出生成，或通过迁移脚本统一映射为某一品牌类别。
