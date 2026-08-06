"""
Label Studio 导入执行脚本（通过 Django ORM 直接导入）。

该脚本通过 Label Studio 的 Django ORM 直接将任务和预测导入数据库，用于自动化部署：
- 创建 Label Studio 项目
- 配置本地文件存储
- 导入任务和预测结果
- 在事务中执行，确保数据一致性

注意：此脚本需要在 Label Studio 的 Django 环境中运行（通过 `label-studio shell` 或类似方式）。
"""

from __future__ import annotations

import json
import os
from pathlib import Path

from django.db import transaction
from io_storages.localfiles.models import LocalFilesImportStorage, LocalFilesImportStorageLink
from organizations.models import Organization
from projects.models import Project
from tasks.models import Prediction, Task
from users.models import User

# Label Studio 标签配置 XML
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
# 默认导入 JSON 文件路径
DEFAULT_IMPORT_JSON = "/Users/guobiao/PRO/me/yoloExample/datasets/softcare/label_studio/softcare_label_studio_import.json"
# 默认项目标题
DEFAULT_PROJECT_TITLE = "Softcare Diaper Review - 2026-08-05"
# 默认本地图片目录
DEFAULT_LOCAL_FILES_PATH = "/Users/guobiao/PRO/me/yoloExample/datasets/softcare/raw/images"


def next_project_title(base_title: str) -> str:
    """
    生成不重复的项目标题。
    
    如果基础标题已存在，自动添加序号（如 "(2)"、"(3)"）。
    
    Args:
        base_title: 基础项目标题
    
    Returns:
        不重复的项目标题
    """
    # 检查基础标题是否可用
    if not Project.objects.filter(title=base_title, deleted_at__isnull=True).exists():
        return base_title
    # 添加序号直到找到可用的标题
    index = 2
    while True:
        title = f"{base_title} ({index})"
        if not Project.objects.filter(title=title, deleted_at__isnull=True).exists():
            return title
        index += 1


def get_default_user() -> User:
    """
    获取默认用户（ID 最小的用户）。
    
    Returns:
        用户对象
    
    Raises:
        RuntimeError: 如果没有用户存在
    """
    user = User.objects.order_by("id").first()
    if user is None:
        raise RuntimeError("Label Studio 没有用户，请先完成初始化和登录。")
    return user


def get_default_organization(user: User) -> Organization | None:
    """
    获取用户的默认组织。
    
    优先使用用户的 active_organization，否则返回第一个组织。
    
    Args:
        user: 用户对象
    
    Returns:
        组织对象，如果不存在则返回 None
    """
    organization = getattr(user, "active_organization", None)
    if organization is not None:
        return organization
    return Organization.objects.order_by("id").first()


def create_project(title: str, user: User, organization: Organization | None) -> Project:
    """
    创建 Label Studio 项目。
    
    Args:
        title: 项目标题
        user: 创建者用户
        organization: 所属组织
    
    Returns:
        创建的项目对象
    """
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


def create_local_files_storage(project: Project, local_files_path: Path) -> LocalFilesImportStorage:
    """
    创建本地文件存储配置。
    
    注册本地图片目录，使 /data/local-files/ 路径具有项目权限。
    
    Args:
        project: 项目对象
        local_files_path: 本地图片目录路径
    
    Returns:
        创建的存储对象
    """
    storage = LocalFilesImportStorage.objects.create(
        project=project,
        title="Softcare raw local images",
        description="Local image directory used by imported Softcare review tasks.",
        path=str(local_files_path.resolve()),
        use_blob_urls=True,
    )
    # 验证存储连接
    storage.validate_connection()
    return storage


def import_tasks(
    project: Project,
    tasks: list[dict[str, object]],
    storage: LocalFilesImportStorage,
) -> tuple[int, int, int]:
    """
    导入任务和预测结果到数据库。
    
    Args:
        project: 项目对象
        tasks: 任务列表
        storage: 本地文件存储对象
    
    Returns:
        元组：(任务数, 有预测的任务数, 预测总数)
    """
    task_count = 0
    prediction_task_count = 0
    prediction_count = 0
    # 遍历任务列表
    for item in tasks:
        # 创建任务
        task = Task.objects.create(
            project=project,
            data=item.get("data", {}),
            meta=item.get("meta", {}),
        )
        # 关联本地文件存储
        local_path = task.data.get("local_path") if isinstance(task.data, dict) else None
        if local_path:
            LocalFilesImportStorageLink.create(task=task, key=local_path, storage=storage)
        task_count += 1
        # 导入预测结果
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
        # 更新任务的预测总数
        if predictions:
            task.total_predictions = len(predictions)
            task.save(update_fields=["total_predictions"])
    return task_count, prediction_task_count, prediction_count


def main() -> None:
    """Label Studio 导入执行脚本主入口。"""
    # 从环境变量读取配置，否则使用默认值
    import_json = Path(os.environ.get("LS_IMPORT_JSON", DEFAULT_IMPORT_JSON))
    base_title = os.environ.get("LS_PROJECT_TITLE", DEFAULT_PROJECT_TITLE)
    local_files_path = Path(os.environ.get("LS_LOCAL_FILES_PATH", DEFAULT_LOCAL_FILES_PATH))
    # 验证输入文件
    if not import_json.is_file():
        raise FileNotFoundError(f"导入 JSON 不存在：{import_json}")
    if not local_files_path.is_dir():
        raise FileNotFoundError(f"本地图片目录不存在：{local_files_path}")

    # 加载任务数据
    tasks = json.loads(import_json.read_text(encoding="utf-8"))
    if not isinstance(tasks, list) or not tasks:
        raise ValueError("导入 JSON 必须是非空任务列表。")

    # 获取用户和组织
    user = get_default_user()
    organization = get_default_organization(user)
    # 生成不重复的项目标题
    title = next_project_title(base_title)

    # 在事务中执行，确保数据一致性
    with transaction.atomic():
        # 创建项目
        project = create_project(title, user, organization)
        # 创建本地文件存储
        storage = create_local_files_storage(project, local_files_path)
        # 导入任务和预测
        task_count, prediction_task_count, prediction_count = import_tasks(project, tasks, storage)

    # 打印结果
    print(f"project_id={project.id}")
    print(f"project_title={project.title}")
    print(f"tasks={task_count}")
    print(f"tasks_with_predictions={prediction_task_count}")
    print(f"predictions={prediction_count}")
    print(f"local_files_storage_id={storage.id}")
    print(f"local_files_path={storage.path}")
    print(f"url=http://localhost:9001/projects/{project.id}/data")


main()
