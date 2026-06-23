# -*- coding: utf-8 -*-
"""PM小帮手 CLI 主入口"""
import os
import uuid
from config import Config
from agent_factory import build_agent

# 初始化 Agent（与 webapp.py 共享同一套构建逻辑）
agent, checkpointer, jira_client, llm = build_agent()


def main():
    if agent is None:
        print("\n❌ Agent 未初始化（LLM/Jira 不可达）")
        print("   请检查 .env 配置中的以下变量：")
        print("   - JIRA_SERVER / JIRA_USER / JIRA_TOKEN")
        print("   - MODEL_API_BASE / MODEL_API_KEY / MODEL_NAME")
        print("   修改后重新运行 python main.py\n")
        return

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
