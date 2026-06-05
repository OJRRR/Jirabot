"""Jira AI Agent 主入口"""
from config import Config
from jira_client import JiraClient
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
    create_issue_link
)

from langchain_openai import ChatOpenAI
from langgraph.prebuilt import create_react_agent
from langgraph.checkpoint.memory import MemorySaver

# 打印配置
Config.print_info()

# 初始化 Jira 客户端
jira = JiraClient().get_client()

# 创建 LLM
llm = ChatOpenAI(
    model=Config.MODEL_NAME,
    api_key=Config.MODEL_API_KEY,
    base_url=Config.MODEL_API_BASE,
    temperature=Config.AI_TEMPERATURE,
    max_tokens=4000
)

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
    create_issue_link
]

# 系统提示词
system_prompt = f"""你是一个专业的Jira助手。

可用工具：
- get_my_tasks: 获取我的任务
- get_project_tasks: 获取指定项目的任务，参数 project_key
- generate_report: 生成单个项目的HTML报告
- generate_portfolio_report: 生成项目集汇总报告（包含所有配置项目）
- get_issue_links: 查看任务依赖关系
- get_task_dependencies: 分析依赖风险
- extract_issue_risks: 提取项目中 Issue Type 为 Risk 的风险项并总结
- create_issue: 创建新的 Jira 任务（支持子任务、Epic关联等）
- get_create_issue_metadata: 【重要】获取指定项目支持的问题类型及每种类型的必填字段列表
- create_issue_link: 在两个已有问题之间创建链接关系

**创建任务的标准流程（必须遵守）**：
1. 用户必须提供项目KEY、问题类型（issue_type，如 Sub-task）、标题（summary）。
2. 如果用户未提供问题类型，请先用 get_create_issue_metadata 查询项目支持的类型，然后让用户选择。
3. 对于 Sub-task，必须提供 parent_key（父任务KEY）。
4. 如果缺少必填字段（如角色名称），先调用 get_create_issue_metadata 获取该类型的必填字段列表，然后向用户询问缺失字段的值。
5. 收集完整信息后，调用 create_issue，将自定义字段通过 additional_fields 参数传入。

当前项目配置: {Config.TARGET_PROJECTS if Config.TARGET_PROJECTS else '所有项目'}

用中文回复。"""

# 创建 Agent
memory = MemorySaver()
agent = create_react_agent(
    model=llm,
    tools=tools,
    prompt=system_prompt,
    checkpointer=memory
)

def main():
    print("\n" + "=" * 60)
    print("🤖 Jira AI Agent 启动成功！")
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
    print("\n输入 exit 退出\n")
    
    config = {"configurable": {"thread_id": "jira_session"}}
    
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