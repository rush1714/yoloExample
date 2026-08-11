# 增量输出与单品牌训练配置改造

日期：2026-08-11

## 结论

- 品牌库已迁移至 `config/brand_keywords.json`，成为 OCR、YOLO-World、Label Studio 和 YOLO YAML 的唯一类别来源。
- `BRAND=all` 保持全品牌流程；`BRAND=<品牌>` 会将 OCR、伪标注、Label Studio 导入/导出和训练数据隔离到 `datasets/<品牌>/`，共享原始图片池 `datasets/multibrand/raw/`。
- 单品牌模式将该品牌标签重编号为类别 `0`；全品牌模式保留品牌库内稳定 `class_id`。
- 常规 OCR、Ollama OCR 与 YOLO-World 预标注均改为逐图持久化：CSV 立即追加，JSON 原子更新；预标注图片和标签在单图推理完成后立即落盘。

## 使用方式

```bash
# 查看当前品牌库可选值
make brand-list

# 生成全品牌配置
make brand-yaml

# 只处理、人工复核并训练 SOFTCARE
make workflow-to-ls BRAND=SOFTCARE
make workflow-after-ls BRAND=SOFTCARE LS_PROJECT_ID=<项目ID>
```

编辑 `config/brand_keywords.json` 后无需手动同步其它配置；重新执行上述命令即可让当前品牌库驱动 OCR 关键词、预标注提示词、Label Studio 标签和生成的 YAML。

## 验证

- 已通过修改脚本的 Python 编译检查。
- 已验证 `BRAND=SOFTCARE` 会生成仅包含 `0: softcare` 且指向 `datasets/softcare/` 的 YAML。
- 已通过 Makefile 干跑确认 `BRAND=KLEESOFT` 会将 OCR、预标注和 Label Studio 输出指向 `datasets/kleesoft/`，并传递单品牌筛选与类别重编号参数。
- 未运行真实 OCR、Ollama 或 YOLO-World 推理，避免耗时模型加载和本地模型服务依赖；增量写入逻辑通过单元测试验证。
