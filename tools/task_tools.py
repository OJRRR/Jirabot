"""任务查询与创建工具"""
import json
import re
from langchain.tools import tool
from jira_client import JiraClient
from config import Config

jira = JiraClient().get_client()


def fetch_all_issues(jql_query, max_results=100):
    """分页获取所有 Issue"""
    all_issues = []
    start_at = 0
    while True:
        result = jira.jql(jql_query, start=start_at, limit=max_results)
        issues = result.get("issues", [])
        if not issues:
            break
        all_issues.extend(issues)
        start_at += max_results
        if start_at >= result.get("total", 0):
            break
    return all_issues


@tool
def get_my_tasks() -> str:
    """
    获取当前用户的所有未完成任务（status != Done）。
    返回 JSON 字符串，包含任务列表。
    """
    try:
        base_jql = "assignee = currentUser() AND status != Done ORDER BY updated DESC"
        jql_query = Config.get_build_jql(base_jql)
        issues = fetch_all_issues(jql_query)
        tasks = []
        for issue in issues[:30]:
            fields = issue.get("fields", {})
            tasks.append({
                "key": issue.get("key"),
                "summary": fields.get("summary"),
                "status": fields.get("status", {}).get("name"),
                "priority": fields.get("priority", {}).get("name"),
                "target_start": fields.get(Config.TARGET_START_FIELD),
                "target_end": fields.get(Config.TARGET_END_FIELD)
            })
        return json.dumps({"success": True, "total": len(tasks), "tasks": tasks}, ensure_ascii=False, indent=2)
    except Exception as e:
        return json.dumps({"error": str(e)})


@tool
def get_project_tasks(project_key: str) -> str:
    """
    获取指定项目的所有任务。
    参数：project_key (项目KEY，如 KO)
    返回 JSON 字符串，包含任务列表。
    """
    try:
        issues = fetch_all_issues(f"project = {project_key} ORDER BY updated DESC")
        tasks = []
        for issue in issues[:30]:
            fields = issue.get("fields", {})
            tasks.append({
                "key": issue.get("key"),
                "summary": fields.get("summary"),
                "status": fields.get("status", {}).get("name"),
                "assignee": fields.get("assignee", {}).get("displayName", "未分配"),
                "target_start": fields.get(Config.TARGET_START_FIELD),
                "target_end": fields.get(Config.TARGET_END_FIELD)
            })
        return json.dumps({"success": True, "project": project_key, "total": len(tasks), "tasks": tasks}, ensure_ascii=False, indent=2)
    except Exception as e:
        return json.dumps({"error": str(e)})


@tool
def get_create_issue_metadata(project_key: str, issue_type_name: str = None) -> str:
    """
    获取在指定项目中创建问题的元数据，包括可用的问题类型及其必填/可选字段。
    注意：此函数使用正确的 Jira API 方法 get_issue_createmeta。
    """
    try:
        if not project_key:
            return json.dumps({"error": "必须提供项目KEY (project_key)"})
        
        # 正确的 API 方法（atlassian-python-api）
        meta_data = jira.get_issue_createmeta(project_key)
        
        # 兼容性处理
        if isinstance(meta_data, str):
            meta_data = json.loads(meta_data)
        
        if not meta_data or 'projects' not in meta_data:
            return json.dumps({"error": "无法获取项目的创建元数据，请检查项目KEY或权限"})

        result = {"project_key": project_key, "issue_types": []}
        
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
                    if 'allowedValues' in field_config:
                        field_info["allowed_values"] = [v.get('value') for v in field_config['allowedValues'] if v.get('value')]
                    
                    if field_config.get('required', False):
                        issue_type_info['required_fields'].append(field_info)
                    else:
                        issue_type_info['optional_fields'].append(field_info)
                result['issue_types'].append(issue_type_info)
            
            if issue_type_name:
                filtered_types = [it for it in result['issue_types'] if it['name'].lower() == issue_type_name.lower()]
                result['issue_types'] = filtered_types
                if not filtered_types:
                    return json.dumps({"error": f"在项目 '{project_key}' 中未找到名为 '{issue_type_name}' 的问题类型。"})
            break
        
        return json.dumps({"success": True, "data": result}, ensure_ascii=False, indent=2)
    except Exception as e:
        return json.dumps({"error": f"获取创建元数据失败: {str(e)}"})


@tool
def create_issue(project_key: str = None, summary: str = None, issue_type: str = None,
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
        return "❌ 创建失败：必须明确指定 issue_type（问题类型），例如 Task、Sub-task、Risk 等。如果不清楚有哪些类型，可以调用 get_create_issue_metadata 工具查看。"
    if missing:
        return f"❌ 创建失败，缺少基础必填字段: {', '.join(missing)}。请补充后重试。"

    try:
        fields = {
            "project": {"key": project_key.upper()},
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
            epic_field_id = Config.EPIC_LINK_FIELD_ID
            if epic_field_id:
                fields[epic_field_id] = epic_link_key
        
        if additional_fields:
            fields.update(additional_fields)
        
        new_issue = jira.create_issue(fields=fields)
        issue_key = new_issue.get("key")
        issue_url = f"{Config.JIRA_SERVER}/browse/{issue_key}"
        
        msg = f"✅ 任务创建成功！\n🔗 {issue_key}: {issue_url}\n📝 摘要: {summary}"
        if parent_key:
            msg += f"\n👪 父任务: {parent_key}"
        if epic_link_key:
            msg += f"\n📂 所属Epic: {epic_link_key}"
        return msg
    except Exception as e:
        error_msg = str(e)
        # 尝试提取缺失字段
        missing_fields = []
        if "required" in error_msg.lower():
            match = re.search(r"required field '?(\w+)'? is missing", error_msg, re.IGNORECASE)
            if match:
                missing_fields.append(match.group(1))
        if missing_fields:
            return f"❌ 创建失败，缺少以下必填字段: {', '.join(missing_fields)}。请使用 additional_fields 提供这些字段的值。\n原始错误: {error_msg}"
        else:
            return f"❌ 创建任务失败: {error_msg}"


@tool
def create_issue_link(inward_issue_key: str, outward_issue_key: str, link_type_name: str = "Relates to") -> str:
    """
    在两个已存在的Jira问题之间创建一个链接。
    """
    if not inward_issue_key or not outward_issue_key:
        return "❌ 创建链接失败: 必须提供两个问题的KEY。"
    try:
        link_data = {
            "type": {"name": link_type_name},
            "inwardIssue": {"key": inward_issue_key},
            "outwardIssue": {"key": outward_issue_key}
        }
        jira.create_issue_link(link_data)
        return f"✅ 成功在问题 {outward_issue_key} 和 {inward_issue_key} 之间创建了 '{link_type_name}' 链接。"
    except Exception as e:
        return f"❌ 创建问题链接失败: {str(e)}"