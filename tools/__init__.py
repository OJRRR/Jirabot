"""tools 包入口

提供工具的懒加载导出：
    from tools import get_my_tasks
    # 仅当第一次访问 get_my_tasks 时才真正 import task_query，触发 JiraClient 懒代理

这样 main.py / webapp.py 启动时不会因为 tools 包就触发网络探测。
"""
from typing import Any

# 单一数据源：工具名 → 子模块名。
# 新增工具只需在这里登记一行，不再需要同步两份清单。
_LAZY_TOOLS = {
    # task_query
    "get_my_tasks": "task_query",
    "get_project_tasks": "task_query",
    "search_issues": "task_query",
    "get_create_issue_metadata": "task_query",
    "get_issue_transitions": "task_query",
    "suggest_epic_tasks": "task_query",
    # task_crud
    "create_issue": "task_crud",
    "create_issue_link": "task_crud",
    "update_issue": "task_crud",
    "add_issue_comment": "task_crud",
    "add_issue_worklog": "task_crud",
    "assign_issue": "task_crud",
    "delete_issue": "task_crud",
    # task_batch
    "batch_create_issues": "task_batch",
    "batch_delete_issues": "task_batch",
    "batch_update_dates": "task_batch",
    "batch_update_issues": "task_batch",
    "import_from_excel": "task_batch",
    # task_planning
    "analyze_meeting_for_projects": "task_planning",
    # report_tools
    "generate_report": "report_tools",
    "generate_portfolio_report": "report_tools",
    # dependency_tools
    "get_issue_links": "dependency_tools",
    "get_task_dependencies": "dependency_tools",
    # risk_extractor
    "extract_issue_risks": "risk_extractor",
}

# 已加载的模块缓存
_loaded: dict = {}


def __getattr__(name: str) -> Any:
    if name not in _LAZY_TOOLS:
        raise AttributeError(f"module 'tools' has no attribute {name!r}")

    module_name = _LAZY_TOOLS[name]
    if module_name not in _loaded:
        # 触发该子模块的 import；其内部 jira = LazyJira() 不会立刻连 Jira
        import importlib
        _loaded[module_name] = importlib.import_module(f".{module_name}", __name__)
    return getattr(_loaded[module_name], name)


def __dir__():
    return sorted(list(_LAZY_TOOLS) + list(globals().keys()))


__all__ = list(_LAZY_TOOLS.keys())
