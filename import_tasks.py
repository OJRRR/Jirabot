"""从图片识别数据，批量导入 EDE 项目（日期写入描述，因EDE项目Task无Target start/end字段）"""
import sys, os
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from jira_client import JiraClient

jira = JiraClient().get_client()

tasks = [
    # === Primary DC - Wave 1 ===
    {"summary": "[PDC] Solution Confirm & Budget Release",       "start": "2026-04-01", "end": "2026-06-01"},
    {"summary": "[PDC] Infra Requirements confirm",              "start": "2026-05-01", "end": "2026-06-01"},
    {"summary": "[PDC] procurement & contract execution",        "start": "2026-06-01", "end": "2026-09-01"},
    {"summary": "[PDC] Data Center Build Out (4months)",        "start": "2026-10-01", "end": "2027-03-01"},
    {"summary": "[PDC] wave 1 - Rack & Cabling Devices & PDU",  "start": "2027-01-01", "end": "2027-03-01"},
    {"summary": "[PDC] wave 1 - Network Device Order & Delivery","start": "2026-01-01", "end": "2026-11-01"},
    {"summary": "[PDC] wave 1 - Network Configuration",         "start": "2027-01-01", "end": "2027-03-01"},
    {"summary": "[PDC] wave 1 - Server & Storage Order & Delivery","start": "2026-07-01", "end": "2026-11-01"},
    {"summary": "[PDC] wave 1 - Private Cloud Platform Implementation","start": "2027-02-01", "end": "2027-05-01"},
    {"summary": "[PDC] wave 1 - Bare Metal Implementation",     "start": "2027-02-01", "end": "2027-04-01"},
    {"summary": "[PDC] wave 1 - Tool Platform Implementation",  "start": "2027-04-01", "end": "2027-05-01"},
    {"summary": "[PDC] Infra Wave 1 Go-live",                   "start": "2027-05-01", "end": "2027-05-01"},

    # === Primary DC - Wave 2 ===
    {"summary": "[PDC] wave 2 - Rack & Cabling Devices & PDU",  "start": "2027-06-01", "end": "2027-08-01"},
    {"summary": "[PDC] wave 2 - Network Device Order & Delivery","start": "2026-12-01", "end": "2027-06-01"},
    {"summary": "[PDC] wave 2 - Network Configuration",         "start": "2027-06-01", "end": "2027-08-01"},
    {"summary": "[PDC] wave 2 - Server & Storage Order & Delivery","start": "2026-12-01", "end": "2027-04-01"},
    {"summary": "[PDC] wave 2 - Private Cloud Platform Implementation","start": "2027-07-01", "end": "2027-09-01"},
    {"summary": "[PDC] wave 2 - Bare Metal Implementation",     "start": "2027-07-01", "end": "2027-09-01"},
    {"summary": "[PDC] wave 2 - Tool Platform Implementation",  "start": "2027-08-01", "end": "2027-09-01"},
    {"summary": "[PDC] Infra Wave 2 Go-live",                   "start": "2027-09-01", "end": "2027-09-01"},

    # === Secondary DC (DR) ===
    {"summary": "[DR] DR scope confirm",                        "start": "2027-03-01", "end": "2027-10-01"},
    {"summary": "[DR] Budget Release",                          "start": "2027-03-01", "end": "2027-10-01"},
    {"summary": "[DR] Data Center Build Out (4 months)",        "start": "2027-10-01", "end": "2028-02-01"},
    {"summary": "[DR] Rack & Cabling Devices & PDU",            "start": "2028-02-01", "end": "2028-03-01"},
    {"summary": "[DR] Network Device Order & Delivery",         "start": "2027-10-01", "end": "2028-02-01"},
    {"summary": "[DR] Network Configuration",                   "start": "2028-03-01", "end": "2028-04-01"},
    {"summary": "[DR] Server & Storage Order & Delivery",       "start": "2027-10-01", "end": "2028-04-01"},
    {"summary": "[DR] Private Cloud Platform Implementation",   "start": "2028-04-01", "end": "2028-07-01"},
    {"summary": "[DR] Bare Metal Implementation",               "start": "2028-04-01", "end": "2028-06-01"},
    {"summary": "[DR] Tool Platform Implementation",            "start": "2028-07-01", "end": "2028-08-01"},
    {"summary": "[DR] DR Systems Deployment",                   "start": "2028-08-01", "end": "2028-10-01"},
    {"summary": "[DR] Infra Go-live",                           "start": "2028-10-01", "end": "2028-10-01"},
]

project_key = "EDE"
success_list = []
fail_list = []

print(f"开始批量导入到项目 {project_key}，共 {len(tasks)} 个任务...\n")

for i, task in enumerate(tasks, 1):
    try:
        desc = f"Plan Start: {task['start']}\\nPlan End: {task['end']}\\n\\nImported from DC migration plan image."
        fields = {
            "project": {"key": project_key},
            "summary": task["summary"],
            "issuetype": {"name": "Task"},
            "description": desc,
        }
        new_issue = jira.create_issue(fields=fields)
        key = new_issue.get("key")
        success_list.append((key, task["summary"], task["start"], task["end"]))
        print(f"[{i}/{len(tasks)}] ✅ {key} - {task['summary']}")
    except Exception as e:
        fail_list.append((task["summary"], str(e)))
        print(f"[{i}/{len(tasks)}] ❌ {task['summary']} - {e}")

print(f"\n{'='*60}")
print(f"导入完成！成功: {len(success_list)}, 失败: {len(fail_list)}")
if fail_list:
    print(f"\n失败任务:")
    for s, e in fail_list:
        print(f"  - {s}: {e}")

# 输出成功列表供后续使用
print(f"\n成功创建的 Issue Key 列表:")
for key, summary, start, end in success_list:
    print(f"  {key}: {summary}")
