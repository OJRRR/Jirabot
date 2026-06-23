# -*- coding: utf-8 -*-
"""Debug script: Find the actual customfield IDs for RDE project"""

import json
import os
import sys

os.environ["PYTHONIOENCODING"] = "utf-8"
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from config import Config
from tools._lazy import LazyJira
from tools.task_tools import get_create_issue_metadata

jira = LazyJira()

project_key = "RDE"

# 1. Get all fields
print("=== get_all_fields() - looking for Epic Name and Epic Link ===")
try:
    all_fields = jira.get_all_fields()
    for f in all_fields:
        name = f.get("name", "").lower()
        fid = f.get("id", "")
        if "epic" in name:
            print(f"  Field: id={fid}, name={f.get('name')}, custom={f.get('custom')}, schema={f.get('schema')}")
    # Also look for Target Start/End
    print("\n  --- Target Start/End fields ---")
    for f in all_fields:
        name = f.get("name", "").lower()
        fid = f.get("id", "")
        if "target" in name and ("start" in name or "end" in name):
            print(f"  Field: id={fid}, name={f.get('name')}, custom={f.get('custom')}, schema={f.get('schema')}")
except Exception as e:
    print(f"  ERROR: {e}")

# 2. Get create metadata raw - Epic type
print("\n=== Raw create_meta for Epic in RDE ===")
try:
    result = get_create_issue_metadata.invoke({"project_key": project_key, "issue_type_name": "Epic"})
    data = json.loads(result)
    issue_types = data.get("data", {}).get("issue_types", [])
    for it in issue_types:
        print(f"\n  Type: {it['name']}")
        print(f"  Required fields:")
        for f in it.get("required_fields", []):
            print(f"    key={f['key']}, name={f['name']}, type={f['type']}")
        print(f"  Optional fields (first 15):")
        for f in it.get("optional_fields", [])[:15]:
            print(f"    key={f['key']}, name={f['name']}, type={f['type']}")
        # Find Epic Name specifically
        for f in it.get("required_fields", []) + it.get("optional_fields", []):
            if "epic" in f.get("name", "").lower():
                print(f"  >>> EPIC FIELD: key={f['key']}, name={f['name']}, type={f['type']}")
except Exception as e:
    print(f"  ERROR: {e}")

# 3. Get create metadata raw - Task type
print("\n=== Raw create_meta for Task in RDE ===")
try:
    result = get_create_issue_metadata.invoke({"project_key": project_key, "issue_type_name": "Task"})
    data = json.loads(result)
    issue_types = data.get("data", {}).get("issue_types", [])
    for it in issue_types:
        for f in it.get("required_fields", []) + it.get("optional_fields", []):
            if "epic" in f.get("name", "").lower():
                print(f"  >>> EPIC FIELD on Task: key={f['key']}, name={f['name']}, type={f['type']}")
except Exception as e:
    print(f"  ERROR: {e}")

# 4. Try creating an Epic with just minimal fields
print("\n=== Try creating Epic with minimal fields ===")
try:
    minimal_fields = {
        "project": {"key": project_key},
        "summary": "[Test] Minimal Epic - debug",
        "issuetype": {"name": "Epic"},
    }
    result = jira.create_issue(fields=minimal_fields)
    print(f"  Created: {result.get('key')}")
    # Delete it immediately
    jira.delete_issue(result['key'], delete_subtasks=True)
    print(f"  Deleted: {result.get('key')}")
except Exception as e:
    print(f"  ERROR: {e}")

# 5. Try with epic name as a separate field (try common patterns)
print("\n=== Try different Epic Name field formats ===")
for epic_name_key in ["customfield_10005", "customfield_10006", "customfield_10800"]:
    try:
        fields = {
            "project": {"key": project_key},
            "summary": f"[Test] Epic with {epic_name_key}",
            "issuetype": {"name": "Epic"},
            epic_name_key: f"Test Epic via {epic_name_key}",
        }
        result = jira.create_issue(fields=fields)
        key = result.get('key')
        print(f"  SUCCESS with {epic_name_key}: created {key}")
        # Verify
        issue = jira.get_issue(key)
        issue_fields = issue.get('fields', {})
        epic_name_val = issue_fields.get(epic_name_key)
        print(f"    Epic Name value: {epic_name_val}")
        jira.delete_issue(key, delete_subtasks=True)
    except Exception as e:
        err = str(e)[:150]
        print(f"  FAIL with {epic_name_key}: {err}")
