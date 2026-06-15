"""按 Category 创建 Epic 并关联下属的 Task

用法：
    python scripts/ede_migration/create_epics.py
"""
import sys, os
_BASE_DIR = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
sys.path.insert(0, _BASE_DIR)

from jira_client import JiraClient

jira = JiraClient().get_client()

# Epic Name 和 Epic Link 字段
EPIC_NAME_FIELD = "customfield_10005"
EPIC_LINK_FIELD = "customfield_10006"

# 定义 Epic（按 Category + 大分组）
# 每个 Epic 需要包含其下属的 Task 的 summary 前缀匹配规则
epics_config = [
    # Primary DC - Wave 1
    {"name": "PDC - DC",       "prefix": "[PDC]", "keywords": ["Infra Requirements", "procurement", "Data Center Build Out", "Rack & Cabling"]},
    {"name": "PDC - Network",  "prefix": "[PDC]", "keywords": ["Network Device", "Network Configuration"]},
    {"name": "PDC - IaaS",     "prefix": "[PDC]", "keywords": ["Server & Storage", "Private Cloud", "Bare Metal"]},
    {"name": "PDC - Dev-Ops",  "prefix": "[PDC]", "keywords": ["Tool Platform"]},
    # DR
    {"name": "DR - DC",        "prefix": "[DR]",  "keywords": ["DR scope", "Budget Release", "Data Center Build Out", "Rack & Cabling"]},
    {"name": "DR - Network",   "prefix": "[DR]",  "keywords": ["Network Device", "Network Configuration"]},
    {"name": "DR - IaaS",      "prefix": "[DR]",  "keywords": ["Server & Storage", "Private Cloud", "Bare Metal"]},
    {"name": "DR - Dev-Ops",   "prefix": "[DR]",  "keywords": ["Tool Platform", "DR Systems"]},
]

# 查询 EDE 项目所有 Task
print("=== 查询 EDE 项目现有 Task ===")
issues = jira.jql("project = EDE AND issuetype = Task ORDER BY key ASC", fields=["summary", "key"])
tasks = []
for issue in issues.get("issues", []):
    tasks.append({
        "key": issue["key"],
        "summary": issue["fields"]["summary"]
    })
print(f"找到 {len(tasks)} 个 Task")

# 创建 Epic 并关联 Task
print(f"\n=== 创建 Epic 并关联 Task ===\n")

for epic_cfg in epics_config:
    epic_name = epic_cfg["name"]
    prefix = epic_cfg["prefix"]
    keywords = epic_cfg["keywords"]

    # 筛选匹配的 Task
    matched_tasks = []
    for task in tasks:
        if task["summary"].startswith(prefix):
            for kw in keywords:
                if kw in task["summary"]:
                    matched_tasks.append(task)
                    break

    if not matched_tasks:
        print(f"⚠️ {epic_name}: 没有匹配的 Task，跳过")
        continue

    # 创建 Epic
    try:
        epic_fields = {
            "project": {"key": "EDE"},
            "summary": epic_name,
            "issuetype": {"name": "Epic"},
            EPIC_NAME_FIELD: epic_name,
        }
        epic = jira.create_issue(fields=epic_fields)
        epic_key = epic.get("key")
        print(f"✅ Epic 创建成功: {epic_key} - {epic_name}")
    except Exception as e:
        print(f"❌ Epic 创建失败: {epic_name} - {e}")
        continue

    # 关联 Task 到 Epic
    linked = 0
    for task in matched_tasks:
        try:
            jira.update_issue_field(task["key"], {EPIC_LINK_FIELD: epic_key})
            linked += 1
        except Exception as e:
            print(f"  ❌ 关联失败: {task['key']} - {e}")

    print(f"  关联 {linked}/{len(matched_tasks)} 个 Task\n")

print("\n=== Epic 创建和关联完成 ===")