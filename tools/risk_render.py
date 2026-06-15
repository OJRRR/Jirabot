"""风险行 HTML 渲染（被 report_tools 和 risk_extractor 共用）

数据契约（risk dict）：
    {
      "key": "KO-1",
      "summary": "...",
      "priority": "High",
      "status": "In Progress",
      "assignee": "张三",
      "target_end": "2026-06-15" or "",
    }
"""
import html

from config import Config
from .constants import is_done, is_in_progress, is_high_priority, is_medium_priority


def _priority_class(priority: str) -> str:
    if is_high_priority(priority):
        return "risk-high"
    if is_medium_priority(priority):
        return "risk-medium"
    return "risk-low"


def _status_icon(status: str) -> str:
    if is_done(status):
        return "✅"
    if is_in_progress(status):
        return "🔄"
    return "⏳"


def _esc(s) -> str:
    if s is None:
        return ""
    return html.escape(str(s), quote=True)


def render_risk_rows_html(risks: list, prepend_col: str = None) -> str:
    """
    把风险列表渲染成 <tr>...</tr> 字符串（不含 <table> 标签）。
    :param risks: list[dict] 见文件顶部数据契约
    :param prepend_col: 若不为空，每行开头会插一列展示该值（如项目KEY）
    :return: str
    """
    rows = []
    for r in risks:
        if not isinstance(r, dict):
            continue
        key = r.get("key") or "-"
        summary = (r.get("summary") or "")[:70]
        priority = r.get("priority") or "-"
        status = r.get("status") or "-"
        assignee = r.get("assignee") or "未分配"
        target_end = r.get("target_end") or "-"
        cls = _priority_class(priority)
        icon = _status_icon(status)

        prepend_td = f'<td><strong>{_esc(prepend_col)}</strong></td>' if prepend_col else ''
        rows.append(
            '<tr>'
            f'{prepend_td}'
            f'<td><a href="{_esc(Config.JIRA_SERVER)}/browse/{_esc(key)}" '
            f'target="_blank" style="color:#667eea;">{_esc(key)}</a></td>'
            f'<td>{_esc(summary)}</td>'
            f'<td class="{_esc(cls)}">{_esc(priority)}</td>'
            f'<td>{icon} {_esc(status)}</td>'
            f'<td>{_esc(assignee)}</td>'
            f'<td>{_esc(target_end if target_end else "-")}</td>'
            '</tr>'
        )
    return "\n".join(rows)