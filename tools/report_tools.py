"""报告生成工具 - 使用外部模板文件"""
import os
import html
import logging
from datetime import datetime
from langchain.tools import tool
from config import Config
from utils import fetch_all_issues
from .constants import is_done, is_in_progress, is_high_priority, BLOCKS_KEYWORDS
from .risk_extractor import get_project_risks
from .risk_render import render_risk_rows_html
from ._lazy import LazyJira

_logger = logging.getLogger("jira_bot.report_tools")
jira = LazyJira()


def _parse_target_date(value):
    """从 Jira 自定义字段解析出 date 对象，解析失败返回 None"""
    if not value or value in ("None", "null"):
        return None
    try:
        return datetime.strptime(value[:10], "%Y-%m-%d").date()
    except (ValueError, TypeError):
        return None


def _normalize_target(value):
    """把字段值里的 'None' / 'null' / 空字符串统一成 None"""
    if not value or value in ("None", "null"):
        return None
    return value


def calculate_task_weight(fields):
    if fields is None:
        return 1
    target_start = _normalize_target(fields.get(Config.TARGET_START_FIELD))
    target_end = _normalize_target(fields.get(Config.TARGET_END_FIELD))
    if target_start and target_end:
        start = _parse_target_date(target_start)
        end = _parse_target_date(target_end)
        if start and end:
            return max((end - start).days, 1)
    return 1


def calculate_task_progress(fields):
    if fields is None:
        return 0, 1
    weight = calculate_task_weight(fields)
    status = fields.get("status", {}).get("name", "")
    if is_done(status):
        return 100, weight
    if is_in_progress(status):
        target_start = _normalize_target(fields.get(Config.TARGET_START_FIELD))
        target_end = _normalize_target(fields.get(Config.TARGET_END_FIELD))
        start = _parse_target_date(target_start) if target_start else None
        end = _parse_target_date(target_end) if target_end else None
        if start and end:
            total_days = (end - start).days
            if total_days > 0:
                today = datetime.now().date()
                elapsed_days = (today - start).days
                progress = max(5, min(95, int(elapsed_days / total_days * 100)))
                return progress, weight
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
    """风险评分；阈值全部从 Config 读，方便 .env 调参。"""
    risks = []
    risk_score = 0

    # 进度维度
    if progress < Config.RISK_PROGRESS_LOW:
        risks.append(f"进度严重滞后（仅完成{progress}%）")
        risk_score += 30
    elif progress < Config.RISK_PROGRESS_MED:
        risks.append(f"进度滞后（仅完成{progress}%）")
        risk_score += 20
    elif progress < Config.RISK_PROGRESS_HIGH:
        risks.append(f"进度偏慢（完成{progress}%）")
        risk_score += 10

    # 超期任务
    if overdue_count > Config.RISK_OVERDUE_HIGH:
        risks.append(f"超期任务较多（{overdue_count}个）")
        risk_score += 25
    elif overdue_count >= Config.RISK_OVERDUE_LOW:
        risks.append(f"存在超期任务（{overdue_count}个）")
        risk_score += 15

    # 高优先级积压
    if high_priority_count > Config.RISK_HIGH_PRIORITY_HIGH:
        risks.append(f"高优先级任务积压严重（{high_priority_count}个）")
        risk_score += 20
    elif high_priority_count >= Config.RISK_HIGH_PRIORITY_LOW:
        risks.append(f"高优先级任务较多（{high_priority_count}个）")
        risk_score += 10

    # 阻塞任务
    if blocked_count > Config.RISK_BLOCKED_HIGH:
        risks.append(f"阻塞任务较多（{blocked_count}个）")
        risk_score += 15
    elif blocked_count >= Config.RISK_BLOCKED_LOW:
        risks.append(f"存在阻塞任务（{blocked_count}个）")
        risk_score += 8

    if risk_score >= Config.RISK_SCORE_HIGH:
        risk_level = "🔴 高风险"
    elif risk_score >= Config.RISK_SCORE_MED:
        risk_level = "🟡 中风险"
    else:
        risk_level = "🟢 低风险"
    return risk_level, risks


def _is_blocked_by_inward_link(issue_links) -> bool:
    """判定一个 issue 是否被 "blocks" 链接阻塞（其它任务通过 blocks 链依赖它）"""
    if not issue_links:
        return False
    for link in issue_links:
        if not isinstance(link, dict):
            continue
        link_type = link.get("type") or {}
        link_type_name = (link_type.get("name") or "").lower()
        if link.get("direction") == "inward" and any(k in link_type_name for k in BLOCKS_KEYWORDS):
            return True
    return False


def load_template(template_name):
    template_path = os.path.join(Config.TEMPLATE_DIR, template_name)
    if not os.path.exists(template_path):
        raise FileNotFoundError(f"模板文件不存在: {template_path}")
    with open(template_path, "r", encoding="utf-8") as f:
        return f.read()


def _esc(s) -> str:
    """统一 HTML escape（供报告模板插入）"""
    if s is None:
        return ""
    return html.escape(str(s), quote=True)


@tool
def generate_portfolio_report() -> str:
    """
    生成项目集风险报告（包含所有配置项目的汇总分析）。
    返回报告文件路径和统计信息。
    """
    try:
        truncation_warning = None
        if Config.TARGET_PROJECTS:
            project_list = Config.TARGET_PROJECTS
        else:
            # 没配置目标项目时，从 Jira 拿全部项目；Jira 默认会限制数量，
            # 若有截断，必须在报告里明显提示用户。
            projects = jira.get_all_projects() or []
            total_projects = len(projects)
            project_list = [p.get('key') for p in projects if p]
            # atlassian-python-api 默认 maxResults=50，超出会被截断；记录这种情况
            if total_projects >= 50:
                truncation_warning = (
                    f"⚠️ Jira 返回了 {total_projects} 个项目，可能受 API 默认 50 上限截断。"
                    f"如需全量分析，请在 .env 的 PROJECTS 里显式列出项目 KEY（逗号分隔）。"
                )
                _logger.warning(truncation_warning)
        if not project_list:
            return "❌ 无法确定要查询的项目"

        all_projects_data = []
        today = datetime.now().date()
        for proj_key in project_list:
            try:
                if not proj_key:
                    continue
                issues_list = fetch_all_issues(jira, f"project = {proj_key} ORDER BY updated DESC")
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
                    if is_done(status_name):
                        done_count += 1
                    elif is_in_progress(status_name):
                        in_progress_count += 1
                    if not is_done(status_name):
                        end_date = _parse_target_date(target_end)
                        if end_date and end_date < today:
                            overdue_count += 1
                    if not is_done(status_name) and is_high_priority(priority_name):
                        high_priority_count += 1
                    if not is_done(status_name) and _is_blocked_by_inward_link(fields.get("issuelinks")):
                        blocked_count += 1
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
                table_rows += (
                    f'<tr><td colspan="7" style="color:#dc3545;">❌ '
                    f'{_esc(proj["key"])}: {_esc(proj["error"])}</td></tr>'
                )
            else:
                risk_class = (
                    "risk-high" if "高风险" in proj['risk_level']
                    else ("risk-medium" if "中风险" in proj['risk_level'] else "risk-low")
                )
                risks_html = '<ul class="risk-list">'
                for r in proj['risks']:
                    risks_html += f'<li>{_esc(r)}</li>'
                risks_html += '</ul>' if proj['risks'] else '<span>暂无风险</span>'
                table_rows += f"""
                    <tr>
                        <td><strong>{_esc(proj['key'])}</strong></td>
                        <td>{proj['total']}</td>
                        <td>{proj['done']}</td>
                        <td>{proj['in_progress']}</td>
                        <td><div class="progress-bar"><div class="progress-fill" style="width: {proj['progress']}%"></div></div>{proj['progress']}%</td>
                        <td class="overdue">{proj['overdue']}</td>
                        <td class="{risk_class}">{_esc(proj['risk_level'])}</td>
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
                risk_table_rows += render_risk_rows_html(result["risks"], prepend_col=proj_key)
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
            _logger.warning("模板文件中缺少 {{RISK_SECTION}} 占位符，风险模块已追加在报告末尾")
        filename = f"portfolio_risk_report_{datetime.now().strftime('%Y%m%d_%H%M%S')}.html"
        filepath = os.path.join(Config.REPORTS_DIR, filename)
        with open(filepath, "w", encoding="utf-8") as f:
            f.write(html)
        success_count = len([p for p in all_projects_data if 'error' not in p])
        msg = f"✅ 项目集风险报告已生成！\n📁 文件: {filepath}\n📊 共分析 {success_count} 个项目，发现 {total_risks_found} 个风险项"
        if truncation_warning:
            msg += f"\n\n{truncation_warning}"
        return msg
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
        issues_list = fetch_all_issues(jira, f"project = {target_project} ORDER BY updated DESC")
        if not issues_list:
            return f"❌ 项目 {target_project} 没有任务数据"
        progress, _, _ = calculate_project_progress(issues_list)
        total = len(issues_list)
        done = 0
        in_progress = 0
        overdue = 0
        high_priority = 0
        blocked = 0
        tasks = []
        today = datetime.now().date()
        for issue in issues_list:
            if issue is None:
                continue
            fields = issue.get("fields", {})
            if fields is None:
                continue
            status = fields.get("status", {}).get("name", "")
            priority = fields.get("priority", {}).get("name", "")
            target_end = fields.get(Config.TARGET_END_FIELD)
            if is_done(status):
                done += 1
            elif is_in_progress(status):
                in_progress += 1
            if not is_done(status):
                end_date = _parse_target_date(target_end)
                if end_date and end_date < today:
                    overdue += 1
            if not is_done(status) and is_high_priority(priority):
                high_priority += 1
            if not is_done(status) and _is_blocked_by_inward_link(fields.get("issuelinks")):
                blocked += 1
            tasks.append({
                "key": issue.get("key", "未知"),
                "summary": (fields.get("summary", "") or "")[:50],
                "status": status,
                "priority": priority,
                "assignee": fields.get("assignee", {}).get("displayName", "未分配"),
                "target_end": (target_end or "")[:10] if _normalize_target(target_end) else "-",
            })
        risk_level, risks = analyze_project_risk(progress, overdue, blocked, high_priority)
        html_template = load_template("single_report.html")
        task_rows = ""
        for task in tasks[:30]:
            task_rows += f"""
                <tr>
                    <td>{_esc(task['key'])}</td>
                    <td>{_esc(task['summary'])}</td>
                    <td>{_esc(task['status'])}</td>
                    <td>{_esc(task['priority'])}</td>
                    <td>{_esc(task['assignee'])}</td>
                    <td>{_esc(task['target_end'])}</td>
                </tr>
            """
        risks_html = "".join(f"<li>{_esc(r)}</li>" for r in risks)
        html = html_template.replace("{{PROJECT}}", _esc(target_project))
        html = html.replace("{{DATE}}", datetime.now().strftime('%Y-%m-%d %H:%M:%S'))
        html = html.replace("{{TOTAL}}", str(total))
        html = html.replace("{{DONE}}", str(done))
        html = html.replace("{{IN_PROGRESS}}", str(in_progress))
        html = html.replace("{{PROGRESS}}", str(progress))
        html = html.replace("{{OVERDUE}}", str(overdue))
        html = html.replace("{{RISK_LEVEL}}", _esc(risk_level))
        html = html.replace("{{RISKS}}", risks_html)
        html = html.replace("{{TASK_ROWS}}", task_rows)
        filename = f"report_{target_project}_{datetime.now().strftime('%Y%m%d_%H%M%S')}.html"
        filepath = os.path.join(Config.REPORTS_DIR, filename)
        with open(filepath, "w", encoding="utf-8") as f:
            f.write(html)
        return f"✅ 报告已生成！\n📁 文件: {filepath}\n📊 进度: {progress}%\n⚠️ 风险等级: {risk_level}"
    except Exception as e:
        return f"❌ 生成报告失败: {str(e)}"