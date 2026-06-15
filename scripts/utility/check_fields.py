"""检查EDE项目Task类型可用的字段

用法：
    python scripts/utility/check_fields.py
"""
import sys, os
_BASE_DIR = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
sys.path.insert(0, _BASE_DIR)

from jira_client import JiraClient

jira = JiraClient().get_client()

print("=== 查询 EDE 项目 Task 类型的字段元数据 ===\n")

try:
    # 新版API：获取问题类型的字段列表
    fields_data = jira.issue_createmeta_fieldtypes("EDE", "10003")  # 10003 通常是 Task
    field_values = fields_data.get("values", [])
    print(f"找到 {len(field_values)} 个字段:\n")
    for f in field_values:
        field_id = f.get("fieldId", "")
        name = f.get("name", "")
        required = f.get("required", False)
        # 只显示与 target/date 相关的字段
        if "target" in name.lower() or "date" in name.lower() or "start" in name.lower() or "end" in name.lower():
            print(f"  {field_id}: {name} (required={required})")
except Exception as e:
    print(f"新版API查询失败: {e}")
    print("尝试旧版API...")
    try:
        meta = jira.createmeta(projectKeys="EDE", issuetypeNames="Task", expand="projects.issuetypes.fields")
        fields = meta["projects"][0]["issuetypes"][0].get("fields", {})
        for field_id, info in fields.items():
            name = info.get("name", "")
            if "target" in name.lower() or "date" in name.lower() or "start" in name.lower() or "end" in name.lower():
                print(f"  {field_id}: {name}")
    except Exception as e2:
        print(f"旧版API也失败: {e2}")

# 也查一下所有自定义字段
print("\n=== 所有自定义字段（含 target/start/end）===")
try:
    all_fields = jira.get_all_custom_fields()
    for f in all_fields:
        name = f.get("name", "")
        if "target" in name.lower() or "start" in name.lower() or "end" in name.lower():
            print(f"  {f.get('id')}: {name}")
except Exception as e:
    print(f"获取自定义字段失败: {e}")