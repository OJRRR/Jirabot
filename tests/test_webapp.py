"""Webapp 集成测试 — Flask test client"""
import json
import pytest
from unittest.mock import patch, MagicMock


@pytest.fixture
def app():
    """创建测试用的 Flask app，mock 掉 agent 避免真实 LLM 调用"""
    with patch("webapp.agent", None), \
         patch("webapp.jira_client") as mock_jira:
        mock_jira.is_offline = False
        from webapp import app
        app.config["TESTING"] = True
        yield app


@pytest.fixture
def client(app):
    return app.test_client()


class TestHealthCheck:
    def test_health_returns_ok(self, client):
        resp = client.get("/health")
        assert resp.status_code == 200
        data = json.loads(resp.data)
        assert data["status"] == "ok"
        assert "agent" in data
        assert "jira" in data


class TestHomePage:
    def test_homepage_returns_200(self, client):
        resp = client.get("/")
        assert resp.status_code == 200
        assert b"<!DOCTYPE html>" in resp.data or b"<html" in resp.data


class TestChatAPI:
    def test_chat_offline_returns_503(self, client):
        resp = client.post("/api/chat",
                           json={"message": "你好"},
                           content_type="application/json")
        assert resp.status_code == 503
        data = json.loads(resp.data)
        assert "error" in data

    def test_chat_stream_offline_returns_503(self, client):
        resp = client.post("/api/chat/stream",
                           json={"message": "你好"},
                           content_type="application/json")
        assert resp.status_code == 503
        data = json.loads(resp.data)
        assert "error" in data

    def test_chat_missing_message(self, client):
        resp = client.post("/api/chat",
                           json={},
                           content_type="application/json")
        assert resp.status_code == 400

    def test_chat_stream_missing_message(self, client):
        resp = client.post("/api/chat/stream",
                           json={},
                           content_type="application/json")
        assert resp.status_code == 400


class TestFileUpload:
    def test_upload_no_file_returns_400(self, client):
        resp = client.post("/api/upload")
        assert resp.status_code == 400


class TestReportRoutes:
    def test_report_not_found(self, client):
        resp = client.get("/report/nonexistent.html")
        assert resp.status_code == 404
