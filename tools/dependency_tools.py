"""依赖关系工具（重构版）"""
import json
import logging
from langchain.tools import tool
from jira_client import JiraClient
from utils import extract_issue_key

_logger = logging.getLogger("jira_bot.dependency_tools")
jira = JiraClient()


def parse_issue_links(issue_links):
    """解析 Issue Links，返回 (incoming, outgoing)"""
    incoming = []
    outgoing = []
    for link in issue_links:
        if not link:
            continue
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
def get_issue_links(issue_key: str = "") -> str:
    """
    获取任务的依赖关系（Issue Links）。
    参数：issue_key - 任务KEY（如 KO-29）
    返回 JSON 字符串，包含 incoming 和 outgoing 列表。
    """
    try:
        key = extract_issue_key(issue_key)
        if not key:
            return json.dumps({"error": "请提供有效的任务Key（如 KO-29）"}, ensure_ascii=False)
        _logger.info("查询依赖: %s", key)
        issue = jira.get_issue(key)
        fields = issue.get("fields", {})
        issue_links = fields.get("issuelinks", [])
        incoming, outgoing = parse_issue_links(issue_links)
        return json.dumps({
            "key": key,
            "incoming": incoming,
            "outgoing": outgoing
        }, ensure_ascii=False, indent=2)
    except Exception as e:
        _logger.error("查询依赖失败 %s: %s", issue_key, e)
        return json.dumps({"error": str(e)}, ensure_ascii=False)


@tool
def get_task_dependencies(issue_key: str = "") -> str:
    """
    获取任务依赖并分析风险。
    参数：issue_key - 任务KEY（如 KO-29）
    返回 JSON 字符串，包含依赖列表和风险分析。
    """
    try:
        key = extract_issue_key(issue_key)
        if not key:
            return json.dumps({"error": "请提供有效的任务Key（如 KO-29）"}, ensure_ascii=False)
        _logger.info("分析依赖风险: %s", key)
        issue = jira.get_issue(key)
        fields = issue.get("fields", {})
        issue_links = fields.get("issuelinks", [])
        incoming, outgoing = parse_issue_links(issue_links)

        risks = []
        for dep in outgoing:
            if dep.get("status") != "Done":
                risks.append(f"依赖 {dep['key']} 未完成，可能阻塞当前任务")
        for dep in incoming:
            if dep.get("status") != "Done":
                risks.append(f"被 {dep['key']} 依赖，该任务进度可能受影响")

        return json.dumps({
            "key": key,
            "summary": fields.get("summary"),
            "outgoing_dependencies": outgoing,
            "incoming_dependencies": incoming,
            "risk_analysis": risks if risks else ["无明显依赖风险"]
        }, ensure_ascii=False, indent=2)
    except Exception as e:
        _logger.error("依赖风险分析失败 %s: %s", issue_key, e)
        return json.dumps({"error": str(e)}, ensure_ascii=False)