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
const { spawn } = require('child_process');
const { URL } = require('url');

const PROJECT_ROOT = path.resolve(__dirname, '..');
const PUBLIC_ROOT = path.join(__dirname, 'public');
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
    id: 'multibrand_raw',
    label: '多品牌 / 原始图片',
    description: 'datasets/multibrand/raw/images',
    relativePath: 'datasets/multibrand/raw/images',
    recursive: true,
  },
  {
    id: 'multibrand_pseudo',
    label: '多品牌 / 预标注图片',
    description: 'datasets/multibrand/pseudo/images',
    relativePath: 'datasets/multibrand/pseudo/images',
    recursive: true,
  },
  {
    id: 'multibrand_train',
    label: '多品牌 / 正式训练图片',
    description: 'datasets/multibrand/images',
    relativePath: 'datasets/multibrand/images',
    recursive: true,
  },
  {
    id: 'diaper_category',
    label: '纸尿裤大类 / 全部图片',
    description: 'datasets/diaper_category',
    relativePath: 'datasets/diaper_category',
    recursive: true,
  },
  {
    id: 'local_datasets',
    label: '本地目录导入数据',
    description: 'datasets/local',
    relativePath: 'datasets/local',
    recursive: true,
  },
  {
    id: 's3_datasets',
    label: 'S3 训练图数据',
    description: 'datasets/s3',
    relativePath: 'datasets/s3',
    recursive: true,
  },
  {
    id: 'softcare_dataset',
    label: 'Softcare 单品牌数据',
    description: 'datasets/softcare',
    relativePath: 'datasets/softcare',
    recursive: true,
  },
  {
    id: 'visual_prompts',
    label: 'YOLOE 参考图',
    description: 'datasets/multibrand/visual_prompts',
    relativePath: 'datasets/multibrand/visual_prompts',
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
    id: 'ec2_artifacts',
    label: 'EC2 训练归档图片',
    description: 'artifacts/diaper_category',
    relativePath: 'artifacts/diaper_category',
    recursive: true,
  },
  {
    id: 's3_ec2_artifacts',
    label: 'S3 / EC2 训练归档',
    description: 'artifacts/s3',
    relativePath: 'artifacts/s3',
    recursive: true,
  },
  {
    id: 'sample_images',
    label: '示例图片',
    description: 'data/samples',
    relativePath: 'data/samples',
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
  'artifacts/diaper_category',
  'artifacts/s3',
  'data/samples',
].map((item) => path.join(PROJECT_ROOT, item));

/**
 * 命令分组和参数定义。
 * 这里只收敛日常最常用的 Make 目标，避免把所有底层目标无差别堆到页面上。
 */
const COMMAND_GROUPS = [
  {
    id: 'prepare_labeling',
    title: '图片来源 / 标注准备',
    description: '按图片来源和前置处理方式组织：Excel、本地目录、S3、OCR、预标注和 Label Studio 导入。',
    children: [
      {
        id: 'excel_ocr_yoloworld',
        title: 'Excel → OCR → YOLO-World → LS',
        description: '业务 Excel 图片下载后，使用常规 OCR 筛选，再用 YOLO-World 预标注并导入 Label Studio。',
        commands: [
          {
            target: 'workflow-to-ls',
            title: '一键到 Label Studio（常规 OCR + YOLO-World）',
            description: '执行 Excel 导入、常规 OCR、YOLO-World 预标注、生成并导入 Label Studio。',
            params: ['BRAND', 'EXCEL', 'EXCEL_COLUMN', 'OCR_LIMIT', 'PSEUDO_LIMIT', 'PSEUDO_CONF'],
          },
          {
            target: 'step-1-import-excel',
            title: '1. Excel 导入图片',
            description: '从 Excel 图片 URL 列下载原始图片。',
            params: ['EXCEL', 'EXCEL_COLUMN', 'EXCEL_WORKERS', 'EXCEL_TIMEOUT'],
          },
          {
            target: 'step-2-ocr',
            title: '2. 常规 OCR 筛选',
            description: '使用 RapidOCR/EasyOCR 筛选品牌候选图片。',
            params: ['BRAND', 'OCR_ENGINE', 'OCR_WORKERS', 'OCR_LIMIT', 'OCR_FUZZY_THRESHOLD', 'OCR_MIN_CONFIDENCE', 'OCR_RESUME'],
          },
          {
            target: 'step-3-pseudo-label',
            title: '3. YOLO-World 预标注',
            description: '用开放词汇模型生成品牌包装候选框。',
            params: ['BRAND', 'PSEUDO_MODEL', 'PSEUDO_LIMIT', 'PSEUDO_CONF', 'PSEUDO_IMGSZ', 'PSEUDO_USE_OCR_CANDIDATES', 'PSEUDO_NMS_IOU', 'PSEUDO_MAX_AREA_RATIO'],
          },
          {
            target: 'yolo-world-ab-test',
            title: 'YOLO-World A/B 测试',
            description: '用同一批图片对比多个 YOLO-World 模型并生成报告。',
            params: ['BRAND', 'AB_MODELS', 'AB_LIMIT', 'AB_PREVIEW_LIMIT', 'PSEUDO_CONF', 'PSEUDO_IMGSZ'],
          },
        ],
      },
      {
        id: 'excel_ollama_yoloworld',
        title: 'Excel → Ollama OCR → YOLO-World → LS',
        description: '业务 Excel 图片下载后，使用本地视觉大模型 OCR，再走 YOLO-World 预标注和 LS 导入。',
        commands: [
          {
            target: 'workflow-to-ls-llm',
            title: '一键到 Label Studio（Ollama OCR）',
            description: '使用本地视觉大模型 OCR，其余流程复用 YOLO-World 和 Label Studio。',
            params: ['BRAND', 'EXCEL', 'EXCEL_COLUMN', 'OCR_LIMIT', 'LLM_OCR_MODEL', 'LLM_OCR_WORKERS', 'PSEUDO_LIMIT'],
          },
          {
            target: 'step-2-ocr-llm',
            title: 'Ollama OCR 筛选',
            description: '使用本地 Ollama 视觉模型提取图片文字。',
            params: ['BRAND', 'OCR_LIMIT', 'LLM_OCR_MODEL', 'LLM_OCR_WORKERS', 'LLM_OCR_TIMEOUT', 'OCR_FUZZY_THRESHOLD', 'OCR_RESUME'],
          },
        ],
      },
      {
        id: 'excel_ocr_yoloe_visual',
        title: 'Excel → OCR → YOLOE Visual → LS',
        description: '业务 Excel 图片下载后，使用 OCR 候选和品牌参考图进行 YOLOE visual prompt 预标注。',
        commands: [
          {
            target: 'workflow-to-ls-visual',
            title: '一键到 Label Studio（YOLOE 视觉参考图）',
            description: '常规 OCR 后使用 YOLOE visual prompt 参考图生成预标注。',
            params: ['BRAND', 'EXCEL', 'EXCEL_COLUMN', 'OCR_LIMIT', 'PSEUDO_LIMIT', 'PSEUDO_VISUAL_MODEL', 'PSEUDO_VISUAL_DEVICE'],
          },
          {
            target: 'visual-prompts-import',
            title: '导入 YOLOE 品牌参考图',
            description: '从品牌图片 Excel 下载 visual prompt 参考图。',
            params: ['VISUAL_PROMPTS_EXCEL', 'VISUAL_PROMPTS_BRAND_COLUMN', 'VISUAL_PROMPTS_ATTACH_COLUMN', 'VISUAL_PROMPTS_LIMIT'],
          },
          {
            target: 'step-3-pseudo-label-visual',
            title: 'YOLOE 视觉参考图预标注',
            description: '读取品牌参考图，用 YOLOE visual prompt 生成候选框。',
            params: ['BRAND', 'PSEUDO_VISUAL_MODEL', 'PSEUDO_VISUAL_DEVICE', 'PSEUDO_VISUAL_REFERENCE_LIMIT', 'PSEUDO_LIMIT', 'PSEUDO_CONF', 'PSEUDO_IMGSZ'],
          },
        ],
      },
      {
        id: 'local_dir_labeling',
        title: '本地目录 → LS',
        description: '本机已有图片目录直接导入 Label Studio，人工标注后转为 YOLO 训练集。',
        commands: [
          {
            target: '1-local-dir-workflow-to-ls',
            title: '一键导入本地目录到 Label Studio',
            description: '扫描本地图片目录，生成单类别导入 JSON 和标签配置，并创建 Label Studio 项目。',
            params: ['LOCAL_IMAGES_DIR', 'LOCAL_DATASET_NAME', 'LOCAL_DATASET_ROOT', 'LOCAL_LABEL_NAME', 'LOCAL_RECURSIVE', 'LOCAL_LIMIT'],
          },
          {
            target: 'local-dir-ls-import-json',
            title: '生成本地目录 LS 导入 JSON',
            description: '只扫描图片目录并生成 Label Studio 导入 JSON / XML，不创建项目。',
            params: ['LOCAL_IMAGES_DIR', 'LOCAL_DATASET_NAME', 'LOCAL_DATASET_ROOT', 'LOCAL_LABEL_NAME', 'LOCAL_RECURSIVE', 'LOCAL_LIMIT'],
          },
          {
            target: 'local-dir-ls-apply',
            title: '导入本地目录任务到 Label Studio',
            description: '使用已生成的导入 JSON 创建 Label Studio 项目和本地文件存储。',
            params: ['LOCAL_IMAGES_DIR', 'LOCAL_DATASET_NAME', 'LOCAL_DATASET_ROOT', 'LOCAL_LABEL_NAME'],
          },
          {
            target: '2-local-dir-workflow-after-ls',
            title: '一键导出并转换 YOLO 训练集',
            description: '人工标注完成后，从 Label Studio 导出并转换为 YOLO 训练集。',
            params: ['LOCAL_DATASET_NAME', 'LOCAL_DATASET_ROOT', 'LOCAL_LABEL_NAME', 'LS_PROJECT_ID', 'LOCAL_LS_TO_YOLO_CLEAR', 'LOCAL_LS_TO_YOLO_SKIP_EMPTY'],
          },
        ],
      },
      {
        id: 's3_images_labeling',
        title: '本地目录 → S3 → LS',
        description: '本地图片上传 S3，Label Studio 通过 S3/proxy 图片地址标注。',
        commands: [
          {
            target: 'brand-s3-check-config',
            title: '检查 S3 参数',
            description: '打印当前 S3 数据集、桶、前缀、代理等关键参数。',
            params: ['BRAND_S3_CONFIG', 'S3_DATASET_NAME', 'S3_LOCAL_IMAGES_DIR', 'S3_BUCKET', 'S3_PREFIX', 'S3_REGION'],
          },
          {
            target: 'brand-s3-upload-images',
            title: '上传本地图片到 S3',
            description: '扫描本地图片目录，上传到 S3，并生成 JSON/CSV/URL 清单。',
            params: ['BRAND_S3_CONFIG', 'S3_DATASET_NAME', 'S3_LABEL_NAME', 'S3_LOCAL_IMAGES_DIR', 'S3_BUCKET', 'S3_PREFIX', 'S3_REGION', 'S3_PROFILE', 'S3_RECURSIVE', 'S3_LIMIT', 'S3_DRY_RUN'],
          },
          {
            target: 'brand-s3-proxy-start',
            title: '启动 S3 图片代理',
            description: '启动本地只读 S3 图片代理，解决 Label Studio 直接加载 S3 图片的 CORS 问题。',
            params: ['BRAND_S3_CONFIG', 'S3_BUCKET', 'S3_REGION', 'S3_PROFILE', 'S3_PROXY_HOST', 'S3_PROXY_PORT', 'S3_PROXY_ALLOWED_ORIGIN'],
          },
          {
            target: 'brand-s3-ls-import-json',
            title: '生成 S3 LS 导入 JSON',
            description: '根据 S3 图片清单生成 Label Studio 导入 JSON 和单类别标签配置。',
            params: ['BRAND_S3_CONFIG', 'S3_DATASET_NAME', 'S3_LABEL_NAME', 'S3_DATASET_ROOT', 'S3_MANIFEST_JSON', 'S3_IMAGE_URL_MODE', 'S3_PROXY_BASE_URL'],
          },
          {
            target: 'brand-s3-ls-apply',
            title: '导入 S3 图片任务到 LS',
            description: '把 S3/proxy 图片任务导入 Label Studio；proxy 模式下需保持代理运行。',
            params: ['S3_DATASET_NAME', 'S3_LS_IMPORT_JSON', 'S3_LS_LABEL_CONFIG_XML'],
          },
          {
            target: '1-brand-s3-workflow-to-ls',
            title: '一键上传 S3 并导入 LS',
            description: '上传图片、生成 S3 LS 导入 JSON，并创建 Label Studio 项目。',
            params: ['BRAND_S3_CONFIG', 'S3_DATASET_NAME', 'S3_LABEL_NAME', 'S3_LOCAL_IMAGES_DIR', 'S3_BUCKET', 'S3_PREFIX', 'S3_REGION', 'S3_PROFILE', 'S3_LIMIT', 'S3_DRY_RUN'],
          },
        ],
      },
    ],
  },
  {
    id: 'label_studio',
    title: 'Label Studio',
    description: '本地标注服务启停、通用导出和标注转 YOLO。',
    children: [
      {
        id: 'label_studio_service',
        title: '服务启停',
        description: '初始化、启动和停止本地 Label Studio。',
        commands: [
          { target: 'ls-setup', title: '首次初始化 Label Studio', description: '创建 PostgreSQL 数据库并执行迁移。', params: ['POSTGRE_USER', 'POSTGRE_NAME', 'POSTGRE_HOST', 'POSTGRE_PORT'] },
          { target: 'ls-start', title: '启动 Label Studio', description: '后台启动 9001 端口的本地 Label Studio。', params: ['LS_PORT'] },
          { target: 'ls-stop', title: '停止 Label Studio', description: '停止占用 LS_PORT 的 Label Studio 进程。', params: ['LS_PORT'] },
        ],
      },
      {
        id: 'label_studio_export',
        title: '导入 / 导出 / 转 YOLO',
        description: '通用 Label Studio 导入、导出和 YOLO 转换命令。',
        commands: [
          { target: 'step-4-import-ls', title: '品牌流程导入 LS', description: '生成导入 JSON，并通过 label-studio shell 创建项目和任务。', params: ['BRAND', 'LS_PROJECT_TITLE'] },
          { target: 'ls-export', title: '导出 Label Studio JSON', description: '从指定项目 ID 导出标注结果。', params: ['BRAND', 'LS_PROJECT_ID', 'LS_EXPORT_PATH', 'LS_EXPORT_FORMAT'] },
          { target: 'ls-to-yolo', title: '品牌 LS 导出转 YOLO', description: '把 Label Studio JSON 转换为正式 images/labels 训练集。', params: ['BRAND', 'LS_EXPORT_PATH', 'LS_TO_YOLO_CLEAR', 'LS_TO_YOLO_SKIP_EMPTY'] },
          { target: 'local-dir-ls-export', title: '本地目录 LS 导出', description: '从指定本地目录 Label Studio 项目导出标注结果 JSON。', params: ['LOCAL_DATASET_NAME', 'LOCAL_DATASET_ROOT', 'LS_PROJECT_ID', 'LOCAL_LS_EXPORT_PATH', 'LS_EXPORT_FORMAT'] },
          { target: 'local-dir-ls-to-yolo', title: '本地目录 LS 转 YOLO', description: '把本地目录 Label Studio 导出 JSON 转换为 images/labels 训练集。', params: ['LOCAL_DATASET_NAME', 'LOCAL_DATASET_ROOT', 'LOCAL_LABEL_NAME', 'LOCAL_LS_EXPORT_PATH', 'LOCAL_LS_TO_YOLO_CLEAR', 'LOCAL_LS_TO_YOLO_SKIP_EMPTY'] },
          { target: 'brand-s3-ls-export', title: 'S3 图片 LS 导出', description: '从指定 S3 图片 Label Studio 项目导出标注结果 JSON。', params: ['S3_DATASET_NAME', 'S3_DATASET_ROOT', 'LS_PROJECT_ID', 'S3_LS_EXPORT_PATH', 'LS_EXPORT_FORMAT'] },
          { target: 'brand-s3-ls-to-yolo', title: 'S3 图片 LS 转 YOLO/manifest', description: '生成 YOLO labels 和 EC2 图片下载 manifest。', params: ['S3_DATASET_NAME', 'S3_LABEL_NAME', 'S3_DATASET_ROOT', 'S3_LS_EXPORT_PATH', 'S3_LS_TO_YOLO_CLEAR', 'S3_LS_TO_YOLO_SKIP_EMPTY'] },
        ],
      },
    ],
  },
  {
    id: 'local_mac_training',
    title: '本地 Mac 训练 / 推理',
    description: '在本地 Mac 上校验数据、生成 YAML、训练模型和推理验证。',
    children: [
      {
        id: 'local_mac_brand',
        title: '品牌 / 多品牌',
        description: '品牌或多品牌数据集的本地训练与推理。',
        commands: [
          { target: 'brand-list', title: '查看品牌列表', description: '输出当前品牌库支持的 BRAND 参数。', params: [] },
          { target: 'brand-yaml', title: '生成品牌 YAML', description: '根据当前 BRAND 生成 YOLO 数据集 YAML。', params: ['BRAND'] },
          { target: 'data-validate', title: '校验 YOLO 数据集', description: '检查图片、标签、类别和坐标是否合法。', params: ['BRAND'] },
          { target: 'train', title: '本地训练 YOLO 模型', description: '训练当前品牌或多品牌模型，并导出 best.pt。', params: ['BRAND', 'TRAIN_BASE_MODEL', 'TRAIN_EPOCHS', 'TRAIN_IMGSZ', 'TRAIN_BATCH', 'TRAIN_DEVICE', 'TRAIN_RESUME', 'TRAIN_NAME'] },
          { target: 'predict', title: '本地推理验证', description: '用指定模型对图片或 URL 推理，输出 JSON 和带框图片。', params: ['PREDICT_SOURCE', 'PREDICT_MODEL', 'PREDICT_CONF', 'PREDICT_IMGSZ', 'PREDICT_OUTPUT_DIR'] },
        ],
      },
      {
        id: 'local_mac_single_class',
        title: '本地目录 / 纸尿裤 YAML',
        description: '单类别数据集 YAML 生成。后续训练可用通用 train 命令并覆盖 TRAIN_DATA_YAML。',
        commands: [
          { target: 'local-dir-yaml', title: '生成本地目录 YOLO YAML', description: '为本地目录单类别训练集生成 Ultralytics 数据集配置。', params: ['LOCAL_DATASET_NAME', 'LOCAL_DATASET_ROOT', 'LOCAL_LABEL_NAME', 'LOCAL_DATA_YAML'] },
          { target: 'diaper-yaml', title: '生成纸尿裤 YAML', description: '生成单类别纸尿裤训练配置。', params: ['DIAPER_COUNTRY', 'DIAPER_VERSION', 'DIAPER_LABEL_NAME'] },
        ],
      },
    ],
  },
  {
    id: 'ec2_training',
    title: 'EC2 训练 / 推理 / 下载',
    description: '按数据来源组织 EC2 上传、下载图片、训练、评估、模型与归档下载。所有 EC2 命令默认 dry-run。',
    ec2: true,
    children: [
      {
        id: 'ec2_local_dir',
        title: '本地目录数据集 → EC2',
        description: '上传本地目录 YOLO 数据集，并在 EC2 使用显式模型参数训练。',
        ec2: true,
        commands: [
          { target: 'local-dir-ec2-upload-data', title: '上传本地目录数据到 EC2', description: '上传本地目录 YOLO 数据集和 YAML 到 EC2，默认 dry-run。', params: ['LOCAL_DATASET_NAME', 'LOCAL_DATASET_ROOT', 'LOCAL_LABEL_NAME', 'EC2_HOST', 'EC2_USER', 'EC2_KEY', 'EC2_RUN_NAME', 'EC2_EXECUTE'] },
          { target: 'local-dir-ec2-train', title: 'EC2 训练本地目录数据', description: '使用 EC2_* 显式模型参数训练本地目录数据集，默认 dry-run。', params: ['LOCAL_DATASET_NAME', 'LOCAL_DATASET_ROOT', 'LOCAL_LABEL_NAME', 'EC2_HOST', 'EC2_USER', 'EC2_KEY', 'EC2_BASE_MODEL', 'EC2_TRAIN_EPOCHS', 'EC2_TRAIN_IMGSZ', 'EC2_TRAIN_BATCH', 'EC2_TRAIN_DEVICE', 'EC2_RUN_NAME', 'EC2_EXECUTE'] },
          { target: 'local-dir-ec2-evaluate', title: '评估归档本地目录训练', description: '归档 EC2 本地目录训练产物并生成评估摘要，默认 dry-run。', params: ['LOCAL_DATASET_NAME', 'LOCAL_LABEL_NAME', 'EC2_HOST', 'EC2_USER', 'EC2_KEY', 'EC2_RUN_NAME', 'EC2_EVAL_NOTES', 'EC2_EXECUTE'] },
          { target: 'local-dir-ec2-download-artifacts', title: '下载本地目录训练归档', description: '下载本地目录训练归档目录，默认 dry-run。', params: ['LOCAL_DATASET_NAME', 'EC2_HOST', 'EC2_USER', 'EC2_KEY', 'EC2_RUN_NAME', 'LOCAL_EC2_LOCAL_ARTIFACT_ROOT', 'EC2_EXECUTE'] },
          { target: 'local-dir-ec2-download-model', title: '下载本地目录 best.pt', description: '下载本地目录训练得到的 best.pt，默认 dry-run。', params: ['LOCAL_DATASET_NAME', 'EC2_HOST', 'EC2_USER', 'EC2_KEY', 'EC2_RUN_NAME', 'LOCAL_FINAL_MODEL', 'EC2_EXECUTE'] },
        ],
      },
      {
        id: 'ec2_s3',
        title: 'S3 图片数据集 → EC2',
        description: '上传 manifest/labels，EC2 从 S3 下载图片，再使用显式模型参数训练。',
        ec2: true,
        commands: [
          { target: 'brand-s3-ec2-upload-manifest', title: '上传 S3 manifest 到 EC2', description: '上传 labels、EC2 图片 manifest 和 YAML，不上传图片大文件。', params: ['S3_DATASET_NAME', 'S3_LABEL_NAME', 'S3_DATASET_ROOT', 'EC2_HOST', 'EC2_USER', 'EC2_KEY', 'EC2_RUN_NAME', 'EC2_EXECUTE'] },
          { target: 'brand-s3-ec2-download-images', title: 'EC2 下载 S3 训练图片', description: '在 EC2 上根据 manifest 从 S3 下载训练图片，默认 dry-run。', params: ['S3_DATASET_NAME', 'EC2_HOST', 'EC2_USER', 'EC2_KEY', 'EC2_PROJECT_ROOT', 'EC2_EXECUTE'] },
          { target: 'brand-s3-ec2-train', title: 'EC2 训练 S3 数据', description: 'EC2 先下载 S3 图片再训练，训练规模由 EC2_* 显式参数控制。', params: ['S3_DATASET_NAME', 'S3_LABEL_NAME', 'EC2_HOST', 'EC2_USER', 'EC2_KEY', 'EC2_BASE_MODEL', 'EC2_TRAIN_EPOCHS', 'EC2_TRAIN_IMGSZ', 'EC2_TRAIN_BATCH', 'EC2_TRAIN_DEVICE', 'EC2_RUN_NAME', 'EC2_EXECUTE'] },
          { target: 'brand-s3-ec2-evaluate', title: '评估归档 S3 EC2 训练', description: '归档 EC2 S3 数据集训练产物并生成评估摘要。', params: ['S3_DATASET_NAME', 'EC2_HOST', 'EC2_USER', 'EC2_KEY', 'EC2_RUN_NAME', 'EC2_EVAL_NOTES', 'EC2_EXECUTE'] },
          { target: 'brand-s3-ec2-download-artifacts', title: '下载 S3 EC2 训练归档', description: '下载 S3 数据集训练归档目录，默认 dry-run。', params: ['S3_DATASET_NAME', 'EC2_HOST', 'EC2_USER', 'EC2_KEY', 'EC2_RUN_NAME', 'S3_EC2_LOCAL_ARTIFACT_ROOT', 'EC2_EXECUTE'] },
          { target: 'brand-s3-ec2-download-model', title: '下载 S3 EC2 best.pt', description: '下载 S3 数据集训练得到的 best.pt，默认 dry-run。', params: ['S3_DATASET_NAME', 'EC2_HOST', 'EC2_USER', 'EC2_KEY', 'EC2_RUN_NAME', 'S3_FINAL_MODEL', 'EC2_EXECUTE'] },
        ],
      },
      {
        id: 'ec2_diaper',
        title: '纸尿裤数据集 → EC2',
        description: '纸尿裤大类数据上传、训练、评估、推理和下载。',
        ec2: true,
        commands: [
          { target: '01-diaper-ec2-upload-project', title: '上传项目代码到 EC2', description: '仅非 Git 部署环境使用；默认 dry-run。', params: ['DIAPER_COUNTRY', 'DIAPER_VERSION', 'EC2_HOST', 'EC2_USER', 'EC2_KEY', 'EC2_EXECUTE'] },
          { target: '02-diaper-ec2-upload-data', title: '上传纸尿裤数据到 EC2', description: '上传本地纸尿裤 YOLO 数据集和 YAML，默认 dry-run。', params: ['DIAPER_COUNTRY', 'DIAPER_VERSION', 'DIAPER_LABEL_NAME', 'DIAPER_DATASET_ROOT', 'DIAPER_DATA_YAML', 'EC2_HOST', 'EC2_USER', 'EC2_KEY', 'EC2_PORT', 'EC2_PROJECT_ROOT', 'EC2_REMOTE_DATA_YAML', 'EC2_EXECUTE'] },
          { target: '03-diaper-ec2-train', title: 'EC2 训练纸尿裤数据', description: '使用 EC2_* 显式模型参数训练纸尿裤数据集，默认 dry-run。', params: ['DIAPER_COUNTRY', 'DIAPER_VERSION', 'DIAPER_LABEL_NAME', 'EC2_HOST', 'EC2_USER', 'EC2_KEY', 'EC2_BASE_MODEL', 'EC2_TRAIN_EPOCHS', 'EC2_TRAIN_IMGSZ', 'EC2_TRAIN_BATCH', 'EC2_TRAIN_DEVICE', 'EC2_RUN_NAME', 'EC2_EXECUTE'] },
          { target: '04-diaper-ec2-evaluate', title: '评估归档纸尿裤训练', description: '归档训练产物并生成 evaluation-summary.md。', params: ['DIAPER_COUNTRY', 'DIAPER_VERSION', 'EC2_HOST', 'EC2_USER', 'EC2_KEY', 'EC2_RUN_NAME', 'EC2_EVAL_NOTES', 'EC2_EXECUTE'] },
          { target: '05-diaper-ec2-download-artifacts', title: '下载纸尿裤训练归档', description: '下载完整训练归档目录。', params: ['DIAPER_COUNTRY', 'DIAPER_VERSION', 'EC2_HOST', 'EC2_USER', 'EC2_KEY', 'EC2_RUN_NAME', 'EC2_EXECUTE'] },
          { target: '06-diaper-ec2-predict', title: 'EC2 推理验证', description: '使用 EC2 模型做推理验证。', params: ['DIAPER_COUNTRY', 'DIAPER_VERSION', 'EC2_HOST', 'EC2_USER', 'EC2_KEY', 'EC2_PREDICT_SOURCE', 'EC2_RUN_NAME', 'EC2_EXECUTE'] },
          { target: '07-diaper-ec2-download-model', title: '下载 EC2 best.pt', description: '下载当前运行标识目录下的 best.pt 模型。', params: ['DIAPER_COUNTRY', 'DIAPER_VERSION', 'EC2_HOST', 'EC2_USER', 'EC2_KEY', 'EC2_RUN_NAME', 'EC2_EXECUTE'] },
        ],
      },
    ],
  },
  {
    id: 'maintenance',
    title: '维护工具',
    description: '帮助、目录准备、EC2 参数查看、清理预览和备份。',
    commands: [
      { target: 'help', title: '查看 Make 帮助', description: '输出 Make 命令列表和常用参数说明。', params: [] },
      { target: 'help-params', title: '查看公共参数', description: '输出公共 Make 参数默认值。', params: [] },
      { target: 'ec2-print-params', title: '查看 EC2 参数', description: '输出 EC2 公共连接与训练参数。', params: [] },
      { target: 'prepare-dirs', title: '创建临时和日志目录', description: '创建 .tmp、logs、Label Studio 工作目录等。', params: [] },
      { target: 'datasets-clean-preview', title: '预览 ignored 数据清理', description: '只预览会被删除的 ignored 数据，不执行删除。', params: [] },
      { target: 'datasets-clean-untracked-except-raw-preview', title: '预览非 raw 未跟踪数据清理', description: '只预览 datasets 下除 raw 外未跟踪内容。', params: [] },
      { target: 'bak-data', title: '备份模型权重', description: '将 models 下 .pt 权重复制到 models/backup。', params: [] },
    ],
  },
];

/**
 * 常用参数默认值和输入类型。
 * 默认值用于页面展示；实际执行时只会传递用户填写的非空值，未填写则继续使用 Makefile 默认值。
 */
const PARAM_DEFINITIONS = {
  BRAND: { label: '品牌', defaultValue: 'all', type: 'select', help: 'all 表示多品牌；也可选择单品牌。' },
  EXCEL: { label: 'Excel 路径', defaultValue: '/Users/guobiao/DOC/森大2.0/18.陈列数据/CI_2026-08-26_最新1801个_02.xlsx', type: 'text' },
  EXCEL_COLUMN: { label: '图片 URL 列名', defaultValue: '生动化照片链接', type: 'text' },
  EXCEL_WORKERS: { label: 'Excel 下载并发', defaultValue: '10', type: 'number' },
  EXCEL_TIMEOUT: { label: '下载超时秒数', defaultValue: '30', type: 'number' },
  OCR_ENGINE: { label: 'OCR 引擎', defaultValue: 'rapidocr', type: 'select', options: ['rapidocr', 'easyocr'] },
  OCR_WORKERS: { label: 'OCR 并发', defaultValue: '10', type: 'number' },
  OCR_LIMIT: { label: 'OCR 数量上限', defaultValue: '', type: 'number', help: '留空表示全量。' },
  OCR_FUZZY_THRESHOLD: { label: 'OCR 模糊匹配阈值', defaultValue: '60', type: 'number' },
  OCR_MIN_CONFIDENCE: { label: 'OCR 最低置信度', defaultValue: '0.2', type: 'number' },
  OCR_RESUME: { label: 'OCR 恢复模式', defaultValue: '0', type: 'select', options: ['0', '1'] },
  LLM_OCR_MODEL: { label: 'Ollama 模型', defaultValue: 'gemma3:12b', type: 'text' },
  LLM_OCR_WORKERS: { label: 'LLM OCR 并发', defaultValue: '1', type: 'number' },
  LLM_OCR_TIMEOUT: { label: 'LLM OCR 超时秒数', defaultValue: '180', type: 'number' },
  PSEUDO_MODEL: { label: 'YOLO-World 权重', defaultValue: 'models/yolov8s-world.pt', type: 'text' },
  PSEUDO_LIMIT: { label: '预标注数量上限', defaultValue: '', type: 'number', help: '留空表示全量。' },
  PSEUDO_CONF: { label: '预标注置信度', defaultValue: '0.03', type: 'number' },
  PSEUDO_IMGSZ: { label: '预标注图片尺寸', defaultValue: '960', type: 'number' },
  PSEUDO_USE_OCR_CANDIDATES: { label: '只处理 OCR 候选', defaultValue: '1', type: 'select', options: ['1', '0'] },
  PSEUDO_NMS_IOU: { label: 'NMS IoU', defaultValue: '0.45', type: 'number' },
  PSEUDO_MAX_AREA_RATIO: { label: '最大框面积比例', defaultValue: '0.45', type: 'number' },
  PSEUDO_VISUAL_MODEL: { label: 'YOLOE 权重', defaultValue: 'models/yoloe-26m-seg.pt', type: 'text' },
  PSEUDO_VISUAL_DEVICE: { label: 'YOLOE 设备', defaultValue: 'mps', type: 'select', options: ['mps', 'cpu', '0'] },
  PSEUDO_VISUAL_REFERENCE_LIMIT: { label: '每品牌参考图上限', defaultValue: '', type: 'number' },
  VISUAL_PROMPTS_EXCEL: { label: '品牌参考图 Excel', defaultValue: '/Users/guobiao/Downloads/品牌图片2_1786525402668.xlsx', type: 'text' },
  VISUAL_PROMPTS_BRAND_COLUMN: { label: '品牌列名', defaultValue: 'brand', type: 'text' },
  VISUAL_PROMPTS_ATTACH_COLUMN: { label: '图片 URL 列名', defaultValue: 'attach_file', type: 'text' },
  VISUAL_PROMPTS_LIMIT: { label: '参考图导入上限', defaultValue: '', type: 'number' },
  AB_MODELS: { label: 'A/B 模型列表', defaultValue: 'models/yolov8s-world.pt,models/yolov8m-world.pt,models/yolov8m-worldv2.pt,models/yolov8x-worldv2.pt', type: 'text' },
  AB_LIMIT: { label: 'A/B 图片上限', defaultValue: '50', type: 'number' },
  AB_PREVIEW_LIMIT: { label: 'A/B 预览图上限', defaultValue: '30', type: 'number' },
  LS_PROJECT_ID: { label: 'LS 项目 ID', defaultValue: '', type: 'text' },
  LS_PORT: { label: 'LS 端口', defaultValue: '9001', type: 'number' },
  LS_PROJECT_TITLE: { label: 'LS 项目标题', defaultValue: '', type: 'text' },
  LS_EXPORT_PATH: { label: 'LS 导出 JSON 路径', defaultValue: '', type: 'text' },
  LS_EXPORT_FORMAT: { label: 'LS 导出格式', defaultValue: 'JSON', type: 'text' },
  LS_PROJECT_IDS: { label: 'LS 项目 ID 列表', defaultValue: '', type: 'text', help: '多个项目用英文逗号分隔，例如 21,20。' },
  LS_TO_YOLO_CLEAR: { label: '转换前清空旧训练集', defaultValue: '0', type: 'select', options: ['0', '1'] },
  LS_TO_YOLO_SKIP_EMPTY: { label: '跳过空标注', defaultValue: '0', type: 'select', options: ['0', '1'] },
  LOCAL_DATASET_NAME: { label: '本地数据集短名称', defaultValue: 'local_dataset', type: 'text', help: '只能填短名称，不要填路径。' },
  LOCAL_IMAGES_DIR: { label: '源图片目录', defaultValue: 'data/local_import/images', type: 'text' },
  LOCAL_DATASET_ROOT: { label: '导出数据集目录', defaultValue: '', type: 'text', help: '留空时使用 datasets/local/<本地数据集短名称>。' },
  LOCAL_LABEL_NAME: { label: '标注类别名', defaultValue: 'diaper', type: 'text' },
  LOCAL_RECURSIVE: { label: '递归扫描子目录', defaultValue: '1', type: 'select', options: ['1', '0'] },
  LOCAL_LIMIT: { label: '导入图片上限', defaultValue: '', type: 'number', help: '留空表示全量。' },
  LOCAL_DATA_YAML: { label: '本地目录 YOLO YAML', defaultValue: '', type: 'text' },
  LOCAL_LS_EXPORT_PATH: { label: '本地目录 LS 导出 JSON', defaultValue: '', type: 'text' },
  LOCAL_LS_TO_YOLO_CLEAR: { label: '转换前清空旧训练集', defaultValue: '0', type: 'select', options: ['0', '1'] },
  LOCAL_LS_TO_YOLO_SKIP_EMPTY: { label: '跳过空标注', defaultValue: '0', type: 'select', options: ['0', '1'] },
  LOCAL_FINAL_MODEL: { label: '本地下载模型路径', defaultValue: '', type: 'text' },
  LOCAL_EC2_REMOTE_DATASET_ROOT: { label: 'EC2 数据集目录', defaultValue: '', type: 'text' },
  LOCAL_EC2_TRAIN_NAME: { label: 'EC2 训练名称', defaultValue: '', type: 'text' },
  LOCAL_EC2_REMOTE_FINAL_MODEL: { label: 'EC2 best.pt 路径', defaultValue: '', type: 'text' },
  LOCAL_EC2_ARTIFACT_ROOT: { label: 'EC2 归档目录', defaultValue: '', type: 'text' },
  LOCAL_EC2_LOCAL_ARTIFACT_ROOT: { label: '本地归档下载目录', defaultValue: '', type: 'text' },
  BRAND_S3_CONFIG: { label: 'S3 配置文件', defaultValue: 'config/brand_s3_ec2.local.yaml', type: 'text' },
  S3_DATASET_NAME: { label: 'S3 数据集短名称', defaultValue: 'local_dataset', type: 'text' },
  S3_LABEL_NAME: { label: 'S3 标注类别名', defaultValue: 'diaper', type: 'text' },
  S3_LOCAL_IMAGES_DIR: { label: 'S3 源图片目录', defaultValue: 'data/local_import/images', type: 'text' },
  S3_DATASET_ROOT: { label: 'S3 本地输出目录', defaultValue: '', type: 'text' },
  S3_BUCKET: { label: 'S3 桶名', defaultValue: '', type: 'text' },
  S3_PREFIX: { label: 'S3 对象前缀', defaultValue: '', type: 'text' },
  S3_REGION: { label: 'S3 区域', defaultValue: 'ap-southeast-1', type: 'text' },
  S3_PROFILE: { label: 'AWS Profile', defaultValue: '', type: 'text' },
  S3_RECURSIVE: { label: 'S3 递归扫描', defaultValue: '1', type: 'select', options: ['1', '0'] },
  S3_LIMIT: { label: 'S3 图片上限', defaultValue: '', type: 'number' },
  S3_DRY_RUN: { label: 'S3 上传 dry-run', defaultValue: '0', type: 'select', options: ['0', '1'] },
  S3_MANIFEST_JSON: { label: 'S3 图片清单 JSON', defaultValue: '', type: 'text' },
  S3_IMAGE_URL_MODE: { label: 'LS 图片地址模式', defaultValue: 'proxy', type: 'select', options: ['proxy', 'https', 's3'] },
  S3_PROXY_HOST: { label: 'S3 代理 Host', defaultValue: '127.0.0.1', type: 'text' },
  S3_PROXY_PORT: { label: 'S3 代理端口', defaultValue: '3010', type: 'number' },
  S3_PROXY_BASE_URL: { label: 'S3 代理 Base URL', defaultValue: 'http://127.0.0.1:3010', type: 'text' },
  S3_PROXY_ALLOWED_ORIGIN: { label: '代理允许 Origin', defaultValue: 'http://localhost:9001', type: 'text' },
  S3_LS_IMPORT_JSON: { label: 'S3 LS 导入 JSON', defaultValue: '', type: 'text' },
  S3_LS_LABEL_CONFIG_XML: { label: 'S3 LS 标签配置', defaultValue: '', type: 'text' },
  S3_LS_TO_YOLO_CLEAR: { label: 'S3 转换前清空 labels', defaultValue: '0', type: 'select', options: ['0', '1'] },
  S3_LS_TO_YOLO_SKIP_EMPTY: { label: 'S3 跳过空标注', defaultValue: '0', type: 'select', options: ['0', '1'] },
  S3_EC2_LOCAL_ARTIFACT_ROOT: { label: 'S3 本地归档下载目录', defaultValue: '', type: 'text' },
  S3_FINAL_MODEL: { label: 'S3 本地下载模型', defaultValue: '', type: 'text' },
  POSTGRE_USER: { label: 'PostgreSQL 用户', defaultValue: 'guobiao', type: 'text' },
  POSTGRE_NAME: { label: 'PostgreSQL 数据库', defaultValue: 'labelstudio', type: 'text' },
  POSTGRE_HOST: { label: 'PostgreSQL Host', defaultValue: 'localhost', type: 'text' },
  POSTGRE_PORT: { label: 'PostgreSQL 端口', defaultValue: '5432', type: 'number' },
  TRAIN_BASE_MODEL: { label: '训练基座模型', defaultValue: 'models/yolo26m.pt', type: 'text' },
  TRAIN_EPOCHS: { label: '训练轮数', defaultValue: '55', type: 'number' },
  TRAIN_IMGSZ: { label: '训练图片尺寸', defaultValue: '960', type: 'number' },
  TRAIN_BATCH: { label: '训练 batch', defaultValue: '-1', type: 'text' },
  TRAIN_DEVICE: { label: '训练设备', defaultValue: 'mps', type: 'select', options: ['mps', 'cpu', '0'] },
  TRAIN_RESUME: { label: '恢复训练', defaultValue: '0', type: 'select', options: ['0', '1'] },
  TRAIN_NAME: { label: '训练 run 名称', defaultValue: '', type: 'text' },
  PREDICT_SOURCE: { label: '推理图片/URL', defaultValue: 'data/samples/multibrand-shelf.webp', type: 'text' },
  PREDICT_MODEL: { label: '推理模型', defaultValue: '', type: 'text' },
  PREDICT_CONF: { label: '推理置信度', defaultValue: '0.35', type: 'number' },
  PREDICT_IMGSZ: { label: '推理图片尺寸', defaultValue: '960', type: 'number' },
  PREDICT_OUTPUT_DIR: { label: '推理输出目录', defaultValue: 'outputs/predict', type: 'text' },
  DIAPER_COUNTRY: { label: '国家/市场', defaultValue: 'CI', type: 'text' },
  DIAPER_VERSION: { label: '数据版本', defaultValue: 'v2026-08-28', type: 'text' },
  DIAPER_EXCEL: { label: '纸尿裤 Excel', defaultValue: '', type: 'text' },
  DIAPER_EXCEL_COLUMN: { label: '纸尿裤图片 URL 列名', defaultValue: '', type: 'text' },
  DIAPER_LABEL_NAME: { label: '纸尿裤标签名', defaultValue: 'diaper', type: 'text' },
  DIAPER_DATASET_ROOT: { label: '纸尿裤本地数据集目录', defaultValue: '', type: 'text' },
  DIAPER_DATA_YAML: { label: '纸尿裤本地 YAML', defaultValue: '', type: 'text' },
  DIAPER_MERGED_LS_EXPORT_PATH: { label: '合并后 LS JSON', defaultValue: '', type: 'text' },
  DIAPER_MERGE_REPORT: { label: '合并报告 JSON', defaultValue: '', type: 'text' },
  EC2_HOST: { label: 'EC2 Host', defaultValue: '3.232.95.101', type: 'text' },
  EC2_USER: { label: 'EC2 用户', defaultValue: 'ec2-user', type: 'text' },
  EC2_KEY: { label: 'SSH 私钥路径', defaultValue: '~/.ssh/smdp-yolo-gpu-key.pem', type: 'text' },
  EC2_PORT: { label: 'EC2 SSH 端口', defaultValue: '22', type: 'number' },
  EC2_PROJECT_ROOT: { label: 'EC2 项目根目录', defaultValue: '/home/ec2-user/yoloExample', type: 'text' },
  EC2_REMOTE_DATA_YAML: { label: 'EC2 YAML 路径', defaultValue: '', type: 'text' },
  EC2_BASE_MODEL: { label: 'EC2 基座模型', defaultValue: 'yolo26m.pt', type: 'text' },
  EC2_TRAIN_EPOCHS: { label: 'EC2 训练轮数', defaultValue: '100', type: 'number' },
  EC2_TRAIN_IMGSZ: { label: 'EC2 图片尺寸', defaultValue: '960', type: 'number' },
  EC2_TRAIN_BATCH: { label: 'EC2 batch', defaultValue: '-1', type: 'text' },
  EC2_TRAIN_DEVICE: { label: 'EC2 设备', defaultValue: '0', type: 'text' },
  EC2_EXECUTE: { label: '真实执行 EC2 命令', defaultValue: '0', type: 'select', options: ['0', '1'], help: '默认 0 只 dry-run；改成 1 才会连接 EC2。' },
  EC2_EVAL_NOTES: { label: '评估备注', defaultValue: 'training start', type: 'text' },
  EC2_RUN_NAME: { label: 'EC2 运行标识', defaultValue: 'yolo26m_img960_e100', type: 'text', help: '只用于模型、归档和报告目录；训练规模由模型参数决定。' },
  EC2_PREDICT_SOURCE: { label: 'EC2 推理图片路径', defaultValue: 'data/samples/multibrand-shelf.webp', type: 'text' },
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
const jobs = new Map();

function jsonResponse(response, statusCode, payload) {
  response.writeHead(statusCode, {
    'Content-Type': 'application/json; charset=utf-8',
    'Cache-Control': 'no-store',
  });
  response.end(JSON.stringify(payload, null, 2));
}

function textResponse(response, statusCode, text, contentType = 'text/plain; charset=utf-8') {
  response.writeHead(statusCode, { 'Content-Type': contentType });
  response.end(text);
}

function notFound(response) {
  jsonResponse(response, 404, { error: '接口不存在' });
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
  return { ...root, absPath: path.join(PROJECT_ROOT, root.relativePath) };
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
      entries = await fsp.readdir(currentPath, { withFileTypes: true });
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
      entries = await fsp.readdir(current, { withFileTypes: true });
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
    const entries = await fsp.readdir(absPath, { withFileTypes: true });
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
    return { count: 0, totalBytes: 0 };
  }
  return { count, totalBytes };
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
  const candidates = [
    'datasets/multibrand',
    'datasets/softcare',
  ];
  const localRoot = path.join(PROJECT_ROOT, 'datasets/local');
  try {
    const localDatasets = await fsp.readdir(localRoot, { withFileTypes: true });
    for (const dataset of localDatasets) {
      if (dataset.isDirectory() && !dataset.name.startsWith('.')) {
        candidates.push(`datasets/local/${dataset.name}`);
      }
    }
  } catch (_error) {
    // 没有本地目录导入数据集时忽略。
  }
  const diaperRoot = path.join(PROJECT_ROOT, 'datasets/diaper_category');
  const discovered = [];
  try {
    const countries = await fsp.readdir(diaperRoot, { withFileTypes: true });
    for (const country of countries) {
      if (!country.isDirectory() || country.name.startsWith('.')) {
        continue;
      }
      const countryPath = path.join(diaperRoot, country.name);
      const versions = await fsp.readdir(countryPath, { withFileTypes: true });
      for (const version of versions) {
        if (version.isDirectory() && !version.name.startsWith('.')) {
          discovered.push(`datasets/diaper_category/${country.name}/${version.name}`);
        }
      }
    }
  } catch (_error) {
    // 没有纸尿裤数据目录时忽略。
  }
  for (const item of discovered) {
    candidates.push(item);
  }

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

async function summarizeDownloadReport(relativePath) {
  const absPath = path.join(PROJECT_ROOT, relativePath);
  if (!(await pathExists(absPath))) {
    return null;
  }
  try {
    const raw = await fsp.readFile(absPath, 'utf8');
    const data = JSON.parse(raw);
    const rows = Array.isArray(data) ? data : [];
    const statusCounts = {};
    for (const row of rows) {
      const status = row.status || 'unknown';
      statusCounts[status] = (statusCounts[status] || 0) + 1;
    }
    return {
      path: relativePath,
      type: 'download_report',
      total: rows.length,
      statusCounts,
    };
  } catch (error) {
    return { path: relativePath, type: 'download_report', error: error.message };
  }
}

async function summarizeSimpleJson(relativePath, keys) {
  const absPath = path.join(PROJECT_ROOT, relativePath);
  if (!(await pathExists(absPath))) {
    return null;
  }
  try {
    const raw = await fsp.readFile(absPath, 'utf8');
    const data = JSON.parse(raw);
    const summary = { path: relativePath, type: 'json_summary' };
    for (const key of keys) {
      if (Object.prototype.hasOwnProperty.call(data, key)) {
        summary[key] = data[key];
      }
    }
    return summary;
  } catch (error) {
    return { path: relativePath, type: 'json_summary', error: error.message };
  }
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

  const reportCandidates = [
    await summarizeDownloadReport('datasets/multibrand/raw/metadata/download_report.json'),
    await summarizeSimpleJson('datasets/softcare/pseudo/metadata/pseudo_label_report.json', ['processed_count', 'image_count', 'box_count', 'class_counts', 'warnings']),
    await summarizeSimpleJson('datasets/diaper_category/CI/v2026-08-28/label_studio/exports/label_studio_to_yolo_report.json', ['converted_count', 'box_count', 'class_counts', 'warnings']),
  ].filter(Boolean);

  return {
    projectRoot: PROJECT_ROOT,
    roots,
    splits: await discoverDatasetSplits(),
    reports: reportCandidates,
  };
}

async function readBrands() {
  const brandPath = path.join(PROJECT_ROOT, 'config/brand_keywords.json');
  try {
    const data = JSON.parse(await fsp.readFile(brandPath, 'utf8'));
    const names = (data.brands || [])
      .filter((brand) => brand.enabled !== false && brand.name)
      .map((brand) => brand.name);
    return ['all', ...names];
  } catch (_error) {
    return ['all'];
  }
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
  const paramDefinitions = JSON.parse(JSON.stringify(PARAM_DEFINITIONS));
  paramDefinitions.BRAND.options = brands;
  jsonResponse(response, 200, {
    projectRoot: PROJECT_ROOT,
    commandGroups: COMMAND_GROUPS,
    params: paramDefinitions,
    dataRoots: DATA_ROOTS,
  });
}

async function handleImages(url, response) {
  const rootId = url.searchParams.get('root') || DATA_ROOTS[0].id;
  const page = Math.max(1, Number.parseInt(url.searchParams.get('page') || '1', 10));
  const pageSize = Math.min(120, Math.max(12, Number.parseInt(url.searchParams.get('pageSize') || '48', 10)));
  const query = (url.searchParams.get('q') || '').trim().toLowerCase();
  const root = dataRootById(rootId);
  if (!root) {
    jsonResponse(response, 400, { error: '未知数据目录' });
    return;
  }
  const files = await walkFiles(root.absPath, { recursive: root.recursive, maxFiles: 50000 });
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
    jsonResponse(response, 400, { error: '缺少 path 参数' });
    return;
  }
  const absPath = path.resolve(PROJECT_ROOT, requested);
  if (!isPathInside(PROJECT_ROOT, absPath) || !isAllowedImagePath(absPath)) {
    jsonResponse(response, 403, { error: '文件不在允许访问的图片目录内' });
    return;
  }
  if (!(await pathExists(absPath))) {
    jsonResponse(response, 404, { error: '图片不存在' });
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

function handleJob(url, response) {
  const id = decodeURIComponent(url.pathname.split('/').pop());
  const job = jobs.get(id);
  if (!job) {
    jsonResponse(response, 404, { error: '任务不存在' });
    return;
  }
  jsonResponse(response, 200, publicJob(job));
}

function handleStopJob(url, response) {
  const parts = url.pathname.split('/');
  const id = decodeURIComponent(parts[3] || '');
  const job = jobs.get(id);
  if (!job) {
    jsonResponse(response, 404, { error: '任务不存在' });
    return;
  }
  const stopped = stopJob(job);
  jsonResponse(response, 200, { stopped, job: publicJob(job) });
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
  response.writeHead(200, { 'Content-Type': contentType });
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
    jsonResponse(response, 405, { error: '不支持的请求方法' });
  } catch (error) {
    jsonResponse(response, 500, { error: error.message });
  }
}

const server = http.createServer(router);

server.listen(PORT, '127.0.0.1', () => {
  console.log(`本地 YOLO 控制台已启动：http://localhost:${PORT}`);
  console.log(`项目根目录：${PROJECT_ROOT}`);
});
