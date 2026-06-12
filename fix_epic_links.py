"""补关联 EDE-28 到 DR - IaaS"""
import sys, os
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from jira_client import JiraClient

jira = JiraClient().get_client()
EPIC_LINK_FIELD = "customfield_10006"

# 补充 EDE-28 到 DR - IaaS
print("=== 补充关联 EDE-28 → EDE-73 (DR - IaaS) ===")
try:
    jira.update_issue_field("EDE-28", {EPIC_LINK_FIELD: "EDE-73"})
    print("✅ EDE-28 已关联到 EDE-73")
except Exception as e:
    print(f"❌ 关联失败: {e}")

# 验证所有关联
print("\n=== 验证所有 Epic 关联 ===")
for epic_key in ["EDE-67", "EDE-68", "EDE-69", "EDE-70", "EDE-71", "EDE-72", "EDE-73", "EDE-74"]:
    try:
        resp = jira.jql(f"'Epic Link' = {epic_key}", fields=["summary"])
        count = len(resp.get("issues", []))
        print(f"  {epic_key}: {count} 个子任务")
    except Exception as e:
        print(f"  {epic_key}: 查询失败 - {e}")

# 检查未关联的
print("\n=== 未关联 Epic 的 Task ===")
resp = jira.jql("project = EDE AND issuetype = Task AND 'Epic Link' is EMPTY", fields=["summary"])
for issue in resp.get("issues", []):
    print(f"  {issue['key']}: {issue['fields']['summary']}")
