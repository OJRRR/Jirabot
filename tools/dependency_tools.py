"""依赖关系工具"""
import json
import re
from langchain.tools import tool
from jira_client import JiraClient
from config import Config

jira = JiraClient().get_client()


def parse_issue_links(issue_links):
    """
    解析 Issue Links，返回 (incoming, outgoing)
    incoming: 别人依赖我（我是前置）
    outgoing: 我依赖别人（我是后置）
    """
    incoming = []
    outgoing = []
    for link in issue_links:
        link_type = link.get("type", {}).get("name", "未知")
        direction = link.get("direction", "")
        if direction == "inward":
            target = link.get("outwardIssue", {})
            if target:
                incoming.append({
                    "key": target.get("key"),
                    "summary": target.get("fields", {}).get("summary", ""),
                    "type": link_type,
                    "status": target.get("fields", {}).get("status", {}).get("name", "")
                })
        else:
            target = link.get("inwardIssue", {})
            if target:
                outgoing.append({
                    "key": target.get("key"),
                    "summary": target.get("fields", {}).get("summary", ""),
                    "type": link_type,
                    "status": target.get("fields", {}).get("status", {}).get("name", "")
                })
    return incoming, outgoing


@tool
def get_issue_links(issue_key: str) -> str:
    """
    获取任务的依赖关系（Issue Links）。
    参数：任务KEY（如 KO-29）
    返回 JSON 字符串，包含 incoming（别人依赖我）和 outgoing（我依赖别人）列表。
    """
    try:
        keys = re.findall(r'[A-Z]+-\d+', issue_key.upper())
        if not keys:
            return json.dumps({"error": "请提供有效的任务Key"})
        issue = jira.issue(keys[0])
        fields = issue.get("fields", {})
        issue_links = fields.get("issuelinks", [])
        incoming, outgoing = parse_issue_links(issue_links)
        return json.dumps({"key": issue_key, "incoming": incoming, "outgoing": outgoing}, ensure_ascii=False, indent=2)
    except Exception as e:
        return json.dumps({"error": str(e)})


@tool
def get_task_dependencies(issue_key: str) -> str:
    """
    获取任务依赖并分析风险。
    参数：任务KEY（如 KO-29）
    返回 JSON 字符串，包含依赖列表和风险分析。
    """
    try:
        keys = re.findall(r'[A-Z]+-\d+', issue_key.upper())
        if not keys:
            return json.dumps({"error": "请提供有效的任务Key"})
        issue = jira.issue(keys[0])
        fields = issue.get("fields", {})
        issue_links = fields.get("issuelinks", [])
        incoming, outgoing = parse_issue_links(issue_links)
        risks = []
        for dep in outgoing:
            if dep.get("status") != "Done":
                risks.append(f"⚠️ 依赖 {dep['key']} 未完成，可能阻塞当前任务")
        for dep in incoming:
            if dep.get("status") != "Done":
                risks.append(f"⚠️ 被 {dep['key']} 依赖，该任务进度可能受影响")
        return json.dumps({
            "key": issue_key,
            "summary": fields.get("summary"),
            "outgoing_dependencies": outgoing,
            "incoming_dependencies": incoming,
            "risk_analysis": risks if risks else ["✅ 无明显依赖风险"]
        }, ensure_ascii=False, indent=2)
    except Exception as e:
        return json.dumps({"error": str(e)})