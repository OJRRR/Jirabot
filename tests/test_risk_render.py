"""Tests for tools.risk_render — 风险行 HTML 渲染"""
import pytest

from tools.risk_render import render_risk_rows_html


class TestRenderRiskRowsHtml:
    """测试 render_risk_rows_html 函数"""

    def test_empty_risks(self):
        """空列表应返回空字符串"""
        result = render_risk_rows_html([])
        assert result == ""

    def test_with_single_risk(self):
        """单个风险项应渲染一行 <tr>"""
        risks = [{
            "key": "RISK-1",
            "summary": "高风险项",
            "priority": "High",
            "status": "In Progress",
            "assignee": "张三",
            "target_end": "2026-06-30",
        }]
        result = render_risk_rows_html(risks)
        assert "<tr>" in result
        assert "</tr>" in result
        assert "RISK-1" in result
        assert "高风险项" in result
        assert "High" in result
        assert "张三" in result

    def test_with_multiple_risks(self):
        """多个风险项应渲染多行"""
        risks = [
            {"key": "R-1", "summary": "A", "priority": "High", "status": "Open", "assignee": "甲", "target_end": ""},
            {"key": "R-2", "summary": "B", "priority": "Medium", "status": "Done", "assignee": "乙", "target_end": "2026-06-01"},
        ]
        result = render_risk_rows_html(risks)
        assert result.count("<tr>") == 2

    def test_with_prepend_col(self):
        """prepend_col 参数应在每行开头添加一列"""
        risks = [{
            "key": "R-1", "summary": "test", "priority": "Low",
            "status": "To Do", "assignee": "甲", "target_end": "",
        }]
        result = render_risk_rows_html(risks, prepend_col="KO")
        assert "<td><strong>KO</strong></td>" in result

    def test_done_status_shows_checkmark(self):
        """Done 状态应显示 ✅"""
        risks = [{
            "key": "R-1", "summary": "done risk", "priority": "Low",
            "status": "Done", "assignee": "甲", "target_end": "",
        }]
        result = render_risk_rows_html(risks)
        assert "✅" in result

    def test_missing_fields(self):
        """缺失字段应使用默认值"""
        risks = [{"key": "R-1"}]
        result = render_risk_rows_html(risks)
        assert "-" in result
        assert "未分配" in result

    def test_high_priority_class(self):
        """High 优先级应有 risk-high CSS 类"""
        risks = [{
            "key": "R-1", "summary": "urgent", "priority": "Highest",
            "status": "Open", "assignee": "甲", "target_end": "",
        }]
        result = render_risk_rows_html(risks)
        assert 'class="risk-high"' in result

    def test_medium_priority_class(self):
        """Medium 优先级应有 risk-medium CSS 类"""
        risks = [{
            "key": "R-1", "summary": "normal", "priority": "Medium",
            "status": "Open", "assignee": "甲", "target_end": "",
        }]
        result = render_risk_rows_html(risks)
        assert 'class="risk-medium"' in result

    def test_low_priority_class(self):
        """Low 优先级应有 risk-low CSS 类"""
        risks = [{
            "key": "R-1", "summary": "low", "priority": "Low",
            "status": "Open", "assignee": "甲", "target_end": "",
        }]
        result = render_risk_rows_html(risks)
        assert 'class="risk-low"' in result

    def test_none_risk_skipped(self):
        """列表中的 None 项应被跳过"""
        risks = [
            {"key": "R-1", "summary": "valid", "priority": "Low",
             "status": "Open", "assignee": "甲", "target_end": ""},
            None,
        ]
        result = render_risk_rows_html(risks)
        assert result.count("<tr>") == 1

    def test_html_escaping(self):
        """HTML 特殊字符应被转义"""
        risks = [{
            "key": "R-1", "summary": '<script>alert("xss")</script>',
            "priority": "Low", "status": "Open", "assignee": "甲", "target_end": "",
        }]
        result = render_risk_rows_html(risks)
        assert "<script>" not in result
        assert "&lt;script&gt;" in result

    def test_contains_link(self):
        """渲染结果应包含指向 Jira 的链接"""
        risks = [{
            "key": "R-1", "summary": "test", "priority": "Low",
            "status": "Open", "assignee": "甲", "target_end": "",
        }]
        result = render_risk_rows_html(risks)
        assert "href=" in result
        assert "/browse/R-1" in result
