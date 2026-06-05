"""风险提取工具"""
import json
from datetime import datetime
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


def get_project_risks(project_key: str) -> dict:
    """获取指定项目的所有 Risk 类型 Issue（内部函数，非工具）"""
    try:
        jql_query = f'project = {project_key} AND issuetype = "Risk" ORDER BY priority DESC, updated DESC'
        issues_list = fetch_all_issues(jql_query)
        if not issues_list:
            return {"project": project_key, "risks": [], "error": None}
        risks = []
        for issue in issues_list:
            if issue is None:
                continue
            fields = issue.get("fields", {})
            if fields is None:
                continue
            status = fields.get("status", {})
            status_name = status.get("name", "") if status else ""
            priority = fields.get("priority", {})
            priority_name = priority.get("name", "") if priority else ""
            assignee = fields.get("assignee", {})
            assignee_name = assignee.get("displayName", "未分配") if assignee else "未分配"
            description = fields.get("description", "") or ""
            target_end = fields.get(Config.TARGET_END_FIELD)
            if target_end in ['None', 'null', None]:
                target_end = ""
            risks.append({
                "key": issue.get("key"),
                "summary": fields.get("summary", ""),
                "description": description[:200] + "..." if len(description) > 200 else description,
                "status": status_name,
                "priority": priority_name,
                "assignee": assignee_name,
                "target_end": target_end[:10] if target_end else "",
                "created": fields.get("created", "")[:10] if fields.get("created") else ""
            })
        return {"project": project_key, "risks": risks, "total": len(risks), "error": None}
    except Exception as e:
        return {"project": project_key, "risks": [], "error": str(e)}


@tool
def extract_issue_risks(project_key: str = None) -> str:
    """
    从 Jira 中提取 Issue Type 为 Risk 的任务并归纳总结。
    参数：project_key - 可选，指定项目KEY（如 KO），不传则分析所有配置的项目。
    """
    try:
        if project_key:
            project_list = [project_key.upper()]
        elif Config.TARGET_PROJECTS:
            project_list = Config.TARGET_PROJECTS
        else:
            projects = jira.get_all_projects()
            project_list = [p.get('key') for p in projects[:10] if p]
        if not project_list:
            return "❌ 无法确定要分析的项目"
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
                if risk["priority"] in ["Highest", "High", "紧急", "高"]:
                    high_priority_risks.append({
                        "project": proj_key,
                        "key": risk["key"],
                        "summary": risk["summary"],
                        "status": risk["status"],
                        "assignee": risk["assignee"]
                    })
                if risk["status"] not in ["Done", "Closed", "已关闭", "已完成"]:
                    open_risks.append({
                        "project": proj_key,
                        "key": risk["key"],
                        "summary": risk["summary"],
                        "priority": risk["priority"],
                        "status": risk["status"],
                        "assignee": risk["assignee"]
                    })
        return generate_risk_summary(all_projects_risks, total_risks, summary_by_priority,
                                      summary_by_status, high_priority_risks, open_risks)
    except Exception as e:
        return f"❌ 提取风险失败: {str(e)}"


def generate_risk_summary(all_projects_risks, total_risks, summary_by_priority,
                          summary_by_status, high_priority_risks, open_risks):
    """生成格式化的风险总结（内部辅助函数）"""
    if total_risks == 0:
        return "✅ 未发现任何 Risk 类型的 Issue。"
    report = []
    report.append("=" * 60)
    report.append("📋 Jira 风险项汇总报告 (Issue Type = Risk)")
    report.append("=" * 60)
    report.append(f"📊 共发现 {total_risks} 个风险项")
    report.append("")
    report.append("📁 各项目风险数量：")
    for proj in all_projects_risks:
        if proj["error"]:
            report.append(f"   ❌ {proj['project']}: {proj['error']}")
        else:
            report.append(f"   📌 {proj['project']}: {proj['total']} 个风险")
            if proj["risks"]:
                keys = [r["key"] for r in proj["risks"][:5]]
                report.append(f"      风险列表: {', '.join(keys)}")
                if len(proj["risks"]) > 5:
                    report.append(f"      ... 还有 {len(proj['risks']) - 5} 个")
    report.append("")
    if summary_by_priority:
        report.append("⚠️ 按优先级分布：")
        for priority, count in sorted(summary_by_priority.items()):
            icon = "🔴" if priority in ["Highest", "High", "紧急", "高"] else "🟡" if priority in ["Medium", "中"] else "🟢"
            report.append(f"   {icon} {priority}: {count} 个")
    report.append("")
    if summary_by_status:
        report.append("📌 按状态分布：")
        for status, count in summary_by_status.items():
            report.append(f"   • {status}: {count} 个")
    report.append("")
    if high_priority_risks:
        report.append("🔴 高优先级风险项（需立即关注）：")
        for risk in high_priority_risks[:10]:
            report.append(f"   • {risk['key']} [{risk['project']}] - {risk['summary'][:50]}")
            report.append(f"      状态: {risk['status']} | 负责人: {risk['assignee']}")
        if len(high_priority_risks) > 10:
            report.append(f"   ... 共 {len(high_priority_risks)} 个高优先级风险")
    report.append("")
    if open_risks:
        report.append("🟡 进行中的风险项：")
        for risk in open_risks[:7]:
            report.append(f"   • {risk['key']} [{risk['project']}] - {risk['summary'][:50]}")
        if len(open_risks) > 7:
            report.append(f"   ... 共 {len(open_risks)} 个进行中的风险")
    report.append("")
    report.append("=" * 60)
    report.append("💡 建议：请优先处理高优先级风险，定期跟进进行中的风险项")
    return "\n".join(report)


def get_risk_html_rows(project_key: str) -> str:
    """获取项目的 Risk 列表 HTML 行（用于报告嵌入，非工具）"""
    result = get_project_risks(project_key)
    if result["error"] or not result["risks"]:
        return ""
    rows = []
    for risk in result["risks"]:
        priority_class = ""
        if risk["priority"] in ["Highest", "High", "紧急", "高"]:
            priority_class = "risk-high"
        elif risk["priority"] in ["Medium", "中"]:
            priority_class = "risk-medium"
        else:
            priority_class = "risk-low"
        status_icon = "✅" if risk["status"] in ["Done", "Closed", "已关闭", "已完成"] else ("🔄" if risk["status"] in ["In Progress", "进行中"] else "⏳")
        row = f"""
            <tr>
                <td><strong>{risk['key']}</strong></td>
                <td><a href="{Config.JIRA_SERVER}/browse/{risk['key']}" target="_blank" style="color:#667eea;">{risk['key']}</a></td>
                <td>{risk['summary'][:70]}</td>
                <td class="{priority_class}">{risk['priority'] or '-'}</td>
                <td>{status_icon} {risk['status']}</td>
                <td>{risk['assignee']}</td>
                <td>{risk['target_end'] or '-'}</td>
            </tr>
        """
        rows.append(row)
    return "\n".join(rows)