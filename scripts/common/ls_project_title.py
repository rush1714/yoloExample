"""Label Studio 项目标题处理工具。

Label Studio 的 ``Project.title`` 字段在数据库中通常只有 50 个字符。
通用标签流程会把类别、国家和版本拼进项目标题；当类别较多或项目重名
需要追加 ``(2)`` 后缀时，标题很容易超过数据库限制。本模块把标题截断
和重名后缀拼接逻辑拆成纯函数，便于在不启动 Django 的单元测试中验证。
"""

from __future__ import annotations

DEFAULT_TITLE_MAX_LENGTH = 50


def normalize_project_title(
        title: str,
        fallback: str,
        max_length: int = DEFAULT_TITLE_MAX_LENGTH,
) -> str:
    """把标题归一化为不超过数据库长度限制的字符串。

    ``fallback`` 用于兜底空标题；截断后会去掉尾部空白，避免标题显示时
    出现不可见差异。如果标题本身只有空白或截断后为空，则再次回退到
    ``fallback`` 的安全截断结果。
    """
    safe_max_length = max(1, int(max_length or DEFAULT_TITLE_MAX_LENGTH))
    value = str(title or "").strip() or str(fallback or "Label Studio Project").strip()
    truncated = value[:safe_max_length].rstrip()
    if truncated:
        return truncated
    fallback_title = str(fallback or "Label Studio Project").strip() or "Label Studio Project"
    return fallback_title[:safe_max_length]


def title_with_index_suffix(
        base_title: str,
        index: int,
        fallback: str,
        max_length: int = DEFAULT_TITLE_MAX_LENGTH,
) -> str:
    """为重名项目追加 ``(N)`` 后缀，并保证最终标题长度合法。"""
    safe_max_length = max(1, int(max_length or DEFAULT_TITLE_MAX_LENGTH))
    suffix = f" ({index})"
    # 极端情况下 max_length 可能小于后缀长度；这里仍保留至少 1 个基础标题
    # 字符，再交给 normalize_project_title 做最终截断，保证不会越界。
    base_length = max(1, safe_max_length - len(suffix))
    safe_base = normalize_project_title(base_title, fallback, base_length)
    return normalize_project_title(f"{safe_base}{suffix}", fallback, safe_max_length)
