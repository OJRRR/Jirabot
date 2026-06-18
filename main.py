# -*- coding: utf-8 -*-
"""PM小帮手 主入口"""
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
)

from langchain_openai import ChatOpenAI
from langgraph.prebuilt import create_react_agent
from langgraph.checkpoint.sqlite import SqliteSaver
from langgraph.checkpoint.memory import MemorySaver

# 初始化日志（文件 + 控制台，带轮转）
setup_logging(Config.LOG_FILE)

# 打印配置
Config.print_info()

# 初始化 Jira 客户端
jira_client = JiraClient()
jira = jira_client.get_client()

# 启动时尝试自动探测 "Target Start" / "Target End" 字段 ID（环境变量 AUTO_DETECT_FIELDS=0 可关闭）
if os.getenv("AUTO_DETECT_FIELDS", "1") == "1" and not jira_client.is_offline:
    try:
        from field_detector import ensure_target_field_ids
        ensure_target_field_ids(jira_client)
    except Exception as _e:
        import logging as _logging
        _logging.getLogger("jira_bot").warning("字段自动探测失败: %s", _e)

# ── 创建 LLM（支持任何 OpenAI 兼容 API，含视觉模型）─
llm = None
agent = None

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

# 工具列表
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
]

if llm is not None:
    from prompts import SYSTEM_PROMPT_TEMPLATE

    # 系统提示词
    system_prompt = SYSTEM_PROMPT_TEMPLATE.format(
        target_projects=Config.TARGET_PROJECTS if Config.TARGET_PROJECTS else '所有项目'
    )

    # 创建 Agent
    # 会话存储：默认用 SQLite 落盘到 BASE_DIR/sessions.db，重启不丢会话
    # 设置环境变量 JIRA_SESSION_BACKEND=memory 可回退到纯内存（多进程调试时方便）
    _session_backend = os.getenv("JIRA_SESSION_BACKEND", "sqlite").lower()
    _sessions_dir = os.path.join(Config.BASE_DIR, "sessions")
    os.makedirs(_sessions_dir, exist_ok=True)
    _session_db_path = os.path.join(_sessions_dir, "sessions.db")

    if _session_backend == "memory":
        checkpointer = MemorySaver()
        print(f"💾 会话存储: MemorySaver（重启即丢失）")
    else:
        # 使用 AsyncSqliteSaver 同时支持 sync（agent.stream/invoke）和 async（agent.astream_events）
        import asyncio

        async def _make_async_saver(db_path: str):
            """在事件循环中创建 AsyncSqliteSaver + aiosqlite 连接。

            返回 (checkpointer, conn) — conn 需要保持存活以维持连接。
            """
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
        except Exception as _e:
            import logging as _logging
            _logging.getLogger("jira_bot").warning("AsyncSqliteSaver 初始化失败: %s", _e)
            print(f"⚠️ AsyncSqliteSaver 初始化失败，回退到 SqliteSaver: {_e}")
            _sqlite_conn = sqlite3.connect(_session_db_path, check_same_thread=False)
            checkpointer = SqliteSaver(_sqlite_conn)
        else:
            print(f"💾 会话存储: AsyncSqliteSaver → {_session_db_path}")

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

def main():
    print("\n" + "=" * 60)
    print("🤖 PM小帮手 启动成功！")
    print("=" * 60)
    print("指令示例：")
    print("  📊 生成项目集报告")
    print("  📊 生成 KO 报告")
    print("  📋 我的任务")
    print("  🔗 查看 KO-29 依赖")
    print("  ⚠️ 风险总结")
    print("  ⚠️ 提取 KO 项目的风险")
    print("  ✨ 在 RDE 项目中创建一个子任务，类型为 Sub-task，父任务 RDE-10，标题 'subtask jirabot测试'")
    print("  ✨ 创建任务并指定类型为 Risk")
    print("  🔗 创建链接：KO-30 阻塞 KO-31")
    print("  ✏️ 更新 KO-29 的摘要为 '新标题'")
    print("  ✏️ 将 KO-29 的优先级改为 High")
    print("  💬 给 KO-29 添加评论：已完成测试")
    print("  ⏱ 给 KO-29 记录工时：2h 30m")
    print("  📦 批量创建3个 Sub-task，父任务 RDE-10")
    print("  🔍 搜索 KO 项目中状态为 In Progress 的任务")
    print("  🔍 找我的高优先级任务")
    print("  👤 把 KO-29 分配给 zhangsan")
    print("\n输入 exit 退出\n")

    config = {"configurable": {"thread_id": f"cli_{uuid.uuid4().hex[:12]}"}}

    while True:
        try:
            user_input = input("🧑 你：").strip()
            if user_input.lower() in ["exit", "quit", "退出"]:
                print("👋 再见！")
                break
            if not user_input:
                continue

            print("\n🤖 AI 思考中...")
            response = agent.invoke({"messages": [("user", user_input)]}, config=config)

            if response and "messages" in response:
                print(f"\n🤖 AI：{response['messages'][-1].content}\n")

        except KeyboardInterrupt:
            print("\n👋 再见！")
            break
        except Exception as e:
            print(f"\n❌ 错误：{e}\n")

if __name__ == "__main__":
    main()
