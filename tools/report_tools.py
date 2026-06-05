"""报告生成工具 - 使用外部模板文件"""
import os
from datetime import datetime
from langchain.tools import tool
from jira_client import JiraClient
from config import Config
from .risk_extractor import get_project_risks

jira = JiraClient().get_client()


def calculate_task_weight(fields):
    if fields is None:
        return 1
    target_start = fields.get(Config.TARGET_START_FIELD)
    target_end = fields.get(Config.TARGET_END_FIELD)
    if target_start == 'None' or target_start == 'null':
        target_start = None
    if target_end == 'None' or target_end == 'null':
        target_end = None
    if target_start and target_end:
        try:
            start = datetime.strptime(target_start[:10], "%Y-%m-%d")
            end = datetime.strptime(target_end[:10], "%Y-%m-%d")
            days = (end - start).days
            return max(days, 1)
        except:
            pass
    return 1


def calculate_task_progress(fields):
    if fields is None:
        return 0, 1
    weight = calculate_task_weight(fields)
    status = fields.get("status", {}).get("name", "")
    if status == "Done":
        return 100, weight
    if status in ["In Progress", "进行中"]:
        target_start = fields.get(Config.TARGET_START_FIELD)
        target_end = fields.get(Config.TARGET_END_FIELD)
        if target_start == 'None' or target_start == 'null':
            target_start = None
        if target_end == 'None' or target_end == 'null':
            target_end = None
        if target_start and target_end:
            try:
                start = datetime.strptime(target_start[:10], "%Y-%m-%d")
                end = datetime.strptime(target_end[:10], "%Y-%m-%d")
                today = datetime.now().date()
                total_days = (end - start).days
                if total_days > 0:
                    elapsed_days = (today - start.date()).days
                    progress = max(5, min(95, int(elapsed_days / total_days * 100)))
                    return progress, weight
            except:
                pass
        return 50, weight
    return 0, weight


def calculate_project_progress(issues):
    total_weight = 0
    completed_weight = 0
    for issue in issues:
        if issue is None:
            continue
        fields = issue.get("fields", {})
        if fields is None:
            continue
        progress, weight = calculate_task_progress(fields)
        total_weight += weight
        completed_weight += weight * progress / 100
    progress = round((completed_weight / total_weight * 100)) if total_weight > 0 else 0
    return progress, total_weight, completed_weight


def analyze_project_risk(progress, overdue_count, blocked_count, high_priority_count):
    risks = []
    risk_score = 0
    if progress < 30:
        risks.append(f"进度严重滞后（仅完成{progress}%）")
        risk_score += 30
    elif progress < 50:
        risks.append(f"进度滞后（仅完成{progress}%）")
        risk_score += 20
    elif progress < 70:
        risks.append(f"进度偏慢（完成{progress}%）")
        risk_score += 10
    if overdue_count > 5:
        risks.append(f"超期任务较多（{overdue_count}个）")
        risk_score += 25
    elif overdue_count > 0:
        risks.append(f"存在超期任务（{overdue_count}个）")
        risk_score += 15
    if high_priority_count > 10:
        risks.append(f"高优先级任务积压严重（{high_priority_count}个）")
        risk_score += 20
    elif high_priority_count > 5:
        risks.append(f"高优先级任务较多（{high_priority_count}个）")
        risk_score += 10
    if blocked_count > 3:
        risks.append(f"阻塞任务较多（{blocked_count}个）")
        risk_score += 15
    elif blocked_count > 0:
        risks.append(f"存在阻塞任务（{blocked_count}个）")
        risk_score += 8
    if risk_score >= 60:
        risk_level = "🔴 高风险"
    elif risk_score >= 30:
        risk_level = "🟡 中风险"
    else:
        risk_level = "🟢 低风险"
    return risk_level, risks


def load_template(template_name):
    template_path = os.path.join(Config.TEMPLATE_DIR, template_name)
    if not os.path.exists(template_path):
        raise FileNotFoundError(f"模板文件不存在: {template_path}")
    with open(template_path, "r", encoding="utf-8") as f:
        return f.read()


def fetch_all_issues(jql_query, max_results=100):
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
def generate_portfolio_report() -> str:
    """
    生成项目集风险报告（包含所有配置项目的汇总分析）。
    返回报告文件路径和统计信息。
    """
    try:
        if Config.TARGET_PROJECTS:
            project_list = Config.TARGET_PROJECTS
        else:
            projects = jira.get_all_projects()
            project_list = [p.get('key') for p in projects[:10] if p]
        if not project_list:
            return "❌ 无法确定要查询的项目"
        
        all_projects_data = []
        for proj_key in project_list:
            try:
                if not proj_key:
                    continue
                issues_list = fetch_all_issues(f"project = {proj_key} ORDER BY updated DESC")
                if not issues_list:
                    all_projects_data.append({"key": proj_key, "error": "无任务数据"})
                    continue
                progress, _, _ = calculate_project_progress(issues_list)
                done_count = 0
                in_progress_count = 0
                overdue_count = 0
                blocked_count = 0
                high_priority_count = 0
                for issue in issues_list:
                    if issue is None:
                        continue
                    fields = issue.get("fields")
                    if fields is None:
                        continue
                    status_name = fields.get("status", {}).get("name", "")
                    priority_name = fields.get("priority", {}).get("name", "")
                    target_end = fields.get(Config.TARGET_END_FIELD)
                    if status_name == "Done":
                        done_count += 1
                    elif status_name in ["In Progress", "进行中"]:
                        in_progress_count += 1
                    if target_end and status_name != "Done":
                        try:
                            end_str = target_end
                            if end_str and end_str not in ['None', 'null', None]:
                                end_date = datetime.strptime(end_str[:10], "%Y-%m-%d").date()
                                if end_date < datetime.now().date():
                                    overdue_count += 1
                        except:
                            pass
                    if status_name != "Done" and priority_name in ["Highest", "High", "紧急", "高"]:
                        high_priority_count += 1
                    issue_links = fields.get("issuelinks")
                    if issue_links:
                        for link in issue_links:
                            if link is None:
                                continue
                            link_type = link.get("type", {})
                            if link_type:
                                link_type_name = link_type.get("name", "").lower()
                                direction = link.get("direction", "")
                                if direction == "inward" and "blocks" in link_type_name:
                                    blocked_count += 1
                                    break
                risk_level, risks = analyze_project_risk(progress, overdue_count, blocked_count, high_priority_count)
                all_projects_data.append({
                    "key": proj_key,
                    "total": len(issues_list),
                    "done": done_count,
                    "in_progress": in_progress_count,
                    "progress": progress,
                    "risk_level": risk_level,
                    "risks": risks,
                    "overdue": overdue_count
                })
            except Exception as e:
                all_projects_data.append({"key": proj_key, "error": str(e)})
        
        html_template = load_template("portfolio_report.html")
        table_rows = ""
        for proj in all_projects_data:
            if "error" in proj:
                table_rows += f'<tr><td colspan="7" style="color:#dc3545;">❌ {proj["key"]}: {proj["error"]}</td></tr>'
            else:
                risk_class = "risk-high" if "高风险" in proj['risk_level'] else ("risk-medium" if "中风险" in proj['risk_level'] else "risk-low")
                risks_html = '<ul class="risk-list">'
                for r in proj['risks']:
                    risks_html += f'<li>{r}</li>'
                risks_html += '</ul>' if proj['risks'] else '<span>暂无风险</span>'
                table_rows += f"""
                    <tr>
                        <td><strong>{proj['key']}</strong></td>
                        <td>{proj['total']}</td>
                        <td>{proj['done']}</td>
                        <td>{proj['in_progress']}</td>
                        <td><div class="progress-bar"><div class="progress-fill" style="width: {proj['progress']}%"></div></div>{proj['progress']}%</td>
                        <td class="overdue">{proj['overdue']}</td>
                        <td class="{risk_class}">{proj['risk_level']}</td>
                        <td>{risks_html}</td>
                    </tr>
                """
        risk_table_rows = ""
        total_risks_found = 0
        for proj in all_projects_data:
            if "error" in proj:
                continue
            proj_key = proj['key']
            result = get_project_risks(proj_key)
            if not result["error"] and result["risks"]:
                total_risks_found += result["total"]
                for risk in result["risks"]:
                    priority_class = ""
                    if risk["priority"] in ["Highest", "High", "紧急", "高"]:
                        priority_class = "risk-high"
                    elif risk["priority"] in ["Medium", "中"]:
                        priority_class = "risk-medium"
                    else:
                        priority_class = "risk-low"
                    status_icon = "✅" if risk["status"] in ["Done", "Closed", "已关闭", "已完成"] else ("🔄" if risk["status"] in ["In Progress", "进行中"] else "⏳")
                    risk_table_rows += f"""
                        <tr>
                            <td><strong>{proj_key}</strong></td>
                            <td><a href="{Config.JIRA_SERVER}/browse/{risk['key']}" target="_blank" style="color:#667eea;">{risk['key']}</a></td>
                            <td>{risk['summary'][:70]}</td>
                            <td class="{priority_class}">{risk['priority'] or '-'}</td>
                            <td>{status_icon} {risk['status']}</td>
                            <td>{risk['assignee']}</td>
                            <td>{risk['target_end'] or '-'}</td>
                        </tr>
                    """
        risk_section = ""
        if risk_table_rows:
            risk_section = f"""
        <div class="table-container" style="margin-top: 24px;">
            <h3 style="margin-bottom: 16px;">⚠️ 风险项明细 (Issue Type = Risk)</h3>
            <p style="margin-bottom: 12px; color: #666; font-size: 13px;">共发现 <strong style="color:#dc3545;">{total_risks_found}</strong> 个风险项</p>
            <table>
                <thead><tr><th>项目</th><th>风险KEY</th><th>摘要</th><th>优先级</th><th>状态</th><th>负责人</th><th>目标结束</th></tr></thead>
                <tbody>{risk_table_rows}</tbody>
            </table>
        </div>
        """
        html = html_template.replace("{{DATE}}", datetime.now().strftime('%Y-%m-%d %H:%M:%S'))
        html = html.replace("{{TABLE_ROWS}}", table_rows)
        if "{{RISK_SECTION}}" in html:
            html = html.replace("{{RISK_SECTION}}", risk_section)
        else:
            html = html + risk_section
            print("⚠️ 警告: 模板文件中缺少 {{RISK_SECTION}} 占位符，风险模块已追加在报告末尾")
        filename = f"portfolio_risk_report_{datetime.now().strftime('%Y%m%d_%H%M%S')}.html"
        filepath = os.path.join(Config.REPORTS_DIR, filename)
        with open(filepath, "w", encoding="utf-8") as f:
            f.write(html)
        success_count = len([p for p in all_projects_data if 'error' not in p])
        return f"✅ 项目集风险报告已生成！\n📁 文件: {filepath}\n📊 共分析 {success_count} 个项目，发现 {total_risks_found} 个风险项"
    except Exception as e:
        return f"❌ 生成报告失败: {str(e)}"


@tool
def generate_report(project_key: str = None) -> str:
    """
    生成单个项目的HTML报告。
    参数 project_key 可选，不传则使用配置的第一个项目或所有项目中的第一个。
    返回报告文件路径和统计信息。
    """
    try:
        if project_key:
            target_project = project_key.upper()
        elif Config.TARGET_PROJECTS:
            target_project = Config.TARGET_PROJECTS[0]
        else:
            projects = jira.get_all_projects()
            target_project = projects[0].get('key') if projects else None
        if not target_project:
            return "❌ 无法确定要查询的项目"
        issues_list = fetch_all_issues(f"project = {target_project} ORDER BY updated DESC")
        if not issues_list:
            return f"❌ 项目 {target_project} 没有任务数据"
        progress, _, _ = calculate_project_progress(issues_list)
        total = len(issues_list)
        done = 0
        in_progress = 0
        overdue = 0
        high_priority = 0
        tasks = []
        for issue in issues_list:
            if issue is None:
                continue
            fields = issue.get("fields", {})
            if fields is None:
                continue
            status = fields.get("status", {}).get("name", "")
            priority = fields.get("priority", {}).get("name", "")
            target_end = fields.get(Config.TARGET_END_FIELD)
            if status == "Done":
                done += 1
            elif status in ["In Progress", "进行中"]:
                in_progress += 1
            if target_end and status != "Done":
                try:
                    end_str = target_end
                    if end_str not in ['None', 'null', None]:
                        end_date = datetime.strptime(end_str[:10], "%Y-%m-%d").date()
                        if end_date < datetime.now().date():
                            overdue += 1
                except:
                    pass
            if status != "Done" and priority in ["Highest", "High", "紧急", "高"]:
                high_priority += 1
            tasks.append({
                "key": issue.get("key", "未知"),
                "summary": fields.get("summary", "")[:50],
                "status": status,
                "priority": priority,
                "assignee": fields.get("assignee", {}).get("displayName", "未分配"),
                "target_end": target_end[:10] if target_end and target_end not in ['None', 'null'] else "-"
            })
        risk_level, risks = analyze_project_risk(progress, overdue, 0, high_priority)
        html_template = load_template("single_report.html")
        task_rows = ""
        for task in tasks[:30]:
            task_rows += f"""
                <tr>
                    <td>{task['key']}</td>
                    <td>{task['summary']}</td>
                    <td>{task['status']}</td>
                    <td>{task['priority']}</td>
                    <td>{task['assignee']}</td>
                    <td>{task['target_end']}</td>
                </tr>
            """
        risks_html = "".join(f"<li>{r}</li>" for r in risks)
        html = html_template.replace("{{PROJECT}}", target_project)
        html = html.replace("{{DATE}}", datetime.now().strftime('%Y-%m-%d %H:%M:%S'))
        html = html.replace("{{TOTAL}}", str(total))
        html = html.replace("{{DONE}}", str(done))
        html = html.replace("{{IN_PROGRESS}}", str(in_progress))
        html = html.replace("{{PROGRESS}}", str(progress))
        html = html.replace("{{OVERDUE}}", str(overdue))
        html = html.replace("{{RISK_LEVEL}}", risk_level)
        html = html.replace("{{RISKS}}", risks_html)
        html = html.replace("{{TASK_ROWS}}", task_rows)
        filename = f"report_{target_project}_{datetime.now().strftime('%Y%m%d_%H%M%S')}.html"
        filepath = os.path.join(Config.REPORTS_DIR, filename)
        with open(filepath, "w", encoding="utf-8") as f:
            f.write(html)
        return f"✅ 报告已生成！\n📁 文件: {filepath}\n📊 进度: {progress}%\n⚠️ 风险等级: {risk_level}"
    except Exception as e:
        return f"❌ 生成报告失败: {str(e)}"