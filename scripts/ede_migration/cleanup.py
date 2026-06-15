"""清理重复任务和测试数据（EDE 项目上线期的一次性脚本）

用法：
    python scripts/ede_migration/cleanup.py
"""
import sys, os
_BASE_DIR = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
sys.path.insert(0, _BASE_DIR)

from jira_client import JiraClient

jira = JiraClient().get_client()

# 要删除的重复 Task（保留 EDE-2~33，删除 EDE-34~65）
# 加上测试任务 EDE-1
duplicate_keys = [f"EDE-{i}" for i in range(34, 66)] + ["EDE-1"]

# 测试 Epic EDE-66 也删除
# 先查 EDE-66 是不是 Epic
try:
    issue = jira.issue("EDE-66")
    itype = issue["fields"]["issuetype"]["name"]
    print(f"EDE-66 类型: {itype}")
    if itype == "Epic":
        duplicate_keys.append("EDE-66")
except Exception as e:
    print(f"EDE-66 查询失败: {e}")

print(f"准备删除 {len(duplicate_keys)} 个 Issue:\n")

success = 0
fail = 0
for key in duplicate_keys:
    try:
        jira.delete_issue(key)
        print(f"✅ 已删除: {key}")
        success += 1
    except Exception as e:
        print(f"❌ 删除失败 {key}: {e}")
        fail += 1

print(f"\n删除完成！成功: {success}, 失败: {fail}")

# 验证剩余任务数
resp = jira.jql("project = EDE AND issuetype = Task ORDER BY key ASC", fields=["summary"])
print(f"\n剩余 Task 数量: {len(resp.get('issues', []))}")