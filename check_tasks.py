import sys, os
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from jira_client import JiraClient

jira = JiraClient().get_client()

# 查 EDE 项目所有 Task
resp = jira.jql("project = EDE AND issuetype = Task ORDER BY key ASC", fields=["summary", "created"])
issues = resp.get("issues", [])
print(f"EDE 项目共有 {len(issues)} 个 Task\n")
for issue in issues:
    key = issue["key"]
    summary = issue["fields"]["summary"]
    created = issue["fields"]["created"][:10]
    print(f"  {key}: {summary} (创建于 {created})")
