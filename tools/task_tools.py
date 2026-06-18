"""任务查询与创建工具"""
import json
import re
import os
import logging
from langchain.tools import tool
from config import Config
from utils import fetch_all_issues, validate_project_key, extract_issue_key
from ._lazy import LazyJira
from .task_common import (
    build_issue_fields,
    build_task_dict,
    process_additional_fields,
)

_logger = logging.getLogger("jira_bot.task_tools")
jira = LazyJira()

# 创建元数据缓存（project_key:issue_type_name → JSON 字符串）
_create_meta_cache: dict = {}

def _resolve_fields_via_meta(additional_fields: dict, project_key: str) -> dict:
    """通过项目元数据查找字段显示名 → customfield ID，不使用全局别名"""
    if not additional_fields or not project_key:
        return process_additional_fields(additional_fields)  # 没项目KEY时回退全局别名
    processed = {}
    try:
        meta_str = _get_create_meta_cached(project_key)
        meta = json.loads(meta_str)
        if meta.get("success"):
            # 建立显示名（小写）→ field_key 的映射
            name_to_key = {}
            for it in meta["data"]["issue_types"]:
                for f in it.get("optional_fields", []) + it.get("required_fields", []):
                    fname = f.get("name", "").lower().strip()
                    fkey = f.get("key", "")
                    if fname and fkey.startswith("customfield_"):
                        name_to_key[fname] = fkey
            # 用显示名匹配
            for k, v in additional_fields.items():
                norm = k.lower().strip()
                if norm in name_to_key:
                    processed[name_to_key[norm]] = v
                elif k.startswith("customfield_"):
                    processed[k] = v
                # 不在元数据中的字段名 → 跳过
    except Exception:
        pass
    # 元数据查找失败或没匹配到，回退全局别名
    if not processed:
        processed = process_additional_fields(additional_fields)
    return processed


def _get_create_meta_cached(project_key: str) -> str:
    """内部：获取项目元数据（带缓存），供 update_issue 等工具查找字段 ID"""
    cache_key = f"{project_key}:"
    if cache_key in _create_meta_cache:
        return _create_meta_cache[cache_key]
    result = get_create_issue_metadata(project_key)
    # 缓存结果（get_create_issue_metadata 内部也会缓存，但只缓存自己的调用）
    _create_meta_cache[cache_key] = result
    return result


def _get_required_fields(project_key: str, issue_type: str) -> list:
    """从缓存的元数据中提取指定项目+问题类型的必填字段名列表。

    如果缓存中无数据，返回 None（表示需要先调用 get_create_issue_metadata）。
    """
    cache_key = f"{project_key}:{issue_type}"
    raw = _create_meta_cache.get(cache_key)
    if raw is None:
        # 也尝试查不带 issue_type 的缓存
        raw = _create_meta_cache.get(f"{project_key}:")
    if raw is None:
        return None

    try:
        meta = json.loads(raw)
        data = meta.get("data", {})
        for it in data.get("issue_types", []):
            if it.get("name", "").lower() == issue_type.lower():
                return [f["name"] for f in it.get("required_fields", [])]
    except (json.JSONDecodeError, KeyError):
        pass
    return []


# ── 查询工具 ──────────────────────────────────────────────

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
        tasks = [build_task_dict(issue) for issue in issues[:max_count] if issue]

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
        tasks = [build_task_dict(issue) for issue in issues[:max_count] if issue]

        _logger.info("项目 %s 任务: 共 %d 条，返回 %d 条", key, len(issues), len(tasks))
        return json.dumps(
            {"success": True, "project": key, "total": len(issues), "returned": len(tasks), "tasks": tasks},
            ensure_ascii=False, indent=2
        )
    except Exception as e:
        _logger.error("获取项目任务失败 %s: %s", project_key, e)
        return json.dumps({"error": str(e)}, ensure_ascii=False)


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
      max_results - 最大返回条数（默认 20，受 Config.MAX_TASKS_PER_TOOL 限制）

    返回 JSON 字符串，包含匹配的任务列表及 truncated 字段（是否被截断）。
    """
    try:
        jql_parts = []

        if project:
            jql_parts.append(f"project = {project}")
        if status:
            jql_parts.append(f'status = "{status}"')
        if assignee:
            if assignee.lower() == "currentuser()" or assignee.lower() == "me":
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

        max_count = min(max_results, Config.MAX_TASKS_PER_TOOL)
        tasks = [build_task_dict(issue) for issue in issues[:max_count] if issue]

        return json.dumps({
            "success": True,
            "jql": jql_query,
            "total": len(issues),
            "returned": len(tasks),
            "tasks": tasks,
            "truncated": len(issues) > max_count,
        }, ensure_ascii=False, indent=2)
    except Exception as e:
        _logger.error("搜索任务失败: %s", e)
        return json.dumps({"error": str(e)}, ensure_ascii=False)


# ── 创建 / 更新 / 写入类工具 ──────────────────────────────

@tool
def get_create_issue_metadata(project_key: str = "", issue_type_name: str = None) -> str:
    """
    获取在指定项目中创建问题的元数据，包括可用的问题类型及其必填/可选字段。
    参数：project_key - 项目KEY，issue_type_name - 可选，按名称过滤问题类型
    结果会被缓存，同一项目+类型的组合不会重复请求 Jira API。
    """
    try:
        key = validate_project_key(project_key)
        cache_key = f"{key}:{issue_type_name or ''}"

        # 命中缓存则直接返回
        if cache_key in _create_meta_cache:
            _logger.debug("命中创建元数据缓存: %s", cache_key)
            return _create_meta_cache[cache_key]

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

        result = json.dumps({"success": True, "data": result}, ensure_ascii=False, indent=2)
        _create_meta_cache[cache_key] = result
        return result
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

        fields, err = build_issue_fields(
            key, summary, issue_type, description, parent_key, epic_link_key, additional_fields,
        )
        if err:
            # build_issue_fields 已经把 "Epic 不能直接关联 Sub-task" 这类业务错误封装好
            return f"创建失败: {err}"

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

        # 尝试从缓存的元数据中获取必填字段列表，给出更有用的提示
        required_fields = _get_required_fields(key, issue_type)
        if required_fields:
            return (f"创建失败: {error_msg}\n\n"
                    f"💡 该问题类型 ({issue_type}) 的必填字段为: {', '.join(required_fields)}。\n"
                    f"请将这些字段的值通过 additional_fields 参数传入，格式如：\n"
                    f'  additional_fields={{"字段名": "值", "另一个字段": "值"}}\n\n'
                    f"如果字段名是自定义字段ID（如 customfield_xxxxx），请先调用 "
                    f"get_create_issue_metadata('{project_key}', '{issue_type}') 查询字段映射。")
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
                 priority: str = None, additional_fields: dict = None,
                 project_key: str = "") -> str:
    """
    更新已有 Issue 的字段值（摘要、描述、优先级、自定义字段等）。
    参数：
      issue_key - 任务KEY（必填）
      summary - 新的摘要（可选）
      description - 新的描述（可选）
      priority - 新的优先级名称（可选，如 Medium、High、Low）
      additional_fields - 其他自定义字段字典（可选）。
        支持 "Target start" / "Target end" 等显示名，会自动映射字段 ID。
        也支持 customfield ID 直接传入。
      project_key - 项目KEY（可选，传了可以更精确地通过项目元数据查找字段 ID）
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

        # 处理 additional_fields，如果传了 project_key 则通过项目元数据辅助查找
        if project_key:
            processed = _resolve_fields_via_meta(additional_fields, project_key)
        else:
            processed = process_additional_fields(additional_fields)

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
    批量创建多个 Jira 任务（使用 Jira bulk API，每次最多 50 条并发提交）。
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

        # 先做逐条校验，把合法任务的 fields 收集起来，非法任务直接进失败列表
        fields_list = []           # 真正要提交到 bulk 的 fields
        task_index_in_batch = []   # 与 fields_list 一一对应的原 tasks 下标
        results = [""] * len(tasks)
        fail_count = 0

        for i, task in enumerate(tasks):
            project_key = task.get("project_key", "")
            summary = task.get("summary", "")
            issue_type = task.get("issue_type", "")
            description = task.get("description", "")
            parent_key = task.get("parent_key")
            epic_link_key = task.get("epic_link_key")
            additional_fields = task.get("additional_fields")

            try:
                pk = validate_project_key(project_key)
            except ValueError as e:
                results[i] = f"  第{i+1}个任务: ❌ {summary or '(无标题)'} - {e}"
                fail_count += 1
                continue

            fields, err = build_issue_fields(
                pk, summary, issue_type, description, parent_key, epic_link_key, additional_fields
            )
            if err:
                results[i] = f"  第{i+1}个任务: ❌ {summary or '(无标题)'} - {err}"
                fail_count += 1
                continue

            fields_list.append(fields)
            task_index_in_batch.append(i)

        success_count = 0
        if fields_list:
            bulk_resp = jira.bulk_create_issues(fields_list)
            created_issues = bulk_resp.get("created", [])
            errors = bulk_resp.get("errors", [])

            # 用 errors 里的 index 反查原 tasks 下标
            err_by_index = {}
            for e in errors:
                idx = e.get("index")
                if idx is not None and 0 <= idx < len(task_index_in_batch):
                    err_by_index[task_index_in_batch[idx]] = e

            for j, orig_i in enumerate(task_index_in_batch):
                if j < len(created_issues) and orig_i not in err_by_index:
                    it = created_issues[j] or {}
                    issue_key = it.get("key") or it.get("id") or "?"
                    summary = tasks[orig_i].get("summary", "")
                    results[orig_i] = f"  第{orig_i+1}个任务: ✅ {issue_key} - {summary}"
                    success_count += 1
                else:
                    err = err_by_index.get(orig_i, {})
                    err_text = (err.get("error") or err.get("errorMessages") or "未知错误")
                    if isinstance(err_text, list):
                        err_text = "; ".join(str(x) for x in err_text)
                    friendly = None
                    err_lc = str(err_text).lower()
                    if "operation value must be a string" in err_lc:
                        friendly = "可能的必填字段缺失（如 Role Name），请通过 additional_fields 补充。"
                    elif "role name is required" in err_lc:
                        friendly = "缺少必填字段 Role Name，请在 additional_fields 中设置。"
                    elif "not on the appropriate screen" in err_lc:
                        friendly = "字段ID错误或不在创建界面上，请检查字段ID是否正确。"
                    summary = tasks[orig_i].get("summary", "")
                    results[orig_i] = f"  第{orig_i+1}个任务: ❌ {summary} - {friendly or err_text}"
                    fail_count += 1

        summary_text = f"批量创建完成！成功: {success_count}, 失败: {fail_count}"
        return summary_text + "\n" + "\n".join(r for r in results if r)
    except json.JSONDecodeError:
        return f"批量创建失败：issues_json 格式无效，请提供有效的 JSON 字符串。"
    except Exception as e:
        _logger.error("批量创建失败: %s", e)
        return f"批量创建失败: {str(e)}"


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


@tool
def batch_delete_issues(issues_json: str = "", delete_subtasks: bool = True, confirmed: bool = False) -> str:
    """
    批量删除多个 Jira Issue。
    警告：此操作不可逆，请谨慎使用！

    参数：
      issues_json - JSON 字符串，包含 issue_keys 数组。格式示例：
        {"issue_keys": ["KO-100", "KO-101", "KO-102"]}
      delete_subtasks - 是否一并删除子任务（默认 True）
      confirmed - 是否确认删除（默认 False）。当用户回复"确认批量删除"时，将 confirmed 设为 True。

    流程：
      1. 先以 confirmed=False 调用，系统会列出待删除的 issue 列表让用户确认。
      2. 用户确认后，再以 confirmed=True 调用执行删除。
      3. 返回每条删除结果（成功/失败），单条失败不影响其他。
    """
    if not issues_json:
        return "批量删除失败：请提供 issues_json 参数。"

    try:
        data = json.loads(issues_json)
        issue_keys = data.get("issue_keys", [])
        if not issue_keys:
            return "批量删除失败：issue_keys 列表为空。"

        # 第一步：确认阶段
        if not confirmed:
            keys_preview = ", ".join(issue_keys[:10])
            more = f" ... 还有 {len(issue_keys) - 10} 个" if len(issue_keys) > 10 else ""
            _logger.warning("用户请求批量删除 %d 个 Issue: %s", len(issue_keys), keys_preview)
            return (
                f"⚠️ 批量删除操作有风险，此操作不可逆！\n"
                f"待删除: {keys_preview}{more}（共 {len(issue_keys)} 个）\n"
                f"请确认后回复「确认批量删除」以继续。"
            )

        # 第二步：执行删除
        _logger.warning("用户确认批量删除 %d 个 Issue", len(issue_keys))
        results = []
        success = 0
        fail = 0

        for raw_key in issue_keys:
            key = extract_issue_key(str(raw_key).strip())
            if not key:
                results.append(f"  ❌ {raw_key} - 无效的 Issue Key")
                fail += 1
                continue
            try:
                jira.delete_issue(key, delete_subtasks=delete_subtasks)
                results.append(f"  ✅ {key} - 已删除")
                success += 1
                _logger.info("批量删除: %s 已删除", key)
            except Exception as e:
                results.append(f"  ❌ {key} - {e}")
                fail += 1
                _logger.error("批量删除 %s 失败: %s", key, e)

        summary = f"📊 批量删除完成！成功: {success}, 失败: {fail}"
        return summary + "\n" + "\n".join(results)

    except json.JSONDecodeError:
        return "批量删除失败：issues_json 格式无效，请提供有效的 JSON 字符串。"
    except Exception as e:
        _logger.error("批量删除失败: %s", e)
        return f"批量删除失败: {str(e)}"


@tool
def import_from_excel(file_path: str = "", project_key: str = "",
                      summary_col: str = "", issue_type_col: str = "",
                      start_date_col: str = "", end_date_col: str = "",
                      sheet_name: str = "Sheet1", header_row: int = 0,
                      dry_run: bool = False) -> str:
    """
    从 Excel (.xlsx) 文件导入并批量创建 Jira 任务（使用 Jira bulk API，≤50 条/批）。
    自动解析列内容，建议提供列名映射以准确识别。

    参数：
      file_path - Excel 文件的完整路径（必填）
      project_key - 目标项目 KEY（必填）
      summary_col - 标题列的列名（可选，AI 会自动识别）
      issue_type_col - 问题类型列的列名（可选）
      start_date_col - 开始日期列的列名（可选）
      end_date_col - 结束日期列的列名（可选）
      sheet_name - 工作表名称，默认 Sheet1
      header_row - 表头行号，默认 0（第一行）
      dry_run - 预览模式（默认 False）。True 时只解析并返回待创建任务列表，不写 Jira。
               建议流程：先用 dry_run=True 让用户确认内容，再调一次 dry_run=False 执行创建。
    """
    import pandas as pd
    from datetime import datetime, date

    if not file_path or not project_key:
        return "导入失败：必须提供 file_path 和 project_key。"
    if not os.path.exists(file_path):
        return f"导入失败：文件不存在 - {file_path}"

    try:
        df = pd.read_excel(file_path, sheet_name=sheet_name, header=header_row)
        df = df.dropna(how="all").reset_index(drop=True)
        if df.empty:
            return "导入失败：Excel 文件为空。"

        headers = list(df.columns)
        _logger.info("Excel 列名: %s", headers)

        # 智能列名映射
        def find_col(candidates, col_hint=""):
            if col_hint and col_hint in headers:
                return col_hint
            for h in headers:
                h_lower = str(h).lower()
                for c in candidates:
                    if c in h_lower:
                        return h
            return None

        summary_col_found = find_col(["summary", "task", "title", "标题", "任务", "任务名称", "task name", "name"], summary_col)
        type_col_found = find_col(["issue type", "issuetype", "type", "问题类型", "类型", "issue_type"], issue_type_col)
        start_col_found = find_col(["start date", "start_date", "start", "开始日期", "开始时间", "开始", "target start"], start_date_col)
        end_col_found = find_col(["end date", "end_date", "end", "due date", "结束日期", "结束时间", "结束", "截止", "target end"], end_date_col)

        if not summary_col_found:
            # 用第一列兜底
            summary_col_found = headers[0]
            _logger.warning("未找到标题列，默认使用第一列: %s", summary_col_found)

        parsed_tasks = []  # [(row_index, fields_or_error)]
        for idx, row in df.iterrows():
            summary = str(row.get(summary_col_found, "")).strip()
            if pd.isna(summary) or not summary or summary == "nan":
                continue

            # 确定 issue_type
            issue_type = "Task"
            if type_col_found:
                raw_type = row.get(type_col_found, "")
                if pd.notna(raw_type):
                    raw_type = str(raw_type).strip()
                    if raw_type.lower() in ["sub-task", "subtask", "子任务", "子任务"]:
                        issue_type = "Sub-task"
                    elif raw_type.lower() in ["epic", "史诗"]:
                        issue_type = "Epic"
                    elif raw_type.lower() in ["risk", "风险"]:
                        issue_type = "Risk"
                    # 其他保持默认 Task

            # 构建 additional_fields
            additional = {}
            if start_col_found:
                val = row.get(start_col_found)
                if pd.notna(val):
                    if isinstance(val, (datetime, date)):
                        additional[Config.TARGET_START_FIELD] = val.strftime("%Y-%m-%d")
                    else:
                        additional[Config.TARGET_START_FIELD] = str(val).strip()
            if end_col_found:
                val = row.get(end_col_found)
                if pd.notna(val):
                    if isinstance(val, (datetime, date)):
                        additional[Config.TARGET_END_FIELD] = val.strftime("%Y-%m-%d")
                    else:
                        additional[Config.TARGET_END_FIELD] = str(val).strip()

            fields, err = build_issue_fields(
                project_key, summary, issue_type, "", None, None,
                additional if additional else None,
            )
            parsed_tasks.append((idx, summary, issue_type, fields, err))

        valid = [t for t in parsed_tasks if t[4] is None and t[3] is not None]
        invalid = [t for t in parsed_tasks if t[4] is not None]

        if not valid and not invalid:
            return "导入失败：Excel 中没有有效的任务数据。"

        # ── Dry-run 预览：不写 Jira，把待创建清单返回 ──
        if dry_run:
            preview = []
            for _, summary, issue_type, fields, _ in valid:
                preview.append({
                    "project_key": project_key,
                    "summary": summary,
                    "issue_type": issue_type,
                    "additional_fields": fields,
                })
            payload = {
                "dry_run": True,
                "total_rows": len(parsed_tasks),
                "to_create": len(preview),
                "invalid": len(invalid),
                "invalid_reasons": [
                    {"row": int(t[0]) + 2, "summary": t[1], "reason": t[4]} for t in invalid
                ],
                "tasks": preview,
            }
            msg = (
                f"🔍 [DRY-RUN] 共解析 {len(parsed_tasks)} 行，"
                f"待创建 {len(preview)} 条，非法 {len(invalid)} 条。\n"
                f"⚠️ 尚未写入 Jira。请向用户确认无误后，"
                f"再以 dry_run=False 重新调用一次。"
            )
            return msg + "\n" + json.dumps(payload, ensure_ascii=False, indent=2)

        # ── 实际写入 Jira：bulk API（≤50/片） ──
        fields_list = [t[3] for t in valid]
        bulk_resp = jira.bulk_create_issues(fields_list)
        created_issues = bulk_resp.get("created", [])
        errors = bulk_resp.get("errors", [])

        # 用 errors.index 反查 valid 列表
        err_by_valid_idx = {e.get("index"): e for e in errors if e.get("index") is not None}

        details = []
        success_count = 0
        fail_count = 0

        for j, (idx, summary, issue_type, fields, err) in enumerate(valid):
            if j in err_by_valid_idx:
                e = err_by_valid_idx[j]
                err_text = e.get("error") or e.get("errorMessages") or "未知错误"
                if isinstance(err_text, list):
                    err_text = "; ".join(str(x) for x in err_text)
                details.append(f"  ❌ 第{int(idx)+2}行 {summary} - {err_text}")
                fail_count += 1
            elif j < len(created_issues):
                it = created_issues[j] or {}
                issue_key = it.get("key") or "?"
                details.append(f"  ✅ {issue_key} - {summary}")
                success_count += 1
            else:
                details.append(f"  ❌ 第{int(idx)+2}行 {summary} - 未返回结果")
                fail_count += 1

        for idx, summary, issue_type, fields, err in invalid:
            details.append(f"  ❌ 第{int(idx)+2}行 {summary} - {err}")
            fail_count += 1

        header = f"📊 Excel 导入完成！共 {len(parsed_tasks)} 行，成功: {success_count}, 失败: {fail_count}"
        return header + "\n" + "\n".join(details)

    except ImportError:
        return "导入失败：缺少 pandas 或 openpyxl 库，请运行 pip install pandas openpyxl。"
    except Exception as e:
        _logger.error("Excel导入失败: %s", e)
        return f"导入失败: {str(e)}"


@tool
def batch_update_dates(updates_json: str = "") -> str:
    """
    批量更新多个 Jira 任务的开始日期和结束日期（用于维护 Jira Plan 时间线）。

    参数 updates_json：JSON 字符串（或直接传 dict 对象），包含 updates 数组。

    格式示例（简洁模式）：
    {"updates": [{"issue_key": "KO-29", "start_date": "2025-06-01", "end_date": "2025-06-15"}]}

    也支持 fields 模式（使用显示名，自动映射 customfield ID）：
    {"updates": [{"issue_key": "KO-29", "fields": {"Target start": "2026-06-20", "Target end": "2026-06-25"}}]}

    说明：
      - issue_key 必填
      - start_date 和 end_date 至少提供一个，格式 YYYY-MM-DD
      - 如果使用 fields 模式，支持 "Target start"、"Target end"、"开始日期" 等别名
      - 两种模式二选一，如果同时提供，fields 优先
    """
    if not updates_json:
        return "批量更新失败：请提供 updates_json 参数。"
    try:
        if isinstance(updates_json, str):
            data = json.loads(updates_json)
        elif isinstance(updates_json, dict):
            data = updates_json
        else:
            return "批量更新失败：updates_json 应为 JSON 字符串或 dict 对象。"
        updates = data.get("updates", [])
        if not updates:
            return "批量更新失败：updates 列表为空。"

        results = []
        success_count = 0
        fail_count = 0

        for i, item in enumerate(updates):
            issue_key = item.get("issue_key", "").strip()
            if not issue_key:
                results.append(f"  第{i+1}项: ❌ 缺少 issue_key")
                fail_count += 1
                continue

            try:
                key = extract_issue_key(issue_key)
                if not key:
                    results.append(f"  第{i+1}项: ❌ 无效的 issue_key: {issue_key}")
                    fail_count += 1
                    continue

                fields_to_update = {}

                # fields 模式（显示名 → customfield 自动映射）
                raw_fields = item.get("fields")
                if raw_fields and isinstance(raw_fields, dict):
                    # 从 issue_key 提取项目KEY（如 EDE-67 → EDE），用于元数据查找
                    proj = key.split("-")[0] if "-" in key else ""
                    fields_to_update.update(_resolve_fields_via_meta(raw_fields, proj))
                else:
                    # 兼容旧模式：start_date / end_date
                    start_date = item.get("start_date")
                    end_date = item.get("end_date")
                    if start_date:
                        fields_to_update[Config.TARGET_START_FIELD] = start_date
                    if end_date:
                        fields_to_update[Config.TARGET_END_FIELD] = end_date

                if not fields_to_update:
                    results.append(f"  第{i+1}项: ❌ {key} - 未提供日期字段")
                    fail_count += 1
                    continue

                jira.update_issue_field(key, fields_to_update)
                changes = [f"{k}={v}" for k, v in fields_to_update.items()]
                results.append(f"  第{i+1}项: ✅ {key} - {'; '.join(changes)}")
                success_count += 1

            except Exception as e:
                results.append(f"  第{i+1}项: ❌ {issue_key} - {str(e)}")
                fail_count += 1

        summary_text = f"批量更新完成！成功: {success_count}, 失败: {fail_count}"
        return f"{summary_text}\n" + "\n".join(results)

    except json.JSONDecodeError:
        return f"批量更新失败：updates_json 格式无效，请提供有效的 JSON 字符串。"
    except Exception as e:
        _logger.error("批量更新日期失败: %s", e)
        return f"批量更新失败: {str(e)}"


@tool
def batch_update_issues(updates_json: str = "") -> str:
    """
    批量更新多个 Jira 任务的负责人、状态、优先级。
    一次调用可同时改多个字段，逐条执行，单条失败不影响其他。

    参数 updates_json：JSON 字符串，包含 updates 数组。

    格式示例：
    {"updates": [
        {"issue_key": "KO-1", "assignee": "张三", "status": "In Progress", "priority": "High"},
        {"issue_key": "KO-2", "assignee": "李四"},
        {"issue_key": "KO-3", "status": "Done"}
    ]}

    说明：
      - issue_key 必填
      - assignee / status / priority 均为可选，至少提供一个
      - status 为目标状态名称（如 "In Progress"、"Done"），会自动查找可用转换
      - priority 为优先级名称（如 "High"、"Medium"、"Low"）
    """
    if not updates_json:
        return "批量更新失败：请提供 updates_json 参数。"
    try:
        if isinstance(updates_json, str):
            data = json.loads(updates_json)
        elif isinstance(updates_json, dict):
            data = updates_json
        else:
            return "批量更新失败：updates_json 应为 JSON 字符串或 dict 对象。"
        updates = data.get("updates", [])
        if not updates:
            return "批量更新失败：updates 列表为空。"

        results = []
        success_count = 0
        fail_count = 0

        for i, item in enumerate(updates):
            issue_key = (item.get("issue_key") or "").strip()
            if not issue_key:
                results.append(f"  第{i+1}项: ❌ 缺少 issue_key")
                fail_count += 1
                continue

            try:
                key = extract_issue_key(issue_key)
                if not key:
                    results.append(f"  第{i+1}项: ❌ 无效的 issue_key: {issue_key}")
                    fail_count += 1
                    continue

                changes = []
                has_work = False

                # 1) 分配负责人
                assignee = item.get("assignee")
                if assignee and str(assignee).strip():
                    has_work = True
                    try:
                        jira.assign_issue(key, str(assignee).strip())
                        changes.append(f"负责人→{assignee}")
                    except Exception as e:
                        results.append(f"  第{i+1}项: ❌ {key} - 分配失败: {e}")
                        fail_count += 1
                        continue

                # 2) 转换状态
                status = item.get("status")
                if status and str(status).strip():
                    has_work = True
                    target_status = str(status).strip()
                    try:
                        jira.transition_issue(key, target_status)
                        changes.append(f"状态→{target_status}")
                    except Exception as e:
                        _logger.warning("状态转换失败 %s -> %s: %s", key, target_status, e)
                        results.append(f"  第{i+1}项: ❌ {key} - 状态转换失败: {e}（目标状态可能不可用，请先用 get_issue_transitions 查看可用状态）")
                        fail_count += 1
                        continue

                # 3) 更新优先级
                priority = item.get("priority")
                if priority and str(priority).strip():
                    has_work = True
                    try:
                        jira.update_issue_field(key, {"priority": {"name": str(priority).strip()}})
                        changes.append(f"优先级→{priority}")
                    except Exception as e:
                        _logger.warning("优先级更新失败 %s -> %s: %s", key, priority, e)
                        results.append(f"  第{i+1}项: ❌ {key} - 优先级更新失败: {e}")
                        fail_count += 1
                        continue

                if not has_work:
                    results.append(f"  第{i+1}项: ❌ {key} - 未提供任何待更新的字段（assignee/status/priority）")
                    fail_count += 1
                    continue

                results.append(f"  第{i+1}项: ✅ {key} - {'; '.join(changes)}")
                success_count += 1

            except Exception as e:
                results.append(f"  第{i+1}项: ❌ {issue_key} - {str(e)}")
                fail_count += 1

        summary_text = f"批量更新完成！成功: {success_count}, 失败: {fail_count}"
        return f"{summary_text}\n" + "\n".join(results)

    except json.JSONDecodeError:
        return f"批量更新失败：updates_json 格式无效，请提供有效的 JSON 字符串。"
    except Exception as e:
        _logger.error("批量更新失败: %s", e)
        return f"批量更新失败: {str(e)}"


@tool
def suggest_epic_tasks(epic_key: str = "") -> str:
    """
    获取 Epic 任务的详细信息（标题、描述等），供 AI 自动拆分子任务。
    调用此工具后，AI 会根据 Epic 的标题和描述内容，自动生成建议的子 Task 清单。

    参数：epic_key - Epic 的任务 KEY（如 KO-100）
    返回 JSON 字符串，包含 Epic 的详细信息和现有子任务列表。
    """
    if not epic_key:
        return json.dumps({"error": "请提供 Epic 的任务 KEY（如 KO-100）"}, ensure_ascii=False)
    try:
        key = extract_issue_key(epic_key)
        if not key:
            return json.dumps({"error": "请提供有效的 Epic 任务 KEY（如 KO-100）"}, ensure_ascii=False)

        _logger.info("获取 Epic 详情用于拆分: %s", key)
        issue = jira.get_issue(key)
        fields = issue.get("fields", {})
        issue_type = fields.get("issuetype", {}) or {}
        issue_type_name = (issue_type.get("name") or "").lower()

        # 检查是否为 Epic
        if issue_type_name != "epic":
            return json.dumps({
                "warning": f"该任务 ({key}) 的问题类型为「{issue_type.get('name', '未知')}」，不是 Epic。"
                           f"建议先创建 Epic 类型的任务再拆分。",
                "epic_key": key,
                "summary": fields.get("summary", ""),
            }, ensure_ascii=False, indent=2)

        # 获取 Epic 的子任务（通过 epic_link 字段）
        project_key = key.split("-")[0]
        epic_field = Config.EPIC_LINK_FIELD_ID or f"\"Epic Link\""
        jql_query = f'project = {project_key} AND "{epic_field}" = {key} ORDER BY created ASC'
        existing_tasks = fetch_all_issues(jira, jql_query, max_results=50)

        sub_tasks = []
        for t in existing_tasks:
            if not t:
                continue
            f = t.get("fields", {}) or {}
            sub_tasks.append({
                "key": t.get("key"),
                "summary": f.get("summary", ""),
                "status": (f.get("status", {}) or {}).get("name", ""),
                "assignee": (f.get("assignee", {}) or {}).get("displayName", "未分配"),
            })

        # 构建返回信息
        description = fields.get("description", "") or ""
        if isinstance(description, dict):
            # 处理 ADF 格式的描述
            try:
                import json as _json
                description = _json.dumps(description, ensure_ascii=False)
            except Exception:
                description = str(description)

        result = {
            "epic_key": key,
            "summary": fields.get("summary", ""),
            "description": (description[:1000] + "...") if len(description) > 1000 else description,
            "project": project_key,
            "status": (fields.get("status", {}) or {}).get("name", ""),
            "assignee": (fields.get("assignee", {}) or {}).get("displayName", "未分配"),
            "existing_sub_tasks": sub_tasks,
            "existing_count": len(sub_tasks),
            "hint": "请根据 Epic 的标题和描述，生成建议拆分的子 Task 清单。每个 Task 应包含 summary 和可选的 description。"
        }

        return json.dumps(result, ensure_ascii=False, indent=2)

    except Exception as e:
        _logger.error("获取 Epic 详情失败 %s: %s", epic_key, e)
        return json.dumps({"error": str(e)}, ensure_ascii=False)


@tool
def analyze_meeting_for_projects(meeting_notes: str = "", project_key: str = "") -> str:
    """
    分析项目会议纪要，生成 Epic → Task → Sub-task 的完整项目结构建议。
    调用此工具后，AI 应根据返回的项目元数据和会议纪要内容，
    生成结构化的任务分解建议并展示给用户确认。

    参数：
      meeting_notes - 会议纪要文本（必填），内容越详细，生成的任务结构越准确
      project_key - 目标项目 KEY（必填），如 KO

    返回 JSON 字符串，包含：
      - 项目元数据（支持的问题类型、必填字段等）
      - 会议纪要原文
      - 格式提示（指导 AI 如何生成结构）
    """
    if not meeting_notes or not project_key:
        return json.dumps({"error": "请提供 meeting_notes（会议纪要）和 project_key（项目KEY）"}, ensure_ascii=False)

    try:
        key = validate_project_key(project_key)
        _logger.info("分析会议纪要，项目: %s", key)

        # 获取项目元数据（了解支持的问题类型和字段）
        meta_str = get_create_issue_metadata.invoke({"project_key": key})
        meta_data = json.loads(meta_str) if isinstance(meta_str, str) else meta_str

        # 获取项目中已有的 Epic 列表（避免重复创建）
        existing_epics = fetch_all_issues(
            jira, f'project = {key} AND issuetype = Epic ORDER BY created DESC',
            max_results=20,
        )
        existing_epic_list = []
        for ep in existing_epics or []:
            if not ep:
                continue
            f = ep.get("fields", {}) or {}
            existing_epic_list.append({
                "key": ep.get("key"),
                "summary": f.get("summary", ""),
                "status": (f.get("status", {}) or {}).get("name", ""),
            })

        result = {
            "project_key": key,
            "meeting_notes": meeting_notes,
            "project_metadata": meta_data,
            "existing_epics": existing_epic_list,
            "format_hint": (
                "请根据会议纪要和项目元数据，生成建议的项目任务结构。\n"
                "按以下 JSON 格式输出建议（只输出 JSON，不要额外说明）：\n"
                "{\n"
                '  "epics": [\n'
                "    {\n"
                '      "summary": "Epic 标题",\n'
                '      "description": "Epic 描述",\n'
                '      "tasks": [\n'
                "        {\n"
                '          "summary": "Task 标题",\n'
                '          "description": "Task 描述",\n'
                '          "sub_tasks": [\n'
                '            { "summary": "Sub-task 标题", "description": "描述（可选）" }\n'
                "          ]\n"
                "        }\n"
                "      ]\n"
                "    }\n"
                "  ]\n"
                "}\n"
                "说明：\n"
                "- epic_link_key 会在创建时自动关联，不需要在建议中包含\n"
                "- parent_key 会在创建 Sub-task 时自动关联到父 Task\n"
                "- 每个 Epic 建议 3-8 个 Task，每个 Task 建议 0-5 个 Sub-task\n"
                "- 优先使用项目元数据中的问题类型和字段\n"
                "- 如果会议纪要不够详细，可以根据常识合理补充"
            ),
        }

        return json.dumps(result, ensure_ascii=False, indent=2)

    except Exception as e:
        _logger.error("分析会议纪要失败: %s", e)
        return json.dumps({"error": str(e)}, ensure_ascii=False)