"""Tests for tools.dependency_tools — Jira 依赖关系管理"""
import json
from unittest.mock import MagicMock, patch

import pytest

from tools.dependency_tools import parse_issue_links, get_issue_links, get_task_dependencies


# ── parse_issue_links ──────────────────────────────────────────

class TestParseIssueLinks:
    """测试 parse_issue_links 解析函数"""

    def test_empty_links(self):
        """空列表应返回空 incoming 和 outgoing"""
        incoming, outgoing = parse_issue_links([])
        assert incoming == []
        assert outgoing == []

    def test_inward_link(self):
        """inward 方向的链接应归入 incoming"""
        links = [{
            "type": {"name": "Blocks"},
            "direction": "inward",
            "outwardIssue": {
                "key": "KO-10",
                "fields": {
                    "summary": "阻塞任务",
                    "status": {"name": "In Progress"},
                },
            },
        }]
        incoming, outgoing = parse_issue_links(links)
        assert len(incoming) == 1
        assert incoming[0]["key"] == "KO-10"
        assert incoming[0]["type"] == "Blocks"
        assert incoming[0]["status"] == "In Progress"
        assert outgoing == []

    def test_outward_link(self):
        """outward 方向的链接应归入 outgoing"""
        links = [{
            "type": {"name": "Depends"},
            "direction": "outward",
            "inwardIssue": {
                "key": "KO-20",
                "fields": {
                    "summary": "被依赖任务",
                    "status": {"name": "Done"},
                },
            },
        }]
        incoming, outgoing = parse_issue_links(links)
        assert incoming == []
        assert len(outgoing) == 1
        assert outgoing[0]["key"] == "KO-20"
        assert outgoing[0]["type"] == "Depends"

    def test_mixed_links(self):
        """同时包含 inward 和 outward 链接"""
        links = [
            {
                "type": {"name": "Blocks"},
                "direction": "inward",
                "outwardIssue": {
                    "key": "KO-10",
                    "fields": {"summary": "A", "status": {"name": "Open"}},
                },
            },
            {
                "type": {"name": "Relates"},
                "direction": "outward",
                "inwardIssue": {
                    "key": "KO-20",
                    "fields": {"summary": "B", "status": {"name": "Done"}},
                },
            },
        ]
        incoming, outgoing = parse_issue_links(links)
        assert len(incoming) == 1
        assert len(outgoing) == 1

    def test_none_links_skipped(self):
        """列表中的 None 项应被跳过"""
        links = [None, {
            "type": {"name": "Blocks"},
            "direction": "inward",
            "outwardIssue": {
                "key": "KO-10",
                "fields": {"summary": "A", "status": {"name": "Open"}},
            },
        }]
        incoming, outgoing = parse_issue_links(links)
        assert len(incoming) == 1

    def test_missing_type(self):
        """缺失 type 字段时应使用默认值"""
        links = [{
            "direction": "inward",
            "outwardIssue": {
                "key": "KO-10",
                "fields": {"summary": "A", "status": {"name": "Open"}},
            },
        }]
        incoming, outgoing = parse_issue_links(links)
        assert incoming[0]["type"] == "未知"


# ── get_issue_links ────────────────────────────────────────────

class TestGetIssueLinks:
    """测试 get_issue_links @tool 函数"""

    def test_returns_json_with_deps(self):
        """应返回包含 incoming/outgoing 的 JSON"""
        with patch("tools.dependency_tools.jira") as mock_jira:
            mock_jira.get_issue.return_value = {
                "key": "KO-29",
                "fields": {
                    "issuelinks": [{
                        "type": {"name": "Blocks"},
                        "direction": "inward",
                        "outwardIssue": {
                            "key": "KO-10",
                            "fields": {"summary": "A", "status": {"name": "Open"}},
                        },
                    }],
                },
            }
            result = get_issue_links.invoke({"issue_key": "KO-29"})
            data = json.loads(result)
            assert data["key"] == "KO-29"
            assert len(data["incoming"]) == 1
            assert data["incoming"][0]["key"] == "KO-10"

    def test_missing_issue_key(self):
        """缺少 issue_key 时应返回错误"""
        with patch("tools.dependency_tools.jira"):
            result = get_issue_links.invoke({"issue_key": ""})
            data = json.loads(result)
            assert "error" in data

    def test_api_error(self):
        """API 错误时应返回 error JSON"""
        with patch("tools.dependency_tools.jira") as mock_jira:
            mock_jira.get_issue.side_effect = Exception("API Error")
            result = get_issue_links.invoke({"issue_key": "KO-99"})
            data = json.loads(result)
            assert "error" in data


# ── get_task_dependencies ──────────────────────────────────────

class TestGetTaskDependencies:
    """测试 get_task_dependencies @tool 函数"""

    def test_returns_risk_analysis(self):
        """应返回依赖列表和风险分析"""
        with patch("tools.dependency_tools.jira") as mock_jira:
            mock_jira.get_issue.return_value = {
                "key": "KO-29",
                "fields": {
                    "summary": "测试任务",
                    "issuelinks": [{
                        "type": {"name": "Depends"},
                        "direction": "outward",
                        "inwardIssue": {
                            "key": "KO-20",
                            "fields": {"summary": "B", "status": {"name": "In Progress"}},
                        },
                    }],
                },
            }
            result = get_task_dependencies.invoke({"issue_key": "KO-29"})
            data = json.loads(result)
            assert data["key"] == "KO-29"
            assert "risk_analysis" in data
            assert len(data["outgoing_dependencies"]) == 1

    def test_no_risk_when_all_done(self):
        """当所有依赖已完成时，不应报风险"""
        with patch("tools.dependency_tools.jira") as mock_jira:
            mock_jira.get_issue.return_value = {
                "key": "KO-29",
                "fields": {
                    "summary": "测试任务",
                    "issuelinks": [{
                        "type": {"name": "Depends"},
                        "direction": "outward",
                        "inwardIssue": {
                            "key": "KO-20",
                            "fields": {"summary": "B", "status": {"name": "Done"}},
                        },
                    }],
                },
            }
            result = get_task_dependencies.invoke({"issue_key": "KO-29"})
            data = json.loads(result)
            assert "无明显依赖风险" in str(data["risk_analysis"])
