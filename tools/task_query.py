"""任务查询与元数据工具"""
import json
import logging
from config import Config
from utils import fetch_all_issues, validate_project_key, extract_issue_key
from ._lazy import LazyJira
from ._decorators import json_tool
from .task_common import (
    build_task_dict,
    register_field_name_mapping,
)

_logger = logging.getLogger("jira_bot.task_query")
jira = LazyJira()

# 创建元数据缓存（project_key:issue_type_name → JSON 字符串）
_create_meta_cache: dict = {}


def _get_create_meta_cached(project_key: str) -> str:
    """内部：获取项目元数据（带缓存），供 update_issue 等工具查找字段 ID"""
    if not project_key:
        return json.dumps({"success": False, "error": "缺少 project_key"})
    cache_key = project_key.upper()
    if cache_key not in _create_meta_cache:
        _create_meta_cache[cache_key] = get_create_issue_metadata.invoke(
            {"project_key": project_key}
        )
    return _create_meta_cache[cache_key]


def _get_required_fields(project_key: str, issue_type: str) -> list:
    """从缓存的元数据中提取指定项目+问题类型的必填字段名列表。"""
    if not project_key or not issue_type:
        return None
    cache_key = project_key.upper()
    if cache_key not in _create_meta_cache:
        return None
    try:
        meta = json.loads(_create_meta_cache[cache_key])
        if not meta.get("success"):
            return None
        for it in meta["data"]["issue_types"]:
            if it.get("name", "").lower() == issue_type.lower():
                return [f.get("name", "") for f in it.get("required_fields", [])]
    except (json.JSONDecodeError, KeyError):
        pass
    return None


@json_tool
def get_my_tasks() -> dict:
    """获取当前用户的所有未完成任务（status != Done）。
    返回 JSON 字符串，包含任务列表。
    """
    jql = 'assignee = currentUser() AND status != Done ORDER BY created DESC'
    issues = fetch_all_issues(jira, jql)
    tasks = [build_task_dict(issue) for issue in issues]
    return {"success": True, "count": len(tasks), "tasks": tasks}


@json_tool
def get_project_tasks(project_key: str = "") -> dict:
    """获取指定项目的所有任务。
    参数：
      project_key - 项目KEY（如 KO）
    返回 JSON 字符串，包含任务列表。
    """
    if not project_key:
        return {"success": False, "error": "请提供 project_key 参数"}
    project_key = validate_project_key(project_key)
    jql = Config.get_build_jql(f'project = "{project_key}" ORDER BY created DESC')
    issues = fetch_all_issues(jira, jql)
    tasks = [build_task_dict(issue) for issue in issues]
    return {"success": True, "count": len(tasks), "tasks": tasks}


@json_tool
def search_issues(query: str = "", project: str = "", status: str = "",
                  assignee: str = "", priority: str = "", issue_type: str = "",
                  max_results: int = 20) -> dict:
    """搜索 Jira 任务，支持按项目、状态、负责人、优先级、问题类型等条件筛选。"""
    jql_parts = []
    if project:
        jql_parts.append(f'project = "{validate_project_key(project)}"')
    if status:
        jql_parts.append(f'status = "{status}"')
    if assignee:
        jql_parts.append(f'assignee = "{assignee}"')
    if priority:
        jql_parts.append(f'priority = "{priority}"')
    if issue_type:
        jql_parts.append(f'issuetype = "{issue_type}"')
    if query:
        jql_parts.append(f'text ~ "{query}"')
    if not jql_parts:
        return {"success": False, "error": "请至少提供一个搜索条件"}
    jql = " AND ".join(jql_parts) + " ORDER BY created DESC"
    jql = Config.get_build_jql(jql)
    issues = fetch_all_issues(jira, jql)
    tasks = [build_task_dict(issue) for issue in issues[:max_results]]
    return {"success": True, "count": len(tasks), "tasks": tasks}


@json_tool
def get_create_issue_metadata(project_key: str = "",
                               issue_type_name: str = None) -> dict:
    """获取在指定项目中创建问题的元数据，包括可用的问题类型及其必填/可选字段。"""
    if not project_key:
        return {"success": False, "error": "请提供 project_key"}
    project_key = validate_project_key(project_key)

    cache_key = f"{project_key.upper()}:{issue_type_name or '__all__'}"
    if cache_key in _create_meta_cache:
        return json.loads(_create_meta_cache[cache_key])

    raw = jira.get_create_issue_metadata(project_key)
    if not raw or "projects" not in raw:
        return {"success": False, "error": f"无法获取项目 {project_key} 的元数据"}

    project_data = None
    for p in raw["projects"]:
        if p.get("key", "").upper() == project_key.upper():
            project_data = p
            break
    if not project_data:
        return {"success": False, "error": f"未找到项目 {project_key}"}

    # 注册显示名 → customfield ID 映射
    for it in project_data.get("issuetypes", []):
        for f in it.get("fields", {}).values():
            fname = f.get("name", "")
            fkey = f.get("key", "")
            ftype = f.get("schema", {}).get("type", "")
            if fname and fkey.startswith("customfield_"):
                register_field_name_mapping(fname, fkey, ftype)

    issue_types = []
    for it in project_data.get("issuetypes", []):
        if issue_type_name and it.get("name", "").lower() != issue_type_name.lower():
            continue
        it_data = {"id": it.get("id"), "name": it.get("name"),
                   "description": it.get("description", ""),
                   "required_fields": [], "optional_fields": []}
        for f in it.get("fields", {}).values():
            field_info = {"name": f.get("name", ""), "key": f.get("key", ""),
                          "required": f.get("required", False),
                          "type": f.get("schema", {}).get("type", "string")}
            if f.get("required"):
                it_data["required_fields"].append(field_info)
            else:
                it_data["optional_fields"].append(field_info)
        issue_types.append(it_data)

    result = {"success": True, "data": {"project_key": project_key,
              "issue_types": issue_types}}
    _create_meta_cache[cache_key] = json.dumps(result, ensure_ascii=False, indent=2)
    return result


@json_tool
def get_issue_transitions(issue_key: str = "") -> dict:
    """获取指定 Issue 当前可用的状态转换列表。"""
    key = extract_issue_key(issue_key)
    if not key:
        return {"success": False, "error": "请提供有效的 issue_key"}
    transitions = jira.get_issue_transitions(key)
    return {"success": True, "data": transitions}


@json_tool
def suggest_epic_tasks(epic_key: str = "") -> dict:
    """获取 Epic 任务的详细信息（标题、描述等），供 AI 自动拆分子任务。"""
    key = extract_issue_key(epic_key)
    if not key:
        return {"success": False, "error": "请提供有效的 Epic KEY"}

    epic = jira.get_issue(key)
    if not epic:
        return {"success": False, "error": f"未找到 {key}"}

    fields = epic.get("fields", {})
    result = {
        "key": key,
        "summary": fields.get("summary", ""),
        "description": fields.get("description", ""),
        "status": fields.get("status", {}).get("name", ""),
        "issuetype": fields.get("issuetype", {}).get("name", ""),
        "priority": fields.get("priority", {}).get("name", ""),
        "assignee": fields.get("assignee", {}).get("displayName", ""),
        "project": fields.get("project", {}).get("key", ""),
    }

    # 获取已有子任务
    jql = f'"Epic Link" = {key} OR parent = {key} ORDER BY created ASC'
    existing = fetch_all_issues(jira, jql)
    result["existing_tasks"] = [build_task_dict(issue) for issue in existing]

    return {"success": True, "epic": result}
