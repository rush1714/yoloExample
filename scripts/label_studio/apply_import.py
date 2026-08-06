"""
Label Studio 多品牌导入执行脚本（通过 Django ORM 直接导入）。

该脚本需要在 Label Studio Django shell 中运行：
- 根据品牌库动态生成多标签项目配置。
- 创建 Label Studio 项目。
- 配置本地文件存储。
- 导入任务和多品牌 predictions。
"""

from __future__ import annotations

import json
import os
import sys
from pathlib import Path

# 该脚本通常通过 label-studio shell 的 exec(open(...).read()) 执行，此时 __file__ 不一定存在。
# Makefile 会导出 PROJECT_ROOT；如果手动执行，则退回到当前工作目录的父级推断。
PROJECT_ROOT = Path(os.environ.get("PROJECT_ROOT", Path.cwd())).resolve()
if not (PROJECT_ROOT / "scripts").is_dir():
    PROJECT_ROOT = Path.cwd().resolve().parents[1]
if str(PROJECT_ROOT / "scripts") not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT / "scripts"))

from common.brand_library import DEFAULT_BRAND_LIBRARY, label_config_xml, load_brand_classes  # type: ignore[import-not-found]
from django.db import transaction  # noqa: ICN001
from io_storages.localfiles.models import LocalFilesImportStorage, LocalFilesImportStorageLink  # type: ignore[import-not-found]  # noqa: ICN001
from organizations.models import Organization  # type: ignore[import-not-found]  # noqa: ICN001
from projects.models import Project  # type: ignore[import-not-found]  # noqa: ICN001
from tasks.models import Prediction, Task  # type: ignore[import-not-found]  # noqa: ICN001
from users.models import User  # type: ignore[import-not-found]  # noqa: ICN001

DEFAULT_IMPORT_JSON = str(PROJECT_ROOT / "datasets" / "multibrand" / "label_studio" / "multibrand_label_studio_import.json")
DEFAULT_PROJECT_TITLE = "Multi Brand Package Review"
DEFAULT_LOCAL_FILES_PATH = str(PROJECT_ROOT / "datasets" / "multibrand" / "raw" / "images")


def next_project_title(base_title: str) -> str:
    """生成不重复的项目标题。"""
    if not Project.objects.filter(title=base_title, deleted_at__isnull=True).exists():
        return base_title
    index = 2
    while True:
        title = f"{base_title} ({index})"
        if not Project.objects.filter(title=title, deleted_at__isnull=True).exists():
            return title
        index += 1


def get_default_user() -> User:
    """获取默认用户（ID 最小的用户）。"""
    user = User.objects.order_by("id").first()
    if user is None:
        raise RuntimeError("Label Studio 没有用户，请先完成初始化和登录。")
    return user


def get_default_organization(user: User) -> Organization | None:
    """获取用户默认组织。"""
    organization = getattr(user, "active_organization", None)
    if organization is not None:
        return organization
    return Organization.objects.order_by("id").first()


def create_project(title: str, user: User, organization: Organization | None, label_config: str) -> Project:
    """创建多品牌 Label Studio 项目。"""
    project = Project.objects.create(
        title=title,
        description="多品牌包装图片复核项目：原图来自 Excel，YOLO-World 多品牌伪标注作为 predictions 导入。",
        label_config=label_config,
        created_by=user,
        organization=organization,
        is_published=True,
        reveal_preannotations_interactively=False,
        show_collab_predictions=True,
    )
    return project


def create_local_files_storage(project: Project, local_files_path: Path) -> LocalFilesImportStorage:
    """注册本地图片目录，使 /data/local-files/ 路径具有项目权限。"""
    storage = LocalFilesImportStorage.objects.create(
        project=project,
        title="Multibrand raw local images",
        description="Local image directory used by imported multi-brand review tasks.",
        path=str(local_files_path.resolve()),
        use_blob_urls=True,
    )
    storage.validate_connection()
    return storage


def import_tasks(project: Project, tasks: list[dict[str, object]], storage: LocalFilesImportStorage) -> tuple[int, int, int]:
    """导入任务和 prediction。"""
    task_count = 0
    prediction_task_count = 0
    prediction_count = 0
    for item in tasks:
        task = Task.objects.create(project=project, data=item.get("data", {}), meta=item.get("meta", {}))
        local_path = task.data.get("local_path") if isinstance(task.data, dict) else None
        if local_path:
            LocalFilesImportStorageLink.create(task=task, key=local_path, storage=storage)
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
    """Label Studio 导入执行主入口。"""
    import_json = Path(os.environ.get("LS_IMPORT_JSON", DEFAULT_IMPORT_JSON))
    base_title = os.environ.get("LS_PROJECT_TITLE", DEFAULT_PROJECT_TITLE)
    local_files_path = Path(os.environ.get("LS_LOCAL_FILES_PATH", DEFAULT_LOCAL_FILES_PATH))
    brand_library = Path(os.environ.get("BRAND_LIBRARY", str(DEFAULT_BRAND_LIBRARY)))

    print(f"LS_IMPORT_JSON={import_json}")
    print(f"LS_PROJECT_TITLE={base_title}")
    print(f"LS_LOCAL_FILES_PATH={local_files_path}")
    print(f"BRAND_LIBRARY={brand_library}")

    if not import_json.is_file():
        raise FileNotFoundError(f"导入 JSON 不存在：{import_json}")
    if not local_files_path.is_dir():
        raise FileNotFoundError(f"本地图片目录不存在：{local_files_path}")

    tasks = json.loads(import_json.read_text(encoding="utf-8"))
    if not isinstance(tasks, list) or not tasks:
        raise ValueError("导入 JSON 必须是非空任务列表。")

    brand_classes = load_brand_classes(brand_library)
    label_config = label_config_xml(brand_classes)
    title = next_project_title(base_title)

    if os.environ.get("LS_APPLY_DRY_RUN", "").lower() in {"1", "true", "yes"}:
        prediction_task_count = sum(1 for task in tasks if task.get("predictions"))
        prediction_count = sum(len(task.get("predictions", []) or []) for task in tasks)
        prediction_box_count = sum(
            len(prediction.get("result", []))
            for task in tasks
            for prediction in (task.get("predictions", []) or [])
        )
        print("dry_run=true")
        print(f"resolved_project_title={title}")
        print(f"user_count={User.objects.count()}")
        print(f"organization_count={Organization.objects.count()}")
        print(f"brand_classes={len(brand_classes)}")
        print(f"tasks={len(tasks)}")
        print(f"tasks_with_predictions={prediction_task_count}")
        print(f"predictions={prediction_count}")
        print(f"prediction_boxes={prediction_box_count}")
        return

    user = get_default_user()
    organization = get_default_organization(user)

    with transaction.atomic():
        project = create_project(title, user, organization, label_config)
        storage = create_local_files_storage(project, local_files_path)
        task_count, prediction_task_count, prediction_count = import_tasks(project, tasks, storage)

    print(f"project_id={project.id}")
    print(f"project_title={project.title}")
    print(f"brand_classes={len(brand_classes)}")
    print(f"tasks={task_count}")
    print(f"tasks_with_predictions={prediction_task_count}")
    print(f"predictions={prediction_count}")
    print(f"local_files_storage_id={storage.id}")
    print(f"local_files_path={storage.path}")
    print(f"url=http://localhost:9001/projects/{project.id}/data")


# label-studio shell 里通常通过 exec(open(...).read()) 执行，此时 __name__ 不一定是 "__main__"。
# 因此这里直接调用 main()，确保 make ls-apply 和手动 exec 都会真正执行导入。
main()
