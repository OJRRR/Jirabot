"""工具装饰器 — 消除 @tool 函数中重复的 try/except/json.dumps 模式

用法：
    from tools._decorators import json_tool

    @json_tool
    def my_tool(args) -> dict:
        '''工具描述'''
        # 直接返回 dict，json_tool 自动处理异常捕获和 JSON 序列化
        return {"success": True, "data": ...}

等效于手写：
    @tool
    def my_tool(args) -> str:
        try:
            ...
            return json.dumps({"success": True, ...}, ensure_ascii=False, indent=2)
        except Exception as e:
            return json.dumps({"success": False, "error": str(e)}, ensure_ascii=False)
"""

import json
import functools
from langchain.tools import tool


def json_tool(func):
    """装饰器：自动捕获异常 + JSON 序列化 + @tool 包装。

    被装饰的函数只需返回 dict，装饰器自动：
    1. try/except 捕获异常 → {"success": False, "error": str(e)}
    2. json.dumps 序列化（ensure_ascii=False, indent=2）
    3. 应用 @tool 装饰器使其成为 LangChain 工具
    """

    @functools.wraps(func)
    def wrapper(*args, **kwargs):
        try:
            result = func(*args, **kwargs)
            if isinstance(result, str):
                # 函数已经返回了 JSON 字符串（如某些特殊情况）
                return result
            return json.dumps(result, ensure_ascii=False, indent=2)
        except Exception as e:
            return json.dumps(
                {"success": False, "error": str(e)},
                ensure_ascii=False,
            )

    # 保留原函数的 docstring 给 @tool 使用
    wrapper.__doc__ = func.__doc__
    wrapper.__name__ = func.__name__

    # 应用 langchain @tool 装饰器
    return tool(wrapper)
