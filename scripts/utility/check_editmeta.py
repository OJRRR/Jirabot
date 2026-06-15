"""检查EDE项目Task类型的可编辑字段

用法：
    python scripts/utility/check_editmeta.py
"""
import sys, os
_BASE_DIR = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
sys.path.insert(0, _BASE_DIR)

from jira_client import JiraClient

jira = JiraClient().get_client()

print("=== 检查 EDE-2 (Task) 的可编辑字段 ===\n")
try:
    meta = jira.get_issue_edit_meta("EDE-2")
    fields = meta.get("fields", {})
    print(f"可编辑字段数量: {len(fields)}\n")
    for field_id, info in fields.items():
        name = info.get("name", "")
        if "target" in name.lower() or "start" in name.lower() or "end" in name.lower():
            print(f"  ✅ {field_id}: {name}")
except Exception as e:
    print(f"查询失败: {e}")

print("\n=== 检查 EDE-67 (Epic) 的可编辑字段 ===\n")
try:
    meta = jira.get_issue_edit_meta("EDE-67")
    fields = meta.get("fields", {})
    for field_id, info in fields.items():
        name = info.get("name", "")
        if "target" in name.lower() or "start" in name.lower() or "end" in name.lower():
            print(f"  ✅ {field_id}: {name}")
except Exception as e:
    print(f"查询失败: {e}")