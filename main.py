"""PM小帮手 主入口"""
import os
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
    create_issue_link,
    get_issue_transitions,
    update_issue,
    add_issue_comment,
    add_issue_worklog,
    batch_create_issues,
    search_issues,
    assign_issue,
    delete_issue,
    import_from_excel,
    batch_update_dates,
)

from langchain_openai import ChatOpenAI
from langgraph.prebuilt import create_react_agent
from langgraph.checkpoint.memory import MemorySaver

# 打印配置
Config.print_info()

# 初始化 Jira 客户端
jira = JiraClient().get_client()

# ── 创建 LLM（支持任何 OpenAI 兼容 API，含视觉模型）─
llm = ChatOpenAI(
    model=Config.MODEL_NAME,
    api_key=Config.MODEL_API_KEY,
    base_url=Config.MODEL_API_BASE,
    temperature=Config.AI_TEMPERATURE,
    max_tokens=4096,
)
print(f"🤖 模型: {Config.MODEL_NAME}")
print(f"🔗 API: {Config.MODEL_API_BASE}")

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
    import_from_excel,
    batch_update_dates,
]

# 系统提示词
system_prompt = f"""你是一个专业的Jira助手。

## 核心原则：用户信息不完整时禁止自行编造
当用户要求你执行**写入操作**（创建/更新/删除/批量操作等）时，**你必须先逐一核验用户是否已提供所有必要信息**。
- 如果缺少必填信息，必须**明确告诉用户缺少哪项信息**，让用户补充，**绝不能自行猜测、假设或编造**缺失的值。
- 例如：用户说"创建个任务"，未提供项目KEY、标题、类型时，你必须列出缺少的字段让用户补充。
- 例如：用户说"把 KO-29 的日期改一下"，但未提供具体日期，你必须问用户改成什么日期。
- 查询/只读操作不受此限制。

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
- get_issue_transitions: 获取 Issue 当前可用的状态转换列表（如 To Do -> In Progress -> Done）
- update_issue: 更新已有 Issue 的字段（摘要、描述、优先级、自定义字段等）
- add_issue_comment: 给 Issue 添加评论
- add_issue_worklog: 给 Issue 记录工时（如 "2h"、"1d 30m"）
- batch_create_issues: 批量创建多个 Jira 任务，用 JSON 字符串传入任务数组
- search_issues: 搜索 Jira 任务，支持按项目、状态、负责人、优先级、问题类型、关键词筛选
- assign_issue: 将任务分配给指定用户
- delete_issue: 删除指定的 Jira Issue（需二次确认）
- import_from_excel: 从 Excel 文件导入并批量创建 Jira 任务。用户上传 xlsx 文件后调用，自动解析列名并映射到 Jira 字段（summary, issue_type, start_date, end_date 等）。
- batch_update_dates: 批量更新多个 Jira 任务的开始日期和结束日期，用于维护 Jira Plan 时间线。传入 JSON 数组，每项含 issue_key, start_date, end_date。

**创建任务的标准流程（必须遵守）**：
1. 用户必须提供项目KEY、问题类型（issue_type，如 Sub-task）、标题（summary）。
2. 如果用户未提供问题类型，请先用 get_create_issue_metadata 查询项目支持的类型，然后让用户选择。
3. 对于 Sub-task，必须提供 parent_key（父任务KEY）。
4. **Epic 层级规则（重要）**：Jira 的层级关系为 `Epic → Task → Sub-task`。
   - Epic 只能直接关联 Task（通过 epic_link_key），不能直接关联 Sub-task。
   - 如果用户想在 Epic 下创建 Sub-task，流程是：先创建 Task（关联到 Epic）→ 再创建 Sub-task（父任务设为该 Task）。
   - 如果 create_issue 或 batch_create_issues 返回"Epic 不能直接关联 Sub-task"错误，请按上述流程引导用户。
5. 在调用 create_issue 之前，**必须先调用 get_create_issue_metadata 获取必填字段列表**。如果发现必填字段有 allowed_values（可选值列表），请向用户展示这些可选值让用户选择。例如字段 "Role Name" 的可选值可能是 ["Administrator", "Developer", ...]。
   **重要：当用户输入模糊（如输入 "infra" 能匹配多个选项时），必须列出所有匹配项让用户明确选择，不能自行决定选哪个。**
6. 收集完整信息后，调用 create_issue，将自定义字段通过 additional_fields 参数传入（如 {{"customfield_xxxxx": "选择的角色名"}}）。

**更新任务的规范**：
1. 如需修改字段（摘要、描述、优先级），直接使用 update_issue 工具。
2. 如需修改状态，先用 get_issue_transitions 查看可用转换，再用 update_issue 的 additional_fields 参数中的 "status" 字段更新，或者引导用户。

**其他操作**：
- 如需批量创建，使用 batch_create_issues，传入 JSON 格式的 issues_json 参数
- 如需搜索任务，使用 search_issues，支持多个筛选条件组合
- 如需分配任务，使用 assign_issue，提供 issue_key 和 assignee 用户名
- 如需删除任务，使用 delete_issue。先调用 delete_issue(issue_key="XXX") 让用户确认；用户确认后，再调用 delete_issue(issue_key="XXX", confirmed=True) 执行删除

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