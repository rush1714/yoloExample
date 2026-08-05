from __future__ import annotations

import json
import os
from pathlib import Path

from django.db import transaction
from organizations.models import Organization
from projects.models import Project
from tasks.models import Prediction, Task
from users.models import User

LABEL_CONFIG = """
<View>
  <Image name="image" value="$image"/>
  <RectangleLabels name="bbox" toName="image">
    <Label value="softcare_diaper" background="#FFA500"/>
  </RectangleLabels>
  <Header value="来源行：$row_number"/>
  <Text name="source_url" value="$source_url"/>
</View>
""".strip()
DEFAULT_IMPORT_JSON = "/Users/guobiao/PRO/me/yoloExample/datasets/softcare/label_studio/softcare_label_studio_import.json"
DEFAULT_PROJECT_TITLE = "Softcare Diaper Review - 2026-08-05"


def next_project_title(base_title: str) -> str:
    if not Project.objects.filter(title=base_title, deleted_at__isnull=True).exists():
        return base_title
    index = 2
    while True:
        title = f"{base_title} ({index})"
        if not Project.objects.filter(title=title, deleted_at__isnull=True).exists():
            return title
        index += 1


def get_default_user() -> User:
    user = User.objects.order_by("id").first()
    if user is None:
        raise RuntimeError("Label Studio 没有用户，请先完成初始化和登录。")
    return user


def get_default_organization(user: User) -> Organization | None:
    organization = getattr(user, "active_organization", None)
    if organization is not None:
        return organization
    return Organization.objects.order_by("id").first()


def create_project(title: str, user: User, organization: Organization | None) -> Project:
    project = Project.objects.create(
        title=title,
        description="Softcare 纸尿裤图片复核项目：原图来自 Excel，YOLO-World 伪标注作为 predictions 导入。",
        label_config=LABEL_CONFIG,
        created_by=user,
        organization=organization,
        is_published=True,
        reveal_preannotations_interactively=False,
        show_collab_predictions=True,
    )
    return project


def import_tasks(project: Project, tasks: list[dict[str, object]]) -> tuple[int, int, int]:
    task_count = 0
    prediction_task_count = 0
    prediction_count = 0
    for item in tasks:
        task = Task.objects.create(
            project=project,
            data=item.get("data", {}),
            meta=item.get("meta", {}),
        )
        task_count += 1
        predictions = item.get("predictions", []) or []
        if predictions:
            prediction_task_count += 1
        for prediction in predictions:
            Prediction.objects.create(
                task=task,
                project=project,
                result=prediction.get("result", []),
                score=prediction.get("score"),
                model_version=prediction.get("model_version", "imported-prediction"),
            )
            prediction_count += 1
        if predictions:
            task.total_predictions = len(predictions)
            task.save(update_fields=["total_predictions"])
    return task_count, prediction_task_count, prediction_count


def main() -> None:
    import_json = Path(os.environ.get("LS_IMPORT_JSON", DEFAULT_IMPORT_JSON))
    base_title = os.environ.get("LS_PROJECT_TITLE", DEFAULT_PROJECT_TITLE)
    if not import_json.is_file():
        raise FileNotFoundError(f"导入 JSON 不存在：{import_json}")

    tasks = json.loads(import_json.read_text(encoding="utf-8"))
    if not isinstance(tasks, list) or not tasks:
        raise ValueError("导入 JSON 必须是非空任务列表。")

    user = get_default_user()
    organization = get_default_organization(user)
    title = next_project_title(base_title)

    with transaction.atomic():
        project = create_project(title, user, organization)
        task_count, prediction_task_count, prediction_count = import_tasks(project, tasks)

    print(f"project_id={project.id}")
    print(f"project_title={project.title}")
    print(f"tasks={task_count}")
    print(f"tasks_with_predictions={prediction_task_count}")
    print(f"predictions={prediction_count}")
    print(f"url=http://localhost:9001/projects/{project.id}/data")


main()
