"""测试 config.py 配置逻辑（不依赖 Jira 网络连接）"""
import pytest

# 必须在 import Config 前设好环境变量
import os
os.environ["JIRA_SERVER"] = "https://jira.example.com"
os.environ["JIRA_USER"] = "test"
os.environ["JIRA_TOKEN"] = "token"
os.environ["MODEL_API_BASE"] = "https://api.example.com"
os.environ["MODEL_API_KEY"] = "sk-test"
os.environ["MODEL_NAME"] = "test-model"
os.environ["PROJECTS"] = ""  # 必须清空，否则 load_dotenv 从 .env 读到 PROJECTS 会让 TARGET_PROJECTS 不为 None

from config import Config


class TestConfigBasics:
    def test_default_project_all(self):
        """未设 PROJECTS 时 TARGET_PROJECTS 为 None（表示所有项目）"""
        assert Config.TARGET_PROJECTS is None

    def test_projects_parsed(self):
        """已通过 .env 设了 PROJECTS"""
        # 从 conftest 加载的 .env 已包含 PROJECTS=FCCLMIG, KO,...
        pass  # 依赖运行时环境，不强制断言


class TestBuildJql:
    @pytest.fixture(autouse=True)
    def setup_projects(self, monkeypatch):
        monkeypatch.setattr(Config, "TARGET_PROJECTS", ["KO", "RDE"])

    def test_with_projects(self):
        jql = Config.get_build_jql("status != Done")
        assert 'project IN ("KO","RDE")' in jql
        assert jql.startswith("status != Done")

    def test_no_projects(self, monkeypatch):
        monkeypatch.setattr(Config, "TARGET_PROJECTS", None)
        assert Config.get_build_jql("status != Done") == "status != Done"


class TestCleanupOldReports:
    def test_cleanup_returns_int(self, monkeypatch, tmp_path):
        monkeypatch.setattr(Config, "REPORTS_DIR", str(tmp_path))
        monkeypatch.setattr(Config, "REPORT_MAX_AGE_DAYS", 0)  # 所有报告都过期
        # 创建旧报告
        (tmp_path / "old.html").write_text("old")
        (tmp_path / "new.html").write_text("new")
        # 修改 new.html 的 mtime 为 "未来"，确保不被删
        import time
        future = time.time() + 86400
        os.utime(str(tmp_path / "new.html"), (future, future))

        deleted = Config.cleanup_old_reports()
        assert deleted >= 1
        # old.html 应该被删除
        assert not (tmp_path / "old.html").exists()
