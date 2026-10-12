"""
将 ai-ocr 识别的图片与预测边界框导入 Label Studio。

该脚本通过 Django ORM 创建专属复核项目，并自动注册本地文件存储。
"""

# pylint: disable=line-too-long,import-error,no-name-in-module,wrong-import-position,too-many-locals

import json
import os
from pathlib import Path

# 确保加载 Django 环境
os.environ.setdefault("DJANGO_SETTINGS_MODULE", "label_studio.core.settings.label_studio")

import django
django.setup()

from django.db import transaction
from organizations.models import Organization
from projects.models import Project
from tasks.models import Task, Prediction
from users.models import User
from io_storages.localfiles.models import LocalFilesImportStorage, LocalFilesImportStorageLink

PROJECT_ROOT = Path("/Users/guobiao/PRO/me/yoloExample")
IMPORT_JSON_PATH = PROJECT_ROOT / "datasets/GH/v2026-09-20/general_kleesoft_purple_allround_purple/label_studio/ai_ocr_label_studio_import.json"
LOCAL_IMAGES_DIR = PROJECT_ROOT / "datasets/GH/v2026-09-20/general_kleesoft_purple_allround_purple/llm/images"

LABEL_CONFIG_XML = """<View>
  <Image name="image" value="$image"/>
  <RectangleLabels name="bbox" toName="image">
    <Label value="kleesoft_purple" background="#FFA500"/>
    <Label value="allround_purple" background="#1E90FF"/>
  </RectangleLabels>
  <Header value="来源：$row_number $image_name"/>
</View>"""


def run_import():
    """执行 Label Studio 项目创建与任务/预测边界框全量导入。"""
    user = User.objects.order_by("id").first()
    if not user:
        raise RuntimeError("No user found in Label Studio database.")

    org = getattr(user, "active_organization", None) or Organization.objects.order_by("id").first()

    base_title = "GH AI-OCR 多模态识别复核 (858张)"
    title = base_title
    idx = 2
    while Project.objects.filter(title=title, deleted_at__isnull=True).exists():
        title = f"{base_title} #{idx}"
        idx += 1

    print(f"Creating project: '{title}' for user: {user.email}")

    with transaction.atomic():
        project = Project.objects.create(
            title=title,
            description="ai-ocr 多模态大模型对加纳陈列照片全量 858 张识别结果复核与位置核对",
            label_config=LABEL_CONFIG_XML,
            created_by=user,
            organization=org,
            is_published=True,
            reveal_preannotations_interactively=False,
            show_collab_predictions=True,
        )

        storage = LocalFilesImportStorage.objects.create(
            project=project,
            title="GH LLM Images Local Storage",
            description="Local storage for ai-ocr review images",
            path=str(LOCAL_IMAGES_DIR.resolve()),
            use_blob_urls=True,
        )
        storage.validate_connection()

        with open(IMPORT_JSON_PATH, "r", encoding="utf-8") as f:
            tasks_data = json.load(f)

        task_count = 0
        pred_task_count = 0
        pred_box_count = 0

        for item in tasks_data:
            task = Task.objects.create(
                project=project,
                data=item.get("data", {}),
                meta=item.get("meta", {})
            )
            local_path = task.data.get("local_path")
            if local_path:
                LocalFilesImportStorageLink.create(task=task, key=local_path, storage=storage)
            task_count += 1

            preds = item.get("predictions", [])
            if preds:
                pred_task_count += 1
            for pred in preds:
                Prediction.objects.create(
                    task=task,
                    project=project,
                    result=pred.get("result", []),
                    score=pred.get("score"),
                    model_version=pred.get("model_version", "ai-ocr-mllm"),
                )
                pred_box_count += len(pred.get("result", []))
            if preds:
                task.total_predictions = len(preds)
                task.save(update_fields=["total_predictions"])

    print("\n" + "="*60)
    print("🎉 导入成功！")
    print(f"项目 ID: {project.id}")
    print(f"项目标题: {project.title}")
    print(f"任务总数: {task_count} 张图片")
    print(f"带预测标注的任务数: {pred_task_count} 个")
    print(f"预测边界框总数: {pred_box_count} 个")
    print(f"👉 访问地址: http://localhost:9001/projects/{project.id}/data")
    print("="*60 + "\n")


if __name__ == "__main__":
    run_import()
