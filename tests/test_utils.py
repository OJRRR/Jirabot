"""测试 utils.py 中的工具函数"""
import pytest
from utils import validate_project_key, extract_issue_key, sanitize_jql_value


class TestValidateProjectKey:
    def test_valid_keys(self):
        assert validate_project_key("KO") == "KO"
        assert validate_project_key("ko") == "KO"
        assert validate_project_key("  ko  ") == "KO"
        assert validate_project_key("RDE123") == "RDE123"
        assert validate_project_key("PROJECT_1") == "PROJECT_1"

    def test_empty_key(self):
        with pytest.raises(ValueError, match="不能为空"):
            validate_project_key("")
        with pytest.raises(ValueError, match="不能为空"):
            validate_project_key("   ")
        with pytest.raises(ValueError, match="不能为空"):
            validate_project_key(None)

    def test_invalid_key(self):
        with pytest.raises(ValueError, match="无效"):
            validate_project_key("KO-1")
        with pytest.raises(ValueError, match="无效"):
            validate_project_key("123")
        with pytest.raises(ValueError, match="无效"):
            validate_project_key("a@b")


class TestExtractIssueKey:
    def test_extract_basic(self):
        assert extract_issue_key("KO-29") == "KO-29"
        assert extract_issue_key("查看 KO-29 的状态") == "KO-29"
        assert extract_issue_key("ko-29") == "KO-29"

    def test_extract_multiple(self):
        # 返回第一个匹配
        result = extract_issue_key("KO-29 和 RDE-10")
        assert result == "KO-29"

    def test_no_match(self):
        assert extract_issue_key("hello world") is None
        assert extract_issue_key("") is None
        assert extract_issue_key(None) is None
        assert extract_issue_key("KO") is None  # 没有数字部分


class TestSanitizeJqlValue:
    def test_normal_value(self):
        assert sanitize_jql_value("hello") == "hello"
        assert sanitize_jql_value("KO-29") == "KO-29"

    def test_with_quotes(self):
        assert sanitize_jql_value('hello"world') == 'hello\\"world'
        assert sanitize_jql_value("it's") == "it\\'s"

    def test_empty(self):
        assert sanitize_jql_value("") == ""
