"""task_tools 的共享 helper - 不含 @tool 装饰的纯函数

被 task_tools / report_tools / risk_extractor 共用。
"""
import logging
from config import Config
from ._lazy import LazyJira

_logger = logging.getLogger("jira_bot.task_tools")
jira = LazyJira()

# Target Start / Target End 常见显示名 → 映射到 Config 中的 customfield ID
_TARGET_START_ALIASES = frozenset({
    "targetstart", "target start", "target_start",
    "start date", "startdate", "start",
    "planned start", "planned start date",
    "开始日期", "开始时间", "开始",
})
_TARGET_END_ALIASES = frozenset({
    "targetend", "target end", "target_end",
    "end date", "enddate", "end",
    "due date", "duedate",
    "planned end", "planned completed date", "planned end date",
    "结束日期", "结束时间", "结束", "截止",
})


def _normalize_field_key(key: str) -> str:
    """把 Target Start/End 的显示名或别名映射为 customfield ID。"""
    if not key or key.startswith("customfield_"):
        return key
    normalized = " ".join(key.strip().lower().replace("-", " ").replace("_", " ").split())
    if normalized in _TARGET_START_ALIASES:
        return Config.TARGET_START_FIELD
    if normalized in _TARGET_END_ALIASES:
        return Config.TARGET_END_FIELD
    return key


def _is_date_custom_field(key: str) -> bool:
    return key in (Config.TARGET_START_FIELD, Config.TARGET_END_FIELD)


def process_additional_fields(additional_fields: dict) -> dict:
    """
    把 additional_fields 转成 Jira API 接受的格式：
    - Target Start/End 显示名自动映射为 customfield ID，日期值用 YYYY-MM-DD 字符串
    - 其他 customfield_* 的字符串值包成 {"value": "..."}（Jira 选项型字段要求）
    - 其他字段原样透传

    之前在 task_tools.py 里 _build_issue_fields / create_issue / update_issue 三处重复
    出现同一段循环，抽到此处。
    """
    if not additional_fields:
        return {}
    processed = {}
    for k, v in additional_fields.items():
        field_key = _normalize_field_key(k)
        if _is_date_custom_field(field_key) and isinstance(v, str):
            # 已知的日期自定义字段 → 直接传日期字符串
            processed[field_key] = v
        elif field_key.startswith("customfield") and isinstance(v, str):
            # 尝试探测是否是日期字段：值匹配 YYYY-MM-DD 或带 T 的 ISO 格式
            import re as _re
            if _re.match(r'^\d{4}-\d{2}-\d{2}', v):
                processed[field_key] = v
            else:
                processed[field_key] = {"value": v}
        else:
            processed[field_key] = v
    return processed


def build_issue_fields(project_key: str, summary: str, issue_type: str,
                       description: str = "", parent_key: str = None,
                       epic_link_key: str = None,
                       additional_fields: dict = None) -> tuple:
    """
    构造 Jira Issue fields dict。
    :return: (fields_dict, error_message) - error_message 不为空时表示校验失败
    """
    if not project_key or not summary or not issue_type:
        return None, "缺少必填字段 (project_key/summary/issue_type)"

    if epic_link_key and issue_type.lower() == "sub-task":
        return None, "Epic 不能直接关联 Sub-task，层级关系为 Epic → Task → Sub-task"

    fields = {
        "project": {"key": project_key},
        "summary": summary,
        "issuetype": {"name": issue_type},
    }

    if description:
        fields["description"] = {
            "type": "doc",
            "version": 1,
            "content": [{"type": "paragraph", "content": [{"type": "text", "text": description}]}],
        }

    if parent_key:
        fields["parent"] = {"key": parent_key}

    if epic_link_key and Config.EPIC_LINK_FIELD_ID:
        fields[Config.EPIC_LINK_FIELD_ID] = epic_link_key

    fields.update(process_additional_fields(additional_fields))

    return fields, None


def build_task_dict(issue, include_assignee: bool = True) -> dict:
    """构建统一的 task 字典"""
    fields = issue.get("fields", {}) or {}
    status = fields.get("status", {}) or {}
    priority = fields.get("priority", {}) or {}
    assignee = fields.get("assignee", {}) or {}

    task = {
        "key": issue.get("key"),
        "summary": fields.get("summary"),
        "status": status.get("name"),
        "priority": priority.get("name"),
        "target_start": fields.get(Config.TARGET_START_FIELD),
        "target_end": fields.get(Config.TARGET_END_FIELD)
    }
    if include_assignee:
        task["assignee"] = assignee.get("displayName", "未分配")
    return task