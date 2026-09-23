'use strict';

/**
 * 本地 Make 可视化控制台服务。
 *
 * 设计目标：
 * 1. 不依赖额外 npm 包，直接使用 Node 内置模块，方便在本地快速启动。
 * 2. 所有可执行命令都走白名单，避免页面输入任意 shell 命令。
 * 3. Make 参数通过 spawn 的数组参数传递，不通过 shell 拼接，降低转义和注入风险。
 * 4. 图片访问只允许项目内明确的数据/输出目录，并且只返回图片类型文件。
 */

const http = require('http');
const fs = require('fs');
const fsp = require('fs/promises');
const path = require('path');
const {spawn} = require('child_process');
const {URL} = require('url');

const PROJECT_ROOT = path.resolve(__dirname, '..');
const PUBLIC_ROOT = path.join(__dirname, 'public');
const CONSOLE_STATE_PATH = path.join(__dirname, 'state.json');
const LABEL_CATALOG_PATH = path.join(PROJECT_ROOT, 'config', 'label_categories.json');
const PORT = Number.parseInt(process.env.PORT || '3000', 10);
const MAX_BODY_BYTES = 128 * 1024;
const MAX_LOG_BYTES = 300 * 1024;
const IMAGE_EXTENSIONS = new Set(['.jpg', '.jpeg', '.png', '.webp', '.gif', '.bmp']);
const TEXT_REPORT_EXTENSIONS = new Set(['.json', '.csv', '.txt', '.xml', '.yaml', '.yml']);

/**
 * 可视化浏览的数据根目录。
 * id 用于前端选择和 API 参数；absPath 永远由服务端计算，不接受前端传入绝对路径。
 */
const DATA_ROOTS = [
    {
        id: 'datasets_all',
        label: '全部 datasets 图片',
        description: 'datasets',
        relativePath: 'datasets',
        recursive: true,
    },
    {
        id: 'legacy_multibrand',
        label: '兼容 / 多品牌旧数据',
        description: 'datasets/multibrand',
        relativePath: 'datasets/multibrand',
        recursive: true,
    },
    {
        id: 'legacy_diaper',
        label: '兼容 / 纸尿裤旧数据',
        description: 'datasets/diaper_category',
        relativePath: 'datasets/diaper_category',
        recursive: true,
    },
    {
        id: 'predict_outputs',
        label: '推理输出图片',
        description: 'outputs/predict',
        relativePath: 'outputs/predict',
        recursive: true,
    },
    {
        id: 'training_outputs',
        label: '训练输出图片',
        description: 'models/train',
        relativePath: 'models/train',
        recursive: true,
    },
    {
        id: 'artifacts',
        label: '训练归档图片',
        description: 'artifacts',
        relativePath: 'artifacts',
        recursive: true,
    },
    {
        id: 'sample_images',
        label: '示例图片',
        description: 'data/samples',
        relativePath: 'data/samples',
        recursive: true,
    },
    {
        id: 'general_kleesoft_purple_allround_purple',
        label: 'v2026-09-20',
        description: 'outputs/ec2_predict/GH/v2026-09-20/general_kleesoft_purple_allround_purple/yolo26m_img960_e100/annotated',
        relativePath: 'outputs/ec2_predict/GH/v2026-09-20/general_kleesoft_purple_allround_purple/yolo26m_img960_e100/annotated',
        recursive: true,
    },
];
/**
 * 文件服务白名单目录。
 * 只要图片位于这些目录下，就允许通过 /api/file 读取。
 */
const ALLOWED_FILE_ROOTS = [
    'datasets',
    'outputs',
    'models/train',
    'artifacts',
    'artifacts/diaper_category',
    'data/samples',
].map((item) => path.join(PROJECT_ROOT, item));

/**
 * 命令分组和参数定义。
 * 这里只收敛日常最常用的 Make 目标，避免把所有底层目标无差别堆到页面上。
 */
const COMMAND_GROUPS = [
    {
        id: 'label_categories',
        title: '类别管理',
        description: '维护可提交 Git 的通用类别列表；命令中的 LABEL_SET/LABELS 会从这里读取。',
        categoryManager: true,
    },
    {
        id: 'prepare_labeling',
        title: '图片来源 / 标注准备',
        description: '按来源组织导入流程：Excel、本地目录、S3；类别统一由 LABEL_SET/LABELS 多选控制。',
        children: [
            {
                id: 'generic_excel',
                title: 'Excel → LS',
                description: '从 Excel 下载图片到国家/版本目录，并按通用类别导入 Label Studio。',
                commands: [
                    {
                        target: '1-label-excel-workflow-to-ls',
                        title: '一键 Excel 导入到 LS',
                        description: '下载 Excel 图片，生成通用类别 YAML/LS JSON，并创建 Label Studio 项目。',
                        params: ['COUNTRY', 'DATA_VERSION', 'LABEL_SET', 'LABELS', 'LABEL_DATASET_NAME', 'EXCEL', 'EXCEL_COLUMN', 'EXCEL_WORKERS', 'EXCEL_TIMEOUT', 'LABEL_IMPORT_LIMIT']
                    },
                    {
                        target: '1-label-excel-ocr-yoloworld-workflow-to-ls',
                        title: '一键 Excel + OCR + YOLO-World 到 LS',
                        description: '使用 brands 类别列表时，下载图片、OCR 筛选、YOLO-World 预标注并导入 Label Studio。',
                        params: ['COUNTRY', 'DATA_VERSION', 'LABEL_SET', 'LABELS', 'LABEL_DATASET_NAME', 'EXCEL', 'EXCEL_COLUMN', 'OCR_LIMIT', 'PSEUDO_LIMIT', 'PSEUDO_CONF']
                    },
                    {
                        target: 'label-excel-import',
                        title: '1. Excel 下载图片',
                        description: '把 Excel 图片 URL 列下载到通用 raw/images 目录。',
                        params: ['COUNTRY', 'DATA_VERSION', 'LABEL_SET', 'LABELS', 'LABEL_DATASET_NAME', 'EXCEL', 'EXCEL_COLUMN', 'EXCEL_WORKERS', 'EXCEL_TIMEOUT']
                    },
                    {
                        target: 'label-ls-import-json-from-raw',
                        title: '2. 生成 LS 导入 JSON',
                        description: '读取下载报告并生成通用类别 Label Studio 导入 JSON/标签配置。',
                        params: ['COUNTRY', 'DATA_VERSION', 'LABEL_SET', 'LABELS', 'LABEL_DATASET_NAME', 'LABEL_IMPORT_LIMIT']
                    },
                    {
                        target: 'label-ls-apply',
                        title: '3. 导入任务到 LS',
                        description: '将已生成的通用类别导入 JSON 创建为 Label Studio 项目。',
                        params: ['COUNTRY', 'DATA_VERSION', 'LABEL_SET', 'LABELS', 'LABEL_DATASET_NAME', 'LABEL_LS_LOCAL_FILES_PATH']
                    },
                ],
            },
            {
                id: 'generic_local_dir',
                title: '本地目录 → LS',
                description: '本机已有图片目录直接按通用类别导入 Label Studio。',
                commands: [
                    {
                        target: '1-label-local-workflow-to-ls',
                        title: '一键本地目录导入到 LS',
                        description: '扫描本地图片目录，生成通用类别 LS JSON/标签配置并创建项目。',
                        params: ['COUNTRY', 'DATA_VERSION', 'LABEL_SET', 'LABELS', 'LABEL_DATASET_NAME', 'LABEL_LOCAL_IMAGES_DIR', 'LABEL_DATASET_ROOT', 'LABEL_RECURSIVE', 'LABEL_IMPORT_LIMIT']
                    },
                    {
                        target: 'label-local-ls-import-json',
                        title: '生成本地目录 LS JSON',
                        description: '只生成导入 JSON 和标签配置，不创建 Label Studio 项目。',
                        params: ['COUNTRY', 'DATA_VERSION', 'LABEL_SET', 'LABELS', 'LABEL_DATASET_NAME', 'LABEL_LOCAL_IMAGES_DIR', 'LABEL_DATASET_ROOT', 'LABEL_RECURSIVE', 'LABEL_IMPORT_LIMIT']
                    },
                ],
            },
            {
                id: 'generic_s3',
                title: '本地目录 → S3 → LS',
                description: '本地图片上传 S3，再按通用类别导入 Label Studio。',
                commands: [
                    {
                        target: 'label-s3-upload-images',
                        title: '上传本地图片到 S3',
                        description: '扫描本地图片目录，上传到 S3，并生成上传清单。',
                        params: ['COUNTRY', 'DATA_VERSION', 'LABEL_SET', 'LABELS', 'LABEL_DATASET_NAME', 'LABEL_LOCAL_IMAGES_DIR', 'LABEL_S3_DATASET_ROOT', 'S3_BUCKET', 'LABEL_S3_PREFIX', 'S3_REGION', 'S3_PROFILE', 'S3_UPLOAD_WORKERS', 'LABEL_RECURSIVE','S3_DRY_RUN']
                    },
                    {
                        target: 'label-s3-ls-import-json',
                        title: '生成 S3 LS 导入 JSON',
                        description: '读取 S3 上传清单，生成通用类别 LS JSON/标签配置。',
                        params: ['COUNTRY', 'DATA_VERSION', 'LABEL_SET', 'LABELS', 'LABEL_DATASET_NAME', 'LABEL_S3_DATASET_ROOT', 'LABEL_S3_MANIFEST_JSON', 'S3_IMAGE_URL_MODE', 'S3_PROXY_BASE_URL', 'LABEL_IMPORT_LIMIT']
                    },
                    {
                        target: 'label-s3-ls-apply',
                        title: '导入 S3 任务到 LS',
                        description: '把 S3/proxy 图片任务导入 Label Studio；proxy 模式需保持代理运行。',
                        params: ['COUNTRY', 'DATA_VERSION', 'LABEL_SET', 'LABELS', 'LABEL_DATASET_NAME', 'LABEL_S3_LS_IMPORT_JSON', 'LABEL_S3_LS_LABEL_CONFIG_XML']
                    },
                    {
                        target: '1-label-s3-workflow-to-ls',
                        title: '一键上传 S3 并导入 LS',
                        description: '上传本地图片到 S3，生成 LS 导入 JSON，并创建 Label Studio 项目。',
                        params: ['COUNTRY', 'DATA_VERSION', 'LABEL_SET', 'LABELS', 'LABEL_DATASET_NAME', 'LABEL_LOCAL_IMAGES_DIR', 'S3_BUCKET', 'LABEL_S3_PREFIX', 'S3_REGION', 'S3_PROFILE', 'S3_UPLOAD_WORKERS', 'S3_DRY_RUN']
                    },
                ],
            },
            {
                id: 'generic_pseudo',
                title: '品牌 OCR / 预标注兼容',
                description: '历史品牌 OCR、YOLO-World、YOLOE 预标注入口；类别仍来自品牌类别列表。',
                commands: [
                    {
                        target: 'workflow-to-ls',
                        title: '兼容：品牌 OCR + YOLO-World 到 LS',
                        description: '保留历史多品牌自动预标注流程，防止遗漏 OCR/YOLO-World 功能。',
                        params: ['BRAND', 'EXCEL', 'EXCEL_COLUMN', 'OCR_LIMIT', 'PSEUDO_LIMIT', 'PSEUDO_CONF']
                    },
                    {
                        target: 'workflow-to-ls-llm',
                        title: '兼容：Ollama OCR 到 LS',
                        description: '保留历史本地视觉大模型 OCR 分支。',
                        params: ['BRAND', 'EXCEL', 'EXCEL_COLUMN', 'OCR_LIMIT', 'LLM_OCR_MODEL', 'LLM_OCR_WORKERS', 'PSEUDO_LIMIT']
                    },
                    {
                        target: 'workflow-to-ls-visual',
                        title: '兼容：YOLOE Visual 到 LS',
                        description: '保留历史 YOLOE visual prompt 分支。',
                        params: ['BRAND', 'EXCEL', 'EXCEL_COLUMN', 'OCR_LIMIT', 'PSEUDO_LIMIT', 'PSEUDO_VISUAL_MODEL', 'PSEUDO_VISUAL_DEVICE']
                    },
                    {
                        target: 'label-ocr',
                        title: '通用类别 OCR 筛选',
                        description: '按当前 LABEL_SET/LABELS 多选类别执行 OCR 候选筛选；类别名称会作为文本匹配词。',
                        params: ['COUNTRY', 'DATA_VERSION', 'LABEL_SET', 'LABELS', 'LABEL_DATASET_NAME', 'OCR_ENGINE', 'OCR_WORKERS', 'OCR_LIMIT', 'OCR_FUZZY_THRESHOLD', 'OCR_RESUME']
                    },
                    {
                        target: 'label-pseudo-label',
                        title: '通用类别 YOLO-World 预标注',
                        description: '按当前 LABEL_SET/LABELS 多选类别生成 YOLO-World 预标注。',
                        params: ['COUNTRY', 'DATA_VERSION', 'LABEL_SET', 'LABELS', 'LABEL_DATASET_NAME', 'PSEUDO_MODEL', 'PSEUDO_LIMIT', 'PSEUDO_CONF', 'PSEUDO_IMGSZ', 'PSEUDO_USE_OCR_CANDIDATES']
                    },
                    {
                        target: 'yolo-world-ab-test',
                        title: 'YOLO-World A/B 测试',
                        description: '对比多个 YOLO-World 模型候选框质量。',
                        params: ['BRAND', 'AB_MODELS', 'AB_LIMIT', 'AB_PREVIEW_LIMIT', 'PSEUDO_CONF', 'PSEUDO_IMGSZ']
                    },
                ],
            },
        ],
    },
    {
        id: 'label_studio',
        title: 'Label Studio',
        description: '服务启停、导出、合并和通用类别转 YOLO。',
        children: [
            {
                id: 'label_studio_service',
                title: '服务启停',
                description: '初始化、启动和停止本地 Label Studio。',
                commands: [
                    {
                        target: 'ls-setup',
                        title: '首次初始化 Label Studio',
                        description: '创建 PostgreSQL 数据库并执行迁移。',
                        params: ['POSTGRE_USER', 'POSTGRE_NAME', 'POSTGRE_HOST', 'POSTGRE_PORT']
                    },
                    {
                        target: 'ls-start',
                        title: '启动 Label Studio',
                        description: '后台启动本地 Label Studio。',
                        params: ['LS_PORT']
                    },
                    {
                        target: 'ls-stop',
                        title: '停止 Label Studio',
                        description: '停止占用 LS_PORT 的 Label Studio 进程。',
                        params: ['LS_PORT']
                    },
                ],
            },
            {
                id: 'label_export_convert',
                title: '导出 / 合并 / 转 YOLO',
                description: '通用类别导出、合并和转换。',
                commands: [
                    {
                        target: 'label-ls-export',
                        title: '导出通用类别 LS JSON',
                        description: '从指定项目 ID 导出标注结果。',
                        params: ['COUNTRY', 'DATA_VERSION', 'LABEL_SET', 'LABELS', 'LABEL_DATASET_NAME', 'LS_PROJECT_ID', 'LABEL_LS_EXPORT_PATH', 'LS_EXPORT_FORMAT']
                    },
                    {
                        target: 'label-to-yolo',
                        title: '通用本地 LS 转 YOLO',
                        description: '把本地图片 LS 导出转换为 YOLO images/labels 和 YAML。',
                        params: ['COUNTRY', 'DATA_VERSION', 'LABEL_SET', 'LABELS', 'LABEL_DATASET_NAME', 'LABEL_DATASET_ROOT', 'LABEL_LS_EXPORT_PATH', 'LABEL_LS_TO_YOLO_CLEAR', 'LABEL_LS_TO_YOLO_SKIP_EMPTY']
                    },
                    {
                        target: '2-label-workflow-after-ls',
                        title: '一键导出并转 YOLO',
                        description: '导出通用类别 LS 标注并转换为 YOLO 训练集。',
                        params: ['COUNTRY', 'DATA_VERSION', 'LABEL_SET', 'LABELS', 'LABEL_DATASET_NAME', 'LS_PROJECT_ID', 'LABEL_LS_TO_YOLO_CLEAR', 'LABEL_LS_TO_YOLO_SKIP_EMPTY']
                    },
                    {
                        target: 'label-merge-ls-projects-to-yolo',
                        title: '合并多个 LS 项目并转 YOLO',
                        description: '多个项目 ID 用英文逗号分隔，合并有效框后转为 YOLO。',
                        params: ['COUNTRY', 'DATA_VERSION', 'LABEL_SET', 'LABELS', 'LABEL_DATASET_NAME', 'LABEL_LS_PROJECT_IDS', 'LABEL_LS_TO_YOLO_CLEAR', 'LABEL_LS_TO_YOLO_SKIP_EMPTY']
                    },
                    {
                        target: 'label-s3-to-yolo',
                        title: 'S3 LS 转 YOLO/EC2 清单',
                        description: 'S3 图片标注导出后，生成 YOLO labels、YAML 和 EC2 图片下载清单。',
                        params: ['COUNTRY', 'DATA_VERSION', 'LABEL_SET', 'LABELS', 'LABEL_DATASET_NAME', 'LABEL_S3_DATASET_ROOT', 'LABEL_S3_LS_EXPORT_PATH', 'LABEL_S3_EC2_IMAGE_MANIFEST_JSON', 'LABEL_S3_EC2_IMAGE_MANIFEST_CSV', 'LABEL_LS_TO_YOLO_CLEAR', 'LABEL_LS_TO_YOLO_SKIP_EMPTY']
                    },
                    {
                        target: 'label-local-s3-to-yolo',
                        title: '本地 LS + S3 清单转 EC2 清单',
                        description: '本地地址 LS 标注后，结合 S3 上传清单生成 EC2 下载训练清单。',
                        params: ['COUNTRY', 'DATA_VERSION', 'LABEL_SET', 'LABELS', 'LABEL_DATASET_NAME', 'LABEL_LS_EXPORT_PATH', 'LABEL_S3_MANIFEST_JSON', 'LABEL_LOCAL_IMAGES_DIR', 'LABEL_S3_DATASET_ROOT', 'LABEL_LS_TO_YOLO_CLEAR', 'LABEL_LS_TO_YOLO_SKIP_EMPTY']
                    },
                    {
                        target: 'label-yolo-s3-to-ec2-manifest',
                        title: '已生成 YOLO + S3 清单转 EC2 清单',
                        description: '只上传已生成的 YOLO 训练图片后，结合 S3 上传清单生成 EC2 下载训练清单。',
                        params: ['COUNTRY', 'DATA_VERSION', 'LABEL_SET', 'LABELS', 'LABEL_DATASET_NAME', 'LABEL_DATASET_ROOT', 'LABEL_S3_MANIFEST_JSON', 'LABEL_S3_EC2_IMAGE_MANIFEST_JSON', 'LABEL_S3_EC2_IMAGE_MANIFEST_CSV', 'LABEL_YOLO_S3_TO_EC2_REPORT', 'LABEL_LS_TO_YOLO_SKIP_EMPTY']
                    },
                ],
            },
        ],
    },
    {
        id: 'local_mac_training',
        title: '本地 Mac 训练 / 推理',
        description: '本地校验数据、生成 YAML、训练模型和推理验证。',
        commands: [
            {
                target: 'label-list',
                title: '查看通用类别列表',
                description: '输出类别配置中的列表和当前 LABEL_SET 可选类别。',
                params: ['LABEL_SET', 'LABELS']
            },
            {
                target: 'label-yaml',
                title: '生成通用类别 YAML',
                description: '按 LABEL_SET/LABELS 生成 YOLO 数据集 YAML。',
                params: ['COUNTRY', 'DATA_VERSION', 'LABEL_SET', 'LABELS', 'LABEL_DATASET_NAME', 'LABEL_DATASET_ROOT', 'LABEL_DATA_YAML']
            },
            {
                target: 'data-validate',
                title: '校验 YOLO 数据集',
                description: '检查图片、标签、类别和坐标是否合法；可覆盖 TRAIN_DATA_YAML。',
                params: ['TRAIN_DATA_YAML']
            },
            {
                target: 'train',
                title: '本地训练 YOLO 模型',
                description: '训练指定 YAML 数据集，并导出 best.pt。',
                params: ['TRAIN_DATA_YAML', 'TRAIN_BASE_MODEL', 'TRAIN_EPOCHS', 'TRAIN_IMGSZ', 'TRAIN_BATCH', 'TRAIN_DEVICE', 'TRAIN_RESUME', 'TRAIN_NAME', 'FINAL_MODEL']
            },
            {
                target: 'predict',
                title: '本地推理验证',
                description: '用指定模型对图片或 URL 推理，输出 JSON 和带框图片。',
                params: ['PREDICT_SOURCE', 'PREDICT_MODEL', 'PREDICT_CONF', 'PREDICT_IMGSZ', 'PREDICT_OUTPUT_DIR']
            },
            {
                target: 'export-model',
                title: '模型导出 (移动端 / ONNX)',
                description: '将 YOLO 模型导出为 iOS CoreML、Android TFLite、NCNN 或 ONNX/TensorRT 格式。',
                params: ['EXPORT_MODEL_PATH', 'EXPORT_FORMAT', 'EXPORT_IMGSZ', 'EXPORT_NMS', 'EXPORT_HALF', 'EXPORT_INT8', 'EXPORT_DEVICE', 'EXPORT_DATA_YAML', 'EXPORT_OUTPUT_DIR']
            },
        ],
    },
    {
        id: 'ec2_training',
        title: 'EC2 训练 / 评估 / 下载',
        description: '通用类别本地数据集或 S3 数据集的 EC2 训练闭环；所有 EC2 命令默认 dry-run。',
        ec2: true,
        children: [
            {
                id: 'ec2_generic_local',
                title: '本地 YOLO 数据集 → EC2',
                description: '上传本地 YOLO 数据集并在 EC2 训练。',
                ec2: true,
                commands: [
                    {
                        target: 'label-ec2-upload-data',
                        title: '上传通用数据到 EC2',
                        description: '上传本地 YOLO images/labels 和 YAML 到 EC2，默认 dry-run。',
                        params: ['COUNTRY', 'DATA_VERSION', 'LABEL_SET', 'LABELS', 'LABEL_DATASET_NAME', 'LABEL_DATASET_ROOT', 'EC2_HOST', 'EC2_USER', 'EC2_KEY', 'EC2_RUN_NAME', 'EC2_EXECUTE']
                    },
                    {
                        target: 'label-ec2-train',
                        title: 'EC2 训练通用数据',
                        description: '使用已上传 YAML 训练，不再按固定类别重写 names。',
                        params: ['COUNTRY', 'DATA_VERSION', 'LABEL_SET', 'LABELS', 'LABEL_DATASET_NAME', 'EC2_HOST', 'EC2_USER', 'EC2_KEY', 'EC2_BASE_MODEL', 'EC2_TRAIN_EPOCHS', 'EC2_TRAIN_IMGSZ', 'EC2_TRAIN_BATCH', 'EC2_TRAIN_DEVICE', 'EC2_RUN_NAME', 'EC2_EXECUTE']
                    },
                    {
                        target: 'label-ec2-evaluate',
                        title: '评估归档通用训练',
                        description: '归档训练产物并生成评估摘要。',
                        params: ['COUNTRY', 'DATA_VERSION', 'LABEL_SET', 'LABELS', 'LABEL_DATASET_NAME', 'EC2_HOST', 'EC2_USER', 'EC2_KEY', 'EC2_RUN_NAME', 'EC2_EVAL_NOTES', 'EC2_EXECUTE']
                    },
                    {
                        target: 'label-ec2-download-artifacts',
                        title: '下载通用训练归档',
                        description: '下载完整训练归档目录。',
                        params: ['COUNTRY', 'DATA_VERSION', 'LABEL_SET', 'LABELS', 'LABEL_DATASET_NAME', 'EC2_HOST', 'EC2_USER', 'EC2_KEY', 'EC2_RUN_NAME', 'EC2_EXECUTE']
                    },
                    {
                        target: 'label-ec2-download-model',
                        title: '下载通用 best.pt',
                        description: '下载训练得到的 best.pt。',
                        params: ['COUNTRY', 'DATA_VERSION', 'LABEL_SET', 'LABELS', 'LABEL_DATASET_NAME', 'EC2_HOST', 'EC2_USER', 'EC2_KEY', 'EC2_RUN_NAME', 'LABEL_FINAL_MODEL', 'EC2_EXECUTE']
                    },
                ],
            },
            {
                id: 'ec2_generic_s3',
                title: 'S3 图片数据集 → EC2',
                description: '上传 labels/manifest/YAML，EC2 从 S3 下载图片并训练。',
                ec2: true,
                commands: [
                    {
                        target: '3-label-s3-workflow-ec2-train',
                        title: '一键上传并训练 S3 数据',
                        description: '上传通用 S3 labels/manifest/YAML，下载图片并训练；默认 dry-run。',
                        params: ['COUNTRY', 'DATA_VERSION', 'LABEL_SET', 'LABELS', 'LABEL_DATASET_NAME', 'LABEL_S3_DATASET_ROOT', 'S3_PUBLIC_BASE_URL', 'S3_EC2_DOWNLOAD_MODE', 'EC2_HOST', 'EC2_USER', 'EC2_KEY', 'EC2_BASE_MODEL', 'EC2_TRAIN_EPOCHS', 'EC2_TRAIN_IMGSZ', 'EC2_TRAIN_BATCH', 'EC2_TRAIN_DEVICE', 'EC2_RUN_NAME', 'EC2_EXECUTE']
                    },
                    {
                        target: 'label-s3-ec2-upload-manifest',
                        title: '上传 S3 manifest 到 EC2',
                        description: '上传 labels、EC2 图片 manifest 和 YAML，不上传图片大文件。',
                        params: ['COUNTRY', 'DATA_VERSION', 'LABEL_SET', 'LABELS', 'LABEL_DATASET_NAME', 'LABEL_S3_DATASET_ROOT', 'LABEL_S3_EC2_IMAGE_MANIFEST_JSON', 'LABEL_S3_EC2_IMAGE_MANIFEST_CSV', 'EC2_HOST', 'EC2_USER', 'EC2_KEY', 'EC2_RUN_NAME', 'EC2_EXECUTE']
                    },
                    {
                        target: 'label-s3-ec2-download-images',
                        title: 'EC2 下载 S3 训练图片',
                        description: 'EC2 读取 ec2_image_manifest.json 下载训练图片。',
                        params: ['COUNTRY', 'DATA_VERSION', 'LABEL_SET', 'LABELS', 'LABEL_DATASET_NAME', 'LABEL_S3_EC2_REMOTE_MANIFEST_JSON', 'S3_PUBLIC_BASE_URL', 'S3_EC2_DOWNLOAD_MODE', 'EC2_HOST', 'EC2_USER', 'EC2_KEY', 'EC2_PROJECT_ROOT', 'EC2_EXECUTE']
                    },
                    {
                        target: 'label-s3-ec2-train',
                        title: 'EC2 训练 S3 数据',
                        description: '使用上传的多/单类别 YAML 训练 S3 数据集。',
                        params: ['COUNTRY', 'DATA_VERSION', 'LABEL_SET', 'LABELS', 'LABEL_DATASET_NAME', 'EC2_HOST', 'EC2_USER', 'EC2_KEY', 'EC2_BASE_MODEL', 'EC2_TRAIN_EPOCHS', 'EC2_TRAIN_IMGSZ', 'EC2_TRAIN_BATCH', 'EC2_TRAIN_DEVICE', 'EC2_RUN_NAME', 'EC2_EXECUTE']
                    },
                    {
                        target: 'label-s3-ec2-evaluate',
                        title: '评估归档 S3 训练',
                        description: '归档 EC2 S3 训练产物并生成评估摘要。',
                        params: ['COUNTRY', 'DATA_VERSION', 'LABEL_SET', 'LABELS', 'LABEL_DATASET_NAME', 'EC2_HOST', 'EC2_USER', 'EC2_KEY', 'EC2_RUN_NAME', 'EC2_EVAL_NOTES', 'EC2_EXECUTE']
                    },
                    {
                        target: 'label-s3-ec2-download-artifacts',
                        title: '下载 S3 训练归档',
                        description: '下载 S3 数据集训练归档目录。',
                        params: ['COUNTRY', 'DATA_VERSION', 'LABEL_SET', 'LABELS', 'LABEL_DATASET_NAME', 'EC2_HOST', 'EC2_USER', 'EC2_KEY', 'EC2_RUN_NAME', 'EC2_EXECUTE']
                    },
                    {
                        target: 'label-s3-ec2-download-model',
                        title: '下载 S3 best.pt',
                        description: '下载 S3 数据集训练得到的 best.pt。',
                        params: ['COUNTRY', 'DATA_VERSION', 'LABEL_SET', 'LABELS', 'LABEL_DATASET_NAME', 'EC2_HOST', 'EC2_USER', 'EC2_KEY', 'EC2_RUN_NAME', 'LABEL_S3_FINAL_MODEL', 'EC2_EXECUTE']
                    },
                    {
                        target: 'label-s3-ec2-predict-manifest',
                        title: 'EC2 S3 批量推理验证',
                        description: 'EC2 读取 S3/Excel/JSON/TXT 图片清单，下载图片推理，并把 JSON、CSV 和带框图上传到指定 S3 目录。',
                        params: ['COUNTRY', 'DATA_VERSION', 'LABEL_SET', 'LABELS', 'LABEL_DATASET_NAME', 'EC2_HOST', 'EC2_USER', 'EC2_KEY', 'EC2_PROJECT_ROOT', 'EC2_RUN_NAME', 'EC2_PREDICT_LOCAL_MANIFEST', 'EC2_PREDICT_MANIFEST_SOURCE', 'EC2_PREDICT_REMOTE_MANIFEST', 'EC2_PREDICT_OUTPUT_S3_URI', 'EC2_PREDICT_MODEL', 'EC2_PREDICT_INPUT_COLUMN', 'EC2_PREDICT_CONF', 'EC2_PREDICT_IMGSZ', 'EC2_PREDICT_LIMIT', 'EC2_PREDICT_WORK_DIR', 'S3_PUBLIC_BASE_URL', 'S3_EC2_DOWNLOAD_MODE', 'EC2_TRAIN_DEVICE', 'EC2_EXECUTE']
                    },
                    {
                        target: 'label-s3-ec2-upload-existing-predict-results',
                        title: '补传已有 EC2 推理结果到 S3',
                        description: '推理已完成但 S3 上传失败时，只上传 EC2 work-dir 中已有 summary、单图 JSON 和带框图，不重新推理。',
                        params: ['COUNTRY', 'DATA_VERSION', 'LABEL_SET', 'LABELS', 'LABEL_DATASET_NAME', 'EC2_HOST', 'EC2_USER', 'EC2_KEY', 'EC2_PROJECT_ROOT', 'EC2_RUN_NAME', 'EC2_PREDICT_WORK_DIR', 'EC2_PREDICT_OUTPUT_S3_URI', 'EC2_EXECUTE']
                    },
                    {
                        target: 'label-s3-ec2-download-predict-results',
                        title: '下载 EC2 批量推理结果',
                        description: '先下载 S3 结果记录文本，再把 summary、单图 JSON、带框图和原始推理图片同步到本地标准目录。',
                        params: ['COUNTRY', 'DATA_VERSION', 'LABEL_SET', 'LABELS', 'LABEL_DATASET_NAME', 'EC2_RUN_NAME', 'EC2_PREDICT_OUTPUT_S3_URI', 'EC2_PREDICT_DOWNLOAD_SOURCE_IMAGES', 'EC2_PREDICT_DOWNLOAD_WORKERS', 'EC2_PREDICT_SOURCE_DOWNLOAD_TIMEOUT', 'S3_PUBLIC_BASE_URL', 'EC2_PREDICT_LOCAL_RESULT_ROOT', 'EC2_PREDICT_LOCAL_SOURCE_IMAGE_ROOT', 'S3_PROFILE', 'S3_REGION', 'S3_ENDPOINT_URL']
                    },
                ],
            },
        ],
    },
    {
        id: 'maintenance',
        title: '维护工具',
        description: '帮助、目录准备、EC2 参数查看、清理预览和备份。',
        commands: [
            {target: 'help', title: '查看 Make 帮助', description: '输出 Make 命令列表和常用参数说明。', params: []},
            {target: 'help-params', title: '查看公共参数', description: '输出公共 Make 参数默认值。', params: []},
            {
                target: 'ec2-print-params',
                title: '查看 EC2 参数',
                description: '输出 EC2 公共连接与训练参数。',
                params: []
            },
            {
                target: 'prepare-dirs',
                title: '创建临时和日志目录',
                description: '创建 .tmp、logs、Label Studio 工作目录等。',
                params: []
            },
            {
                target: 'datasets-clean-preview',
                title: '预览 ignored 数据清理',
                description: '只预览会被删除的 ignored 数据，不执行删除。',
                params: []
            },
            {
                target: 'datasets-clean-untracked-except-raw-preview',
                title: '预览非 raw 未跟踪数据清理',
                description: '只预览 datasets 下除 raw 外未跟踪内容。',
                params: []
            },
            {
                target: 'bak-data',
                title: '备份模型权重',
                description: '将 models 下 .pt 权重复制到 models/backup。',
                params: []
            },
        ],
    },
];
/**
 * 常用参数默认值和输入类型。
 * 默认值用于页面展示；实际执行时只会传递用户填写的非空值，未填写则继续使用 Makefile 默认值。
 */
const PARAM_DEFINITIONS = {
    LABEL_CATALOG: {
        label: '类别配置文件',
        defaultValue: 'config/label_categories.json',
        type: 'text',
        help: '可提交 Git 的通用类别配置。'
    },
    COUNTRY: {
        label: '国家/市场',
        defaultValue: 'default',
        type: 'text',
        help: '用于默认目录：datasets/<COUNTRY>/<DATA_VERSION>/<数据集>。'
    },
    DATA_VERSION: {
        label: '数据版本',
        defaultValue: '',
        type: 'text',
        help: '留空时 Make 默认使用当天日期，例如 v2026-09-18。'
    },
    LABEL_SET: {
        label: '类别列表',
        defaultValue: 'general',
        type: 'select',
        options: ['general'],
        help: '来自 config/label_categories.json。'
    },
    LABELS: {
        label: '选择类别',
        defaultValue: '',
        type: 'multiselect',
        options: [],
        help: '可多选；需要全部类别时请全选。命令行空值仍表示全部。'
    },
    LABEL_DATASET_NAME: {
        label: '数据集短名称',
        defaultValue: '',
        type: 'text',
        help: '留空时根据 LABEL_SET/LABELS 自动生成。'
    },
    LABEL_DATA_DOMAIN: {
        label: '数据来源域（兼容）',
        defaultValue: 'local',
        type: 'select',
        options: ['excel', 'local', 's3'],
        help: '历史兼容参数；新标准目录不再按来源分层。'
    },
    LABEL_DATASET_ROOT: {
        label: '通用数据集目录',
        defaultValue: '',
        type: 'text',
        help: '留空时使用 datasets/<国家>/<版本>/<数据集>。'
    },
    LABEL_DATA_YAML: {
        label: '通用 YOLO YAML',
        defaultValue: '',
        type: 'text',
        help: '留空时写入 config/generated/<国家>_<版本>_<数据集>.yaml。'
    },
    LABEL_PSEUDO_YAML: {label: '通用伪标注 YAML', defaultValue: '', type: 'text'},
    LABEL_IMPORT_LIMIT: {label: '导入任务上限', defaultValue: '', type: 'number', help: '留空表示全量。'},
    LABEL_RECURSIVE: {label: '递归扫描图片', defaultValue: '1', type: 'select', options: ['1', '0']},
    LABEL_LOCAL_IMAGES_DIR: {label: '源图片目录', defaultValue: 'data/local_import/images', type: 'text'},
    LABEL_LS_IMPORT_JSON: {label: '通用 LS 导入 JSON', defaultValue: '', type: 'text'},
    LABEL_LS_LABEL_CONFIG_XML: {label: '通用 LS 标签配置', defaultValue: '', type: 'text'},
    LABEL_LS_LOCAL_FILES_PATH: {
        label: 'LS 本地文件根目录',
        defaultValue: '',
        type: 'text',
        help: 'Excel 流程默认 raw/images，本地目录流程默认源图片目录。'
    },
    LABEL_LS_EXPORT_PATH: {label: '通用 LS 导出 JSON', defaultValue: '', type: 'text'},
    LABEL_LS_TO_YOLO_CLEAR: {label: '转换前清空旧输出', defaultValue: '0', type: 'select', options: ['0', '1']},
    LABEL_LS_TO_YOLO_SKIP_EMPTY: {label: '跳过空标注', defaultValue: '0', type: 'select', options: ['0', '1']},
    LABEL_LS_PROJECT_IDS: {
        label: 'LS 项目 ID 列表',
        defaultValue: '',
        type: 'text',
        help: '多个项目用英文逗号分隔，例如 21,20。'
    },
    LABEL_S3_DATASET_ROOT: {label: '通用 S3 本地目录', defaultValue: '', type: 'text'},
    LABEL_S3_PREFIX: {
        label: '通用 S3 业务前缀',
        defaultValue: '',
        type: 'text',
        help: '留空时使用 COUNTRY/DATA_VERSION/LABEL_DATASET_NAME。'
    },
    LABEL_S3_MANIFEST_JSON: {label: '通用 S3 上传清单', defaultValue: '', type: 'text'},
    LABEL_S3_LS_IMPORT_JSON: {label: '通用 S3 LS 导入 JSON', defaultValue: '', type: 'text'},
    LABEL_S3_LS_LABEL_CONFIG_XML: {label: '通用 S3 LS 标签配置', defaultValue: '', type: 'text'},
    LABEL_S3_LS_EXPORT_PATH: {label: '通用 S3 LS 导出 JSON', defaultValue: '', type: 'text'},
    LABEL_S3_EC2_IMAGE_MANIFEST_JSON: {label: '通用 EC2 图片清单 JSON', defaultValue: '', type: 'text'},
    LABEL_S3_EC2_IMAGE_MANIFEST_CSV: {label: '通用 EC2 图片清单 CSV', defaultValue: '', type: 'text'},
    LABEL_YOLO_S3_TO_EC2_REPORT: {label: 'YOLO+S3 转 EC2 报告', defaultValue: '', type: 'text'},
    LABEL_S3_EC2_REMOTE_MANIFEST_JSON: {label: '远端 EC2 图片清单 JSON', defaultValue: '', type: 'text'},
    LABEL_S3_FINAL_MODEL: {label: '通用 S3 本地模型路径', defaultValue: '', type: 'text'},
    LABEL_FINAL_MODEL: {label: '通用本地模型路径', defaultValue: '', type: 'text'},
    TRAIN_DATA_YAML: {
        label: '训练 YAML',
        defaultValue: '',
        type: 'text',
        help: '本地训练/校验要读取的 YOLO 数据集 YAML。'
    },
    FINAL_MODEL: {label: '导出模型路径', defaultValue: '', type: 'text'},
    EXPORT_MODEL_PATH: {
        label: '待导出模型路径',
        defaultValue: 'models/yolo26s.pt',
        type: 'text',
        help: '待导出的 .pt 模型权重路径，支持 models/ 下的文件名或相对/绝对路径。'
    },
    EXPORT_FORMAT: {
        label: '导出格式',
        defaultValue: 'onnx',
        type: 'select',
        options: ['coreml', 'tflite', 'ncnn', 'onnx', 'openvino', 'engine', 'torchscript'],
        help: 'coreml: iOS 首选; tflite: Android 首选; ncnn: 移动端极速推理; onnx: 通用跨平台。'
    },
    EXPORT_IMGSZ: {
        label: '导出图片尺寸',
        defaultValue: '640',
        type: 'number',
        help: '导出输入边长，移动端推荐 320、480 或 640。'
    },
    EXPORT_NMS: {
        label: '集成 NMS 后处理',
        defaultValue: '1',
        type: 'select',
        options: ['1', '0'],
        help: '强烈推荐 1（开启），将非极大值抑制打包进模型，极大幅度简化移动端解析代码。'
    },
    EXPORT_HALF: {
        label: 'FP16 半精度',
        defaultValue: '0',
        type: 'select',
        options: ['0', '1'],
        help: '开启后模型体积减半，加速 GPU/NPU 推理；iOS CoreML 推荐开启。'
    },
    EXPORT_INT8: {
        label: 'INT8 量化',
        defaultValue: '0',
        type: 'select',
        options: ['0', '1'],
        help: '开启后为 INT8 量化模型（Android 低端机推荐，需指定校准数据集）。'
    },
    EXPORT_DEVICE: {
        label: '导出设备',
        defaultValue: 'cpu',
        type: 'select',
        options: ['cpu', 'mps', 'cuda:0', '0']
    },
    EXPORT_DATA_YAML: {
        label: 'INT8 校准数据集 YAML',
        defaultValue: '',
        type: 'text',
        help: '仅在 EXPORT_INT8=1 时使用。'
    },
    EXPORT_OUTPUT_DIR: {
        label: '导出产物目标目录',
        defaultValue: '',
        type: 'text',
        help: '可选；留空时保存在原权重同级或 Ultralytics 默认目录。'
    },
    BRAND: {label: '品牌', defaultValue: 'all', type: 'select', help: 'all 表示多品牌；也可选择单品牌。'},
    EXCEL: {
        label: 'Excel 路径',
        defaultValue: '/Users/guobiao/DOC/森大2.0/18.陈列数据/CI_2026-08-26_最新1801个_02.xlsx',
        type: 'text'
    },
    EXCEL_COLUMN: {label: '图片 URL 列名', defaultValue: '生动化照片链接', type: 'text'},
    EXCEL_WORKERS: {label: 'Excel 下载并发', defaultValue: '10', type: 'number'},
    EXCEL_TIMEOUT: {label: '下载超时秒数', defaultValue: '30', type: 'number'},
    OCR_ENGINE: {label: 'OCR 引擎', defaultValue: 'rapidocr', type: 'select', options: ['rapidocr', 'easyocr']},
    OCR_WORKERS: {label: 'OCR 并发', defaultValue: '10', type: 'number'},
    OCR_LIMIT: {label: 'OCR 数量上限', defaultValue: '', type: 'number', help: '留空表示全量。'},
    OCR_FUZZY_THRESHOLD: {label: 'OCR 模糊匹配阈值', defaultValue: '60', type: 'number'},
    OCR_MIN_CONFIDENCE: {label: 'OCR 最低置信度', defaultValue: '0.2', type: 'number'},
    OCR_RESUME: {label: 'OCR 恢复模式', defaultValue: '0', type: 'select', options: ['0', '1']},
    LLM_OCR_MODEL: {label: 'Ollama 模型', defaultValue: 'gemma3:12b', type: 'text'},
    LLM_OCR_WORKERS: {label: 'LLM OCR 并发', defaultValue: '1', type: 'number'},
    LLM_OCR_TIMEOUT: {label: 'LLM OCR 超时秒数', defaultValue: '180', type: 'number'},
    PSEUDO_MODEL: {label: 'YOLO-World 权重', defaultValue: 'models/yolov8s-world.pt', type: 'text'},
    PSEUDO_LIMIT: {label: '预标注数量上限', defaultValue: '', type: 'number', help: '留空表示全量。'},
    PSEUDO_CONF: {label: '预标注置信度', defaultValue: '0.03', type: 'number'},
    PSEUDO_IMGSZ: {label: '预标注图片尺寸', defaultValue: '960', type: 'number'},
    PSEUDO_USE_OCR_CANDIDATES: {label: '只处理 OCR 候选', defaultValue: '1', type: 'select', options: ['1', '0']},
    PSEUDO_NMS_IOU: {label: 'NMS IoU', defaultValue: '0.45', type: 'number'},
    PSEUDO_MAX_AREA_RATIO: {label: '最大框面积比例', defaultValue: '0.45', type: 'number'},
    PSEUDO_VISUAL_MODEL: {label: 'YOLOE 权重', defaultValue: 'models/yoloe-26m-seg.pt', type: 'text'},
    PSEUDO_VISUAL_DEVICE: {label: 'YOLOE 设备', defaultValue: 'mps', type: 'select', options: ['mps', 'cpu', '0']},
    PSEUDO_VISUAL_REFERENCE_LIMIT: {label: '每品牌参考图上限', defaultValue: '', type: 'number'},
    VISUAL_PROMPTS_EXCEL: {
        label: '品牌参考图 Excel',
        defaultValue: '/Users/guobiao/Downloads/品牌图片2_1786525402668.xlsx',
        type: 'text'
    },
    VISUAL_PROMPTS_BRAND_COLUMN: {label: '品牌列名', defaultValue: 'brand', type: 'text'},
    VISUAL_PROMPTS_ATTACH_COLUMN: {label: '图片 URL 列名', defaultValue: 'attach_file', type: 'text'},
    VISUAL_PROMPTS_LIMIT: {label: '参考图导入上限', defaultValue: '', type: 'number'},
    AB_MODELS: {
        label: 'A/B 模型列表',
        defaultValue: 'models/yolov8s-world.pt,models/yolov8m-world.pt,models/yolov8m-worldv2.pt,models/yolov8x-worldv2.pt',
        type: 'text'
    },
    AB_LIMIT: {label: 'A/B 图片上限', defaultValue: '50', type: 'number'},
    AB_PREVIEW_LIMIT: {label: 'A/B 预览图上限', defaultValue: '30', type: 'number'},
    LS_PROJECT_ID: {label: 'LS 项目 ID,多个可以是21,20', defaultValue: '', type: 'text', help: '单项目填 21；多项目合并命令可填 21,20。'},
    LS_SOURCE_PROJECT_ID: {
        label: '源 LS 项目 ID',
        defaultValue: '',
        type: 'text',
        help: '复制已标注项目时填写源项目 ID。'
    },
    LS_CLONE_PROJECT_TITLE: {
        label: '复制项目标题',
        defaultValue: '',
        type: 'text',
        help: '留空时使用源项目标题 + Annotated Copy。'
    },
    LS_CLONE_LABEL_NAME: {
        label: '复制标签过滤',
        defaultValue: '',
        type: 'text',
        help: '可选；只复制包含该标签有效框的任务。'
    },
    LS_CLONE_ANNOTATION_INDEX: {
        label: '复制标注选择',
        defaultValue: 'latest',
        type: 'select',
        options: ['latest', 'first']
    },
    LS_LOCAL_FILES_PATH: {
        label: 'LS 本地文件目录',
        defaultValue: '',
        type: 'text',
        help: '复制项目时可指定新项目 Local Files storage 根目录；留空自动推断。'
    },
    LS_PORT: {label: 'LS 端口', defaultValue: '9001', type: 'number'},
    LS_PROJECT_TITLE: {label: 'LS 项目标题', defaultValue: '', type: 'text'},
    LS_EXPORT_PATH: {label: 'LS 导出 JSON 路径', defaultValue: '', type: 'text'},
    LS_EXPORT_FORMAT: {label: 'LS 导出格式', defaultValue: 'JSON', type: 'text'},
    LS_PROJECT_IDS: {
        label: 'LS 项目 ID 列表',
        defaultValue: '',
        type: 'text',
        help: '多个项目用英文逗号分隔，例如 21,20。'
    },
    LS_TO_YOLO_CLEAR: {label: '转换前清空旧训练集', defaultValue: '0', type: 'select', options: ['0', '1']},
    LS_TO_YOLO_SKIP_EMPTY: {label: '跳过空标注', defaultValue: '0', type: 'select', options: ['0', '1']},
    LOCAL_DATASET_NAME: {
        label: '本地数据集短名称',
        defaultValue: 'dataset',
        type: 'text',
        help: '只能填短名称，不要填路径。'
    },
    LOCAL_IMAGES_DIR: {label: '源图片目录', defaultValue: 'data/local_import/images', type: 'text'},
    LOCAL_DATASET_ROOT: {
        label: '导出数据集目录',
        defaultValue: '',
        type: 'text',
        help: '留空时使用 datasets/<国家>/<版本>/<本地数据集短名称>。'
    },
    LOCAL_LABEL_NAME: {label: '标注类别名', defaultValue: 'diaper', type: 'text'},
    LOCAL_RECURSIVE: {label: '递归扫描子目录', defaultValue: '1', type: 'select', options: ['1', '0']},
    LOCAL_LIMIT: {label: '导入图片上限', defaultValue: '', type: 'number', help: '留空表示全量。'},
    LOCAL_DATA_YAML: {label: '本地目录 YOLO YAML', defaultValue: '', type: 'text'},
    LOCAL_LS_EXPORT_PATH: {label: '本地目录 LS 导出 JSON', defaultValue: '', type: 'text'},
    LOCAL_LS_TO_YOLO_CLEAR: {label: '转换前清空旧训练集', defaultValue: '0', type: 'select', options: ['0', '1']},
    LOCAL_LS_TO_YOLO_SKIP_EMPTY: {label: '跳过空标注', defaultValue: '0', type: 'select', options: ['0', '1']},
    LOCAL_FINAL_MODEL: {label: '本地下载模型路径', defaultValue: '', type: 'text'},
    LOCAL_EC2_REMOTE_DATASET_ROOT: {label: 'EC2 数据集目录', defaultValue: '', type: 'text'},
    LOCAL_EC2_TRAIN_NAME: {label: 'EC2 训练名称', defaultValue: '', type: 'text'},
    LOCAL_EC2_REMOTE_FINAL_MODEL: {label: 'EC2 best.pt 路径', defaultValue: '', type: 'text'},
    LOCAL_EC2_ARTIFACT_ROOT: {label: 'EC2 归档目录', defaultValue: '', type: 'text'},
    LOCAL_EC2_LOCAL_ARTIFACT_ROOT: {label: '本地归档下载目录', defaultValue: '', type: 'text'},
    BRAND_S3_CONFIG: {label: 'S3 配置文件', defaultValue: 'config/brand_s3_ec2.local.yaml', type: 'text'},
    S3_DATASET_NAME: {label: 'S3 数据集短名称', defaultValue: 'dataset', type: 'text'},
    S3_LABEL_NAME: {label: 'S3 标注类别名', defaultValue: 'diaper', type: 'text'},
    S3_LOCAL_IMAGES_DIR: {label: 'S3 源图片目录', defaultValue: 'data/local_import/images', type: 'text'},
    S3_DATASET_ROOT: {label: 'S3 本地输出目录', defaultValue: '', type: 'text'},
    S3_BUCKET: {label: 'S3 桶名', defaultValue: 'uat-smdp4cust-bak', type: 'text'},
    S3_PREFIX: {
        label: 'S3 业务前缀',
        defaultValue: 'dataset',
        type: 'text',
        help: '只填业务子目录；实际上传会自动使用 yolo-training/<S3_PREFIX>。'
    },
    S3_REGION: {label: 'S3 区域', defaultValue: 'af-south-1', type: 'text'},
    S3_PROFILE: {label: 'AWS Profile', defaultValue: 'smdp-yolo', type: 'text'},
    S3_ENDPOINT_URL: {
        label: 'S3 Endpoint URL',
        defaultValue: '',
        type: 'text',
        help: '兼容 S3 服务端点，AWS S3 通常留空。'
    },
    S3_PUBLIC_BASE_URL: {
        label: 'S3 公开 Base URL',
        defaultValue: '',
        type: 'text',
        help: '公开桶或 CDN 前缀；留空时由桶和区域推导。'
    },
    S3_RECURSIVE: {label: 'S3 递归扫描', defaultValue: '1', type: 'select', options: ['1', '0']},
    S3_LIMIT: {label: 'S3 图片上限', defaultValue: '', type: 'number'},
    S3_DRY_RUN: {label: 'S3 上传 dry-run', defaultValue: '0', type: 'select', options: ['0', '1']},
    S3_UPLOAD_WORKERS: {
        label: 'S3 上传并发',
        defaultValue: '8',
        type: 'number',
        help: '并发上传线程数；断点续传会跳过已成功上传的图片。'
    },
    S3_MANIFEST_JSON: {label: 'S3 图片清单 JSON', defaultValue: '', type: 'text'},
    S3_IMAGE_URL_MODE: {
        label: 'LS 图片地址模式',
        defaultValue: 'nginx',
        type: 'select',
        options: ['nginx', 'proxy', 'https', 's3']
    },
    S3_PROXY_BACKEND: {label: 'S3 代理后端', defaultValue: 'nginx', type: 'select', options: ['nginx', 'python']},
    S3_PROXY_HOST: {label: 'S3 代理 Host', defaultValue: '127.0.0.1', type: 'text'},
    S3_PROXY_PORT: {label: 'S3 代理端口', defaultValue: '3010', type: 'number'},
    S3_PROXY_BASE_URL: {label: 'S3 代理 Base URL', defaultValue: 'http://127.0.0.1:3010', type: 'text'},
    S3_PROXY_ALLOWED_ORIGIN: {label: '代理允许 Origin', defaultValue: 'http://localhost:9001', type: 'text'},
    S3_NGINX_BIN: {label: 'Nginx 命令', defaultValue: 'nginx', type: 'text'},
    S3_NGINX_MODE: {
        label: 'Nginx 回源模式',
        defaultValue: 'presign',
        type: 'select',
        options: ['presign', 'direct'],
        help: '私有桶用 presign；公开桶可用 direct。'
    },
    S3_NGINX_PRESIGN_EXPIRES: {
        label: '预签名秒数',
        defaultValue: '604800',
        type: 'number',
        help: '默认 7 天，过期前可刷新 Nginx 图片代理。'
    },
    S3_NGINX_CONF: {
        label: 'Nginx 配置路径',
        defaultValue: '',
        type: 'text',
        help: '留空时使用 .tmp/s3-nginx/<数据集>/nginx.conf。'
    },
    S3_NGINX_MAP: {
        label: 'Nginx map 路径',
        defaultValue: '',
        type: 'text',
        help: '留空时使用 .tmp/s3-nginx/<数据集>/s3_image_map.conf。'
    },
    S3_NGINX_CACHE_DIR: {
        label: 'Nginx 缓存目录',
        defaultValue: '',
        type: 'text',
        help: '留空时使用 .tmp/s3-nginx/<数据集>/cache。'
    },
    S3_NGINX_PID: {
        label: 'Nginx PID 路径',
        defaultValue: '',
        type: 'text',
        help: '留空时使用 .tmp/s3-nginx/<数据集>/nginx.pid。'
    },
    S3_LS_IMPORT_JSON: {label: 'S3 LS 导入 JSON', defaultValue: '', type: 'text'},
    S3_LS_LABEL_CONFIG_XML: {label: 'S3 LS 标签配置', defaultValue: '', type: 'text'},
    S3_LS_EXPORT_PATH: {
        label: 'S3 LS 导出 JSON',
        defaultValue: '',
        type: 'text',
        help: '通用流程留空时使用 datasets/<国家>/<版本>/<数据集>/label_studio/exports/label_studio_export.json。'
    },
    S3_DATA_YAML: {
        label: 'S3 YOLO YAML',
        defaultValue: '',
        type: 'text',
        help: '通用流程留空时使用 config/generated/<国家>_<版本>_<数据集>.yaml。'
    },
    S3_EC2_IMAGE_MANIFEST_JSON: {
        label: '本地 EC2 图片清单 JSON',
        defaultValue: '',
        type: 'text',
        help: '标注转 YOLO 后生成，默认 metadata/ec2_image_manifest.json；不同于上传清单 s3_images.json。'
    },
    S3_EC2_IMAGE_MANIFEST_CSV: {
        label: '本地 EC2 图片清单 CSV',
        defaultValue: '',
        type: 'text',
        help: '标注转 YOLO 后生成，默认 metadata/ec2_image_manifest.csv；会随 JSON 一起上传到 EC2。'
    },
    S3_EC2_REMOTE_MANIFEST_JSON: {
        label: '远端 EC2 图片清单 JSON',
        defaultValue: '',
        type: 'text',
        help: '通用流程默认 datasets/<国家>/<版本>/<数据集>/s3/metadata/ec2_image_manifest.json。'
    },
    S3_EC2_REMOTE_MANIFEST_CSV: {
        label: '远端 EC2 图片清单 CSV',
        defaultValue: '',
        type: 'text',
        help: '通用流程默认 datasets/<国家>/<版本>/<数据集>/s3/metadata/ec2_image_manifest.csv。'
    },
    S3_EC2_DOWNLOAD_MODE: {
        label: 'EC2 图片下载模式',
        defaultValue: 'auto',
        type: 'select',
        options: ['auto', 'public', 'boto3'],
        help: 'auto 优先公共 URL，public 强制公共 URL，boto3 使用 AWS SDK/IAM。'
    },
    S3_LS_TO_YOLO_CLEAR: {label: 'S3 转换前清空 labels', defaultValue: '0', type: 'select', options: ['0', '1']},
    S3_LS_TO_YOLO_SKIP_EMPTY: {label: 'S3 跳过空标注', defaultValue: '0', type: 'select', options: ['0', '1']},
    S3_EC2_LOCAL_ARTIFACT_ROOT: {label: 'S3 本地归档下载目录', defaultValue: '', type: 'text'},
    S3_FINAL_MODEL: {label: 'S3 本地下载模型', defaultValue: '', type: 'text'},
    POSTGRE_USER: {label: 'PostgreSQL 用户', defaultValue: 'guobiao', type: 'text'},
    POSTGRE_NAME: {label: 'PostgreSQL 数据库', defaultValue: 'labelstudio', type: 'text'},
    POSTGRE_HOST: {label: 'PostgreSQL Host', defaultValue: 'localhost', type: 'text'},
    POSTGRE_PORT: {label: 'PostgreSQL 端口', defaultValue: '5432', type: 'number'},
    TRAIN_BASE_MODEL: {label: '训练基座模型', defaultValue: 'models/yolo26m.pt', type: 'text'},
    TRAIN_EPOCHS: {label: '训练轮数', defaultValue: '55', type: 'number'},
    TRAIN_IMGSZ: {label: '训练图片尺寸', defaultValue: '960', type: 'number'},
    TRAIN_BATCH: {label: '训练 batch', defaultValue: '-1', type: 'text'},
    TRAIN_DEVICE: {label: '训练设备', defaultValue: 'mps', type: 'select', options: ['mps', 'cpu', '0']},
    TRAIN_RESUME: {label: '恢复训练', defaultValue: '0', type: 'select', options: ['0', '1']},
    TRAIN_NAME: {label: '训练 run 名称', defaultValue: '', type: 'text'},
    PREDICT_SOURCE: {label: '推理图片/URL', defaultValue: 'data/samples/multibrand-shelf.webp', type: 'text'},
    PREDICT_MODEL: {label: '推理模型', defaultValue: '', type: 'text'},
    PREDICT_CONF: {label: '推理置信度', defaultValue: '0.35', type: 'number'},
    PREDICT_IMGSZ: {label: '推理图片尺寸', defaultValue: '960', type: 'number'},
    PREDICT_OUTPUT_DIR: {label: '推理输出目录', defaultValue: 'outputs/predict', type: 'text'},
    DIAPER_COUNTRY: {label: '国家/市场', defaultValue: 'CI', type: 'text'},
    DIAPER_VERSION: {label: '数据版本', defaultValue: 'v2026-08-28', type: 'text'},
    DIAPER_EXCEL: {label: '纸尿裤 Excel', defaultValue: '', type: 'text'},
    DIAPER_EXCEL_COLUMN: {label: '纸尿裤图片 URL 列名', defaultValue: '', type: 'text'},
    DIAPER_LABEL_NAME: {label: '纸尿裤标签名', defaultValue: 'diaper', type: 'text'},
    DIAPER_DATASET_ROOT: {label: '纸尿裤本地数据集目录', defaultValue: '', type: 'text'},
    DIAPER_DATA_YAML: {label: '纸尿裤本地 YAML', defaultValue: '', type: 'text'},
    DIAPER_MERGED_LS_EXPORT_PATH: {label: '合并后 LS JSON', defaultValue: '', type: 'text'},
    DIAPER_MERGE_REPORT: {label: '合并报告 JSON', defaultValue: '', type: 'text'},
    S3_LOCAL_MERGED_LS_EXPORT_PATH: {
        label: 'S3 本地 LS 合并导出',
        defaultValue: '',
        type: 'text',
        help: '本地地址多项目 LS 合并后的 JSON；默认写到 S3 数据集 label_studio/exports。'
    },
    S3_LOCAL_MERGE_REPORT: {
        label: 'S3 本地 LS 合并报告',
        defaultValue: '',
        type: 'text',
        help: '本地地址多项目 LS 合并报告 JSON。'
    },
    EC2_HOST: {label: 'EC2 Host', defaultValue: '3.232.95.101', type: 'text'},
    EC2_USER: {label: 'EC2 用户', defaultValue: 'ec2-user', type: 'text'},
    EC2_KEY: {label: 'SSH 私钥路径', defaultValue: '~/.ssh/smdp-yolo-gpu-key.pem', type: 'text'},
    EC2_PORT: {label: 'EC2 SSH 端口', defaultValue: '22', type: 'number'},
    EC2_PROJECT_ROOT: {label: 'EC2 项目根目录', defaultValue: '/home/ec2-user/yoloExample', type: 'text'},
    EC2_REMOTE_DATA_YAML: {label: 'EC2 YAML 路径', defaultValue: '', type: 'text'},
    EC2_BASE_MODEL: {label: 'EC2 基座模型', defaultValue: 'yolo26m.pt', type: 'text'},
    EC2_TRAIN_EPOCHS: {label: 'EC2 训练轮数', defaultValue: '100', type: 'number'},
    EC2_TRAIN_IMGSZ: {label: 'EC2 图片尺寸', defaultValue: '960', type: 'number'},
    EC2_TRAIN_BATCH: {label: 'EC2 batch', defaultValue: '-1', type: 'text'},
    EC2_TRAIN_DEVICE: {label: 'EC2 设备', defaultValue: '0', type: 'text'},
    EC2_EXECUTE: {
        label: '真实执行 EC2 命令',
        defaultValue: '0',
        type: 'select',
        options: ['0', '1'],
        help: '默认 0 只 dry-run；改成 1 才会连接 EC2。'
    },
    EC2_EVAL_NOTES: {label: '评估备注', defaultValue: 'training start', type: 'text'},
    EC2_RUN_NAME: {
        label: 'EC2 运行标识',
        defaultValue: 'yolo26m_img960_e100',
        type: 'text',
        help: '只用于模型、归档和报告目录；训练规模由模型参数决定。'
    },
    EC2_PREDICT_SOURCE: {label: 'EC2 推理图片路径', defaultValue: 'data/samples/multibrand-shelf.webp', type: 'text'},
    EC2_PREDICT_MANIFEST_SOURCE: {
        label: 'EC2 批量推理清单',
        defaultValue: '',
        type: 'text',
        help: '支持 s3://、http(s):// 或 EC2 本地 txt/csv/json/xlsx 清单；本地文件推荐填 EC2_PREDICT_LOCAL_MANIFEST。'
    },
    EC2_PREDICT_LOCAL_MANIFEST: {
        label: '本地推理清单',
        defaultValue: '',
        type: 'text',
        help: '本机 Excel/CSV/JSON/TXT 文件路径；执行时会先 rsync 上传到 EC2。'
    },
    EC2_PREDICT_REMOTE_MANIFEST: {
        label: '远端推理清单路径',
        defaultValue: '',
        type: 'text',
        help: '留空时自动上传到 EC2 推理工作目录的 manifest 子目录。'
    },
    EC2_PREDICT_OUTPUT_S3_URI: {
        label: '推理结果 S3 目录',
        defaultValue: '',
        type: 'text',
        help: '必填，格式 s3://bucket/prefix；结果会上传 summary、单图 JSON 和带框图片。'
    },
    EC2_PREDICT_MODEL: {
        label: 'EC2 推理模型',
        defaultValue: '',
        type: 'text',
        help: '留空时使用当前数据集和 EC2_RUN_NAME 对应的远端 best.pt。'
    },
    EC2_PREDICT_INPUT_COLUMN: {
        label: '清单图片地址列',
        defaultValue: '',
        type: 'text',
        help: 'CSV/Excel/JSON 可指定列名；留空时自动扫描图片地址。'
    },
    EC2_PREDICT_WORK_DIR: {label: 'EC2 推理工作目录', defaultValue: '', type: 'text'},
    EC2_PREDICT_CONF: {label: 'EC2 推理置信度', defaultValue: '0.35', type: 'number'},
    EC2_PREDICT_IMGSZ: {label: 'EC2 推理图片尺寸', defaultValue: '960', type: 'number'},
    EC2_PREDICT_LIMIT: {label: 'EC2 推理数量上限', defaultValue: '0', type: 'number', help: '0 表示全量。'},
    EC2_PREDICT_DOWNLOAD_SOURCE_IMAGES: {
        label: '下载原始推理图片',
        defaultValue: '1',
        type: 'select',
        options: ['1', '0']
    },
    EC2_PREDICT_SOURCE_DOWNLOAD_TIMEOUT: {
        label: '原图下载超时秒数',
        defaultValue: '30',
        type: 'number',
        help: '下载 HTTP(S) 原始推理图片的超时秒数，避免单张图片长时间卡住。'
    },
    EC2_PREDICT_DOWNLOAD_WORKERS: {
        label: '下载并发数',
        defaultValue: '8',
        type: 'number',
        help: '并发下载推理结果文件和原始推理图片的线程数。'
    },
    EC2_PREDICT_LOCAL_RESULT_ROOT: {label: '本地推理结果目录', defaultValue: '', type: 'text'},
    EC2_PREDICT_LOCAL_SOURCE_IMAGE_ROOT: {label: '本地推理原图目录', defaultValue: '', type: 'text'},
    LABEL_S3_LS_TO_YOLO_REPORT: {label: '通用 S3 转换报告', defaultValue: '', type: 'text'},
    LABEL_S3_DATA_YAML: {label: '通用 S3 YOLO YAML', defaultValue: '', type: 'text'},
};

function collectCommands(nodes) {
    const commands = [];
    for (const node of nodes) {
        if (Array.isArray(node.commands)) {
            commands.push(...node.commands);
        }
        if (Array.isArray(node.children)) {
            commands.push(...collectCommands(node.children));
        }
    }
    return commands;
}

const TARGETS = new Set(collectCommands(COMMAND_GROUPS).map((command) => command.target));
const ALLOWED_VARIABLES = new Set(Object.keys(PARAM_DEFINITIONS));
const SENSITIVE_STATE_PARAMS = new Set(['EC2_KEY', 'POSTGRE_PASSWORD']);
const jobs = new Map();

const DEFAULT_CONSOLE_STATE = {
    paramCache: {},
    favorites: [],
};

function plainObject(value) {
    return value && typeof value === 'object' && !Array.isArray(value);
}

function sanitizeParamCache(rawCache) {
    const cleaned = {};
    if (!plainObject(rawCache)) {
        return cleaned;
    }
    for (const [key, rawValue] of Object.entries(rawCache)) {
        if (!ALLOWED_VARIABLES.has(key)) {
            continue;
        }
        const value = String(rawValue ?? '').trim();
        if (value && !SENSITIVE_STATE_PARAMS.has(key)) {
            cleaned[key] = value.slice(0, 2000);
        }
    }
    return cleaned;
}

function sanitizeFavoriteParams(rawParams) {
    const cleaned = sanitizeParamCache(rawParams);
    for (const key of SENSITIVE_STATE_PARAMS) {
        delete cleaned[key];
    }
    return cleaned;
}

function sanitizeFavorites(rawFavorites) {
    if (!Array.isArray(rawFavorites)) {
        return [];
    }
    return rawFavorites.slice(0, 200).flatMap((item, index) => {
        if (!plainObject(item) || !TARGETS.has(String(item.target || ''))) {
            return [];
        }
        const id = String(item.id || `fav_${Date.now()}_${index}`).slice(0, 80);
        const group = String(item.group || '默认').trim().slice(0, 80) || '默认';
        const title = String(item.title || item.target).trim().slice(0, 120) || String(item.target);
        return [{id, group, title, target: String(item.target), params: sanitizeFavoriteParams(item.params)}];
    });
}

function sanitizeConsoleState(rawState) {
    if (!plainObject(rawState)) {
        return {...DEFAULT_CONSOLE_STATE};
    }
    return {
        paramCache: sanitizeParamCache(rawState.paramCache),
        favorites: sanitizeFavorites(rawState.favorites),
    };
}

function mergeConsoleState(rawState) {
    const state = sanitizeConsoleState(rawState);
    return {
        ...DEFAULT_CONSOLE_STATE,
        ...state,
    };
}

function jsonResponse(response, statusCode, payload) {
    response.writeHead(statusCode, {
        'Content-Type': 'application/json; charset=utf-8',
        'Cache-Control': 'no-store',
    });
    response.end(JSON.stringify(payload, null, 2));
}

function textResponse(response, statusCode, text, contentType = 'text/plain; charset=utf-8') {
    response.writeHead(statusCode, {'Content-Type': contentType});
    response.end(text);
}

function notFound(response) {
    jsonResponse(response, 404, {error: '接口不存在'});
}

function isPathInside(parent, candidate) {
    const relative = path.relative(parent, candidate);
    return relative === '' || (!relative.startsWith('..') && !path.isAbsolute(relative));
}

function projectRelativePath(absPath) {
    return path.relative(PROJECT_ROOT, absPath).split(path.sep).join('/');
}

function dataRootById(rootId) {
    const root = DATA_ROOTS.find((item) => item.id === rootId);
    if (!root) {
        return null;
    }
    return {...root, absPath: path.join(PROJECT_ROOT, root.relativePath)};
}

function isAllowedImagePath(absPath) {
    const ext = path.extname(absPath).toLowerCase();
    return IMAGE_EXTENSIONS.has(ext) && ALLOWED_FILE_ROOTS.some((root) => isPathInside(root, absPath));
}

async function readJsonBody(request) {
    let total = 0;
    const chunks = [];
    for await (const chunk of request) {
        total += chunk.length;
        if (total > MAX_BODY_BYTES) {
            throw new Error('请求体过大');
        }
        chunks.push(chunk);
    }
    if (chunks.length === 0) {
        return {};
    }
    return JSON.parse(Buffer.concat(chunks).toString('utf8'));
}

async function pathExists(absPath) {
    try {
        await fsp.access(absPath);
        return true;
    } catch (_error) {
        return false;
    }
}

async function readConsoleState() {
    try {
        const raw = await fsp.readFile(CONSOLE_STATE_PATH, 'utf8');
        return sanitizeConsoleState(JSON.parse(raw));
    } catch (error) {
        if (error.code === 'ENOENT') {
            return mergeConsoleState({});
        }
        throw error;
    }
}

async function writeConsoleState(rawState) {
    const state = sanitizeConsoleState(rawState);
    const tempPath = `${CONSOLE_STATE_PATH}.tmp`;
    await fsp.writeFile(tempPath, `${JSON.stringify(state, null, 2)}\n`, 'utf8');
    await fsp.rename(tempPath, CONSOLE_STATE_PATH);
    return state;
}

async function readLabelCatalog() {
    try {
        const raw = await fsp.readFile(LABEL_CATALOG_PATH, 'utf8');
        return sanitizeLabelCatalog(JSON.parse(raw));
    } catch (error) {
        if (error.code === 'ENOENT') {
            return {description: 'YOLO 通用标签类别配置。', sets: []};
        }
        throw error;
    }
}

function slugify(value, fallback = 'label') {
    const ascii = String(value || '')
        .trim()
        .toLowerCase()
        .replace(/[^a-z0-9]+/g, '_')
        .replace(/^_+|_+$/g, '');
    if (ascii) return ascii;
    const unicode = String(value || '')
        .trim()
        .replace(/[^0-9a-zA-Z一-鿿]+/g, '_')
        .replace(/^_+|_+$/g, '');
    return unicode || fallback;
}

function sanitizeLabelCatalog(rawCatalog) {
    const catalog = plainObject(rawCatalog) ? rawCatalog : {};
    const rawSets = Array.isArray(catalog.sets) ? catalog.sets : [];
    return {
        description: String(catalog.description || 'YOLO 通用标签类别配置。').slice(0, 1000),
        sets: rawSets.slice(0, 50).flatMap((rawSet) => {
            if (!plainObject(rawSet)) return [];
            const name = slugify(rawSet.name || rawSet.display_name || 'labels', 'labels').slice(0, 80);
            const rawClasses = Array.isArray(rawSet.classes) ? rawSet.classes : [];
            return [{
                name,
                display_name: String(rawSet.display_name || name).trim().slice(0, 120) || name,
                description: String(rawSet.description || '').slice(0, 1000),
                task_type: String(rawSet.task_type || 'detection').slice(0, 60),
                classes: rawClasses.slice(0, 500).flatMap((rawClass, index) => {
                    if (!plainObject(rawClass) && typeof rawClass !== 'string') return [];
                    const item = typeof rawClass === 'string' ? {name: rawClass} : rawClass;
                    const className = String(item.name || item.display_name || '').trim();
                    if (!className) return [];
                    const classId = Number.isInteger(Number(item.class_id)) ? Number(item.class_id) : index;
                    const aliases = Array.isArray(item.aliases)
                        ? item.aliases.map((alias) => String(alias).trim()).filter(Boolean).slice(0, 100)
                        : [];
                    return [{
                        class_id: classId,
                        name: className.slice(0, 120),
                        class_name: slugify(item.class_name || className).slice(0, 120),
                        aliases,
                        enabled: item.enabled !== false,
                        description: String(item.description || '').slice(0, 500),
                    }];
                }),
            }];
        }),
    };
}

async function writeLabelCatalog(rawCatalog) {
    const catalog = sanitizeLabelCatalog(rawCatalog);
    const tempPath = `${LABEL_CATALOG_PATH}.tmp`;
    await fsp.writeFile(tempPath, `${JSON.stringify(catalog, null, 2)}\n`, 'utf8');
    await fsp.rename(tempPath, LABEL_CATALOG_PATH);
    return catalog;
}

async function walkFiles(rootPath, options = {}) {
    const recursive = options.recursive !== false;
    const maxFiles = options.maxFiles || 20000;
    const includeReports = options.includeReports || false;
    const files = [];

    async function visit(currentPath, depth) {
        if (files.length >= maxFiles) {
            return;
        }
        let entries;
        try {
            entries = await fsp.readdir(currentPath, {withFileTypes: true});
        } catch (_error) {
            return;
        }

        for (const entry of entries) {
            if (files.length >= maxFiles) {
                return;
            }
            if (entry.name.startsWith('.')) {
                continue;
            }
            const absPath = path.join(currentPath, entry.name);
            if (entry.isDirectory()) {
                if (recursive && depth < 12) {
                    await visit(absPath, depth + 1);
                }
                continue;
            }
            if (!entry.isFile()) {
                continue;
            }
            const ext = path.extname(entry.name).toLowerCase();
            if (!IMAGE_EXTENSIONS.has(ext) && !(includeReports && TEXT_REPORT_EXTENSIONS.has(ext))) {
                continue;
            }
            let stat;
            try {
                stat = await fsp.stat(absPath);
            } catch (_error) {
                continue;
            }
            files.push({
                name: entry.name,
                absPath,
                relativePath: projectRelativePath(absPath),
                size: stat.size,
                mtimeMs: stat.mtimeMs,
                ext,
                isImage: IMAGE_EXTENSIONS.has(ext),
            });
        }
    }

    await visit(rootPath, 0);
    return files;
}

function formatBytes(bytes) {
    if (bytes < 1024) {
        return `${bytes} B`;
    }
    const units = ['KB', 'MB', 'GB', 'TB'];
    let value = bytes / 1024;
    for (const unit of units) {
        if (value < 1024) {
            return `${value.toFixed(value >= 10 ? 1 : 2)} ${unit}`;
        }
        value /= 1024;
    }
    return `${value.toFixed(1)} PB`;
}

async function countFilesByExtension(rootPath) {
    const summary = {
        exists: await pathExists(rootPath),
        totalFiles: 0,
        imageFiles: 0,
        labelFiles: 0,
        jsonFiles: 0,
        csvFiles: 0,
        modelFiles: 0,
        totalBytes: 0,
        readableSize: '0 B',
        byExtension: {},
    };
    if (!summary.exists) {
        return summary;
    }

    const stack = [rootPath];
    while (stack.length > 0) {
        const current = stack.pop();
        let entries;
        try {
            entries = await fsp.readdir(current, {withFileTypes: true});
        } catch (_error) {
            continue;
        }
        for (const entry of entries) {
            if (entry.name.startsWith('.')) {
                continue;
            }
            const absPath = path.join(current, entry.name);
            if (entry.isDirectory()) {
                stack.push(absPath);
                continue;
            }
            if (!entry.isFile()) {
                continue;
            }
            let stat;
            try {
                stat = await fsp.stat(absPath);
            } catch (_error) {
                continue;
            }
            const ext = path.extname(entry.name).toLowerCase() || '(no ext)';
            summary.totalFiles += 1;
            summary.totalBytes += stat.size;
            summary.byExtension[ext] = (summary.byExtension[ext] || 0) + 1;
            if (IMAGE_EXTENSIONS.has(ext)) {
                summary.imageFiles += 1;
            } else if (ext === '.txt') {
                summary.labelFiles += 1;
            } else if (ext === '.json') {
                summary.jsonFiles += 1;
            } else if (ext === '.csv') {
                summary.csvFiles += 1;
            } else if (ext === '.pt' || ext === '.onnx' || ext === '.pth') {
                summary.modelFiles += 1;
            }
        }
    }
    summary.readableSize = formatBytes(summary.totalBytes);
    return summary;
}

async function countFilesInDirectory(absPath, extensions) {
    let count = 0;
    let totalBytes = 0;
    try {
        const entries = await fsp.readdir(absPath, {withFileTypes: true});
        for (const entry of entries) {
            if (!entry.isFile()) {
                continue;
            }
            const ext = path.extname(entry.name).toLowerCase();
            if (extensions.has(ext)) {
                count += 1;
                try {
                    totalBytes += (await fsp.stat(path.join(absPath, entry.name))).size;
                } catch (_error) {
                    // 单个文件读取失败不影响目录整体统计。
                }
            }
        }
    } catch (_error) {
        return {count: 0, totalBytes: 0};
    }
    return {count, totalBytes};
}

async function datasetSplitSummary(datasetRelativePath) {
    const datasetRoot = path.join(PROJECT_ROOT, datasetRelativePath);
    const splits = {};
    for (const split of ['train', 'val', 'test']) {
        const imageStats = await countFilesInDirectory(path.join(datasetRoot, 'images', split), IMAGE_EXTENSIONS);
        const labelStats = await countFilesInDirectory(path.join(datasetRoot, 'labels', split), new Set(['.txt']));
        splits[split] = {
            images: imageStats.count,
            labels: labelStats.count,
            imageBytes: imageStats.totalBytes,
        };
    }
    return {
        dataset: datasetRelativePath,
        splits,
    };
}

async function discoverDatasetSplits() {
    const candidates = [];
    const datasetsRoot = path.join(PROJECT_ROOT, 'datasets');

    async function visit(currentPath, depth) {
        if (depth > 5) return;
        const imageRoot = path.join(currentPath, 'images');
        const labelRoot = path.join(currentPath, 'labels');
        if (await pathExists(imageRoot) || await pathExists(labelRoot)) {
            candidates.push(projectRelativePath(currentPath));
        }
        let entries;
        try {
            entries = await fsp.readdir(currentPath, {withFileTypes: true});
        } catch (_error) {
            return;
        }
        for (const entry of entries) {
            if (entry.isDirectory() && !entry.name.startsWith('.') && !['images', 'labels', 'raw', 'pseudo', 'ocr'].includes(entry.name)) {
                await visit(path.join(currentPath, entry.name), depth + 1);
            }
        }
    }

    await visit(datasetsRoot, 0);

    const results = [];
    for (const candidate of candidates) {
        const hasImages = await pathExists(path.join(PROJECT_ROOT, candidate, 'images'));
        const hasLabels = await pathExists(path.join(PROJECT_ROOT, candidate, 'labels'));
        if (hasImages || hasLabels) {
            results.push(await datasetSplitSummary(candidate));
        }
    }
    return results;
}

async function summarizeReportFile(file) {
    try {
        const raw = await fsp.readFile(file.absPath, 'utf8');
        const data = JSON.parse(raw);
        if (Array.isArray(data)) {
            return {path: file.relativePath, type: 'json_array', total: data.length};
        }
        if (!plainObject(data)) {
            return {path: file.relativePath, type: 'json_value'};
        }
        const keys = ['converted_count', 'box_count', 'class_counts', 'merged_count', 'total_input_tasks', 'total_kept_tasks', 'warnings'];
        const summary = {path: file.relativePath, type: 'json_summary'};
        for (const key of keys) {
            if (Object.prototype.hasOwnProperty.call(data, key)) {
                summary[key] = key === 'warnings' && Array.isArray(data[key]) ? data[key].length : data[key];
            }
        }
        if (Array.isArray(data.items)) summary.items = data.items.length;
        return summary;
    } catch (error) {
        return {path: file.relativePath, type: 'json_summary', error: error.message};
    }
}

async function discoverReportSummaries() {
    const datasetFiles = await walkFiles(path.join(PROJECT_ROOT, 'datasets'), {
        recursive: true,
        includeReports: true,
        maxFiles: 8000
    });
    const reportFiles = datasetFiles
        .filter((file) => file.ext === '.json' && /(report|manifest|s3_images)/.test(file.name))
        .sort((left, right) => right.mtimeMs - left.mtimeMs)
        .slice(0, 12);
    const summaries = [];
    for (const file of reportFiles) {
        summaries.push(await summarizeReportFile(file));
    }
    return summaries;
}

async function dataSummary() {
    const roots = [];
    for (const root of DATA_ROOTS) {
        const absPath = path.join(PROJECT_ROOT, root.relativePath);
        roots.push({
            ...root,
            ...(await countFilesByExtension(absPath)),
        });
    }

    return {
        projectRoot: PROJECT_ROOT,
        roots,
        splits: await discoverDatasetSplits(),
        reports: await discoverReportSummaries(),
    };
}

async function readBrands() {
    try {
        const data = await readLabelCatalog();
        const brandSet = (data.sets || []).find((item) => item.name === 'brands');
        const catalogNames = (brandSet?.classes || [])
            .filter((brand) => brand.enabled !== false && brand.name)
            .map((brand) => brand.name);
        if (catalogNames.length > 0) {
            return ['all', ...catalogNames];
        }
    } catch (_error) {
        // 读取通用类别失败时继续回退到历史品牌库。
    }

    try {
        const brandPath = path.join(PROJECT_ROOT, 'config', 'brand_keywords.json');
        const data = JSON.parse(await fsp.readFile(brandPath, 'utf8'));
        const names = (data.brands || [])
            .filter((brand) => brand.enabled !== false && brand.name)
            .map((brand) => brand.name);
        return ['all', ...names];
    } catch (_fallbackError) {
        return ['all'];
    }
}

async function labelCatalogOptions() {
    const catalog = await readLabelCatalog();
    const sets = Array.isArray(catalog.sets) ? catalog.sets : [];
    const setNames = sets.map((item) => item.name).filter(Boolean);
    const labelsBySet = {};
    for (const item of sets) {
        labelsBySet[item.name] = (item.classes || []).filter((label) => label.enabled !== false).map((label) => label.name);
    }
    return {catalog, setNames, labelsBySet};
}

function normalizeVariables(rawVariables) {
    const variables = {};
    if (!rawVariables || typeof rawVariables !== 'object' || Array.isArray(rawVariables)) {
        return variables;
    }
    for (const [key, rawValue] of Object.entries(rawVariables)) {
        if (!/^[A-Z0-9_]+$/.test(key)) {
            throw new Error(`变量名不合法：${key}`);
        }
        if (!ALLOWED_VARIABLES.has(key)) {
            throw new Error(`变量不在页面白名单中：${key}`);
        }
        const value = String(rawValue ?? '').trim();
        if (value.length === 0) {
            continue;
        }
        variables[key] = value;
    }
    return variables;
}

function commandLineForDisplay(target, variables) {
    const parts = ['make', target];
    for (const [key, value] of Object.entries(variables)) {
        const safeValue = /[\s'"\\]/.test(value) ? JSON.stringify(value) : value;
        parts.push(`${key}=${safeValue}`);
    }
    return parts.join(' ');
}

function appendJobLog(job, chunk) {
    job.log += chunk;
    if (job.log.length > MAX_LOG_BYTES) {
        job.log = `...前面日志已截断...\n${job.log.slice(-MAX_LOG_BYTES)}`;
    }
}

function publicJob(job) {
    return {
        id: job.id,
        target: job.target,
        variables: job.variables,
        commandLine: job.commandLine,
        status: job.status,
        startedAt: job.startedAt,
        finishedAt: job.finishedAt,
        exitCode: job.exitCode,
        signal: job.signal,
        log: job.log,
    };
}

function startJob(target, variables) {
    if (!TARGETS.has(target)) {
        throw new Error(`命令不在白名单中：${target}`);
    }
    const id = `job_${Date.now()}_${Math.random().toString(36).slice(2, 8)}`;
    const makeArgs = [target, ...Object.entries(variables).map(([key, value]) => `${key}=${value}`)];
    const job = {
        id,
        target,
        variables,
        commandLine: commandLineForDisplay(target, variables),
        status: 'running',
        startedAt: new Date().toISOString(),
        finishedAt: null,
        exitCode: null,
        signal: null,
        log: '',
        process: null,
    };
    const child = spawn('make', makeArgs, {
        cwd: PROJECT_ROOT,
        env: process.env,
        shell: false,
        detached: true,
    });
    job.process = child;
    jobs.set(id, job);

    appendJobLog(job, `$ ${job.commandLine}\n`);
    child.stdout.on('data', (chunk) => appendJobLog(job, chunk.toString('utf8')));
    child.stderr.on('data', (chunk) => appendJobLog(job, chunk.toString('utf8')));
    child.on('error', (error) => {
        job.status = 'failed';
        job.finishedAt = new Date().toISOString();
        appendJobLog(job, `\n[启动失败] ${error.message}\n`);
    });
    child.on('close', (code, signal) => {
        if (job.status === 'stopping') {
            job.status = 'stopped';
        } else {
            job.status = code === 0 ? 'success' : 'failed';
        }
        job.exitCode = code;
        job.signal = signal;
        job.finishedAt = new Date().toISOString();
        appendJobLog(job, `\n[任务结束] status=${job.status} exitCode=${code} signal=${signal || ''}\n`);
    });
    return job;
}

function stopJob(job) {
    if (!job || !job.process || !['running', 'stopping'].includes(job.status)) {
        return false;
    }
    job.status = 'stopping';
    appendJobLog(job, '\n[停止请求] 正在终止 Make 进程组...\n');
    try {
        process.kill(-job.process.pid, 'SIGTERM');
    } catch (_error) {
        try {
            job.process.kill('SIGTERM');
        } catch (error) {
            appendJobLog(job, `[停止失败] ${error.message}\n`);
            return false;
        }
    }
    return true;
}

async function handleConfig(_request, response) {
    const brands = await readBrands();
    const {catalog, setNames, labelsBySet} = await labelCatalogOptions();
    const paramDefinitions = JSON.parse(JSON.stringify(PARAM_DEFINITIONS));
    paramDefinitions.BRAND.options = brands;
    paramDefinitions.LABEL_SET.options = setNames.length > 0 ? setNames : ['general'];
    paramDefinitions.LABELS.options = Object.values(labelsBySet).flat().filter((value, index, array) => array.indexOf(value) === index);
    jsonResponse(response, 200, {
        projectRoot: PROJECT_ROOT,
        commandGroups: COMMAND_GROUPS,
        params: paramDefinitions,
        dataRoots: DATA_ROOTS,
        labelCatalog: catalog,
        labelsBySet,
    });
}

async function handleImages(url, response) {
    const rootId = url.searchParams.get('root') || DATA_ROOTS[0].id;
    const page = Math.max(1, Number.parseInt(url.searchParams.get('page') || '1', 10));
    const pageSize = Math.min(120, Math.max(12, Number.parseInt(url.searchParams.get('pageSize') || '48', 10)));
    const query = (url.searchParams.get('q') || '').trim().toLowerCase();
    const root = dataRootById(rootId);
    if (!root) {
        jsonResponse(response, 400, {error: '未知数据目录'});
        return;
    }
    const files = await walkFiles(root.absPath, {recursive: root.recursive, maxFiles: 50000});
    const images = files
        .filter((file) => file.isImage)
        .filter((file) => !query || file.relativePath.toLowerCase().includes(query) || file.name.toLowerCase().includes(query))
        .sort((left, right) => right.mtimeMs - left.mtimeMs);
    const start = (page - 1) * pageSize;
    const items = images.slice(start, start + pageSize).map((file) => ({
        name: file.name,
        relativePath: file.relativePath,
        size: file.size,
        readableSize: formatBytes(file.size),
        mtime: new Date(file.mtimeMs).toISOString(),
        url: `/api/file?path=${encodeURIComponent(file.relativePath)}`,
    }));
    jsonResponse(response, 200, {
        root: rootId,
        page,
        pageSize,
        total: images.length,
        items,
    });
}

async function handleFile(url, response) {
    const requested = url.searchParams.get('path');
    if (!requested) {
        jsonResponse(response, 400, {error: '缺少 path 参数'});
        return;
    }
    const absPath = path.resolve(PROJECT_ROOT, requested);
    if (!isPathInside(PROJECT_ROOT, absPath) || !isAllowedImagePath(absPath)) {
        jsonResponse(response, 403, {error: '文件不在允许访问的图片目录内'});
        return;
    }
    if (!(await pathExists(absPath))) {
        jsonResponse(response, 404, {error: '图片不存在'});
        return;
    }
    const ext = path.extname(absPath).toLowerCase();
    const contentType = {
        '.jpg': 'image/jpeg',
        '.jpeg': 'image/jpeg',
        '.png': 'image/png',
        '.webp': 'image/webp',
        '.gif': 'image/gif',
        '.bmp': 'image/bmp',
    }[ext] || 'application/octet-stream';
    response.writeHead(200, {
        'Content-Type': contentType,
        'Cache-Control': 'private, max-age=60',
    });
    fs.createReadStream(absPath).pipe(response);
}

async function handleStartJob(request, response) {
    const body = await readJsonBody(request);
    const target = String(body.target || '').trim();
    const variables = normalizeVariables(body.variables || {});
    const job = startJob(target, variables);
    jsonResponse(response, 201, publicJob(job));
}

async function handleGetState(_request, response) {
    jsonResponse(response, 200, await readConsoleState());
}

async function handlePutState(request, response) {
    const body = await readJsonBody(request);
    jsonResponse(response, 200, await writeConsoleState(body));
}

async function handleGetLabelCatalog(_request, response) {
    jsonResponse(response, 200, await readLabelCatalog());
}

async function handlePutLabelCatalog(request, response) {
    const body = await readJsonBody(request);
    const catalog = await writeLabelCatalog(body);
    jsonResponse(response, 200, catalog);
}

function handleJob(url, response) {
    const id = decodeURIComponent(url.pathname.split('/').pop());
    const job = jobs.get(id);
    if (!job) {
        jsonResponse(response, 404, {error: '任务不存在'});
        return;
    }
    jsonResponse(response, 200, publicJob(job));
}

function handleStopJob(url, response) {
    const parts = url.pathname.split('/');
    const id = decodeURIComponent(parts[3] || '');
    const job = jobs.get(id);
    if (!job) {
        jsonResponse(response, 404, {error: '任务不存在'});
        return;
    }
    const stopped = stopJob(job);
    jsonResponse(response, 200, {stopped, job: publicJob(job)});
}

async function handleStatic(url, response) {
    let relativePath = url.pathname === '/' ? 'index.html' : url.pathname.replace(/^\//, '');
    if (relativePath.includes('..')) {
        textResponse(response, 403, 'Forbidden');
        return;
    }
    const absPath = path.join(PUBLIC_ROOT, relativePath);
    if (!isPathInside(PUBLIC_ROOT, absPath) || !(await pathExists(absPath))) {
        notFound(response);
        return;
    }
    const ext = path.extname(absPath).toLowerCase();
    const contentType = {
        '.html': 'text/html; charset=utf-8',
        '.js': 'text/javascript; charset=utf-8',
        '.css': 'text/css; charset=utf-8',
        '.svg': 'image/svg+xml',
    }[ext] || 'application/octet-stream';
    response.writeHead(200, {'Content-Type': contentType});
    fs.createReadStream(absPath).pipe(response);
}

async function router(request, response) {
    const url = new URL(request.url, `http://${request.headers.host || 'localhost'}`);
    try {
        if (request.method === 'GET' && url.pathname === '/api/config') {
            await handleConfig(request, response);
            return;
        }
        if (request.method === 'GET' && url.pathname === '/api/data/summary') {
            jsonResponse(response, 200, await dataSummary());
            return;
        }
        if (request.method === 'GET' && url.pathname === '/api/state') {
            await handleGetState(request, response);
            return;
        }
        if (request.method === 'GET' && url.pathname === '/api/label-catalog') {
            await handleGetLabelCatalog(request, response);
            return;
        }
        if (request.method === 'PUT' && url.pathname === '/api/label-catalog') {
            await handlePutLabelCatalog(request, response);
            return;
        }
        if (request.method === 'PUT' && url.pathname === '/api/state') {
            await handlePutState(request, response);
            return;
        }
        if (request.method === 'GET' && url.pathname === '/api/images') {
            await handleImages(url, response);
            return;
        }
        if (request.method === 'GET' && url.pathname === '/api/file') {
            await handleFile(url, response);
            return;
        }
        if (request.method === 'POST' && url.pathname === '/api/jobs') {
            await handleStartJob(request, response);
            return;
        }
        if (request.method === 'GET' && /^\/api\/jobs\/[^/]+$/.test(url.pathname)) {
            handleJob(url, response);
            return;
        }
        if (request.method === 'POST' && /^\/api\/jobs\/[^/]+\/stop$/.test(url.pathname)) {
            handleStopJob(url, response);
            return;
        }
        if (request.method === 'GET') {
            await handleStatic(url, response);
            return;
        }
        jsonResponse(response, 405, {error: '不支持的请求方法'});
    } catch (error) {
        jsonResponse(response, 500, {error: error.message});
    }
}

const server = http.createServer(router);

server.listen(PORT, '127.0.0.1', () => {
    console.log(`本地 YOLO 控制台已启动：http://localhost:${PORT}`);
    console.log(`项目根目录：${PROJECT_ROOT}`);
});
