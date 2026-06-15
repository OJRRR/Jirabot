"""Tests for tools.risk_extractor — Jira 风险提取工具"""
import json
from unittest.mock import MagicMock, patch

import pytest

from tools.risk_extractor import get_project_risks, extract_issue_risks, _generate_risk_summary


# ── get_project_risks ─────────────────────────────────────────

class TestGetProjectRisks:
    """测试 get_project_risks 函数"""

    def test_empty_project(self):
        """无 Risk 类型的项目应返回空列表"""
        with patch("tools.risk_extractor.jira") as mock_jira:
            mock_jira.jql.return_value = {"issues": []}
            result = get_project_risks("KO")
            assert result["project"] == "KO"
            assert result["risks"] == []
            assert result["error"] is None

    def test_with_risks(self):
        """应正确解析 Risk 类型 issue"""
        with patch("tools.risk_extractor.jira") as mock_jira:
            mock_jira.jql.return_value = {
                "issues": [{
                    "key": "RISK-1",
                    "fields": {
                        "summary": "高风险项",
                        "description": "这是一个风险描述",
                        "status": {"name": "Open"},
                        "priority": {"name": "High"},
                        "assignee": {"displayName": "张三"},
                        "created": "2026-06-01T10:00:00.000+0800",
                    },
                }],
            }
            result = get_project_risks("KO")
            assert result["total"] == 1
            assert len(result["risks"]) == 1
            assert result["risks"][0]["key"] == "RISK-1"
            assert result["risks"][0]["priority"] == "High"
            assert result["risks"][0]["assignee"] == "张三"

    def test_api_error(self):
        """API 错误应返回 error 字段"""
        with patch("tools.risk_extractor.jira") as mock_jira:
            mock_jira.jql.side_effect = Exception("API Error")
            result = get_project_risks("KO")
            assert result["error"] is not None


# ── extract_issue_risks ───────────────────────────────────────

class TestExtractIssueRisks:
    """测试 extract_issue_risks @tool 函数"""

    def test_no_projects(self):
        """无项目时应返回提示"""
        with patch("tools.risk_extractor.jira") as mock_jira:
            mock_jira.get_all_projects.return_value = []
            with patch("config.Config.TARGET_PROJECTS", []):
                # project_key 是 str 类型，传空字符串表示不指定
                result = extract_issue_risks.invoke({"project_key": ""})
                assert "无法确定" in result

    def test_no_risks_found(self):
        """无 Risk issue 时应返回提示"""
        # 直接 patch get_project_risks 返回空结果
        with patch("tools.risk_extractor.get_project_risks",
                   return_value={"project": "KO", "risks": [], "total": 0, "error": None}):
            with patch("config.Config.TARGET_PROJECTS", ["KO"]):
                result = extract_issue_risks.invoke({"project_key": "KO"})
                assert "未发现" in result

    def test_summary_only_mode(self):
        """summary_only=True 应返回精简版"""
        with patch("tools.risk_extractor.jira") as mock_jira:
            mock_jira.jql.return_value = {
                "issues": [{
                    "key": "RISK-1",
                    "fields": {
                        "summary": "高风险项",
                        "description": "desc",
                        "status": {"name": "Open"},
                        "priority": {"name": "Highest"},
                        "assignee": {"displayName": "张三"},
                        "created": "2026-06-01T10:00:00.000+0800",
                    },
                }],
            }
            with patch("config.Config.TARGET_PROJECTS", ["KO"]):
                result = extract_issue_risks.invoke({"project_key": "KO", "summary_only": True})
                assert "概览" in result
                # 精简版不应有长分隔线
                assert "=" * 60 not in result


# ── _generate_risk_summary ────────────────────────────────────

class TestGenerateRiskSummary:
    """测试 _generate_risk_summary 内部函数"""

    def test_zero_risks(self):
        result = _generate_risk_summary([], 0, {}, {}, [], [], False)
        assert "未发现" in result

    def test_with_risks(self):
        all_risks = [{"project": "KO", "risks": [], "total": 1, "error": None}]
        result = _generate_risk_summary(
            all_risks, 1,
            {"High": 1}, {"Open": 1},
            [], [], False,
        )
        assert "1 个风险项" in result

    def test_summary_only(self):
        result = _generate_risk_summary(
            [], 5,
            {"High": 3, "Medium": 2}, {"Open": 5},
            [{"key": "R-1", "project": "KO", "summary": "urgent", "status": "Open", "assignee": "甲"}],
            [{"key": "R-1", "project": "KO", "summary": "urgent", "priority": "High", "status": "Open", "assignee": "甲"}],
            summary_only=True,
        )
        assert "概览" in result
        assert "=" * 60 not in result
