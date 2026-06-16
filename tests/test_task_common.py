"""测试 tools/task_common.py 中的共享工具函数"""
import pytest
import sys, os

# mock Config 环境
os.environ["JIRA_SERVER"] = "https://jira.example.com"
os.environ["JIRA_USER"] = "test"
os.environ["JIRA_TOKEN"] = "token"
os.environ["MODEL_API_BASE"] = "https://api.example.com"
os.environ["MODEL_API_KEY"] = "sk-test"
os.environ["MODEL_NAME"] = "test-model"
os.environ["EPIC_LINK_FIELD_ID"] = "customfield_10001"

from config import Config
from tools.task_common import (
    process_additional_fields,
    build_issue_fields,
    build_task_dict,
)


class TestProcessAdditionalFields:
    def test_empty(self):
        assert process_additional_fields(None) == {}
        assert process_additional_fields({}) == {}

    def test_customfield_string(self):
        result = process_additional_fields({"customfield_12345": "High"})
        assert result == {"customfield_12345": {"value": "High"}}

    def test_non_customfield_passthrough(self):
        result = process_additional_fields({"priority": "High", "labels": ["bug"]})
        assert result == {"priority": "High", "labels": ["bug"]}

    def test_mixed(self):
        result = process_additional_fields({
            "customfield_111": "Option A",
            "summary": "test",
        })
        assert result["customfield_111"] == {"value": "Option A"}
        assert result["summary"] == "test"

    def test_target_start_display_name_maps_to_customfield(self, monkeypatch):
        monkeypatch.setattr(Config, "TARGET_START_FIELD", "customfield_16519")
        result = process_additional_fields({"Target Start": "2025-06-08"})
        assert result == {"customfield_16519": "2025-06-08"}

    def test_target_end_aliases(self, monkeypatch):
        monkeypatch.setattr(Config, "TARGET_END_FIELD", "customfield_16520")
        for alias in ("targetEnd", "Target End", "Start Date", "End Date"):
            if alias == "Start Date":
                monkeypatch.setattr(Config, "TARGET_START_FIELD", "customfield_16519")
                result = process_additional_fields({alias: "2025-06-08"})
                assert result == {"customfield_16519": "2025-06-08"}
            else:
                result = process_additional_fields({alias: "2025-12-31"})
                assert result == {"customfield_16520": "2025-12-31"}

    def test_date_customfield_not_wrapped_as_option(self, monkeypatch):
        monkeypatch.setattr(Config, "TARGET_START_FIELD", "customfield_16519")
        monkeypatch.setattr(Config, "TARGET_END_FIELD", "customfield_16520")
        result = process_additional_fields({
            "customfield_16519": "2025-06-08",
            "customfield_16520": "2025-12-31",
        })
        assert result == {
            "customfield_16519": "2025-06-08",
            "customfield_16520": "2025-12-31",
        }


class TestBuildIssueFields:
    def test_basic_fields(self):
        fields, err = build_issue_fields("KO", "测试任务", "Task")
        assert err is None
        assert fields["project"] == {"key": "KO"}
        assert fields["summary"] == "测试任务"
        assert fields["issuetype"] == {"name": "Task"}
        assert "description" not in fields

    def test_missing_required(self):
        fields, err = build_issue_fields("", "test", "Task")
        assert fields is None
        assert "缺少" in err

        fields, err = build_issue_fields("KO", "", "Task")
        assert fields is None
        assert "缺少" in err

    def test_with_description(self):
        fields, err = build_issue_fields("KO", "test", "Task", description="详情")
        assert err is None
        assert fields["description"]["content"][0]["content"][0]["text"] == "详情"

    def test_with_parent(self):
        fields, err = build_issue_fields("KO", "subtask", "Sub-task", parent_key="KO-100")
        assert err is None
        assert fields["parent"] == {"key": "KO-100"}

    def test_epic_with_subtask(self):
        fields, err = build_issue_fields("KO", "test", "Sub-task", epic_link_key="KO-50")
        assert fields is None
        assert "Epic 不能直接关联" in err

    def test_epic_link_with_field_id(self, monkeypatch):
        monkeypatch.setattr(Config, "EPIC_LINK_FIELD_ID", "customfield_10001")
        fields, err = build_issue_fields("KO", "task", "Task", epic_link_key="KO-50")
        assert err is None
        assert fields["customfield_10001"] == "KO-50"


class TestBuildTaskDict:
    def test_basic_issue(self):
        issue = {
            "key": "KO-29",
            "fields": {
                "summary": "测试任务",
                "status": {"name": "In Progress"},
                "priority": {"name": "High"},
                "assignee": {"displayName": "张三"},
                Config.TARGET_START_FIELD: "2026-06-01",
                Config.TARGET_END_FIELD: "2026-06-15",
            }
        }
        task = build_task_dict(issue)
        assert task["key"] == "KO-29"
        assert task["summary"] == "测试任务"
        assert task["status"] == "In Progress"
        assert task["priority"] == "High"
        assert task["assignee"] == "张三"

    def test_missing_fields(self):
        issue = {"key": "KO-30", "fields": {}}
        task = build_task_dict(issue)
        assert task["key"] == "KO-30"
        assert task["status"] is None
        assert task["assignee"] == "未分配"

    def test_include_assignee_false(self):
        issue = {
            "key": "KO-31",
            "fields": {"assignee": {"displayName": "李四"}}
        }
        task = build_task_dict(issue, include_assignee=False)
        assert "assignee" not in task
