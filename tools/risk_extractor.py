"""风险提取工具（重构版）"""
import json
import logging
from datetime import datetime
from langchain.tools import tool
from config import Config
from utils import fetch_all_issues, validate_project_key
from .constants import is_done, is_high_priority, is_medium_priority
from ._lazy import LazyJira

_logger = logging.getLogger("jira_bot.risk_extractor")
jira = LazyJira()


def get_project_risks(project_key: str) -> dict:
    """获取指定项目的所有 Risk 类型 Issue（内部函数，非工具）"""
    try:
        jql_query = f'project = {project_key} AND issuetype = "Risk" ORDER BY priority DESC, updated DESC'
        _logger.debug("查询风险项: %s", jql_query)
        issues_list = fetch_all_issues(jira, jql_query, Config.JQL_PAGE_SIZE)
        if not issues_list:
            return {"project": project_key, "risks": [], "total": 0, "error": None}

        risks = []
        for issue in issues_list:
            if not issue:
                continue
            fields = issue.get("fields", {})
            if not fields:
                continue

            status = fields.get("status", {}) or {}
            priority = fields.get("priority", {}) or {}
            assignee = fields.get("assignee", {}) or {}

            description = fields.get("description", "") or ""
            target_end = fields.get(Config.TARGET_END_FIELD)
            if target_end in ('None', 'null', None):
                target_end = ""

            risks.append({
                "key": issue.get("key"),
                "summary": fields.get("summary", ""),
                "description": (description[:200] + "...") if len(description) > 200 else description,
                "status": status.get("name", ""),
                "priority": priority.get("name", ""),
                "assignee": assignee.get("displayName", "未分配"),
                "target_end": target_end[:10] if target_end else "",
                "created": (fields.get("created", "") or "")[:10]
            })

        return {"project": project_key, "risks": risks, "total": len(risks), "error": None}
    except Exception as e:
        _logger.error("获取项目风险失败 %s: %s", project_key, e)
        return {"project": project_key, "risks": [], "error": str(e)}


@tool
def extract_issue_risks(project_key: str = None, summary_only: bool = False) -> str:
    """
    从 Jira 中提取 Issue Type 为 Risk 的任务并归纳总结。
    参数：
      project_key - 可选，指定项目KEY（如 KO），不传则分析所有配置的项目。
      summary_only - 默认 False。True 时只输出关键数字 + Top-5 高优先级 + Top-5 进行中，
                     不输出各项目列表、按状态/优先级分布等大段文本，节省 token。
    """
    try:
        if project_key:
            project_list = [validate_project_key(project_key)]
        elif Config.TARGET_PROJECTS:
            project_list = Config.TARGET_PROJECTS
        else:
            projects = jira.get_all_projects()
            project_list = [p.get('key') for p in projects[:10] if p]

        if not project_list:
            return "无法确定要分析的项目"

        _logger.info("提取风险项，项目数: %d (summary_only=%s)", len(project_list), summary_only)

        all_projects_risks = []
        total_risks = 0
        summary_by_priority = {}
        summary_by_status = {}
        high_priority_risks = []
        open_risks = []

        for proj_key in project_list:
            result = get_project_risks(proj_key)
            all_projects_risks.append(result)
            if result["error"]:
                continue
            total_risks += result["total"]
            for risk in result["risks"]:
                priority = risk["priority"] or "未指定"
                summary_by_priority[priority] = summary_by_priority.get(priority, 0) + 1
                status = risk["status"]
                summary_by_status[status] = summary_by_status.get(status, 0) + 1

                if is_high_priority(risk["priority"]):
                    high_priority_risks.append({
                        "project": proj_key, "key": risk["key"],
                        "summary": risk["summary"], "status": risk["status"],
                        "assignee": risk["assignee"]
                    })
                if not is_done(risk["status"]):
                    open_risks.append({
                        "project": proj_key, "key": risk["key"],
                        "summary": risk["summary"], "priority": risk["priority"],
                        "status": risk["status"], "assignee": risk["assignee"]
                    })

        return _generate_risk_summary(all_projects_risks, total_risks,
                                      summary_by_priority, summary_by_status,
                                      high_priority_risks, open_risks,
                                      summary_only=summary_only)
    except Exception as e:
        _logger.error("提取风险失败: %s", e)
        return f"提取风险失败: {str(e)}"


def _generate_risk_summary(all_projects_risks, total_risks, summary_by_priority,
                           summary_by_status, high_priority_risks, open_risks,
                           summary_only: bool = False):
    """生成格式化的风险总结（内部辅助函数）"""
    if total_risks == 0:
        return "未发现任何 Risk 类型的 Issue。"

    if summary_only:
        # 极简版：关键数字 + Top-5 高优先级 + Top-5 进行中
        lines = [f"📊 风险概览：共 {total_risks} 个"]
        if summary_by_priority:
            parts = [f"{p}: {c}" for p, c in sorted(summary_by_priority.items(),
                                                    key=lambda x: -x[1])]
            lines.append("按优先级：" + " / ".join(parts))
        if high_priority_risks:
            lines.append("")
            lines.append("🔥 Top-5 高优先级：")
            for risk in high_priority_risks[:5]:
                lines.append(f"  • {risk['key']} [{risk['project']}] - {risk['summary'][:50]}")
        if open_risks:
            lines.append("")
            lines.append("⏳ Top-5 进行中：")
            for risk in open_risks[:5]:
                lines.append(f"  • {risk['key']} [{risk['project']}] - {risk['summary'][:50]}")
        return "\n".join(lines)

    # 完整版
    lines = []
    lines.append("=" * 60)
    lines.append("Jira 风险项汇总报告 (Issue Type = Risk)")
    lines.append("=" * 60)
    lines.append(f"共发现 {total_risks} 个风险项\n")

    lines.append("各项目风险数量：")
    for proj in all_projects_risks:
        if proj["error"]:
            lines.append(f"   {proj['project']}: {proj['error']}")
        else:
            lines.append(f"   {proj['project']}: {proj['total']} 个风险")
            if proj["risks"]:
                keys = [r["key"] for r in proj["risks"][:5]]
                lines.append(f"      风险列表: {', '.join(keys)}")
                if len(proj["risks"]) > 5:
                    lines.append(f"      ... 还有 {len(proj['risks']) - 5} 个")

    lines.append("")
    if summary_by_priority:
        lines.append("按优先级分布：")
        for priority, count in sorted(summary_by_priority.items()):
            if is_high_priority(priority):
                icon = "🔴"
            elif is_medium_priority(priority):
                icon = "🟡"
            else:
                icon = "🟢"
            lines.append(f"   {icon} {priority}: {count} 个")

    lines.append("")
    if summary_by_status:
        lines.append("按状态分布：")
        for status, count in summary_by_status.items():
            lines.append(f"   • {status}: {count} 个")

    lines.append("")
    if high_priority_risks:
        lines.append("高优先级风险项（需立即关注）：")
        for risk in high_priority_risks[:10]:
            lines.append(f"   • {risk['key']} [{risk['project']}] - {risk['summary'][:50]}")
            lines.append(f"      状态: {risk['status']} | 负责人: {risk['assignee']}")
        if len(high_priority_risks) > 10:
            lines.append(f"   ... 共 {len(high_priority_risks)} 个高优先级风险")

    lines.append("")
    if open_risks:
        lines.append("进行中的风险项：")
        for risk in open_risks[:7]:
            lines.append(f"   • {risk['key']} [{risk['project']}] - {risk['summary'][:50]}")
        if len(open_risks) > 7:
            lines.append(f"   ... 共 {len(open_risks)} 个进行中的风险")

    lines.append("")
    lines.append("=" * 60)
    lines.append("建议：请优先处理高优先级风险，定期跟进进行中的风险项")
    return "\n".join(lines)


def get_risk_html_rows(project_key: str) -> str:
    """获取项目的 Risk 列表 HTML 行（用于报告嵌入，非工具）"""
    from .risk_render import render_risk_rows_html
    result = get_project_risks(project_key)
    if result["error"] or not result["risks"]:
        return ""
    return render_risk_rows_html(result["risks"])