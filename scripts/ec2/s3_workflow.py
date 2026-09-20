"""S3 训练图清单在 EC2 上下载、训练、评估和产物下载的编排工具。"""

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
    remote_command,
    remote_project_path,
    rsync_ssh_arg,
    run_or_print,
    shell_join,
    ssh_base_args,
    ssh_target,
)


def remote_dataset_root(args: argparse.Namespace) -> str:
    """返回 EC2 上 S3 数据集根目录。"""
    if args.remote_dataset_root:
        return args.remote_dataset_root
    return f"datasets/{args.dataset_name}"


def validate_upload_inputs(args: argparse.Namespace) -> None:
    """在上传到 EC2 前检查本地训练标签、EC2 下载清单和 YAML 是否已生成。"""
    local_dataset_root = Path(args.dataset_root).resolve()
    labels_root = local_dataset_root / "labels"
    local_manifest = Path(args.ec2_manifest_json).resolve()
    local_manifest_csv = Path(args.ec2_manifest_csv).resolve()
    local_data_yaml = Path(args.data_yaml).resolve()
    s3_upload_manifest = local_manifest.with_name("s3_images.json")
    missing_messages: list[str] = []
    if not labels_root.is_dir():
        missing_messages.append(
            f"YOLO labels 目录不存在：{labels_root}。请先执行 make 2-brand-s3-workflow-after-ls LS_PROJECT_ID=<项目ID> 生成训练标签。"
        )
    if not local_manifest.is_file():
        manifest_message = f"EC2 图片下载清单不存在：{local_manifest}。"
        if s3_upload_manifest.is_file():
            manifest_message += (
                f"已找到上传/Label Studio 导入清单：{s3_upload_manifest}；"
                "但 EC2 训练需要标注转换后生成的 ec2_image_manifest.json，"
                "其中包含 split、training_image_name 和 label_path 等训练字段。"
            )
        manifest_message += "请先执行 make 2-brand-s3-workflow-after-ls LS_PROJECT_ID=<项目ID>。"
        missing_messages.append(manifest_message)
    if not local_manifest_csv.is_file():
        missing_messages.append(
            f"EC2 图片下载 CSV 清单不存在：{local_manifest_csv}。请先执行 make 2-brand-s3-workflow-after-ls LS_PROJECT_ID=<项目ID>。"
        )
    if not local_data_yaml.is_file():
        missing_messages.append(
            f"YOLO 数据集 YAML 不存在：{local_data_yaml}。请先执行 make 2-brand-s3-workflow-after-ls LS_PROJECT_ID=<项目ID> 生成 YAML。"
        )
    if missing_messages:
        raise SystemExit("无法上传 S3 EC2 训练输入：\n- " + "\n- ".join(missing_messages))


def upload_manifest(args: argparse.Namespace) -> None:
    """上传 labels、图片下载 manifest 和本地 YAML 到 EC2，不上传图片大文件。"""
    validate_upload_inputs(args)
    target = ssh_target(args.user, args.host)
    local_dataset_root = Path(args.dataset_root).resolve()
    local_data_yaml = Path(args.data_yaml).resolve()
    local_manifest = Path(args.ec2_manifest_json).resolve()
    local_manifest_csv = Path(args.ec2_manifest_csv).resolve()
    remote_dataset_abs = remote_project_path(args, remote_dataset_root(args))
    remote_manifest_abs = remote_project_path(args, args.remote_manifest_json)
    remote_manifest_csv_abs = remote_project_path(args, args.remote_manifest_csv)
    remote_data_yaml_abs = remote_project_path(args, args.remote_data_yaml)
    mkdir_command = (
        f"mkdir -p {shlex.quote(remote_dataset_abs)} "
        f"{shlex.quote(posixpath.dirname(remote_manifest_abs))} "
        f"{shlex.quote(posixpath.dirname(remote_manifest_csv_abs))} "
        f"{shlex.quote(posixpath.dirname(remote_data_yaml_abs))}"
    )
    run_or_print(["ssh", *ssh_base_args(args.port, args.key), target, mkdir_command], args.execute)
    run_or_print(
        [
            "rsync",
            "-avz",
            "-e",
            rsync_ssh_arg(args.port, args.key),
            f"{local_dataset_root / 'labels'}/",
            f"{target}:{remote_dataset_abs}/labels/",
        ],
        args.execute,
    )
    run_or_print(
        ["rsync", "-avz", "-e", rsync_ssh_arg(args.port, args.key), str(local_manifest),
         f"{target}:{remote_manifest_abs}"],
        args.execute,
    )
    if local_manifest_csv.is_file():
        run_or_print(
            ["rsync", "-avz", "-e", rsync_ssh_arg(args.port, args.key), str(local_manifest_csv),
             f"{target}:{remote_manifest_csv_abs}"],
            args.execute,
        )
    run_or_print(
        ["rsync", "-avz", "-e", rsync_ssh_arg(args.port, args.key), str(local_data_yaml),
         f"{target}:{remote_data_yaml_abs}"],
        args.execute,
    )


def download_images_command(args: argparse.Namespace) -> str:
    """生成 EC2 端根据 manifest 从 S3 下载图片的 Python 单行命令。"""
    manifest_abs = remote_project_path(args, args.remote_manifest_json)
    dataset_abs = remote_project_path(args, remote_dataset_root(args))
    code = r'''
import json
from pathlib import Path
from urllib.error import HTTPError, URLError
from urllib.parse import quote, urlsplit
from urllib.request import urlretrieve

download_mode = "__DOWNLOAD_MODE__"
public_base_url = "__PUBLIC_BASE_URL__".rstrip("/")
if download_mode not in {"auto", "public", "boto3"}:
    raise SystemExit(f"未知 S3 下载模式：{download_mode}，只能是 auto/public/boto3。")


def public_url_for_item(item):
    """优先读取 manifest 中的公共 URL；没有时用 public_base_url + s3_key 拼出 URL。"""
    for field_name in ("source_url", "https_url", "public_url"):
        value = str(item.get(field_name) or "").strip()
        if value.startswith(("http://", "https://")):
            return value
    if public_base_url and item.get("s3_key"):
        parsed_base = urlsplit(public_base_url)
        safe_key = quote(str(item["s3_key"]).lstrip("/"), safe="/")
        if parsed_base.query:
            separator = "&" if not public_base_url.endswith(("?", "&")) else ""
            return f"{public_base_url}{separator}key={quote(str(item['s3_key']), safe='/')}"
        return f"{public_base_url}/{safe_key}"
    return ""


def download_public_url(url, target):
    """通过公共 HTTP(S) URL 下载图片，不需要 EC2 配置 AWS credentials。"""
    try:
        urlretrieve(url, str(target))
    except (HTTPError, URLError, OSError) as exc:
        raise RuntimeError(f"公共 URL 下载失败：{url} -> {target}: {exc}") from exc


_s3_client = None


def s3_client():
    """懒加载 boto3 client；public 模式成功时不会触发 AWS 凭证检查。"""
    global _s3_client  # pylint: disable=global-statement
    if _s3_client is None:
        try:
            import boto3
        except ImportError as exc:
            raise SystemExit("EC2 缺少 boto3，请先在远端环境安装 boto3，或使用 S3_EC2_DOWNLOAD_MODE=public。") from exc
        _s3_client = boto3.client("s3")
    return _s3_client


manifest_path = Path(MANIFEST)
dataset_root = Path(DATASET_ROOT)
payload = json.loads(manifest_path.read_text(encoding="utf-8"))
items = payload.get("items", payload if isinstance(payload, list) else [])
if not isinstance(items, list) or not items:
    raise SystemExit("EC2 图片下载清单为空或格式不正确；请确认使用的是 ec2_image_manifest.json，而不是上传阶段的 s3_images.json。")
for index, item in enumerate(items):
    if not isinstance(item, dict):
        raise SystemExit(f"EC2 图片下载清单第 {index} 项不是对象；请重新生成 ec2_image_manifest.json。")
    missing = [field for field in ("split",) if not item.get(field)]
    needs_boto3_identity = download_mode == "boto3" or (download_mode == "auto" and not public_url_for_item(item))
    if needs_boto3_identity:
        missing.extend(field for field in ("s3_bucket", "s3_key") if not item.get(field))
    if download_mode == "public" and not public_url_for_item(item):
        missing.append("source_url/https_url/public_url 或 public_base_url+s3_key")
    if missing:
        raise SystemExit(
            f"EC2 图片下载清单第 {index} 项缺少字段：{', '.join(missing)}。"
            "请确认上传的是标注转换生成的 ec2_image_manifest.json；公共下载模式需要 manifest 中有公共 URL 或传入 S3_PUBLIC_BASE_URL。"
        )
for item in items:
    split = item["split"]
    image_name = item.get("training_image_name") or Path(str(item.get("relative_path") or item.get("image_name") or item.get("s3_key") or "image")).name
    target = dataset_root / "images" / split / image_name
    target.parent.mkdir(parents=True, exist_ok=True)
    if target.exists() and target.stat().st_size > 0:
        print(f"skip existing {target}")
        continue
    public_url = public_url_for_item(item)
    if download_mode in {"auto", "public"} and public_url:
        print(f"download {public_url} -> {target}")
        try:
            download_public_url(public_url, target)
            continue
        except RuntimeError as exc:
            if download_mode == "public":
                raise SystemExit(str(exc)) from exc
            print(f"公共 URL 下载失败，回退 boto3：{exc}")
    elif download_mode == "public":
        raise SystemExit(f"图片 {image_name} 没有可用公共 URL，无法在 public 模式下载。")
    print(f"download s3://{item['s3_bucket']}/{item['s3_key']} -> {target}")
    s3_client().download_file(item["s3_bucket"], item["s3_key"], str(target))
print(f"downloaded/checked {len(items)} images")
'''.strip()
    code = (
        code.replace("MANIFEST", repr(manifest_abs))
        .replace("DATASET_ROOT", repr(dataset_abs))
        .replace("__DOWNLOAD_MODE__", args.download_mode)
        .replace("__PUBLIC_BASE_URL__", args.public_base_url)
    )
    return shell_join([*args.python_cmd.split(), "-c", code])


def download_images(args: argparse.Namespace) -> None:
    """在 EC2 上根据 manifest 从 S3 下载训练图片。"""
    command = download_images_command(args)
    run_or_print(remote_command(args, command), args.execute)


def prepare_remote_dataset_yaml(args: argparse.Namespace) -> str:
    """生成 EC2 训练使用的绝对路径单类别 YAML。"""
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


def upload_existing_yaml_command(args: argparse.Namespace) -> str:
    """保留已上传 YAML 时只做存在性检查，避免覆盖多类别 names。"""
    remote_data_yaml_abs = remote_project_path(args, args.remote_data_yaml)
    return f"test -f {shlex.quote(remote_data_yaml_abs)}"


def train(args: argparse.Namespace) -> None:
    """在 EC2 上确保图片已下载、生成 YAML 后启动训练。"""
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
    command = (
        f"mkdir -p {shlex.quote(args.artifact_root)} && "
        f"{download_images_command(args)} && "
        f"{upload_existing_yaml_command(args) if args.skip_generate_yaml else prepare_remote_dataset_yaml(args)} && "
        f"{training_command}"
    )
    run_or_print(remote_command(args, command), args.execute)


def resolve_remote_run_dir(args: argparse.Namespace) -> str:
    """读取训练写入的真实 Ultralytics run 目录。"""
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
    parser = argparse.ArgumentParser(description="S3 训练图 EC2 工作流工具。")
    parser.add_argument(
        "action",
        choices=["upload-manifest", "download-images", "train", "evaluate", "download-model", "download-artifacts"],
    )
    parser.add_argument("--host", required=True, help="EC2 公网地址或 SSH Host 别名")
    parser.add_argument("--user", default="ubuntu", help="SSH 用户")
    parser.add_argument("--key", default=None, help="SSH 私钥路径")
    parser.add_argument("--port", type=int, default=22, help="SSH 端口")
    parser.add_argument("--execute", action="store_true", help="实际执行；默认只打印命令")
    parser.add_argument("--ec2-project-root", default="/home/ubuntu/yoloExample", help="EC2 上项目根目录")
    parser.add_argument("--activate-cmd", default="source /opt/pytorch/bin/activate",
                        help="EC2 上执行训练前的环境激活命令")
    parser.add_argument("--python-cmd", default="python3", help="EC2 上 Python 执行命令")
    parser.add_argument("--run-name", default="default", help="训练运行标识，仅用于归档和报告")
    parser.add_argument("--dataset-name", default="dataset", help="S3 数据集短名称")
    parser.add_argument("--label-name", default="diaper", help="单类别显示名")
    parser.add_argument("--dataset-root", default="datasets/dataset", help="本地 S3 工作流数据集根目录")
    parser.add_argument("--data-yaml", default="config/generated/dataset.yaml", help="本地 YAML 路径")
    parser.add_argument("--ec2-manifest-json", default="datasets/dataset/s3/metadata/ec2_image_manifest.json",
                        help="本地 EC2 图片 JSON 清单")
    parser.add_argument("--ec2-manifest-csv", default="datasets/dataset/s3/metadata/ec2_image_manifest.csv",
                        help="本地 EC2 图片 CSV 清单")
    parser.add_argument("--public-base-url", default="",
                        help="公开 S3/CDN Base URL；public/auto 下载模式下可用来拼接图片下载地址")
    parser.add_argument("--download-mode", choices=["auto", "public", "boto3"], default="auto",
                        help="EC2 下载 S3 图片模式：auto 优先公共 URL，public 强制公共 URL，boto3 使用 AWS SDK")
    parser.add_argument("--remote-dataset-root", default="", help="EC2 上数据集根目录；相对路径按项目根目录解析")
    parser.add_argument("--remote-data-yaml", default="config/generated/dataset.yaml", help="EC2 上 YAML 相对项目路径")
    parser.add_argument("--remote-manifest-json", default="datasets/dataset/s3/metadata/ec2_image_manifest.json",
                        help="EC2 上图片下载 JSON 清单")
    parser.add_argument("--remote-manifest-csv", default="datasets/dataset/s3/metadata/ec2_image_manifest.csv",
                        help="EC2 上图片下载 CSV 清单")
    parser.add_argument("--train-name", default="dataset", help="EC2 训练 run 名称")
    parser.add_argument("--base-model", default="yolo26m.pt", help="EC2 上基座模型路径或 Ultralytics 模型名")
    parser.add_argument("--remote-final-model", default="models/ec2/dataset/default/best.pt",
                        help="EC2 上导出的 best.pt 相对项目路径")
    parser.add_argument("--local-model", default="models/dataset/default/best.pt", help="下载到本地的模型路径")
    parser.add_argument("--artifact-root", default="artifacts/dataset/default", help="EC2 上训练产物归档目录")
    parser.add_argument("--latest-run-file", default="artifacts/dataset/default/latest-run.txt",
                        help="EC2 上记录实际 run 目录的清单文件")
    parser.add_argument("--local-artifact-root", default="outputs/ec2/dataset/default", help="本地归档下载目录")
    parser.add_argument("--epochs", type=int, default=100, help="训练轮数")
    parser.add_argument("--imgsz", type=int, default=960, help="训练尺寸")
    parser.add_argument("--batch", default="16", help="batch 大小")
    parser.add_argument("--device", default="0", help="EC2 GPU 设备")
    parser.add_argument("--resume", action="store_true", help="恢复训练")
    parser.add_argument("--skip-generate-yaml", action="store_true",
                        help="不在 EC2 重新生成单类别 YAML，直接使用已上传 YAML")
    parser.add_argument("--notes", default="", help="写入 evaluation-summary.md 的备注")
    return parser


def main() -> None:
    """入口。"""
    args = build_parser().parse_args()
    actions = {
        "upload-manifest": upload_manifest,
        "download-images": download_images,
        "train": train,
        "evaluate": evaluate,
        "download-model": download_model,
        "download-artifacts": download_artifacts,
    }
    actions[args.action](args)


if __name__ == "__main__":
    main()
