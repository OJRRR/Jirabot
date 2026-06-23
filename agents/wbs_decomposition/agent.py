# -*- coding: utf-8 -*-
"""WBS 拆解子 Agent — 创建独立的 ReAct Agent 并暴露 decompose_epic 接口"""

import os
import logging
from config import Config
from langchain_openai import ChatOpenAI
from langgraph.prebuilt import create_react_agent
from .prompts import WBS_SYSTEM_PROMPT

_logger = logging.getLogger("jira_bot.wbs_agent")


def get_wbs_model_config() -> dict:
    """获取 WBS 子 Agent 的独立模型配置。

    优先级：环境变量 WBS_MODEL_* > 主配置 Config.MODEL_*
    这样可以让 WBS 拆解使用与主 Agent 不同的模型（如更便宜、更快的模型）。
    """
    return {
        "model": os.getenv("WBS_MODEL_NAME") or Config.MODEL_NAME,
        "api_key": os.getenv("WBS_MODEL_API_KEY") or Config.MODEL_API_KEY,
        "base_url": os.getenv("WBS_MODEL_API_BASE") or Config.MODEL_API_BASE,
    }


def create_wbs_agent():
    """创建 WBS 拆解子 Agent（使用 create_react_agent）。

    子 Agent 只能调用 suggest_epic_tasks（只读工具），
    不包含任何创建/更新/删除类工具。

    Returns:
        Agent 实例，如果模型配置不完整则返回 None
    """
    cfg = get_wbs_model_config()

    if not cfg["model"] or not cfg["api_key"]:
        _logger.warning("WBS 子 Agent 模型配置不完整（model=%s, key=%s），将无法使用",
                        cfg["model"], "***" if cfg["api_key"] else "缺失")
        return None

    llm = ChatOpenAI(
        model=cfg["model"],
        api_key=cfg["api_key"],
        base_url=cfg["base_url"],
        temperature=0.3,  # 低温度，追求确定性的拆解结果
        max_tokens=4096,
    )

    # 子 Agent 只能调用 suggest_epic_tasks（只读工具，获取 Epic 详情）
    from tools.task_query import suggest_epic_tasks
    wbs_tools = [suggest_epic_tasks]

    agent = create_react_agent(
        model=llm,
        tools=wbs_tools,
        prompt=WBS_SYSTEM_PROMPT,
    )

    _logger.info("✅ WBS 子 Agent 初始化成功（模型: %s, API: %s）",
                 cfg["model"], cfg["base_url"])
    return agent


# ── 全局实例（懒初始化，首次调用 decompose_epic 时才创建）──
wbs_agent = None


def get_wbs_agent():
    """获取或创建 WBS 子 Agent 全局实例（懒初始化）"""
    global wbs_agent
    if wbs_agent is None:
        wbs_agent = create_wbs_agent()
    return wbs_agent


async def decompose_epic(epic_key: str) -> str:
    """对指定 Epic 进行 WBS 拆解。

    这是子 Agent 的唯一对外接口。内部创建独立的 ReAct Agent，
    使用专用提示词和独立模型配置执行 WBS 拆解。

    Args:
        epic_key: Epic 的 Jira KEY（如 KO-100）

    Returns:
        WBS 拆解结果文本，包含：
        - WBS 树（缩进列表）
        - 任务清单（Markdown 表格）
        - 拆解说明
    """
    agent = get_wbs_agent()
    if agent is None:
        return (
            "❌ WBS 拆解失败：子 Agent 未初始化。\n"
            "请检查模型配置——确保主配置（MODEL_NAME / MODEL_API_KEY / MODEL_API_BASE）"
            "或 WBS 专用配置（WBS_MODEL_NAME / WBS_MODEL_API_KEY / WBS_MODEL_API_BASE）已正确设置。"
        )

    # 构建清晰的指令，引导子 Agent 按步骤执行
    prompt = (
        f"请对 Epic {epic_key} 进行 WBS 拆解。\n\n"
        f"步骤：\n"
        f"1. 先调用 suggest_epic_tasks(epic_key=\"{epic_key}\") 获取 Epic 详情\n"
        f"2. 根据 Epic 的标题和描述，分析其性质，选择合适的拆解策略\n"
        f"3. 按 PMI 标准（100%覆盖、MECE、80小时法则）逐层拆解\n"
        f"4. 输出完整的 WBS 树 + 任务清单 + 拆解说明"
    )

    try:
        response = await agent.ainvoke({"messages": [("user", prompt)]})
        if response and "messages" in response:
            content = response["messages"][-1].content
            return content or "⚠️ WBS 拆解完成，但未生成文本内容。"
        return "⚠️ WBS 拆解失败：Agent 未返回有效响应。"
    except Exception as e:
        _logger.error("WBS 拆解异常: %s", e, exc_info=True)
        return f"❌ WBS 拆解异常: {str(e)}"
