"""检查 EDE-66 是不是 Epic

用法：
    python scripts/utility/check_epic.py
"""
import sys, os
_BASE_DIR = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
sys.path.insert(0, _BASE_DIR)

from jira_client import JiraClient

jira = JiraClient().get_client()

# 测试 Epic Link 更新
print("=== 测试 Epic Link (customfield_10006) ===")
try:
    jira.update_issue_field("EDE-34", {"customfield_10006": "EDE-66"})
    print("✅ Epic Link 更新成功")
except Exception as e:
    print(f"❌ Epic Link 更新失败: {e}")

# 验证
print("\n=== 验证 EDE-34 ===")
try:
    issue = jira.issue("EDE-34")
    epic_link = issue.get("fields", {}).get("customfield_10006")
    print(f"  Epic Link: {epic_link}")
except Exception as e:
    print(f"查询失败: {e}")