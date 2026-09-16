"""兼容旧路径的 S3 EC2 工作流入口。"""

# pylint: disable=wildcard-import,unused-wildcard-import,wrong-import-position,duplicate-code

from __future__ import annotations

import sys
from pathlib import Path

SCRIPTS_ROOT = Path(__file__).resolve().parents[1]
if str(SCRIPTS_ROOT) not in sys.path:
    sys.path.insert(0, str(SCRIPTS_ROOT))

from ec2.s3_workflow import *  # noqa: F403,E402
from ec2.s3_workflow import main  # noqa: E402


if __name__ == "__main__":
    main()
