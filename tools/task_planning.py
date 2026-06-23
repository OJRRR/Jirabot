"""任务规划工具 — 会议纪要分析、Epic 拆解建议"""
import json
import logging
from config import Config
from utils import fetch_all_issues, validate_project_key
from ._lazy import LazyJira
from ._decorators import json_tool
from .task_common import build_task_dict
from .task_query import _get_create_meta_cached

_logger = logging.getLogger("jira_bot.task_planning")
jira = LazyJira()


@json_tool
def analyze_meeting_for_projects(meeting_notes: str = "",
                                  project_key: str = "") -> dict:
    """分析项目会议纪要，生成 Epic → Task → Sub-task 的完整项目结构建议。"""
    if not meeting_notes:
        return {"success": False, "error": "请提供 meeting_notes 参数"}

    # 收集上下文信息
    context = {"meeting_notes": meeting_notes}

    # 获取指定项目的元数据（如果提供）
    if project_key:
        project_key = validate_project_key(project_key)
        meta_str = _get_create_meta_cached(project_key)
        meta = json.loads(meta_str)
        if meta.get("success"):
            context["project_metadata"] = meta["data"]
        else:
            context["project_error"] = meta.get("error", "获取项目元数据失败")

        # 获取项目现有的 Epic
        try:
            jql = Config.get_build_jql(
                f'project = "{project_key}" AND issuetype = Epic '
                f'ORDER BY created DESC')
            epics = fetch_all_issues(jira, jql)
            context["existing_epics"] = [
                {"key": e.get("key", ""),
                 "summary": e.get("fields", {}).get("summary", ""),
                 "status": e.get("fields", {}).get("status", {}).get("name", "")}
                for e in epics[:20]
            ]
        except (ValueError, RuntimeError):
            context["existing_epics"] = []

        # 获取项目最近的 Task
        try:
            jql = Config.get_build_jql(
                f'project = "{project_key}" AND issuetype = Task '
                f'ORDER BY created DESC')
            tasks = fetch_all_issues(jira, jql)
            context["recent_tasks"] = [build_task_dict(t) for t in tasks[:20]]
        except (ValueError, RuntimeError):
            context["recent_tasks"] = []
    else:
        context["project_metadata"] = None
        context["note"] = "未指定项目，AI 应根据会议纪要内容推断涉及的项目"

    return {"success": True, "context": context}
