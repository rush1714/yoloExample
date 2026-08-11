# OCR/预标注增量输出与单品牌配置改造

## 目标

1. OCR（常规与 Ollama）和 YOLO-World 预标注在每张图片完成后立即持久化结果，运行中断时已完成部分可查看、可继续使用。
2. 将 `data/` 中的品牌库与 YOLO 数据集 YAML 配置迁移到专用 `config/` 目录；`data/` 仅保留样例等数据资源。
3. 以品牌库为唯一类别来源。修改品牌库后，OCR 关键词、YOLO-World 提示词、Label Studio 标签、生成的 YAML 类别及 CLI 可选品牌都会随本次命令自动同步。
4. 通过一个 `BRAND` 参数支持全品牌或单一品牌运行；单品牌结果隔离到 `datasets/<品牌>/`，同时复用 `datasets/multibrand/raw/` 原图池。

## 设计决定

- 使用 `config/brand_keywords.json` 作为唯一可编辑品牌库，保留其中全品牌的稳定 `class_id`。不再把配置文件放在 `data/`。
- 新增 Make 参数 `BRAND ?= all`：`all` 对应 `multibrand`；指定 `SOFTCARE`、`KLEESOFT` 等有效品牌时，将自动派生安全的品牌 slug、`datasets/<slug>/`、`config/generated/<slug>.yaml` 与 `config/generated/<slug>_pseudo.yaml`。将提供 `brand-list` 显示当前品牌库中的可用值。
- 单品牌流程将类别重编号为 `0`，避免源品牌的全局 `class_id`（如 `KLEESOFT=1`）在单类 YAML 中形成空洞；多品牌流程继续使用品牌库内稳定的 `class_id`。同一个选择与重编号规则会用于 YAML、预标注、Label Studio 导入/导出，保证标签 ID 一致。
- OCR 的 JSON 将保持合法 JSON，在每张图完成后用原子替换写入完整的当前结果集合；CSV 每张图完成后追加一行，候选清单每次命中后追加一行。这样 JSON/CSV 都可在运行期间读取，不会留下半截 JSON。并发任务由主线程统一写报告，避免多线程争抢同一个文件。
- 伪标注会先完成单图推理，再原子落盘图片标签和即时更新 JSON/CSV 元数据；已处理图片即使后续失败也保留已完成结果。默认不改变当前的“每次重新处理输入列表”行为，避免自动跳过掩盖品牌库或推理参数变更；可在后续单独加入显式 `--resume`。

## 实施步骤

1. **迁移配置与统一类别选择**
   - 将 `data/brand_keywords.json` 移至 `config/brand_keywords.json`，将 `data/multibrand.yaml`、`data/multibrand_pseudo.yaml` 迁移为由 `config/generated/` 管理的生成文件，并添加必要的 `.gitignore`/`.gitkeep`。
   - 更新 `scripts/common/brand_library.py` 的默认配置路径，并新增公共的品牌选择与可选紧凑重编号工具；保留对重复品牌、禁用品牌和 `class_id` 冲突的现有验证。
   - 更新 `scripts/config/write_brand_yolo_yaml.py`：接收数据集根目录、品牌过滤及紧凑类别选项；自动创建输出父目录，并根据本次运行的目标数据集写入 YAML。
   - 更新所有默认路径与 CLI 说明：`scripts/ocr/filter_brand_candidates.py`、`scripts/pseudo_label/generate_yolo_world.py`、`scripts/label_studio/generate_import.py`、`scripts/label_studio/export_to_yolo.py`、`scripts/label_studio/apply_import.py`、`scripts/training/train.py`、`scripts/training/validate_dataset.py`。

2. **实现 OCR 增量持久化**
   - 在 `scripts/ocr/filter_brand_candidates.py` 中把当前 `write_reports(results, ...)` 的末尾批量写出改为可初始化、可逐条记录的报告写入器：初始化时创建 JSON/CSV/候选清单，`record(result)` 在每个完成的 future 后立即更新三类文件。
   - 常规 OCR 保持并发识别和线程独立 OCR reader；只有完成的结果回到主线程后才输出，防止 CSV/JSON 并发写损坏。
   - `scripts/ocr/filter_brand_candidates_llm.py` 复用同一写入器，在每张 Ollama 请求完成后立即记录，保持两种 OCR 的输出格式一致。
   - 给 OCR 增加品牌过滤参数，并以公共品牌选择逻辑加载当前选择品牌及其 aliases；`BRAND=all` 时仍使用全部启用品牌。

3. **实现预标注增量持久化**
   - 在 `scripts/pseudo_label/generate_yolo_world.py` 中引入逐条 JSON/CSV 元数据写入器：每次 `predict_image` 成功后先写对应标签及图片，再写当张 metadata/report 行。
   - 增加与 YAML/Label Studio 相同的品牌过滤和单品牌紧凑 ID 参数，确保生成标签的 class ID 与当前 `config/generated/<slug>_pseudo.yaml` 一致。
   - 保留现有候选清单、分割策略、NMS/覆盖过滤以及输出报告字段；把最终统计改为从已即时保存的结果累加得出。

4. **改造 Makefile 为品牌驱动工作流**
   - 把 `BRAND_LIBRARY`、训练 YAML、伪标注 YAML 切到 `config/`，拆分共享原图路径和当前运行输出根目录。
   - 新增 `BRAND`、派生的 `DATASET_NAME`/路径/模型名称、以及 `brand-list`、`brand-yaml` 同步目标；`help-params` 显示当前品牌与由品牌库动态解析的可选值。
   - 将同一品牌筛选参数自动传给 OCR、预标注、YAML 生成、Label Studio 导入/导出；单品牌场景自动启用紧凑 ID，不再需要用户手工拼接多个 `--brand-filter`。
   - 保持默认 `BRAND=all` 与现有多品牌工作流等价；为单品牌给出诸如 `make workflow-to-ls BRAND=SOFTCARE`、`make workflow-after-ls BRAND=SOFTCARE LS_PROJECT_ID=<id>` 的入口，输出隔离且原图复用。

5. **同步文档与验证**
   - 更新 `设计.md`、`README.md` 中的配置路径、增量报告行为、品牌同步机制和单品牌命令；按项目要求新增/更新 `docs/reports/2026-08-11-...md`，记录改造结论与验证结果。
   - 新增标准库 `unittest` 覆盖：品牌过滤/紧凑 ID、修改临时品牌库后 YAML 类别同步、OCR 报告逐条写入后 JSON/CSV/候选清单可立即读取、预标注元数据逐条写入。
   - 运行 `make brand-list`、全品牌与单品牌 `make brand-yaml`，检查 YAML 的数据目录与类别 ID；修改临时品牌库后验证 CLI 可选项和生成 YAML 随之变化。
   - 运行单元测试、相关脚本 `--help`、`make -n` 流程展开、`pylint` 静态检查和 `git diff --check`。不会运行真实 OCR、Ollama 或 YOLO-World 推理，以避免下载模型与长时间本地推理；将明确报告这一限制。
