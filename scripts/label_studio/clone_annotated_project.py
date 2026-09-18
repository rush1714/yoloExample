"""复制 Label Studio 项目中已有有效标注的任务到新项目。

该脚本通过 `label-studio shell` 执行，直接使用 Label Studio Django ORM。
它只复制已经有有效矩形框 annotation 的任务，不复制未标注任务，也不复制
prediction，适合从一个大项目中拆出已经确认过的训练样本继续复核或导出。
"""

# pylint: disable=line-too-long,invalid-name,wrong-import-position,import-error,no-name-in-module

from __future__ import annotations

import os
import sys
from pathlib import Path
from urllib.parse import parse_qs, unquote, urlsplit

# label-studio shell 里 __file__ 可能不可用，因此优先使用 Makefile 注入的 PROJECT_ROOT。
PROJECT_ROOT = Path(os.environ.get("PROJECT_ROOT", Path.cwd())).resolve()
if not (PROJECT_ROOT / "scripts").is_dir():
    PROJECT_ROOT = Path.cwd().resolve().parents[1]
if str(PROJECT_ROOT / "scripts") not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT / "scripts"))

from django.db import transaction  # noqa: E402,ICN001
from io_storages.localfiles.models import LocalFilesImportStorage, LocalFilesImportStorageLink  # type: ignore[import-not-found]  # noqa: E402,ICN001
from organizations.models import Organization  # type: ignore[import-not-found]  # noqa: E402,ICN001
from projects.models import Project  # type: ignore[import-not-found]  # noqa: E402,ICN001
from tasks.models import Annotation, Task  # type: ignore[import-not-found]  # noqa: E402,ICN001
from users.models import User  # type: ignore[import-not-found]  # noqa: E402,ICN001


def env_text(name: str, default: str = "") -> str:
    """读取环境变量并去掉首尾空白。"""
    return os.environ.get(name, default).strip()


def next_project_title(base_title: str) -> str:
    """生成一个未被使用的新项目标题。"""
    if not Project.objects.filter(title=base_title, deleted_at__isnull=True).exists():
        return base_title
    index = 2
    while True:
        title = f"{base_title} ({index})"
        if not Project.objects.filter(title=title, deleted_at__isnull=True).exists():
            return title
        index += 1


def default_user() -> User:
    """获取默认创建用户。"""
    user = User.objects.order_by("id").first()
    if user is None:
        raise RuntimeError("Label Studio 没有用户，请先完成初始化和登录。")
    return user


def default_organization(user: User) -> Organization | None:
    """获取用户当前组织，缺省时取第一个组织。"""
    organization = getattr(user, "active_organization", None)
    if organization is not None:
        return organization
    return Organization.objects.order_by("id").first()


def result_has_valid_box(result: dict[str, object], label_name: str | None) -> bool:
    """判断一个 result 是否是需要复制的有效矩形框。"""
    if result.get("type") != "rectanglelabels":
        return False
    value = result.get("value")
    if not isinstance(value, dict):
        return False
    labels = value.get("rectanglelabels")
    if not isinstance(labels, list) or not labels:
        return False
    if label_name and label_name not in [str(item) for item in labels]:
        return False
    try:
        width = float(value["width"])
        height = float(value["height"])
    except (KeyError, TypeError, ValueError):
        return False
    return width > 0 and height > 0


def annotation_has_valid_box(annotation: Annotation, label_name: str | None) -> bool:
    """判断 annotation 是否有至少一个有效矩形框。"""
    if annotation.was_cancelled or not isinstance(annotation.result, list):
        return False
    return any(isinstance(result, dict) and result_has_valid_box(result, label_name) for result in annotation.result)


def selected_annotation(task: Task, annotation_index: str, label_name: str | None) -> Annotation | None:
    """从任务中选择 first/latest 有效 annotation。"""
    annotations = [
        annotation
        for annotation in task.annotations.order_by("id")
        if annotation_has_valid_box(annotation, label_name)
    ]
    if not annotations:
        return None
    return annotations[0] if annotation_index == "first" else annotations[-1]


def parse_local_file_url(value: str) -> Path | None:
    """解析 Label Studio /data/local-files/?d=<path> 本地图片地址。"""
    parsed = urlsplit(value)
    if parsed.path != "/data/local-files/":
        return None
    values = parse_qs(parsed.query).get("d")
    return Path(unquote(values[0])).expanduser().resolve() if values else None


def task_local_path(task: Task) -> Path | None:
    """从任务 data 中提取本地图片路径。"""
    data = task.data if isinstance(task.data, dict) else {}
    local_path = data.get("local_path")
    if isinstance(local_path, str) and local_path:
        return Path(local_path).expanduser().resolve()
    image = data.get("image")
    if isinstance(image, str) and image:
        return parse_local_file_url(image)
    return None


def inferred_storage_path(tasks: list[Task]) -> Path | None:
    """根据已标注任务推断新项目需要授权的本地文件根目录。"""
    explicit = env_text("LS_LOCAL_FILES_PATH")
    if explicit:
        return Path(explicit).expanduser().resolve()
    parents = [path.parent for task in tasks if (path := task_local_path(task)) is not None]
    if not parents:
        return None
    try:
        return Path(os.path.commonpath([str(parent) for parent in parents])).resolve()
    except ValueError:
        return None


def create_project(source: Project, title: str, user: User, organization: Organization | None) -> Project:
    """按源项目配置创建新项目。"""
    return Project.objects.create(
        title=next_project_title(title),
        description=f"复制自项目 {source.id}: {source.title}，仅包含已有有效标注任务。",
        label_config=source.label_config,
        created_by=user,
        organization=organization,
        is_published=True,
        reveal_preannotations_interactively=getattr(source, "reveal_preannotations_interactively", False),
        show_collab_predictions=getattr(source, "show_collab_predictions", True),
    )


def create_storage(project: Project, storage_path: Path | None) -> LocalFilesImportStorage | None:
    """为新项目创建本地文件存储权限；没有本地文件任务时返回 None。"""
    if storage_path is None:
        return None
    storage = LocalFilesImportStorage.objects.create(
        project=project,
        title=f"Cloned annotated images {project.id}",
        description="Local file storage copied for annotated task clone.",
        path=str(storage_path),
        use_blob_urls=True,
    )
    storage.validate_connection()
    return storage


def clone_task_with_annotation(
    source_task: Task,
    annotation: Annotation,
    target_project: Project,
    storage: LocalFilesImportStorage | None,
    user: User,
) -> Task:
    """复制一个任务及其选中的 annotation。"""
    new_task = Task.objects.create(
        project=target_project,
        data=source_task.data if isinstance(source_task.data, dict) else {},
        meta=source_task.meta if isinstance(source_task.meta, dict) else {},
    )
    local_path = task_local_path(source_task)
    if storage is not None and local_path is not None:
        LocalFilesImportStorageLink.create(task=new_task, key=str(local_path), storage=storage)
    result = annotation.result if isinstance(annotation.result, list) else []
    Annotation.objects.create(
        task=new_task,
        project=target_project,
        completed_by=annotation.completed_by or user,
        updated_by=annotation.updated_by or annotation.completed_by or user,
        result=result,
        was_cancelled=False,
        ground_truth=annotation.ground_truth,
        lead_time=annotation.lead_time,
        prediction=annotation.prediction,
        result_count=len(result),
    )
    new_task.total_annotations = 1
    new_task.is_labeled = True
    new_task.save(update_fields=["total_annotations", "is_labeled"])
    return new_task


def main() -> None:
    """复制项目入口。"""
    source_project_id = env_text("LS_SOURCE_PROJECT_ID")
    if not source_project_id:
        raise ValueError("请通过 LS_SOURCE_PROJECT_ID=<项目ID> 指定源项目。")
    annotation_index = env_text("LS_CLONE_ANNOTATION_INDEX", "latest")
    if annotation_index not in {"first", "latest"}:
        raise ValueError("LS_CLONE_ANNOTATION_INDEX 只能是 first 或 latest。")
    label_name = env_text("LS_CLONE_LABEL_NAME") or None
    source_project = Project.objects.get(id=int(source_project_id), deleted_at__isnull=True)
    user = default_user()
    organization = default_organization(user)
    title = env_text("LS_CLONE_PROJECT_TITLE") or env_text("LS_PROJECT_TITLE") or f"{source_project.title} Annotated Copy"
    selected: list[tuple[Task, Annotation]] = []
    skipped = 0
    for task in source_project.tasks.order_by("id"):
        annotation = selected_annotation(task, annotation_index, label_name)
        if annotation is None:
            skipped += 1
            continue
        selected.append((task, annotation))
    storage_path = inferred_storage_path([task for task, _annotation in selected])
    with transaction.atomic():
        target_project = create_project(source_project, title, user, organization)
        storage = create_storage(target_project, storage_path)
        for task, annotation in selected:
            clone_task_with_annotation(task, annotation, target_project, storage, user)
    print(f"source_project_id={source_project.id}")
    print(f"source_project_title={source_project.title}")
    print(f"project_id={target_project.id}")
    print(f"project_title={target_project.title}")
    print(f"copied_tasks={len(selected)}")
    print(f"skipped_without_valid_annotation={skipped}")
    print(f"label_filter={label_name or 'all'}")
    print(f"annotation_index={annotation_index}")
    print(f"local_files_path={storage_path or '-'}")
    print(f"url=http://localhost:9001/projects/{target_project.id}/data")


# label-studio shell 中通过 exec(open(...).read()) 执行，因此直接调用 main()。
main()
