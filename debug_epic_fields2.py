# -*- coding: utf-8 -*-
"""Debug v2: Test Epic Link format and full hierarchy"""

import os
import sys

os.environ["PYTHONIOENCODING"] = "utf-8"
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from config import Config
from tools._lazy import LazyJira

jira = LazyJira()
project_key = "RDE"

# Correct field IDs for RDE:
# Epic Name: customfield_10005
# Epic Link: customfield_10006 (type=any, gh-epic-link)
# Target start: customfield_12914
# Target end: customfield_12915

created = []

try:
    # 1. Create Epic
    print("=== 1. Create Epic ===")
    epic_fields = {
        "project": {"key": project_key},
        "summary": "[Test] Hierarchy test Epic - please delete",
        "issuetype": {"name": "Epic"},
        "customfield_10005": "[Test] Hierarchy test Epic",
        "customfield_12914": "2026-07-01",
        "customfield_12915": "2026-08-15",
    }
    epic = jira.create_issue(fields=epic_fields)
    epic_key = epic["key"]
    created.append(epic_key)
    print(f"  Epic created: {epic_key}")

    # Verify fields
    ep = jira.get_issue(epic_key)
    ef = ep.get("fields", {})
    print(f"  Epic Name: {ef.get('customfield_10005')}")
    print(f"  Target start: {ef.get('customfield_12914')}")
    print(f"  Target end: {ef.get('customfield_12915')}")

    # 2. Create Task linked to Epic - try different Epic Link formats
    print("\n=== 2. Create Task with Epic Link ===")

    # Format A: Direct string
    task_fields_a = {
        "project": {"key": project_key},
        "summary": f"[Test] Task-A for {epic_key}",
        "issuetype": {"name": "Task"},
        "customfield_10006": epic_key,
    }
    try:
        task_a = jira.create_issue(fields=task_fields_a)
        task_key_a = task_a["key"]
        created.append(task_key_a)
        print(f"  Format A (direct string): SUCCESS - {task_key_a}")
        tf = jira.get_issue(task_key_a).get("fields", {})
        print(f"    Epic Link value: {tf.get('customfield_10006')}")
    except Exception as e:
        print(f"  Format A (direct string): FAIL - {str(e)[:200]}")

    # Format B: As dict with key
    task_fields_b = {
        "project": {"key": project_key},
        "summary": f"[Test] Task-B for {epic_key}",
        "issuetype": {"name": "Task"},
        "customfield_10006": {"key": epic_key},
    }
    try:
        task_b = jira.create_issue(fields=task_fields_b)
        task_key_b = task_b["key"]
        created.append(task_key_b)
        print(f"  Format B (dict key): SUCCESS - {task_key_b}")
        tf = jira.get_issue(task_key_b).get("fields", {})
        print(f"    Epic Link value: {tf.get('customfield_10006')}")
    except Exception as e:
        print(f"  Format B (dict key): FAIL - {str(e)[:200]}")

    # Format C: As int ID (if Epic has numeric ID)
    epic_id = ep.get("id")
    task_fields_c = {
        "project": {"key": project_key},
        "summary": f"[Test] Task-C for {epic_key}",
        "issuetype": {"name": "Task"},
        "customfield_10006": epic_id,
    }
    try:
        task_c = jira.create_issue(fields=task_fields_c)
        task_key_c = task_c["key"]
        created.append(task_key_c)
        print(f"  Format C (int id): SUCCESS - {task_key_c}")
        tf = jira.get_issue(task_key_c).get("fields", {})
        print(f"    Epic Link value: {tf.get('customfield_10006')}")
    except Exception as e:
        print(f"  Format C (int id): FAIL - {str(e)[:200]}")

    # 3. Create Sub-task (doesn't need Epic Link, needs parent)
    print("\n=== 3. Create Sub-task under Task ===")
    # Find a Task to use as parent (use the first successful one)
    parent_key = None
    for k in created:
        if k != epic_key:
            parent_key = k
            break

    if parent_key:
        sub_fields = {
            "project": {"key": project_key},
            "summary": f"[Test] Sub-task under {parent_key}",
            "issuetype": {"name": "Sub-task"},
            "parent": {"key": parent_key},
        }
        try:
            sub = jira.create_issue(fields=sub_fields)
            sub_key = sub["key"]
            created.append(sub_key)
            print(f"  Sub-task created: {sub_key} (parent: {parent_key})")
            sf = jira.get_issue(sub_key).get("fields", {})
            print(f"    Parent: {sf.get('parent', {}).get('key')}")
        except Exception as e:
            print(f"  Sub-task FAIL: {str(e)[:200]}")
    else:
        print("  No parent Task available")

    # 4. Verify Epic -> Sub-task directly is rejected
    print("\n=== 4. Epic -> Sub-task directly (should fail) ===")
    sub_direct_fields = {
        "project": {"key": project_key},
        "summary": "[Test] Invalid Sub-task to Epic",
        "issuetype": {"name": "Sub-task"},
        "customfield_10006": epic_key,
    }
    try:
        bad = jira.create_issue(fields=sub_direct_fields)
        print(f"  UNEXPECTED SUCCESS: {bad['key']} - Jira allowed it!")
        created.append(bad['key'])
    except Exception as e:
        print(f"  Correctly rejected: {str(e)[:200]}")

finally:
    # Cleanup
    print(f"\n=== Cleanup ({len(created)} issues) ===")
    for key in reversed(created):
        try:
            jira.delete_issue(key, delete_subtasks=True)
            print(f"  Deleted: {key}")
        except Exception as e:
            print(f"  Failed to delete {key}: {str(e)[:100]}")
