"""EC2 工作流共享的 SSH、rsync 和远端路径工具。"""

from __future__ import annotations

import posixpath
import shlex
import subprocess
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[2]


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


def command_with_environment(args, command: str) -> str:
    """在远程命令前添加项目目录切换和环境激活。"""
    parts = [f"cd {shlex.quote(args.ec2_project_root)}"]
    if args.activate_cmd:
        parts.append(args.activate_cmd)
    parts.append(command)
    return " && ".join(parts)


def remote_command(args, command: str) -> list[str]:
    """构造在 EC2 项目目录中执行的远程命令。"""
    return [
        "ssh",
        *ssh_base_args(args.port, args.key),
        ssh_target(args.user, args.host),
        command_with_environment(args, command),
    ]


def remote_project_path(args, path_value: str) -> str:
    """把相对 EC2 项目根目录的路径转换为远端绝对路径。"""
    if path_value.startswith("/"):
        return path_value
    return posixpath.join(args.ec2_project_root, path_value)
