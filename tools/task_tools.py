"""任务查询与创建工具（重构版）"""
import json
import re
import logging
from langchain.tools import tool
from jira_client import JiraClient
from config import Config
from utils import fetch_all_issues, validate_project_key, extract_issue_key

_logger = logging.getLogger("jira_bot.task_tools")
jira = JiraClient()


def _build_task_dict(issue, include_assignee: bool = True) -> dict:
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


@tool
def get_my_tasks() -> str:
    """
    获取当前用户的所有未完成任务（status != Done）。
    返回 JSON 字符串，包含任务列表。
    """
    try:
        base_jql = "assignee = currentUser() AND status != Done ORDER BY updated DESC"
        jql_query = Config.get_build_jql(base_jql)
        _logger.info("查询我的任务")
        issues = fetch_all_issues(jira, jql_query, Config.JQL_PAGE_SIZE)

        max_count = Config.MAX_TASKS_PER_TOOL
        tasks = [_build_task_dict(issue) for issue in issues[:max_count] if issue]

        _logger.info("我的任务: 共 %d 条，返回 %d 条", len(issues), len(tasks))
        return json.dumps(
            {"success": True, "total": len(issues), "returned": len(tasks), "tasks": tasks},
            ensure_ascii=False, indent=2
        )
    except Exception as e:
        _logger.error("获取我的任务失败: %s", e)
        return json.dumps({"error": str(e)}, ensure_ascii=False)


@tool
def get_project_tasks(project_key: str = "") -> str:
    """
    获取指定项目的所有任务。
    参数：project_key - 项目KEY（如 KO）
    返回 JSON 字符串，包含任务列表。
    """
    try:
        key = validate_project_key(project_key)
        _logger.info("查询项目任务: %s", key)
        issues = fetch_all_issues(jira, f"project = {key} ORDER BY updated DESC", Config.JQL_PAGE_SIZE)

        max_count = Config.MAX_TASKS_PER_TOOL
        tasks = [_build_task_dict(issue) for issue in issues[:max_count] if issue]

        _logger.info("项目 %s 任务: 共 %d 条，返回 %d 条", key, len(issues), len(tasks))
        return json.dumps(
            {"success": True, "project": key, "total": len(issues), "returned": len(tasks), "tasks": tasks},
            ensure_ascii=False, indent=2
        )
    except Exception as e:
        _logger.error("获取项目任务失败 %s: %s", project_key, e)
        return json.dumps({"error": str(e)}, ensure_ascii=False)


@tool
def get_create_issue_metadata(project_key: str = "", issue_type_name: str = None) -> str:
    """
    获取在指定项目中创建问题的元数据，包括可用的问题类型及其必填/可选字段。
    参数：project_key - 项目KEY，issue_type_name - 可选，按名称过滤问题类型
    """
    try:
        key = validate_project_key(project_key)
        _logger.info("获取创建元数据: %s %s", key, issue_type_name if issue_type_name else "")

        meta_data = jira.get_issue_createmeta(key)

        if isinstance(meta_data, str):
            meta_data = json.loads(meta_data)

        if not meta_data or 'projects' not in meta_data:
            return json.dumps({"error": "无法获取项目的创建元数据，请检查项目KEY或权限"}, ensure_ascii=False)

        result = {"project_key": key, "issue_types": []}

        for project in meta_data.get('projects', []):
            for issue_type in project.get('issuetypes', []):
                issue_type_info = {
                    "name": issue_type.get('name'),
                    "description": issue_type.get('description'),
                    "subtask": issue_type.get('subtask', False),
                    "required_fields": [],
                    "optional_fields": []
                }
                for field_key, field_config in issue_type.get('fields', {}).items():
                    field_info = {
                        "name": field_config.get('name'),
                        "key": field_key,
                        "type": field_config.get('schema', {}).get('type'),
                        "allowed_values": None
                    }
                    if 'allowedValues' in field_config and field_config['allowedValues']:
                        allowed = []
                        for v in field_config['allowedValues']:
                            if isinstance(v, str):
                                allowed.append(v)
                            elif isinstance(v, dict):
                                # Jira 返回的对象可能有 value / name / id
                                allowed.append(v.get('value') or v.get('name') or v.get('id') or str(v))
                        field_info["allowed_values"] = allowed

                    if field_config.get('required', False):
                        issue_type_info['required_fields'].append(field_info)
                    else:
                        issue_type_info['optional_fields'].append(field_info)

                result['issue_types'].append(issue_type_info)

            if issue_type_name:
                filtered = [it for it in result['issue_types'] if it['name'].lower() == issue_type_name.lower()]
                result['issue_types'] = filtered
                if not filtered:
                    return json.dumps(
                        {"error": f"在项目 '{key}' 中未找到名为 '{issue_type_name}' 的问题类型。"},
                        ensure_ascii=False
                    )
            break

        return json.dumps({"success": True, "data": result}, ensure_ascii=False, indent=2)
    except Exception as e:
        _logger.error("获取创建元数据失败 %s: %s", project_key, e)
        return json.dumps({"error": f"获取创建元数据失败: {str(e)}"}, ensure_ascii=False)


@tool
def create_issue(project_key: str = "", summary: str = "", issue_type: str = "",
                 description: str = "", parent_key: str = None, epic_link_key: str = None,
                 additional_fields: dict = None) -> str:
    """
    在 Jira 中创建新的 Issue，支持子任务、Epic关联等。
    重要：必须明确指定 issue_type 参数。
    """
    missing = []
    if not project_key:
        missing.append("project_key")
    if not summary:
        missing.append("summary")
    if not issue_type:
        return ("创建失败：必须明确指定 issue_type（问题类型），例如 Task、Sub-task、Risk 等。"
                "如果不清楚有哪些类型，可以调用 get_create_issue_metadata 工具查看。")
    if missing:
        return f"创建失败，缺少基础必填字段: {', '.join(missing)}。请补充后重试。"

    try:
        key = validate_project_key(project_key)
        _logger.info("创建Issue: %s / %s / %s", key, issue_type, summary)

        fields = {
            "project": {"key": key},
            "summary": summary,
            "issuetype": {"name": issue_type}
        }

        if description:
            fields["description"] = {
                "type": "doc",
                "version": 1,
                "content": [{"type": "paragraph", "content": [{"type": "text", "text": description}]}]
            }

        if parent_key:
            fields["parent"] = {"key": parent_key}

        if epic_link_key:
            if issue_type.lower() == "sub-task":
                return ("创建失败：Epic 不能直接关联 Sub-task，层级关系为 Epic → Task → Sub-task。\n"
                        "请将 Sub-task 的父任务设为 Task，再将 Task 关联到 Epic。")
            epic_field_id = Config.EPIC_LINK_FIELD_ID
            if epic_field_id:
                fields[epic_field_id] = epic_link_key

        if additional_fields:
            # Jira API 要求选项类型自定义字段的值用 {"value": "选项名"} 格式
            processed = {}
            for k, v in additional_fields.items():
                if k.startswith("customfield") and isinstance(v, str):
                    processed[k] = {"value": v}
                else:
                    processed[k] = v
            fields.update(processed)

        new_issue = jira.create_issue(fields=fields)
        issue_key = new_issue.get("key")
        issue_url = f"{Config.JIRA_SERVER}/browse/{issue_key}"

        msg = f"任务创建成功！\n{issue_key}: {issue_url}\n摘要: {summary}"
        if parent_key:
            msg += f"\n父任务: {parent_key}"
        if epic_link_key:
            msg += f"\n所属Epic: {epic_link_key}"
        _logger.info("创建成功: %s", issue_key)
        return msg
    except Exception as e:
        error_msg = str(e)
        _logger.error("创建失败: %s", error_msg)
        missing_fields = []
        if "required" in error_msg.lower():
            # 匹配多种 Jira 错误格式:
            # 1. "required field 'customfield_12345' is missing"
            # 2. "Role Name is required"
            # 3. "required field 'Role Name'"
            patterns = [
                re.compile(r"required field '?(\w+)'? is missing", re.IGNORECASE),
                re.compile(r"'?(\w+(?:\s+\w+)*)'? is required", re.IGNORECASE),
                re.compile(r"required field '?(\w+(?:\s+\w+)*)'?", re.IGNORECASE),
            ]
            for pattern in patterns:
                match = pattern.search(error_msg)
                if match:
                    missing_fields.append(match.group(1))
                    break
        if missing_fields:
            return (f"创建失败，缺少必填字段: {', '.join(missing_fields)}。\n"
                    f"请先调用 get_create_issue_metadata('{project_key}', '{issue_type}') 工具查询该类型的必填字段及可选值列表，"
                    f"然后将字段的值通过 additional_fields 参数传入。\n"
                    f"原始错误: {error_msg}")
        return f"创建任务失败: {error_msg}"


@tool
def create_issue_link(inward_issue_key: str = "", outward_issue_key: str = "",
                      link_type_name: str = "Relates to") -> str:
    """
    在两个已存在的Jira问题之间创建一个链接。
    参数：inward_issue_key, outward_issue_key - 两个问题的KEY，link_type_name - 链接类型（默认 Relates to）。
    """
    if not inward_issue_key or not outward_issue_key:
        return "创建链接失败: 必须提供两个问题的KEY。"
    try:
        _logger.info("创建链接: %s -> %s (%s)", inward_issue_key, outward_issue_key, link_type_name)
        link_data = {
            "type": {"name": link_type_name},
            "inwardIssue": {"key": inward_issue_key},
            "outwardIssue": {"key": outward_issue_key}
        }
        jira.create_issue_link(link_data)
        return f"成功在问题 {outward_issue_key} 和 {inward_issue_key} 之间创建了 '{link_type_name}' 链接。"
    except Exception as e:
        _logger.error("创建链接失败: %s", e)
        return f"创建问题链接失败: {str(e)}"


@tool
def get_issue_transitions(issue_key: str = "") -> str:
    """
    获取指定 Issue 当前可用的状态转换列表。
    参数：issue_key - 任务KEY（如 KO-29）
    返回 JSON 字符串，包含可用的转换目标和状态。
    """
    try:
        key = extract_issue_key(issue_key)
        if not key:
            return json.dumps({"error": "请提供有效的任务Key（如 KO-29）"}, ensure_ascii=False)
        _logger.info("获取状态转换: %s", key)
        transitions = jira.get_issue_transitions(key)
        if not transitions:
            return json.dumps({"issue_key": key, "transitions": [], "message": "当前没有可用的状态转换"}, ensure_ascii=False)
        return json.dumps({
            "issue_key": key,
            "transitions": [{"id": t["id"], "name": t["name"], "to_status": t["to"]} for t in transitions]
        }, ensure_ascii=False, indent=2)
    except Exception as e:
        _logger.error("获取状态转换失败 %s: %s", issue_key, e)
        return json.dumps({"error": str(e)}, ensure_ascii=False)


@tool
def update_issue(issue_key: str = "", summary: str = None, description: str = None,
                 priority: str = None, additional_fields: dict = None) -> str:
    """
    更新已有 Issue 的字段值（摘要、描述、优先级、自定义字段等）。
    参数：
      issue_key - 任务KEY（必填）
      summary - 新的摘要（可选）
      description - 新的描述（可选）
      priority - 新的优先级名称（可选，如 Medium、High、Low）
      additional_fields - 其他自定义字段字典（可选，如 {"customfield_xxxxx": "值"}）
    """
    if not issue_key:
        return "更新失败：必须提供 issue_key。"
    try:
        key = extract_issue_key(issue_key)
        if not key:
            return "更新失败：请提供有效的任务Key（如 KO-29）。"

        fields = {}
        if summary is not None:
            fields["summary"] = summary
        if description is not None:
            fields["description"] = {
                "type": "doc",
                "version": 1,
                "content": [{"type": "paragraph", "content": [{"type": "text", "text": description}]}]
            }
        if priority is not None:
            fields["priority"] = {"name": priority}
        if additional_fields:
            processed = {}
            for k, v in additional_fields.items():
                if k.startswith("customfield") and isinstance(v, str):
                    processed[k] = {"value": v}
                else:
                    processed[k] = v
            fields.update(processed)

        if not fields:
            return "更新失败：至少需要提供一个待更新的字段。"

        _logger.info("更新Issue字段: %s", key)
        jira.update_issue_field(key, fields)
        updated_fields = ", ".join(k for k in fields.keys())
        return f"✅ 任务 {key} 更新成功！\n已更新字段: {updated_fields}"
    except Exception as e:
        error_msg = str(e)
        _logger.error("更新失败 %s: %s", issue_key, error_msg)
        return f"更新任务失败: {error_msg}"


@tool
def add_issue_comment(issue_key: str = "", comment: str = "") -> str:
    """
    给指定 Issue 添加评论。
    参数：
      issue_key - 任务KEY（必填）
      comment - 评论内容（必填）
    """
    if not issue_key or not comment:
        return "添加评论失败：必须提供 issue_key 和 comment。"
    try:
        key = extract_issue_key(issue_key)
        if not key:
            return "添加评论失败：请提供有效的任务Key。"
        _logger.info("添加评论: %s", key)
        jira.add_comment(key, comment)
        return f"✅ 已成功为 {key} 添加评论。"
    except Exception as e:
        _logger.error("添加评论失败 %s: %s", issue_key, e)
        return f"添加评论失败: {str(e)}"


@tool
def add_issue_worklog(issue_key: str = "", time_spent: str = "", comment: str = None,
                      started: str = None) -> str:
    """
    给指定 Issue 记录工时。
    参数：
      issue_key - 任务KEY（必填）
      time_spent - 花费时间，使用可读格式如 "2h"、"30m"、"1d 2h"（必填）
      comment - 工作描述（可选）
      started - 开始时间，格式 "2026-06-08T10:00:00.000+0800"（可选，默认为当前时间）
    """
    if not issue_key or not time_spent:
        return "记录工时失败：必须提供 issue_key 和 time_spent。"
    try:
        key = extract_issue_key(issue_key)
        if not key:
            return "记录工时失败：请提供有效的任务Key。"
        _logger.info("记录工时: %s %s", key, time_spent)
        jira.add_worklog(key, time_spent, comment=comment, started=started)
        msg = f"✅ 已成功为 {key} 记录工时: {time_spent}"
        if comment:
            msg += f"\n工作描述: {comment}"
        return msg
    except Exception as e:
        _logger.error("记录工时失败 %s: %s", issue_key, e)
        return f"记录工时失败: {str(e)}"


@tool
def batch_create_issues(issues_json: str = "") -> str:
    """
    批量创建多个 Jira 任务。一次调用可创建多个任务（支持 Sub-task、Epic关联等）。
    参数 issues_json：JSON 字符串，包含 tasks 数组，每个 task 的结构与 create_issue 一致。
    
    issues_json 格式示例：
    {
      "tasks": [
        {
          "project_key": "KO",
          "summary": "任务1",
          "issue_type": "Task",
          "description": "描述1",
          "parent_key": null,
          "additional_fields": {}
        },
        {
          "project_key": "KO",
          "summary": "任务2",
          "issue_type": "Sub-task",
          "parent_key": "KO-100"
        }
      ]
    }
    """
    if not issues_json:
        return "批量创建失败：请提供 issues_json 参数。"
    try:
        data = json.loads(issues_json)
        tasks = data.get("tasks", [])
        if not tasks:
            return "批量创建失败：tasks 列表为空。"
        
        results = []
        success_count = 0
        fail_count = 0
        
        for i, task in enumerate(tasks):
            project_key = task.get("project_key", "")
            summary = task.get("summary", "")
            issue_type = task.get("issue_type", "")
            description = task.get("description", "")
            parent_key = task.get("parent_key")
            epic_link_key = task.get("epic_link_key")
            additional_fields = task.get("additional_fields")
            
            if not project_key or not summary or not issue_type:
                results.append(f"  第{i+1}个任务: ❌ 缺少必填字段 (project_key/summary/issue_type)")
                fail_count += 1
                continue
            
            try:
                # 复用 create_issue 的字段构建逻辑
                fields = {
                    "project": {"key": project_key},
                    "summary": summary,
                    "issuetype": {"name": issue_type}
                }
                if description:
                    fields["description"] = {
                        "type": "doc",
                        "version": 1,
                        "content": [{"type": "paragraph", "content": [{"type": "text", "text": description}]}]
                    }
                if parent_key:
                    fields["parent"] = {"key": parent_key}
                if epic_link_key and Config.EPIC_LINK_FIELD_ID:
                    if issue_type.lower() == "sub-task":
                        results.append(f"  第{i+1}个任务: ❌ {summary} - Epic 不能直接关联 Sub-task")
                        fail_count += 1
                        continue
                    fields[Config.EPIC_LINK_FIELD_ID] = epic_link_key
                if additional_fields:
                    processed = {}
                    for k, v in additional_fields.items():
                        if k.startswith("customfield") and isinstance(v, str):
                            processed[k] = {"value": v}
                        else:
                            processed[k] = v
                    fields.update(processed)
                
                new_issue = jira.create_issue(fields=fields)
                issue_key = new_issue.get("key")
                results.append(f"  第{i+1}个任务: ✅ {issue_key} - {summary}")
                success_count += 1
            except Exception as e:
                error_msg = str(e)
                # 友好化常见错误
                friendly = None
                if "Operation value must be a string" in error_msg:
                    friendly = f"可能的必填字段缺失（如 Role Name），请通过 additional_fields 补充。"
                elif "Role Name is required" in error_msg:
                    friendly = f"缺少必填字段 Role Name，请在 additional_fields 中设置。"
                elif "cannot be set" in error_msg.lower() and "not on the appropriate screen" in error_msg.lower():
                    friendly = f"字段ID错误或不在创建界面上，请检查字段ID是否正确。"
                if friendly:
                    results.append(f"  第{i+1}个任务: ❌ {summary} - {friendly}")
                else:
                    results.append(f"  第{i+1}个任务: ❌ {summary} - {error_msg}")
                fail_count += 1
        
        summary_text = f"批量创建完成！成功: {success_count}, 失败: {fail_count}"
        return f"{summary_text}\n" + "\n".join(results)
    except json.JSONDecodeError:
        return f"批量创建失败：issues_json 格式无效，请提供有效的 JSON 字符串。"
    except Exception as e:
        _logger.error("批量创建失败: %s", e)
        return f"批量创建失败: {str(e)}"


@tool
def search_issues(query: str = "", project: str = "", status: str = "",
                  assignee: str = "", priority: str = "", issue_type: str = "",
                  max_results: int = 20) -> str:
    """
    搜索 Jira 任务，支持按项目、状态、负责人、优先级、问题类型等条件筛选。
    所有筛选条件均为可选，会通过 AND 组合查询。
    
    参数：
      query - 搜索关键词（会在摘要中搜索）（可选）
      project - 项目KEY筛选（可选，如 KO）
      status - 状态筛选（可选，如 "In Progress", "Done"）
      assignee - 负责人筛选（可选，用户名或 "currentUser()"）
      priority - 优先级筛选（可选，如 High, Medium, Low）
      issue_type - 问题类型筛选（可选，如 Task, Sub-task, Risk）
      max_results - 最大返回条数（默认 20，最大 50）
    
    返回 JSON 字符串，包含匹配的任务列表。
    """
    try:
        jql_parts = []
        
        if project:
            jql_parts.append(f"project = {project}")
        if status:
            jql_parts.append(f'status = "{status}"')
        if assignee:
            if assignee.lower() == "currentUser()" or assignee.lower() == "me":
                jql_parts.append("assignee = currentUser()")
            else:
                jql_parts.append(f'assignee = "{assignee}"')
        if priority:
            jql_parts.append(f'priority = "{priority}"')
        if issue_type:
            jql_parts.append(f'issuetype = "{issue_type}"')
        if query:
            jql_parts.append(f'summary ~ "{query}"')
        
        if not jql_parts:
            return json.dumps({"error": "请至少提供一个搜索条件。"}, ensure_ascii=False)
        
        jql_query = " AND ".join(jql_parts) + " ORDER BY updated DESC"
        
        _logger.info("搜索任务: %s", jql_query)
        issues = fetch_all_issues(jira, jql_query, Config.JQL_PAGE_SIZE)
        
        max_count = min(max_results, 50)
        tasks = [_build_task_dict(issue) for issue in issues[:max_count] if issue]
        
        return json.dumps({
            "success": True,
            "jql": jql_query,
            "total": len(issues),
            "returned": len(tasks),
            "tasks": tasks
        }, ensure_ascii=False, indent=2)
    except Exception as e:
        _logger.error("搜索任务失败: %s", e)
        return json.dumps({"error": str(e)}, ensure_ascii=False)


@tool
def assign_issue(issue_key: str = "", assignee: str = "") -> str:
    """
    将 Jira 任务分配给指定用户。
    参数：
      issue_key - 任务KEY（必填）
      assignee - 用户名（必填），对于 Jira Server 使用用户名，例如 "zhangsan"
    """
    if not issue_key or not assignee:
        return "分配失败：必须提供 issue_key 和 assignee。"
    try:
        key = extract_issue_key(issue_key)
        if not key:
            return "分配失败：请提供有效的任务Key。"
        
        _logger.info("分配任务: %s -> %s", key, assignee)
        jira.assign_issue(key, assignee)
        return f"✅ 已将 {key} 分配给 {assignee}。"
    except Exception as e:
        _logger.error("分配失败 %s: %s", issue_key, e)
        return f"分配任务失败: {str(e)}"


@tool
def delete_issue(issue_key: str = "", delete_subtasks: bool = True, confirmed: bool = False) -> str:
    """
    删除指定的 Jira Issue。
    警告：此操作不可逆，请谨慎使用！
    
    参数：
      issue_key - 要删除的任务KEY（必填）
      delete_subtasks - 如果该 Issue 有子任务，是否一并删除（默认 True，设为 False 则删除失败）
      confirmed - 是否确认删除（默认 False）。当用户回复"确认删除 XXX"时，将 confirmed 设为 True 再调用。
    """
    if not issue_key:
        return "删除失败：必须提供 issue_key。"
    try:
        key = extract_issue_key(issue_key)
        if not key:
            return "删除失败：请提供有效的任务Key。"
        
        if not confirmed:
            _logger.warning("用户请求删除Issue: %s (delete_subtasks=%s)", key, delete_subtasks)
            return f"⚠️ 删除操作有风险，此操作不可逆！请确认：(回复「确认删除 {key}」以继续)"
        
        # confirmed=True，执行删除
        _logger.warning("用户确认删除Issue: %s", key)
        jira.delete_issue(key, delete_subtasks=delete_subtasks)
        _logger.info("已删除Issue: %s", key)
        return f"✅ 已成功删除 {key}。"
    except Exception as e:
        _logger.error("删除失败 %s: %s", issue_key, e)
        return f"删除失败: {str(e)}"