"""Tests for tools._lazy — LazyJira 懒加载代理"""
import pytest
from unittest.mock import patch, MagicMock

from tools._lazy import LazyJira


class TestLazyJiraCreation:
    """测试 LazyJira 创建（不触发网络连接）"""

    def test_create_lazy_jira(self):
        """创建 LazyJira 不应触发 JiraClient 实例化"""
        jira = LazyJira()
        assert isinstance(jira, LazyJira)

    def test_no_instance_until_access(self):
        """在首次属性访问前，_instance 应未设置"""
        jira = LazyJira()
        assert "_instance" not in jira.__dict__

    def test_repr_without_import(self):
        """__repr__ 不应触发 JiraClient 创建"""
        jira = LazyJira()
        assert "LazyJira" in repr(jira)


class TestLazyJiraDelegation:
    """测试 LazyJira 的透明代理行为"""

    def test_attribute_access_triggers_creation(self):
        """首次属性访问应触发 JiraClient 创建"""
        jira = LazyJira()
        with patch("tools._lazy.JiraClient") as mock_jc:
            mock_jc.return_value = MagicMock()
            mock_jc.return_value.some_method.return_value = "result"
            # 通过 LazyJira 访问属性
            result = jira.some_method()
            assert result == "result"
            mock_jc.assert_called_once()

    def test_second_access_reuses_instance(self):
        """第二次属性访问应复用已创建的实例"""
        jira = LazyJira()
        with patch("tools._lazy.JiraClient") as mock_jc:
            mock_client = MagicMock()
            mock_client.some_method.return_value = "result"
            mock_jc.return_value = mock_client

            jira.some_method()
            jira.some_method()
            # JiraClient 只应创建一次
            mock_jc.assert_called_once()

    def test_call_delegation(self):
        """LazyJira() 调用应委托给 JiraClient.__call__"""
        jira = LazyJira()
        with patch("tools._lazy.JiraClient") as mock_jc:
            mock_client = MagicMock()
            mock_client.return_value = "called"
            mock_jc.return_value = mock_client

            result = jira("arg1", kw=1)
            assert result == "called"
            mock_client.assert_called_once_with("arg1", kw=1)

    def test_private_attr_not_proxied(self):
        """_instance 属性不应通过代理访问"""
        jira = LazyJira()
        # _instance 在未设置时不应通过 __getattr__ 路由
        with pytest.raises(AttributeError):
            _ = jira._instance


class TestLazyJiraEdgeCases:
    """测试边界情况"""

    def test_multiple_lazy_instances(self):
        """多个 LazyJira 实例应各自独立"""
        a = LazyJira()
        b = LazyJira()
        assert a is not b

    def test_truthiness(self):
        """LazyJira 应为 truthy"""
        assert LazyJira()
