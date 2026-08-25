"""纸尿裤大类数据集 EC2 上传、训练、推理、评估归档与模型下载工具。"""

from __future__ import annotations

import argparse
import shlex
import subprocess
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[2]
TRAIN_PROFILES = {
    "smoke": {"base_model": "yolo11n.pt", "imgsz": 640, "epochs": 5},
    "baseline": {"base_model": "yolo11s.pt", "imgsz": 960, "epochs": 100},
    "improve": {"base_model": "yolo11m.pt", "imgsz": 960, "epochs": 150},
}


def ssh_target(user: str, host: str) -> str:
    """组合 SSH 目标。"""
    return f"{user}@{host}" if user else host


def ssh_base_args(port: int, key: str | None) -> list[str]:
    """生成 ssh/rsync 共用连接参数。"""
    args = ["-p", str(port)]
    if key:
        args.extend(["-i", key])
    return args


def rsync_ssh_arg(port: int, key: str | None) -> str:
    """生成 rsync -e 参数。"""
    parts = ["ssh", "-p", str(port)]
    if key:
        parts.extend(["-i", key])
    return " ".join(shlex.quote(item) for item in parts)


def quote_cmd(parts: list[str]) -> str:
    """把命令数组格式化为可复制执行的 shell 字符串。"""
    return " ".join(shlex.quote(item) for item in parts)


def shell_join(parts: list[str]) -> str:
    """把远程命令片段安全拼接为 shell 字符串。"""
    return " ".join(shlex.quote(item) for item in parts)


def run_or_print(command: list[str], execute: bool) -> None:
    """默认 dry-run 打印命令；execute=True 时实际执行。"""
    print(quote_cmd(command))
    if execute:
        subprocess.run(command, check=True)


def command_with_environment(args: argparse.Namespace, command: str) -> str:
    """在远程命令前添加项目目录切换和 PyTorch 环境激活。"""
    parts = [f"cd {shlex.quote(args.ec2_project_root)}"]
    if args.activate_cmd:
        parts.append(args.activate_cmd)
    parts.append(command)
    return " && ".join(parts)


def remote_python_command(args: argparse.Namespace, command: str) -> list[str]:
    """构造在 EC2 项目目录中执行的远程命令。"""
    remote = command_with_environment(args, command)
    return ["ssh", *ssh_base_args(args.port, args.key), ssh_target(args.user, args.host), remote]


def upload_data(args: argparse.Namespace) -> None:
    """上传当前国家/版本数据集和 YAML 到 EC2。"""
    target = ssh_target(args.user, args.host)
    dataset_root = Path(args.dataset_root).resolve()
    data_yaml = Path(args.data_yaml).resolve()
    mkdir_command = (
        f"mkdir -p {shlex.quote(args.ec2_project_root)}/datasets/diaper_category/"
        f"{shlex.quote(args.country)}/{shlex.quote(args.version)} "
        f"{shlex.quote(args.ec2_project_root)}/config/generated"
    )
    run_or_print(["ssh", *ssh_base_args(args.port, args.key), target, mkdir_command], args.execute)
    run_or_print(
        [
            "rsync",
            "-avz",
            "-e",
            rsync_ssh_arg(args.port, args.key),
            f"{dataset_root}/",
            f"{target}:{args.ec2_project_root}/datasets/diaper_category/{args.country}/{args.version}/",
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
            f"{target}:{args.ec2_project_root}/config/generated/{data_yaml.name}",
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


def train(args: argparse.Namespace) -> None:
    """在 EC2 上启动训练。"""
    command = shell_join(
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
        ]
    )
    if args.resume:
        command += " --resume"
    run_or_print(remote_python_command(args, command), args.execute)


def evaluate(args: argparse.Namespace) -> None:
    """在 EC2 上归档训练产物并生成 evaluation-summary.md。"""
    command = shell_join(
        [
            *args.python_cmd.split(),
            "scripts/reports/summarize_yolo_run.py",
            "--run-dir",
            f"models/train/{args.train_name}",
            "--dataset-root",
            f"datasets/diaper_category/{args.country}/{args.version}",
            "--dataset-yaml",
            args.remote_data_yaml,
            "--artifact-dir",
            args.artifact_root,
            "--profile",
            args.profile,
            "--model",
            args.base_model,
            "--imgsz",
            str(args.imgsz),
            "--epochs",
            str(args.epochs),
            "--batch",
            str(args.batch),
            "--device",
            args.device,
            "--notes",
            args.notes,
        ]
    )
    run_or_print(remote_python_command(args, command), args.execute)


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
            f"outputs/diaper_category/{args.country}/{args.version}/{args.profile}",
        ]
    )
    run_or_print(remote_python_command(args, command), args.execute)


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


def apply_profile_defaults(args: argparse.Namespace) -> None:
    """根据 smoke/baseline/improve 档位填充默认训练参数。"""
    defaults = TRAIN_PROFILES.get(args.profile)
    if defaults is None:
        return
    if args.base_model is None:
        args.base_model = str(defaults["base_model"])
    if args.imgsz is None:
        args.imgsz = int(defaults["imgsz"])
    if args.epochs is None:
        args.epochs = int(defaults["epochs"])


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
    parser.add_argument("--profile", choices=["smoke", "baseline", "improve", "custom"], default="smoke", help="训练档位")
    parser.add_argument("--country", default="default", help="国家代码")
    parser.add_argument("--version", default="v1", help="数据版本")
    parser.add_argument("--dataset-root", default="datasets/diaper_category/default/v1", help="本地数据集根目录")
    parser.add_argument("--data-yaml", default="config/generated/diaper_category_default_v1.yaml", help="本地 YAML 路径")
    parser.add_argument("--remote-data-yaml", default="config/generated/diaper_category_default_v1.yaml", help="EC2 上 YAML 相对项目路径")
    parser.add_argument("--train-name", default="diaper_category_default_v1", help="EC2 训练 run 名称")
    parser.add_argument("--base-model", default=None, help="EC2 上基座模型路径或 Ultralytics 模型名")
    parser.add_argument("--remote-final-model", default="models/ec2/diaper_category/default/v1/best.pt", help="EC2 上导出的 best.pt 相对项目路径")
    parser.add_argument("--local-model", default="models/diaper_category/default/v1/best.pt", help="下载到本地的模型路径")
    parser.add_argument("--artifact-root", default="artifacts/diaper_category/default/v1/smoke", help="EC2 上训练产物归档目录")
    parser.add_argument("--local-artifact-root", default="outputs/ec2/diaper_category/default/v1/smoke", help="本地归档下载目录")
    parser.add_argument("--epochs", type=int, default=None, help="训练轮数；未设置时由 profile 决定")
    parser.add_argument("--imgsz", type=int, default=None, help="训练/推理尺寸；未设置时由 profile 决定")
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
    apply_profile_defaults(args)
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
