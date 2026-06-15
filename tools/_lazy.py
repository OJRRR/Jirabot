"""JiraClient 懒加载代理

解决两个问题：
1. `from tools import ...` 顶层 import 即触发 JiraClient 单例，导致首次网络探测失败时整个 import 炸
2. 单测 / 脚本想 mock JiraClient 时，必须先 patch 模块级变量

用法：
    from tools._lazy import LazyJira
    jira = LazyJira()    # 模块级定义，不触发网络
    ...
    jira.jql("...")      # 首次调用时才真正创建 JiraClient
"""
from typing import Any
from jira_client import JiraClient


class LazyJira:
    """
    JiraClient 的透明懒加载代理。
    JiraClient 自身用 __new__ 保证单例，这里再加一层延迟到首次属性访问。
    """

    def _ensure(self) -> JiraClient:
        # 用 object.__setattr__ 绕过自身的 __getattr__ 递归
        inst = self.__dict__.get("_instance")
        if inst is None:
            inst = JiraClient()
            object.__setattr__(self, "_instance", inst)
        return inst

    def __getattr__(self, name: str) -> Any:
        if name in ("_instance",):
            raise AttributeError(name)
        return getattr(self._ensure(), name)

    def __call__(self, *args, **kwargs):
        return self._ensure()(*args, **kwargs)