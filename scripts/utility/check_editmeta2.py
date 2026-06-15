"""直接调用REST API检查可编辑字段（绕过 atlassian-python-api 抽象层）

用法：
    python scripts/utility/check_editmeta2.py
"""
import sys, os
_BASE_DIR = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
sys.path.insert(0, _BASE_DIR)

from jira_client import JiraClient

jira = JiraClient().get_client()

for key in ["EDE-2", "EDE-67"]:
    url = f"{jira.url}/rest/api/2/issue/{key}/editmeta"
    resp = jira.get(url)
    print(f"\n{key} 返回类型: {type(resp)}")
    if isinstance(resp, str):
        print(f"内容前200字符: {resp[:200]}")
    else:
        fields = resp.get("fields", {})
        print(f"可编辑字段数: {len(fields)}")
        for fid, info in fields.items():
            name = info.get("name", "")
            if "target" in name.lower():
                print(f"  ✅ {fid}: {name}")