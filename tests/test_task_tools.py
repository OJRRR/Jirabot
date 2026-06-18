"""Tests for tools.task_tools — Jira 任务查询与创建工具"""
import json
from unittest.mock import MagicMock, patch

import pytest

from tools.task_tools import (
    get_my_tasks,
    get_project_tasks,
    search_issues,
    get_create_issue_metadata,
    create_issue,
    create_issue_link,
    get_issue_transitions,
    update_issue,
    add_issue_comment,
    add_issue_worklog,
    batch_create_issues,
    assign_issue,
    delete_issue,
    import_from_excel,
    batch_update_dates,
    batch_update_issues,
    suggest_epic_tasks,
    analyze_meeting_for_projects,
)


# ── 查询工具 ──────────────────────────────────────────────────

class TestGetMyTasks:
    """测试 get_my_tasks @tool 函数"""

    def test_returns_tasks(self):
        with patch("tools.task_tools.jira") as mock_jira:
            mock_jira.jql.return_value = {
                "issues": [{
                    "key": "KO-29",
                    "fields": {
                        "summary": "测试任务",
                        "status": {"name": "In Progress"},
                        "priority": {"name": "High"},
                        "assignee": {"displayName": "张三"},
                    },
                }],
            }
            result = get_my_tasks.invoke({})
            data = json.loads(result)
            assert data["success"] is True
            assert data["total"] == 1
            assert data["tasks"][0]["key"] == "KO-29"

    def test_empty_result(self):
        with patch("tools.task_tools.jira") as mock_jira:
            mock_jira.jql.return_value = {"issues": []}
            result = get_my_tasks.invoke({})
            data = json.loads(result)
            assert data["success"] is True
            assert data["total"] == 0

    def test_api_error(self):
        with patch("tools.task_tools.jira") as mock_jira:
            mock_jira.jql.side_effect = Exception("API Error")
            result = get_my_tasks.invoke({})
            data = json.loads(result)
            assert "error" in data


class TestGetProjectTasks:
    """测试 get_project_tasks @tool 函数"""

    def test_returns_tasks(self):
        with patch("tools.task_tools.jira") as mock_jira:
            mock_jira.jql.return_value = {
                "issues": [{
                    "key": "KO-1",
                    "fields": {
                        "summary": "项目任务",
                        "status": {"name": "To Do"},
                        "priority": {"name": "Medium"},
                    },
                }],
            }
            result = get_project_tasks.invoke({"project_key": "KO"})
            data = json.loads(result)
            assert data["success"] is True
            assert data["project"] == "KO"

    def test_missing_project_key(self):
        """缺少 project_key 时应报错"""
        result = get_project_tasks.invoke({"project_key": ""})
        data = json.loads(result)
        assert "error" in data


class TestSearchIssues:
    """测试 search_issues @tool 函数"""

    def test_no_conditions(self):
        """无搜索条件时应报错"""
        result = search_issues.invoke({})
        data = json.loads(result)
        assert "error" in data

    def test_with_project_filter(self):
        with patch("tools.task_tools.jira") as mock_jira:
            mock_jira.jql.return_value = {"issues": []}
            result = search_issues.invoke({"project": "KO"})
            data = json.loads(result)
            assert data["success"] is True

    def test_with_all_filters(self):
        with patch("tools.task_tools.jira") as mock_jira:
            mock_jira.jql.return_value = {"issues": []}
            result = search_issues.invoke({
                "project": "KO",
                "status": "In Progress",
                "assignee": "zhangsan",
                "priority": "High",
                "issue_type": "Task",
                "query": "搜索词",
            })
            data = json.loads(result)
            assert data["success"] is True

    def test_assignee_me(self):
        """assignee=me 应转换为 currentUser()"""
        with patch("tools.task_tools.jira") as mock_jira:
            mock_jira.jql.return_value = {"issues": []}
            result = search_issues.invoke({"assignee": "me"})
            data = json.loads(result)
            assert "currentUser()" in data["jql"]


# ── 创建 / 更新 / 写入类工具 ──────────────────────────────────

class TestCreateIssue:
    """测试 create_issue @tool 函数"""

    def test_missing_required_fields(self):
        """缺少必填字段时应报错"""
        result = create_issue.invoke({"project_key": "KO"})
        assert "失败" in result

    def test_create_success(self):
        with patch("tools.task_tools.jira") as mock_jira:
            mock_jira.create_issue.return_value = {"key": "KO-100"}
            result = create_issue.invoke({
                "project_key": "KO",
                "summary": "新任务",
                "issue_type": "Task",
            })
            assert "成功" in result
            assert "KO-100" in result

    def test_create_with_description(self):
        with patch("tools.task_tools.jira") as mock_jira:
            mock_jira.create_issue.return_value = {"key": "KO-101"}
            result = create_issue.invoke({
                "project_key": "KO",
                "summary": "带描述的任务",
                "issue_type": "Task",
                "description": "这是描述",
            })
            assert "成功" in result

    def test_api_error(self):
        with patch("tools.task_tools.jira") as mock_jira:
            mock_jira.create_issue.side_effect = Exception("API Error")
            result = create_issue.invoke({
                "project_key": "KO",
                "summary": "test",
                "issue_type": "Task",
            })
            assert "失败" in result


class TestCreateIssueLink:
    """测试 create_issue_link @tool 函数"""

    def test_missing_keys(self):
        result = create_issue_link.invoke({"inward_issue_key": "KO-1"})
        assert "失败" in result

    def test_create_link_success(self):
        with patch("tools.task_tools.jira") as mock_jira:
            mock_jira.create_issue_link.return_value = True
            result = create_issue_link.invoke({
                "inward_issue_key": "KO-1",
                "outward_issue_key": "KO-2",
            })
            assert "成功" in result


class TestUpdateIssue:
    """测试 update_issue @tool 函数"""

    def test_missing_key(self):
        result = update_issue.invoke({"issue_key": ""})
        assert "失败" in result

    def test_no_fields(self):
        result = update_issue.invoke({"issue_key": "KO-29"})
        assert "失败" in result

    def test_update_success(self):
        with patch("tools.task_tools.jira") as mock_jira:
            result = update_issue.invoke({
                "issue_key": "KO-29",
                "summary": "更新后的标题",
            })
            assert "成功" in result


class TestAddIssueComment:
    """测试 add_issue_comment @tool 函数"""

    def test_missing_fields(self):
        result = add_issue_comment.invoke({"issue_key": "KO-29"})
        assert "失败" in result

    def test_add_comment_success(self):
        with patch("tools.task_tools.jira") as mock_jira:
            result = add_issue_comment.invoke({
                "issue_key": "KO-29",
                "comment": "测试评论",
            })
            assert "成功" in result


class TestAddIssueWorklog:
    """测试 add_issue_worklog @tool 函数"""

    def test_missing_fields(self):
        result = add_issue_worklog.invoke({"issue_key": "KO-29"})
        assert "失败" in result

    def test_add_worklog_success(self):
        with patch("tools.task_tools.jira") as mock_jira:
            result = add_issue_worklog.invoke({
                "issue_key": "KO-29",
                "time_spent": "2h",
            })
            assert "成功" in result


class TestAssignIssue:
    """测试 assign_issue @tool 函数"""

    def test_missing_fields(self):
        result = assign_issue.invoke({"issue_key": "KO-29"})
        assert "失败" in result

    def test_assign_success(self):
        with patch("tools.task_tools.jira") as mock_jira:
            result = assign_issue.invoke({
                "issue_key": "KO-29",
                "assignee": "zhangsan",
            })
            assert "已将" in result


class TestDeleteIssue:
    """测试 delete_issue @tool 函数"""

    def test_missing_key(self):
        result = delete_issue.invoke({"issue_key": ""})
        assert "失败" in result

    def test_not_confirmed(self):
        """未确认时应返回确认提示"""
        result = delete_issue.invoke({"issue_key": "KO-29"})
        assert "确认" in result

    def test_confirmed_delete(self):
        with patch("tools.task_tools.jira") as mock_jira:
            result = delete_issue.invoke({
                "issue_key": "KO-29",
                "confirmed": True,
            })
            assert "成功" in result


class TestGetIssueTransitions:
    """测试 get_issue_transitions @tool 函数"""

    def test_missing_key(self):
        result = get_issue_transitions.invoke({"issue_key": ""})
        data = json.loads(result)
        assert "error" in data

    def test_no_transitions(self):
        with patch("tools.task_tools.jira") as mock_jira:
            mock_jira.get_issue_transitions.return_value = []
            result = get_issue_transitions.invoke({"issue_key": "KO-29"})
            data = json.loads(result)
            assert "没有可用的状态转换" in data.get("message", "")


class TestBatchCreateIssues:
    """测试 batch_create_issues @tool 函数"""

    def test_empty_input(self):
        result = batch_create_issues.invoke({"issues_json": ""})
        assert "失败" in result

    def test_invalid_json(self):
        result = batch_create_issues.invoke({"issues_json": "not json"})
        assert "失败" in result

    def test_empty_tasks(self):
        result = batch_create_issues.invoke({"issues_json": '{"tasks": []}'})
        assert "失败" in result

    def test_batch_create_success(self):
        with patch("tools.task_tools.jira") as mock_jira:
            mock_jira.bulk_create_issues.return_value = {
                "created": [{"key": "KO-200"}, {"key": "KO-201"}],
                "errors": [],
            }
            tasks_json = json.dumps({
                "tasks": [
                    {"project_key": "KO", "summary": "任务1", "issue_type": "Task"},
                    {"project_key": "KO", "summary": "任务2", "issue_type": "Task"},
                ]
            })
            result = batch_create_issues.invoke({"issues_json": tasks_json})
            assert "成功: 2" in result


class TestBatchUpdateDates:
    """测试 batch_update_dates @tool 函数"""

    def test_empty_input(self):
        result = batch_update_dates.invoke({"updates_json": ""})
        assert "失败" in result

    def test_empty_updates(self):
        result = batch_update_dates.invoke({"updates_json": '{"updates": []}'})
        assert "失败" in result

    def test_update_success(self):
        with patch("tools.task_tools.jira") as mock_jira:
            updates_json = json.dumps({
                "updates": [
                    {"issue_key": "KO-29", "start_date": "2026-06-01", "end_date": "2026-06-15"},
                ]
            })
            result = batch_update_dates.invoke({"updates_json": updates_json})
            assert "成功: 1" in result

    def test_missing_date_fields(self):
        """缺少 start_date 和 end_date 时应失败"""
        with patch("tools.task_tools.jira"):
            updates_json = json.dumps({
                "updates": [{"issue_key": "KO-29"}]
            })
            result = batch_update_dates.invoke({"updates_json": updates_json})
            assert "成功: 0" in result


class TestGetCreateIssueMetadata:
    """测试 get_create_issue_metadata @tool 函数"""

    def test_missing_project(self):
        result = get_create_issue_metadata.invoke({"project_key": ""})
        data = json.loads(result)
        assert "error" in data

    def test_no_metadata(self):
        with patch("tools.task_tools.jira") as mock_jira:
            mock_jira.get_issue_createmeta.return_value = {}
            result = get_create_issue_metadata.invoke({"project_key": "KO"})
            data = json.loads(result)
            assert "error" in data


class TestBatchUpdateIssues:
    """测试 batch_update_issues @tool 函数"""

    def test_empty_input(self):
        result = batch_update_issues.invoke({"updates_json": ""})
        assert "失败" in result

    def test_empty_updates(self):
        result = batch_update_issues.invoke({"updates_json": '{"updates": []}'})
        assert "失败" in result

    def test_missing_issue_key(self):
        updates_json = json.dumps({"updates": [{"assignee": "张三"}]})
        result = batch_update_issues.invoke({"updates_json": updates_json})
        assert "成功: 0" in result

    def test_no_fields_to_update(self):
        updates_json = json.dumps({"updates": [{"issue_key": "KO-1"}]})
        result = batch_update_issues.invoke({"updates_json": updates_json})
        assert "成功: 0" in result

    def test_assign_success(self):
        with patch("tools.task_tools.jira") as mock_jira:
            updates_json = json.dumps({
                "updates": [{"issue_key": "KO-1", "assignee": "张三"}]
            })
            result = batch_update_issues.invoke({"updates_json": updates_json})
            assert "成功: 1" in result
            assert "负责人→张三" in result

    def test_assign_and_transition_and_priority(self):
        with patch("tools.task_tools.jira") as mock_jira:
            updates_json = json.dumps({
                "updates": [{
                    "issue_key": "KO-1",
                    "assignee": "张三",
                    "status": "In Progress",
                    "priority": "High"
                }]
            })
            result = batch_update_issues.invoke({"updates_json": updates_json})
            assert "成功: 1" in result
            assert "负责人→张三" in result
            assert "状态→In Progress" in result
            assert "优先级→High" in result

    def test_mixed_success_and_failure(self):
        with patch("tools.task_tools.jira") as mock_jira:
            mock_jira.assign_issue.side_effect = Exception("分配失败")
            updates_json = json.dumps({
                "updates": [
                    {"issue_key": "KO-1", "assignee": "张三"},
                    {"issue_key": "KO-2", "assignee": "李四"},
                ]
            })
            result = batch_update_issues.invoke({"updates_json": updates_json})
            assert "成功: 0" in result


class TestSuggestEpicTasks:
    """测试 suggest_epic_tasks @tool 函数"""

    def test_missing_key(self):
        result = suggest_epic_tasks.invoke({"epic_key": ""})
        data = json.loads(result)
        assert "error" in data

    def test_not_an_epic(self):
        with patch("tools.task_tools.jira") as mock_jira:
            mock_jira.get_issue.return_value = {
                "key": "KO-100",
                "fields": {
                    "summary": "不是Epic",
                    "issuetype": {"name": "Task"},
                    "status": {"name": "To Do"},
                },
            }
            result = suggest_epic_tasks.invoke({"epic_key": "KO-100"})
            data = json.loads(result)
            assert "warning" in data

    def test_epic_with_details(self):
        with patch("tools.task_tools.jira") as mock_jira:
            mock_jira.get_issue.return_value = {
                "key": "KO-100",
                "fields": {
                    "summary": "用户登录模块",
                    "description": "实现用户登录功能",
                    "issuetype": {"name": "Epic"},
                    "status": {"name": "To Do"},
                    "assignee": {"displayName": "张三"},
                },
            }
            mock_jira.jql.return_value = {"issues": []}
            result = suggest_epic_tasks.invoke({"epic_key": "KO-100"})
            data = json.loads(result)
            assert data["epic_key"] == "KO-100"
            assert data["summary"] == "用户登录模块"
            assert data["existing_count"] == 0
            assert "hint" in data

    def test_epic_with_existing_subtasks(self):
        with patch("tools.task_tools.jira") as mock_jira:
            mock_jira.get_issue.return_value = {
                "key": "KO-100",
                "fields": {
                    "summary": "用户登录模块",
                    "issuetype": {"name": "Epic"},
                    "status": {"name": "In Progress"},
                },
            }
            mock_jira.jql.return_value = {
                "issues": [
                    {
                        "key": "KO-101",
                        "fields": {
                            "summary": "设计登录页面",
                            "status": {"name": "Done"},
                            "assignee": {"displayName": "张三"},
                        },
                    },
                    {
                        "key": "KO-102",
                        "fields": {
                            "summary": "实现登录API",
                            "status": {"name": "In Progress"},
                            "assignee": {"displayName": "李四"},
                        },
                    },
                ]
            }
            result = suggest_epic_tasks.invoke({"epic_key": "KO-100"})
            data = json.loads(result)
            assert data["existing_count"] == 2
            assert len(data["existing_sub_tasks"]) == 2
            assert data["existing_sub_tasks"][0]["key"] == "KO-101"


class TestAnalyzeMeetingForProjects:
    """测试 analyze_meeting_for_projects @tool 函数"""

    def test_missing_params(self):
        result = analyze_meeting_for_projects.invoke({"meeting_notes": "", "project_key": ""})
        data = json.loads(result)
        assert "error" in data

    def test_missing_notes(self):
        result = analyze_meeting_for_projects.invoke({"meeting_notes": "", "project_key": "KO"})
        data = json.loads(result)
        assert "error" in data

    def test_successful_analysis(self):
        with patch("tools.task_tools.jira") as mock_jira:
            mock_jira.jql.return_value = {"issues": []}
            result = analyze_meeting_for_projects.invoke({
                "meeting_notes": "我们要做一个用户登录模块和支付模块",
                "project_key": "KO",
            })
            data = json.loads(result)
            assert data["project_key"] == "KO"
            assert "meeting_notes" in data
            assert "format_hint" in data
            assert data["meeting_notes"] == "我们要做一个用户登录模块和支付模块"

    def test_with_existing_epics(self):
        with patch("tools.task_tools.jira") as mock_jira:
            mock_jira.jql.return_value = {
                "issues": [
                    {
                        "key": "KO-100",
                        "fields": {
                            "summary": "已有Epic",
                            "issuetype": {"name": "Epic"},
                            "status": {"name": "In Progress"},
                        },
                    },
                ]
            }
            result = analyze_meeting_for_projects.invoke({
                "meeting_notes": "新增报表模块",
                "project_key": "KO",
            })
            data = json.loads(result)
            assert len(data["existing_epics"]) == 1
            assert data["existing_epics"][0]["key"] == "KO-100"
            assert data["existing_epics"][0]["summary"] == "已有Epic"
