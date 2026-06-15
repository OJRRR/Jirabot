"""pytest 共享 fixtures 和 mock 配置"""
import sys
import os

import pytest
from unittest.mock import MagicMock

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

# 确保 Config 所需的环境变量存在（避免导入时炸）
os.environ.setdefault("JIRA_SERVER", "https://jira.example.com")
os.environ.setdefault("JIRA_USER", "test")
os.environ.setdefault("JIRA_TOKEN", "test-token")
os.environ.setdefault("MODEL_API_BASE", "https://api.example.com")
os.environ.setdefault("MODEL_API_KEY", "sk-test")
os.environ.setdefault("MODEL_NAME", "test-model")
os.environ.setdefault("EPIC_LINK_FIELD_ID", "customfield_10001")


def _build_mock_client():
    """构建一个带预设返回值的 mock JiraClient。"""
    client = MagicMock()
    client.get_issue.return_value = {
        "id": "10001",
        "key": "TEST-1",
        "fields": {
            "summary": "Test Issue",
            "status": {"name": "In Progress"},
            "priority": {"name": "Medium"},
            "assignee": {"displayName": "Test User"},
            "issuelinks": [],
        },
    }
    client.jql.return_value = {"issues": []}
    client.search_issues.return_value = []
    client.create_issue.return_value = {"id": "20000", "key": "TEST-NEW"}
    client.create_issue_link.return_value = {"id": "link123"}
    client.delete_issue_link.return_value = True
    client.update_issue.return_value = {"id": "10001", "key": "TEST-1"}
    client.delete_issue.return_value = True
    client.get_all_projects.return_value = []
    client.get_issue_transitions.return_value = []
    client.get_issue_createmeta.return_value = {}
    client.bulk_create_issues.return_value = {"created": [], "errors": []}
    return client


@pytest.fixture(autouse=True)
def _block_real_jira(monkeypatch):
    """全局阻止 JiraClient 创建真实连接。

    通过将 JiraClient 单例 _instance 预置为 MagicMock，
    后续任何 LazyJira 属性访问都不会发出真实 HTTP 请求。
    """
    from jira_client import JiraClient

    mock = _build_mock_client()
    monkeypatch.setattr(JiraClient, "_instance", mock)
    return mock


@pytest.fixture
def mock_jira_client(_block_real_jira):
    """创建一个 mock JiraClient（兼容旧测试命名）"""
    return _block_real_jira


@pytest.fixture
def sample_issue_dict():
    """返回一个标准的 issue dict 样本。"""
    return {
        "id": "10001",
        "key": "PROJ-123",
        "fields": {
            "summary": "测试任务",
            "status": {"name": "In Progress"},
            "priority": {"name": "High"},
            "assignee": {"displayName": "张三"},
        },
    }


@pytest.fixture
def sample_issues_list():
    """返回两个 issue dict 的列表。"""
    return [
        {
            "id": "10001",
            "key": "PROJ-123",
            "fields": {
                "summary": "Task A",
                "status": {"name": "Done"},
                "priority": {"name": "High"},
            },
        },
        {
            "id": "10002",
            "key": "PROJ-456",
            "fields": {
                "summary": "Task B",
                "status": {"name": "In Progress"},
                "priority": {"name": "Medium"},
            },
        },
    ]


@pytest.fixture
def sample_risk_fields():
    """返回一组风险字段样本。"""
    return {
        "key": "RISK-1",
        "summary": "高风险项",
        "priority": "High",
        "status": "Open",
        "assignee": "李四",
        "target_end": "2026-06-30",
    }
