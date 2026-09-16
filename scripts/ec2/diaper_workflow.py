"""纸尿裤大类数据集 EC2 上传、训练、推理、评估归档与模型下载工具。"""

# pylint: disable=line-too-long,duplicate-code

from __future__ import annotations

import argparse
import base64
import posixpath
import shlex
import sys
from pathlib import Path

SCRIPTS_ROOT = Path(__file__).resolve().parents[1]
if str(SCRIPTS_ROOT) not in sys.path:
    sys.path.insert(0, str(SCRIPTS_ROOT))

from ec2.common import (  # pylint: disable=wrong-import-position
    PROJECT_ROOT,
    remote_command,
    remote_project_path,
    rsync_ssh_arg,
    run_or_print,
    shell_join,
    ssh_base_args,
    ssh_target,
)


def remote_dataset_root(args: argparse.Namespace) -> str:
    """返回远端数据集相对或绝对路径，默认兼容纸尿裤国家/版本目录。"""
    if args.remote_dataset_root:
        return args.remote_dataset_root
    return f"datasets/diaper_category/{args.country}/{args.version}"


def upload_data(args: argparse.Namespace) -> None:
    """上传当前国家/版本数据集和 YAML 到 EC2。"""
    target = ssh_target(args.user, args.host)
    dataset_root = Path(args.dataset_root).resolve()
    data_yaml = Path(args.data_yaml).resolve()
    remote_dataset_abs = remote_project_path(args, remote_dataset_root(args))
    remote_data_yaml_abs = remote_project_path(args, args.remote_data_yaml)
    mkdir_command = (
        f"mkdir -p {shlex.quote(remote_dataset_abs)} "
        f"{shlex.quote(posixpath.dirname(remote_data_yaml_abs))}"
    )
    run_or_print(["ssh", *ssh_base_args(args.port, args.key), target, mkdir_command], args.execute)
    run_or_print(
        [
            "rsync",
            "-avz",
            "-e",
            rsync_ssh_arg(args.port, args.key),
            f"{dataset_root}/",
            f"{target}:{remote_dataset_abs}/",
        ],
        args.execute,
    )
    run_or_print(
        [
            "rsync",
            "-avz",
            "-e",
            rsync_ssh_arg(args.port, args.key),
            str(data_yaml),
            f"{target}:{remote_data_yaml_abs}",
        ],
        args.execute,
    )


def upload_project(args: argparse.Namespace) -> None:
    """上传训练和推理所需项目代码到 EC2，排除本地大文件输出。"""
    target = ssh_target(args.user, args.host)
    excludes = [
        ".git/",
        ".venv/",
        "datasets/",
        "models/train/",
        "outputs/",
        "logs/",
        ".tmp/",
        ".label-studio-data/",
    ]
    command = ["rsync", "-avz", "-e", rsync_ssh_arg(args.port, args.key)]
    for pattern in excludes:
        command.extend(["--exclude", pattern])
    command.extend([f"{PROJECT_ROOT}/", f"{target}:{args.ec2_project_root}/"])
    run_or_print(command, args.execute)


def prepare_remote_dataset_yaml(args: argparse.Namespace) -> str:
    """在 EC2 生成使用绝对数据目录的单类别 YAML，避免相对路径解析偏差。"""
    remote_dataset_abs = remote_project_path(args, remote_dataset_root(args))
    yaml_content = "\n".join(
        [
            f"path: {remote_dataset_abs}",
            "train: images/train",
            "val: images/val",
            "test: images/test",
            "",
            "names:",
            f"  0: {args.label_name}",
            "",
        ]
    )
    encoded_content = base64.b64encode(yaml_content.encode("utf-8")).decode("ascii")
    remote_data_yaml_abs = remote_project_path(args, args.remote_data_yaml)
    return (
        f"mkdir -p {shlex.quote(posixpath.dirname(remote_data_yaml_abs))} && "
        f"echo {encoded_content} | base64 --decode > {shlex.quote(remote_data_yaml_abs)}"
    )



def train(args: argparse.Namespace) -> None:
    """在 EC2 上生成专用 YAML 后启动训练。"""
    training_command = shell_join(
        [
            *args.python_cmd.split(),
            "scripts/training/train.py",
            "--data",
            args.remote_data_yaml,
            "--base-model",
            args.base_model,
            "--epochs",
            str(args.epochs),
            "--imgsz",
            str(args.imgsz),
            "--batch",
            str(args.batch),
            "--device",
            args.device,
            "--project",
            "models/train",
            "--name",
            args.train_name,
            "--export-model",
            args.remote_final_model,
            "--run-dir-output",
            args.latest_run_file,
        ]
    )
    if args.resume:
        training_command += " --resume"
    command = f"mkdir -p {shlex.quote(args.artifact_root)} && {prepare_remote_dataset_yaml(args)} && {training_command}"
    run_or_print(remote_command(args, command), args.execute)


def resolve_remote_run_dir(args: argparse.Namespace) -> str:
    """读取训练写入的真实 Ultralytics run 目录清单。"""
    latest_run_file = shlex.quote(args.latest_run_file)
    fallback = shlex.quote(f"runs/detect/models/train/{args.train_name}")
    return f"$(cat {latest_run_file} 2>/dev/null || printf '%s' {fallback})"


def evaluate(args: argparse.Namespace) -> None:
    """在 EC2 上归档训练产物并生成 evaluation-summary.md。"""
    command = (
        f"{shell_join([*args.python_cmd.split(), 'scripts/reports/summarize_yolo_run.py'])} "
        f"--run-dir {resolve_remote_run_dir(args)} "
        f"--export-model {shlex.quote(args.remote_final_model)} "
        f"--dataset-root {shlex.quote(remote_dataset_root(args))} "
        f"--dataset-yaml {shlex.quote(args.remote_data_yaml)} "
        f"--artifact-dir {shlex.quote(args.artifact_root)} "
        f"--run-name {shlex.quote(args.run_name)} "
        f"--model {shlex.quote(args.base_model)} "
        f"--imgsz {args.imgsz} --epochs {args.epochs} "
        f"--batch {shlex.quote(str(args.batch))} --device {shlex.quote(args.device)} "
        f"--notes {shlex.quote(args.notes)}"
    )
    run_or_print(remote_command(args, command), args.execute)


def predict(args: argparse.Namespace) -> None:
    """在 EC2 上执行推理验证。"""
    command = shell_join(
        [
            *args.python_cmd.split(),
            "scripts/inference/predict.py",
            args.predict_source,
            "--model",
            args.remote_final_model,
            "--conf",
            str(args.predict_conf),
            "--imgsz",
            str(args.imgsz),
            "--device",
            args.device,
            "--output-dir",
            f"outputs/diaper_category/{args.country}/{args.version}/{args.run_name}",
        ]
    )
    run_or_print(remote_command(args, command), args.execute)


def download_model(args: argparse.Namespace) -> None:
    """从 EC2 下载训练好的 best.pt。"""
    target = ssh_target(args.user, args.host)
    local_model = Path(args.local_model).resolve()
    local_model.parent.mkdir(parents=True, exist_ok=True)
    run_or_print(
        [
            "rsync",
            "-avz",
            "-e",
            rsync_ssh_arg(args.port, args.key),
            f"{target}:{args.ec2_project_root}/{args.remote_final_model}",
            str(local_model),
        ],
        args.execute,
    )


def download_artifacts(args: argparse.Namespace) -> None:
    """从 EC2 下载完整训练归档目录。"""
    target = ssh_target(args.user, args.host)
    local_root = Path(args.local_artifact_root).resolve()
    local_root.mkdir(parents=True, exist_ok=True)
    run_or_print(
        [
            "rsync",
            "-avz",
            "-e",
            rsync_ssh_arg(args.port, args.key),
            f"{target}:{args.ec2_project_root}/{args.artifact_root}/",
            f"{local_root}/",
        ],
        args.execute,
    )


def build_parser() -> argparse.ArgumentParser:
    """构造命令行解析器。"""
    parser = argparse.ArgumentParser(description="纸尿裤大类 EC2 工作流工具。")
    parser.add_argument(
        "action",
        choices=["upload-data", "upload-project", "train", "evaluate", "predict", "download-model", "download-artifacts"],
    )
    parser.add_argument("--host", required=True, help="EC2 公网地址或 SSH Host 别名")
    parser.add_argument("--user", default="ubuntu", help="SSH 用户")
    parser.add_argument("--key", default=None, help="SSH 私钥路径")
    parser.add_argument("--port", type=int, default=22, help="SSH 端口")
    parser.add_argument("--execute", action="store_true", help="实际执行；默认只打印命令")
    parser.add_argument("--ec2-project-root", default="/home/ubuntu/yoloExample", help="EC2 上项目根目录")
    parser.add_argument("--activate-cmd", default="source /opt/pytorch/bin/activate", help="EC2 上执行训练前的环境激活命令")
    parser.add_argument("--python-cmd", default="python3", help="EC2 上 Python 执行命令")
    parser.add_argument("--run-name", default="default", help="训练运行标识，仅用于归档和报告")
    parser.add_argument("--country", default="default", help="国家代码")
    parser.add_argument("--version", default="v1", help="数据版本")
    parser.add_argument("--label-name", default="diaper", help="单类别显示名，写入训练 YAML 的 names[0]")
    parser.add_argument("--dataset-root", default="datasets/diaper_category/default/v1", help="本地数据集根目录")
    parser.add_argument("--data-yaml", default="config/generated/diaper_category_default_v1.yaml", help="本地 YAML 路径")
    parser.add_argument("--remote-dataset-root", default="", help="EC2 上数据集根目录；相对路径按项目根目录解析")
    parser.add_argument("--remote-data-yaml", default="config/generated/diaper_category_default_v1.yaml", help="EC2 上 YAML 相对项目路径")
    parser.add_argument("--train-name", default="diaper_category_default_v1", help="EC2 训练 run 名称")
    parser.add_argument("--base-model", default="yolo26m.pt", help="EC2 上基座模型路径或 Ultralytics 模型名")
    parser.add_argument("--remote-final-model", default="models/ec2/diaper_category/default/v1/best.pt", help="EC2 上导出的 best.pt 相对项目路径")
    parser.add_argument("--local-model", default="models/diaper_category/default/v1/best.pt", help="下载到本地的模型路径")
    parser.add_argument("--artifact-root", default="artifacts/diaper_category/default/v1/default", help="EC2 上训练产物归档目录")
    parser.add_argument("--latest-run-file", default="artifacts/diaper_category/default/v1/default/latest-run.txt", help="EC2 上记录实际 Ultralytics run 目录的清单文件")
    parser.add_argument("--local-artifact-root", default="outputs/ec2/diaper_category/default/v1/default", help="本地归档下载目录")
    parser.add_argument("--epochs", type=int, default=100, help="训练轮数")
    parser.add_argument("--imgsz", type=int, default=960, help="训练/推理尺寸")
    parser.add_argument("--batch", default="16", help="batch 大小")
    parser.add_argument("--device", default="0", help="EC2 GPU 设备")
    parser.add_argument("--resume", action="store_true", help="恢复训练")
    parser.add_argument("--predict-source", default="data/samples/multibrand-shelf.webp", help="EC2 上推理输入")
    parser.add_argument("--predict-conf", type=float, default=0.35, help="推理置信度")
    parser.add_argument("--notes", default="", help="写入 evaluation-summary.md 的备注")
    return parser


def main() -> None:
    """入口。"""
    args = build_parser().parse_args()
    actions = {
        "upload-data": upload_data,
        "upload-project": upload_project,
        "train": train,
        "evaluate": evaluate,
        "predict": predict,
        "download-model": download_model,
        "download-artifacts": download_artifacts,
    }
    actions[args.action](args)


if __name__ == "__main__":
    main()
