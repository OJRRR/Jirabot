# -*- coding: utf-8 -*-
"""Epic 创建功能实际 API 验证脚本

用法: python test_epic_live.py RDE
"""

import json
import os
import re
import sys

os.environ["PYTHONIOENCODING"] = "utf-8"

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from config import Config
from tools._lazy import LazyJira
from tools.task_tools import (
    get_create_issue_metadata,
    create_issue,
    delete_issue,
    search_issues,
)

jira = LazyJira()

GREEN = "\033[92m"
RED = "\033[91m"
YELLOW = "\033[93m"
BLUE = "\033[94m"
RESET = "\033[0m"
BOLD = "\033[1m"

pass_count = 0
fail_count = 0
created_keys = []


def ok(msg):
    global pass_count
    pass_count += 1
    print(f"  {GREEN}PASS{RESET}  {msg}")


def no(msg, detail=""):
    global fail_count
    fail_count += 1
    print(f"  {RED}FAIL{RESET}  {msg}")
    if detail:
        print(f"       {RED}{detail}{RESET}")


def warn(msg):
    print(f"  {YELLOW}WARN{RESET}  {msg}")


def info(msg):
    print(f"  {BLUE}INFO{RESET}  {msg}")


def section(title):
    print(f"\n{BOLD}{'='*60}{RESET}")
    print(f"{BOLD}{title}{RESET}")
    print(f"{BOLD}{'='*60}{RESET}")


# ============================================================
# Test 1: Config Check
# ============================================================
def test_config():
    section("Test 1: Config / Field ID Check")

    if Config.JIRA_SERVER:
        ok(f"JIRA_SERVER = {Config.JIRA_SERVER}")
    else:
        no("JIRA_SERVER not set")

    if Config.JIRA_USER:
        ok(f"JIRA_USER = {Config.JIRA_USER}")
    else:
        no("JIRA_USER not set")

    if Config.EPIC_NAME_FIELD_ID:
        ok(f"EPIC_NAME_FIELD_ID = {Config.EPIC_NAME_FIELD_ID}")
    else:
        no("EPIC_NAME_FIELD_ID not set - Epic creation may fail!")

    if Config.EPIC_LINK_FIELD_ID:
        ok(f"EPIC_LINK_FIELD_ID = {Config.EPIC_LINK_FIELD_ID}")
    else:
        no("EPIC_LINK_FIELD_ID not set - Task-Epic link will fail!")

    if Config.TARGET_START_FIELD:
        ok(f"TARGET_START_FIELD = {Config.TARGET_START_FIELD}")
    else:
        no("TARGET_START_FIELD not set")

    if Config.TARGET_END_FIELD:
        ok(f"TARGET_END_FIELD = {Config.TARGET_END_FIELD}")
    else:
        no("TARGET_END_FIELD not set")


# ============================================================
# Test 2: Check RDE project supports Epic type
# ============================================================
def test_metadata(project_key):
    section(f"Test 2: Check {project_key} project supports Epic")

    # Verify connection first
    try:
        result = jira.jql(f"project = {project_key}", limit=1)
        ok(f"Jira connection OK: {Config.JIRA_SERVER}")
    except Exception as e:
        no(f"Jira connection failed: {e}")
        return None

    # Get create metadata
    result = get_create_issue_metadata.invoke({"project_key": project_key})
    data = json.loads(result)

    if not data.get("success"):
        no(f"Metadata fetch failed: {data.get('error', 'unknown')}")
        return None

    ok(f"Metadata fetched for {project_key}")

    issue_types = data.get("data", {}).get("issue_types", [])
    type_names = [it["name"] for it in issue_types]
    info(f"Supported types: {', '.join(type_names)}")

    epic_types = [it for it in issue_types if it["name"].lower() == "epic"]
    if not epic_types:
        no(f"{project_key} does NOT support Epic type!")
        return None

    epic = epic_types[0]
    ok(f"{project_key} supports Epic type")

    # Check Epic required fields
    required = [f["name"] for f in epic.get("required_fields", [])]
    optional = [f["name"] for f in epic.get("optional_fields", [])]
    all_fields = epic.get("required_fields", []) + epic.get("optional_fields", [])

    info(f"Epic required fields: {required}")
    info(f"Epic optional fields: {len(optional)} total")

    # Check Epic Name field
    epic_name_fields = [f for f in all_fields if "epic name" in f.get("name", "").lower()]
    if epic_name_fields:
        en_field = epic_name_fields[0]
        ok(f"Epic Name field found: {en_field['key']} ({en_field['name']})")
        # Verify matches config
        if en_field["key"] == Config.EPIC_NAME_FIELD_ID:
            ok(f"EPIC_NAME_FIELD_ID matches: {Config.EPIC_NAME_FIELD_ID}")
        else:
            no(f"EPIC_NAME_FIELD_ID mismatch! Config={Config.EPIC_NAME_FIELD_ID}, Actual={en_field['key']}")
    else:
        no("Epic Name field not found in metadata!")

    # Check Epic Link field (for Task -> Epic association)
    # The Epic Link is not on the Epic type but on other types like Task
    task_types = [it for it in issue_types if it["name"].lower() == "task"]
    if task_types:
        task_fields = task_types[0].get("required_fields", []) + task_types[0].get("optional_fields", [])
        epic_link_fields = [f for f in task_fields if "epic link" in f.get("name", "").lower()]
        if epic_link_fields:
            el_field = epic_link_fields[0]
            ok(f"Epic Link field on Task: {el_field['key']} ({el_field['name']})")
            if el_field["key"] == Config.EPIC_LINK_FIELD_ID:
                ok(f"EPIC_LINK_FIELD_ID matches: {Config.EPIC_LINK_FIELD_ID}")
            else:
                no(f"EPIC_LINK_FIELD_ID mismatch! Config={Config.EPIC_LINK_FIELD_ID}, Actual={el_field['key']}")
        else:
            no("Epic Link field not found on Task type!")
    else:
        warn("Task type not found in metadata")

    return epic


# ============================================================
# Test 3: Create Epic via API
# ============================================================
def test_create_epic(project_key):
    section(f"Test 3: Create Epic via API in {project_key}")

    result = create_issue.invoke({
        "project_key": project_key,
        "summary": "[Test] Epic creation verification - please delete",
        "issue_type": "Epic",
        "description": "Auto-created by test_epic_live.py for Epic creation verification.",
        "additional_fields": {
            "Target start": "2026-07-01",
            "Target end": "2026-08-15",
        },
    })
    print(f"    Result: {result[:300]}")

    if "成功" in result:
        match = re.search(r"([A-Z]+-\d+)", result)
        if match:
            epic_key = match.group(1)
            created_keys.append(epic_key)
            ok(f"Epic created: {epic_key}")

            # Verify the created Epic via Jira API
            try:
                issue = jira.get_issue(epic_key)
                fields = issue.get("fields", {})
                issue_type = fields.get("issuetype", {}).get("name", "")

                if issue_type.lower() == "epic":
                    ok(f"Verified: {epic_key} is type 'Epic'")
                else:
                    no(f"Type mismatch: expected 'Epic', got '{issue_type}'")

                # Check Epic Name field was set
                if Config.EPIC_NAME_FIELD_ID:
                    epic_name_val = fields.get(Config.EPIC_NAME_FIELD_ID)
                    if epic_name_val:
                        ok(f"Epic Name field set: {epic_name_val}")
                    else:
                        no(f"Epic Name field ({Config.EPIC_NAME_FIELD_ID}) not set on created Epic")

                # Check Target dates
                start_val = fields.get(Config.TARGET_START_FIELD)
                end_val = fields.get(Config.TARGET_END_FIELD)
                if start_val:
                    ok(f"Target start set: {start_val}")
                else:
                    warn(f"Target start ({Config.TARGET_START_FIELD}) not set")
                if end_val:
                    ok(f"Target end set: {end_val}")
                else:
                    warn(f"Target end ({Config.TARGET_END_FIELD}) not set")

                return epic_key
            except Exception as e:
                no(f"Failed to verify created Epic: {e}")
                return epic_key
        else:
            no("Could not extract issue key from result", result[:200])
            return None
    else:
        no("Epic creation failed", result[:300])
        return None


# ============================================================
# Test 4: Epic -> Task -> Sub-task hierarchy
# ============================================================
def test_hierarchy(project_key, epic_key):
    section("Test 4: Epic -> Task -> Sub-task hierarchy")

    if not epic_key:
        warn("No Epic key available, skipping hierarchy test")
        return

    # 4a: Create Task linked to Epic
    info(f"Creating Task linked to {epic_key}...")
    task_result = create_issue.invoke({
        "project_key": project_key,
        "summary": f"[Test] Task linked to {epic_key} - please delete",
        "issue_type": "Task",
        "description": f"Test Task linked to Epic {epic_key}.",
        "epic_link_key": epic_key,
    })
    print(f"    Result: {task_result[:300]}")

    task_match = re.search(r"([A-Z]+-\d+)", task_result)
    if "成功" in task_result and task_match:
        task_key = task_match.group(1)
        created_keys.append(task_key)
        ok(f"Task created: {task_key} (linked to {epic_key})")

        # Verify Epic Link on the created Task
        try:
            task_issue = jira.get_issue(task_key)
            task_fields = task_issue.get("fields", {})
            if Config.EPIC_LINK_FIELD_ID:
                linked_epic = task_fields.get(Config.EPIC_LINK_FIELD_ID)
                if linked_epic == epic_key:
                    ok(f"Task {task_key} correctly linked to Epic {epic_key}")
                else:
                    no(f"Epic link mismatch: expected {epic_key}, got {linked_epic}")
        except Exception as e:
            no(f"Failed to verify Task-Epic link: {e}")

        # 4b: Create Sub-task under Task
        info(f"Creating Sub-task under {task_key}...")
        sub_result = create_issue.invoke({
            "project_key": project_key,
            "summary": f"[Test] Sub-task of {task_key} - please delete",
            "issue_type": "Sub-task",
            "parent_key": task_key,
        })
        print(f"    Result: {sub_result[:300]}")

        sub_match = re.search(r"([A-Z]+-\d+)", sub_result)
        if "成功" in sub_result and sub_match:
            sub_key = sub_match.group(1)
            created_keys.append(sub_key)
            ok(f"Sub-task created: {sub_key} (parent: {task_key})")

            # Verify parent relationship
            try:
                sub_issue = jira.get_issue(sub_key)
                sub_fields = sub_issue.get("fields", {})
                parent = sub_fields.get("parent", {})
                if parent.get("key") == task_key:
                    ok(f"Sub-task {sub_key} correctly has parent {task_key}")
                else:
                    no(f"Parent mismatch: expected {task_key}, got {parent.get('key')}")
            except Exception as e:
                no(f"Failed to verify Sub-task parent: {e}")
        else:
            no("Sub-task creation failed", sub_result[:300])
    else:
        no("Task creation failed", task_result[:300])
        return

    # 4c: Verify Epic -> Sub-task directly is rejected
    info("Verifying Epic -> Sub-task directly is rejected...")
    invalid_result = create_issue.invoke({
        "project_key": project_key,
        "summary": "[Test] Invalid Sub-task directly to Epic",
        "issue_type": "Sub-task",
        "epic_link_key": epic_key,
    })
    if "失败" in invalid_result and "Epic" in invalid_result:
        ok("Epic -> Sub-task directly correctly rejected")
    else:
        no("Epic -> Sub-task should have been rejected!", invalid_result[:200])


# ============================================================
# Test 5: Verify Epic Link field on existing Tasks
# ============================================================
def test_epic_link_field(project_key):
    section("Test 5: Verify EPIC_LINK_FIELD_ID on existing issues")

    # Search for a Task that has an Epic Link
    epic_link_id = Config.EPIC_LINK_FIELD_ID
    if not epic_link_id:
        no("EPIC_LINK_FIELD_ID not set, skipping")
        return

    info(f"Searching for Tasks with Epic Link ({epic_link_id}) in {project_key}...")
    try:
        jql = f'project = {project_key} AND issuetype = Task AND "{epic_link_id}" IS NOT EMPTY ORDER BY updated DESC'
        issues = jira.jql(jql, limit=5)
        if issues and issues.get("total", 0) > 0:
            issue_list = issues.get("issues", [])
            count = len(issue_list)
            ok(f"Found {count} Task(s) with Epic Link in {project_key}")

            for iss in issue_list[:3]:
                key = iss.get("key", "?")
                fields = iss.get("fields", {}) or {}
                linked = fields.get(epic_link_id, "N/A")
                info(f"  {key} -> Epic: {linked}")
        else:
            warn(f"No Tasks with Epic Link found in {project_key}")
    except Exception as e:
        no(f"Epic Link query failed: {e}")


# ============================================================
# Cleanup
# ============================================================
def cleanup():
    if not created_keys:
        return
    section("Cleanup: Deleting test issues")
    # Delete in reverse order: Sub-task first, then Task, then Epic
    for key in reversed(created_keys):
        try:
            result = delete_issue.invoke({
                "issue_key": key,
                "confirmed": True,
                "delete_subtasks": True,
            })
            if "成功" in result:
                info(f"Deleted: {key}")
            else:
                warn(f"Delete may have failed for {key}: {result[:100]}")
        except Exception as e:
            warn(f"Delete exception for {key}: {e}")


# ============================================================
# Main
# ============================================================
def main():
    global pass_count, fail_count

    if len(sys.argv) < 2:
        print("Usage: python test_epic_live.py PROJECT_KEY")
        print("Example: python test_epic_live.py RDE")
        return 1

    project_key = sys.argv[1].upper().strip()
    print(f"\n{BOLD}Epic Creation Live Verification{RESET}")
    print(f"Project: {project_key}")
    print(f"Server:  {Config.JIRA_SERVER}")
    print(f"EPIC_NAME_FIELD_ID: {Config.EPIC_NAME_FIELD_ID or '(not set)'}")
    print(f"EPIC_LINK_FIELD_ID: {Config.EPIC_LINK_FIELD_ID or '(not set)'}")

    try:
        # Test 1: Config
        test_config()

        # Test 2: Metadata / Epic support
        epic_meta = test_metadata(project_key)

        # Test 5: Existing Epic Link field verification
        test_epic_link_field(project_key)

        # Test 3: Create Epic
        epic_key = test_create_epic(project_key)

        # Test 4: Hierarchy
        if epic_key:
            test_hierarchy(project_key, epic_key)

    except Exception as e:
        import traceback
        print(f"\n{RED}Unhandled exception: {e}{RESET}")
        traceback.print_exc()
        fail_count += 1

    finally:
        cleanup()

    # Summary
    total = pass_count + fail_count
    print(f"\n{BOLD}{'='*60}{RESET}")
    if total == 0:
        print(f"{YELLOW}No tests executed{RESET}")
    elif fail_count == 0:
        print(f"{GREEN}ALL PASSED: {pass_count}/{total}{RESET}")
    else:
        print(f"{RED}FAILURES: {pass_count}/{total} passed, {fail_count} failed{RESET}")
    print(f"{BOLD}{'='*60}{RESET}\n")

    return 0 if fail_count == 0 else 1


if __name__ == "__main__":
    sys.exit(main())
