import sys, os, json
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from jira_client import JiraClient

jira = JiraClient().get_client()

# 查询 EDE 项目 Task 类型的创建可用字段
resp = jira.get("rest/api/2/issue/createmeta", params={
    "projectKeys": "EDE",
    "issuetypeNames": "Task",
    "expand": "projects.issuetypes.fields"
})

for proj in resp.get("projects", []):
    print(f"Project: {proj.get('key')} - {proj.get('name')}")
    for it in proj.get("issuetypes", []):
        print(f"  IssueType: {it.get('name')}")
        fields = it.get("fields", {})
        print(f"  可用字段数: {len(fields)}")
        for fid, fdata in fields.items():
            fname = fdata.get("name", "")
            ftype = fdata.get("schema", {}).get("type", "")
            required = fdata.get("required", False)
            print(f"    {fid}: {fname} (type={ftype}, required={required})")
