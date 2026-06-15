"""task_tools 的共享 helper - 不含 @tool 装饰的纯函数

被 task_tools / report_tools / risk_extractor 共用。
"""
import logging
from config import Config
from ._lazy import LazyJira

_logger = logging.getLogger("jira_bot.task_tools")
jira = LazyJira()


def process_additional_fields(additional_fields: dict) -> dict:
    """
    把 additional_fields 转成 Jira API 接受的格式：
    - customfield_* 的字符串值需要包成 {"value": "..."}（Jira 选项型字段要求）
    - 其他字段原样透传

    之前在 task_tools.py 里 _build_issue_fields / create_issue / update_issue 三处重复
    出现同一段循环，抽到此处。
    """
    if not additional_fields:
        return {}
    processed = {}
    for k, v in additional_fields.items():
        if k.startswith("customfield") and isinstance(v, str):
            processed[k] = {"value": v}
        else:
            processed[k] = v
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