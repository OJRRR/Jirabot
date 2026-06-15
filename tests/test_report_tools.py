"""Tests for tools.report_tools — Jira 报告生成工具"""
import os
import json
from datetime import datetime, date
from unittest.mock import MagicMock, patch

import pytest

from tools.report_tools import (
    _parse_target_date,
    _normalize_target,
    calculate_task_weight,
    calculate_task_progress,
    calculate_project_progress,
    analyze_project_risk,
    _is_blocked_by_inward_link,
    _esc,
    generate_report,
    generate_portfolio_report,
)


# ── _parse_target_date ────────────────────────────────────────

class TestParseTargetDate:
    def test_valid_date_str(self):
        assert _parse_target_date("2026-06-15") == date(2026, 6, 15)

    def test_datetime_str(self):
        assert _parse_target_date("2026-06-15T10:00:00.000+0800") == date(2026, 6, 15)

    def test_none_value(self):
        assert _parse_target_date(None) is None
        assert _parse_target_date("None") is None
        assert _parse_target_date("null") is None

    def test_empty(self):
        assert _parse_target_date("") is None

    def test_invalid_format(self):
        assert _parse_target_date("not-a-date") is None


# ── _normalize_target ─────────────────────────────────────────

class TestNormalizeTarget:
    def test_none_strings(self):
        assert _normalize_target(None) is None
        assert _normalize_target("None") is None
        assert _normalize_target("null") is None
        assert _normalize_target("") is None

    def test_valid_value(self):
        assert _normalize_target("2026-06-15") == "2026-06-15"


# ── calculate_task_weight ─────────────────────────────────────

class TestCalculateTaskWeight:
    def test_no_fields(self):
        assert calculate_task_weight(None) == 1

    def test_no_dates(self):
        assert calculate_task_weight({}) == 1

    def test_with_dates(self, monkeypatch):
        monkeypatch.setattr("config.Config.TARGET_START_FIELD", "customfield_start")
        monkeypatch.setattr("config.Config.TARGET_END_FIELD", "customfield_end")
        fields = {
            "customfield_start": "2026-06-01",
            "customfield_end": "2026-06-15",
        }
        weight = calculate_task_weight(fields)
        assert weight == 14  # 15 - 1 = 14 days

    def test_same_day(self, monkeypatch):
        monkeypatch.setattr("config.Config.TARGET_START_FIELD", "customfield_start")
        monkeypatch.setattr("config.Config.TARGET_END_FIELD", "customfield_end")
        fields = {
            "customfield_start": "2026-06-15",
            "customfield_end": "2026-06-15",
        }
        weight = calculate_task_weight(fields)
        assert weight == 1  # min 1 day


# ── calculate_task_progress ───────────────────────────────────

class TestCalculateTaskProgress:
    def test_done_status(self, monkeypatch):
        monkeypatch.setattr("config.Config.TARGET_START_FIELD", "cf_start")
        monkeypatch.setattr("config.Config.TARGET_END_FIELD", "cf_end")
        fields = {"status": {"name": "Done"}}
        progress, weight = calculate_task_progress(fields)
        assert progress == 100

    def test_todo_status(self, monkeypatch):
        monkeypatch.setattr("config.Config.TARGET_START_FIELD", "cf_start")
        monkeypatch.setattr("config.Config.TARGET_END_FIELD", "cf_end")
        fields = {"status": {"name": "To Do"}}
        progress, weight = calculate_task_progress(fields)
        assert progress == 0

    def test_in_progress_with_dates(self, monkeypatch):
        monkeypatch.setattr("config.Config.TARGET_START_FIELD", "cf_start")
        monkeypatch.setattr("config.Config.TARGET_END_FIELD", "cf_end")
        today = date.today()
        start = today.replace(day=1)
        # end 在下个月
        if today.month == 12:
            end = today.replace(year=today.year + 1, month=1, day=1)
        else:
            end = today.replace(month=today.month + 1, day=1)
        fields = {
            "status": {"name": "In Progress"},
            "cf_start": start.strftime("%Y-%m-%d"),
            "cf_end": end.strftime("%Y-%m-%d"),
        }
        progress, weight = calculate_task_progress(fields)
        assert 5 <= progress <= 95  # clamped range

    def test_in_progress_no_dates(self, monkeypatch):
        monkeypatch.setattr("config.Config.TARGET_START_FIELD", "cf_start")
        monkeypatch.setattr("config.Config.TARGET_END_FIELD", "cf_end")
        fields = {"status": {"name": "In Progress"}}
        progress, weight = calculate_task_progress(fields)
        assert progress == 50  # default

    def test_none_fields(self):
        progress, weight = calculate_task_progress(None)
        assert progress == 0
        assert weight == 1


# ── calculate_project_progress ────────────────────────────────

class TestCalculateProjectProgress:
    def test_empty_issues(self):
        progress, total, completed = calculate_project_progress([])
        assert progress == 0
        assert total == 0

    def test_all_done(self, monkeypatch):
        monkeypatch.setattr("config.Config.TARGET_START_FIELD", "cf_start")
        monkeypatch.setattr("config.Config.TARGET_END_FIELD", "cf_end")
        issues = [
            {"fields": {"status": {"name": "Done"}}},
            {"fields": {"status": {"name": "Done"}}},
        ]
        progress, total, completed = calculate_project_progress(issues)
        assert progress == 100

    def test_skips_none_issues(self):
        progress, total, completed = calculate_project_progress([None])
        assert total == 0


# ── analyze_project_risk ──────────────────────────────────────

class TestAnalyzeProjectRisk:
    def test_low_risk(self):
        level, risks = analyze_project_risk(progress=90, overdue_count=0, blocked_count=0, high_priority_count=0)
        assert "低风险" in level

    def test_high_risk_low_progress(self):
        level, risks = analyze_project_risk(progress=5, overdue_count=10, blocked_count=5, high_priority_count=8)
        assert "高风险" in level

    def test_medium_risk(self):
        level, risks = analyze_project_risk(progress=50, overdue_count=3, blocked_count=2, high_priority_count=3)
        assert "中风险" in level


# ── _is_blocked_by_inward_link ────────────────────────────────

class TestIsBlockedByInwardLink:
    def test_no_links(self):
        assert not _is_blocked_by_inward_link(None)
        assert not _is_blocked_by_inward_link([])

    def test_blocks_inward(self):
        links = [{
            "type": {"name": "Blocks"},
            "direction": "inward",
        }]
        assert _is_blocked_by_inward_link(links)

    def test_non_blocks_inward(self):
        links = [{
            "type": {"name": "Relates"},
            "direction": "inward",
        }]
        assert not _is_blocked_by_inward_link(links)


# ── _esc ──────────────────────────────────────────────────────

class TestEsc:
    def test_none(self):
        assert _esc(None) == ""

    def test_safe_string(self):
        assert _esc("hello") == "hello"

    def test_html_chars(self):
        assert _esc("<script>") == "&lt;script&gt;"
        assert _esc('"quote"') == "&quot;quote&quot;"


# ── generate_report ───────────────────────────────────────────

class TestGenerateReport:
    def test_no_project_found(self):
        """无可用项目时应返回错误"""
        with patch("tools.report_tools.jira") as mock_jira:
            mock_jira.get_all_projects.return_value = []
            with patch("config.Config.TARGET_PROJECTS", []):
                result = generate_report.invoke({})
                assert "无法确定" in result or "❌" in result


# ── generate_portfolio_report ─────────────────────────────────

class TestGeneratePortfolioReport:
    def test_no_projects(self):
        with patch("tools.report_tools.jira") as mock_jira:
            mock_jira.get_all_projects.return_value = []
            with patch("config.Config.TARGET_PROJECTS", []):
                result = generate_portfolio_report.invoke({})
                assert "无法确定" in result or "❌" in result
