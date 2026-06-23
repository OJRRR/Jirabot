# -*- coding: utf-8 -*-
"""Agent 工厂 — 创建 LangGraph Agent 实例，供 CLI 和 Web 共用。

解耦自 main.py，避免 webapp.py import 时触发 CLI 循环和打印输出。
"""

import os
import sqlite3
import uuid
from config import Config
from jira_client import JiraClient
from utils import configure_console_encoding, setup_logging

configure_console_encoding()
from tools import (
    get_my_tasks,
    get_project_tasks,
    generate_report,
    generate_portfolio_report,
    get_issue_links,
    get_task_dependencies,
    extract_issue_risks,
    create_issue,
    get_create_issue_metadata,
    create_issue_link,
    get_issue_transitions,
    update_issue,
    add_issue_comment,
    add_issue_worklog,
    batch_create_issues,
    search_issues,
    assign_issue,
    delete_issue,
    batch_delete_issues,
    import_from_excel,
    batch_update_dates,
    batch_update_issues,
    suggest_epic_tasks,
    analyze_meeting_for_projects,
)

from agents.wbs_decomposition import decompose_epic

from langchain_openai import ChatOpenAI
from langgraph.prebuilt import create_react_agent
from langgraph.checkpoint.sqlite import SqliteSaver
from langgraph.checkpoint.memory import MemorySaver


def build_agent():
    """构建 LangGraph Agent 及相关组件。

    Returns:
        (agent, checkpointer, jira_client, llm)
        - agent: LangGraph ReAct Agent 实例（LLM/Jira 不可用时为 None）
        - checkpointer: 会话存储实例
        - jira_client: JiraClient 单例
        - llm: ChatOpenAI 实例（不可用时为 None）
    """
    # ── 初始化日志 ──
    setup_logging(Config.LOG_FILE)

    # ── 打印配置 ──
    Config.print_info()

    # ── 初始化 Jira 客户端 ──
    jira_client = JiraClient()
    jira = jira_client.get_client()

    # 启动时尝试自动探测 "Target Start" / "Target End" 字段 ID
    if os.getenv("AUTO_DETECT_FIELDS", "1") == "1" and not jira_client.is_offline:
        try:
            from field_detector import ensure_target_field_ids
            ensure_target_field_ids(jira_client)
        except Exception as _e:
            import logging as _logging
            _logging.getLogger("jira_bot").warning("字段自动探测失败: %s", _e)

    # ── 创建 LLM ──
    llm = None
    try:
        llm = ChatOpenAI(
            model=Config.MODEL_NAME,
            api_key=Config.MODEL_API_KEY,
            base_url=Config.MODEL_API_BASE,
            temperature=Config.AI_TEMPERATURE,
            max_tokens=4096,
        )
        print(f"🤖 模型: {Config.MODEL_NAME}")
        print(f"🔗 API: {Config.MODEL_API_BASE}")
    except Exception as _e:
        import logging as _logging
        _logging.getLogger("jira_bot").warning("LLM 初始化失败（离线模式）: %s", _e)

    # ── WBS 拆解子 Agent 工具 ──
    from langchain.tools import tool as langchain_tool

    @langchain_tool
    async def call_wbs_agent(epic_key: str = "") -> str:
        """
        【WBS拆解专家】对 Epic 进行专业的工作分解结构（WBS）拆解。
        调用独立的 WBS 拆解专家子 Agent，按 PMI 标准（100%覆盖、MECE、80小时法则）
        生成完整的 WBS 树和任务清单。

        参数：
          epic_key - 要拆解的 Epic 的 Jira KEY（如 KO-100）

        返回：WBS 树（缩进列表）+ 任务清单（Markdown 表格）+ 拆解说明

        注意：此工具只做拆解分析，不会创建任何 Jira 任务。
        适用场景：用户说"拆解"、"WBS"、"分解"、"拆分"、"任务分解"等。
        """
        if not epic_key:
            return "WBS 拆解失败：请提供 Epic 的 Jira KEY（如 KO-100）。"
        try:
            result = await decompose_epic(epic_key)
            return result
        except Exception as e:
            return f"❌ WBS 拆解失败: {str(e)}"

    # ── 工具列表 ──
    tools = [
        get_my_tasks,
        get_project_tasks,
        generate_report,
        generate_portfolio_report,
        get_issue_links,
        get_task_dependencies,
        extract_issue_risks,
        create_issue,
        get_create_issue_metadata,
        create_issue_link,
        get_issue_transitions,
        update_issue,
        add_issue_comment,
        add_issue_worklog,
        batch_create_issues,
        search_issues,
        assign_issue,
        delete_issue,
        batch_delete_issues,
        import_from_excel,
        batch_update_dates,
        batch_update_issues,
        suggest_epic_tasks,
        analyze_meeting_for_projects,
        call_wbs_agent,
    ]

    # ── Agent 构建 ──
    agent = None
    checkpointer = MemorySaver()

    if llm is not None:
        from prompts import SYSTEM_PROMPT_TEMPLATE

        system_prompt = SYSTEM_PROMPT_TEMPLATE.format(
            target_projects=Config.TARGET_PROJECTS if Config.TARGET_PROJECTS else '所有项目'
        )

        _session_backend = os.getenv("JIRA_SESSION_BACKEND", "memory").lower()
        _sessions_dir = os.path.join(Config.BASE_DIR, "sessions")
        os.makedirs(_sessions_dir, exist_ok=True)
        _session_db_path = os.path.join(_sessions_dir, "sessions.db")

        if _session_backend == "sqlite":
            _sqlite_conn = sqlite3.connect(_session_db_path, check_same_thread=False)
            checkpointer = SqliteSaver(_sqlite_conn)
            print(f"💾 会话存储: SqliteSaver → {_session_db_path}（仅 sync，无流式）")
        elif _session_backend == "async":
            import asyncio

            async def _make_async_saver(db_path: str):
                import aiosqlite
                from langgraph.checkpoint.sqlite.aio import AsyncSqliteSaver
                _conn = await aiosqlite.connect(db_path)
                _saver = AsyncSqliteSaver(_conn)
                await _saver.setup()
                return _saver, _conn

            _aio_loop = asyncio.new_event_loop()
            asyncio.set_event_loop(_aio_loop)
            try:
                checkpointer, _async_conn = _aio_loop.run_until_complete(
                    _make_async_saver(_session_db_path)
                )
                print(f"💾 会话存储: AsyncSqliteSaver → {_session_db_path}（仅 CLI）")
            except Exception as _e:
                import logging as _logging
                _logging.getLogger("jira_bot").warning("AsyncSqliteSaver 初始化失败: %s", _e)
                print(f"⚠️ AsyncSqliteSaver 初始化失败，回退到 MemorySaver: {_e}")
                checkpointer = MemorySaver()
        else:
            checkpointer = MemorySaver()
            print(f"💾 会话存储: MemorySaver（跨线程安全，重启不保留会话）")

        try:
            agent = create_react_agent(
                model=llm,
                tools=tools,
                prompt=system_prompt,
                checkpointer=checkpointer
            )
            print("✅ Agent 初始化成功")
        except Exception as _e:
            import logging as _logging
            _logging.getLogger("jira_bot").warning("Agent 初始化失败: %s", _e)
    else:
        print("⚠️ LLM 未初始化，Agent 不可用（离线模式）")

    return agent, checkpointer, jira_client, llm
