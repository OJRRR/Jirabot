"""任务 CRUD 工具 — 创建、更新、删除、分配单个 Issue"""
import json
import logging
from langchain.tools import tool
from config import Config
from utils import extract_issue_key, validate_project_key
from ._lazy import LazyJira
from .task_common import (
    build_issue_fields,
    process_additional_fields,
    _resolve_fields_via_meta,
)

_logger = logging.getLogger("jira_bot.task_crud")
jira = LazyJira()


@tool
def create_issue(project_key: str = "", summary: str = "",
                 issue_type: str = "", description: str = "",
                 parent_key: str = None, epic_link_key: str = None,
                 additional_fields: dict = None) -> str:
    """在 Jira 中创建新的 Issue，支持子任务、Epic关联等。
    重要：必须明确指定 issue_type 参数。
    """
    try:
        if not project_key or not summary or not issue_type:
            return json.dumps(
                {"success": False,
                 "error": "请提供 project_key、summary、issue_type 参数"},
                ensure_ascii=False)
        project_key = validate_project_key(project_key)

        if additional_fields:
            additional_fields = _resolve_fields_via_meta(
                additional_fields, project_key)

        fields, err = build_issue_fields(
            project_key=project_key, summary=summary,
            issue_type=issue_type, description=description,
            parent_key=parent_key, epic_link_key=epic_link_key,
            additional_fields=additional_fields)
        if err:
            return json.dumps({"success": False, "error": err},
                              ensure_ascii=False)

        result = jira.create_issue(fields)
        key = result.get("key", "未知")
        return json.dumps(
            {"success": True, "key": key,
             "message": f"成功创建 {key}"},
            ensure_ascii=False, indent=2)
    except Exception as e:
        return json.dumps({"success": False, "error": str(e)},
                          ensure_ascii=False)


@tool
def create_issue_link(inward_issue_key: str = "",
                      outward_issue_key: str = "",
                      link_type_name: str = "Relates to") -> str:
    """在两个已存在的Jira问题之间创建一个链接。
    参数：
      inward_issue_key, outward_issue_key - 两个问题的KEY
      link_type_name - 链接类型（默认 Relates to）
    """
    try:
        if not inward_issue_key or not outward_issue_key:
            return json.dumps(
                {"success": False,
                 "error": "请提供 inward_issue_key 和 outward_issue_key"},
                ensure_ascii=False)
        result = jira.create_issue_link(inward_issue_key, outward_issue_key,
                                        link_type_name)
        return json.dumps(
            {"success": True, "message": f"成功创建链接: {inward_issue_key} "
                                         f"{link_type_name} {outward_issue_key}",
             "data": result},
            ensure_ascii=False, indent=2)
    except Exception as e:
        return json.dumps({"success": False, "error": str(e)},
                          ensure_ascii=False)


@tool
def update_issue(issue_key: str = "", summary: str = None,
                 description: str = None, priority: str = None,
                 additional_fields: dict = None,
                 project_key: str = "") -> str:
    """更新已有 Issue 的字段值（摘要、描述、优先级、自定义字段等）。"""
    try:
        key = extract_issue_key(issue_key)
        if not key:
            return json.dumps({"success": False,
                               "error": "请提供有效的 issue_key"},
                              ensure_ascii=False)

        updates = {}
        if summary is not None:
            updates["summary"] = summary
        if description is not None:
            updates["description"] = description
        if priority is not None:
            updates["priority"] = {"name": priority}

        if additional_fields:
            if project_key:
                additional_fields = _resolve_fields_via_meta(
                    additional_fields, project_key)
            else:
                additional_fields = process_additional_fields(
                    additional_fields)
            updates.update(additional_fields)

        if not updates:
            return json.dumps({"success": False,
                               "error": "请至少提供一个要更新的字段"},
                              ensure_ascii=False)

        jira.update_issue_field(key, updates)
        return json.dumps(
            {"success": True,
             "message": f"成功更新 {key}"},
            ensure_ascii=False, indent=2)
    except Exception as e:
        return json.dumps({"success": False, "error": str(e)},
                          ensure_ascii=False)


@tool
def add_issue_comment(issue_key: str = "", comment: str = "") -> str:
    """给指定 Issue 添加评论。
    参数：
      issue_key - 任务KEY（必填）
      comment - 评论内容（必填）
    """
    try:
        key = extract_issue_key(issue_key)
        if not key or not comment:
            return json.dumps(
                {"success": False,
                 "error": "请提供 issue_key 和 comment 参数"},
                ensure_ascii=False)
        result = jira.add_comment(key, comment)
        return json.dumps(
            {"success": True,
             "message": f"成功给 {key} 添加评论", "data": result},
            ensure_ascii=False, indent=2)
    except Exception as e:
        return json.dumps({"success": False, "error": str(e)},
                          ensure_ascii=False)


@tool
def add_issue_worklog(issue_key: str = "", time_spent: str = "",
                      comment: str = None, started: str = None) -> str:
    """给指定 Issue 记录工时。"""
    try:
        key = extract_issue_key(issue_key)
        if not key or not time_spent:
            return json.dumps(
                {"success": False,
                 "error": "请提供 issue_key 和 time_spent 参数"},
                ensure_ascii=False)
        result = jira.add_worklog(key, time_spent, comment=comment,
                                  started=started)
        return json.dumps(
            {"success": True,
             "message": f"成功给 {key} 记录工时 {time_spent}",
             "data": result},
            ensure_ascii=False, indent=2)
    except Exception as e:
        return json.dumps({"success": False, "error": str(e)},
                          ensure_ascii=False)


@tool
def assign_issue(issue_key: str = "", assignee: str = "") -> str:
    """将 Jira 任务分配给指定用户。"""
    try:
        key = extract_issue_key(issue_key)
        if not key or not assignee:
            return json.dumps(
                {"success": False,
                 "error": "请提供 issue_key 和 assignee 参数"},
                ensure_ascii=False)
        jira.assign_issue(key, assignee)
        return json.dumps(
            {"success": True,
             "message": f"成功将 {key} 分配给 {assignee}"},
            ensure_ascii=False)
    except Exception as e:
        return json.dumps({"success": False, "error": str(e)},
                          ensure_ascii=False)


@tool
def delete_issue(issue_key: str = "", delete_subtasks: bool = True,
                 confirmed: bool = False) -> str:
    """删除指定的 Jira Issue。
    警告：此操作不可逆，请谨慎使用！
    """
    try:
        key = extract_issue_key(issue_key)
        if not key:
            return json.dumps({"success": False,
                               "error": "请提供有效的 issue_key"},
                              ensure_ascii=False)
        if not confirmed:
            return json.dumps(
                {"success": False,
                 "error": f"⚠️ 即将删除 {key}，请设置 confirmed=true 确认"},
                ensure_ascii=False)
        jira.delete_issue(key, delete_subtasks=delete_subtasks)
        return json.dumps(
            {"success": True,
             "message": f"成功删除 {key}"},
            ensure_ascii=False)
    except Exception as e:
        return json.dumps({"success": False, "error": str(e)},
                          ensure_ascii=False)
