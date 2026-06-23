# -*- coding: utf-8 -*-
"""Epic 创建功能实际 API 验证脚本 v2 — 自动探测 RDE 项目的真实字段 ID

用法: python test_epic_live2.py RDE
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
# Auto-detected field IDs for the target project
detected_fields = {}


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
# Test 1: Config check + auto-detect actual field IDs
# ============================================================
def test_config_and_detect(project_key):
    global detected_fields
    section("Test 1: Config check + Auto-detect field IDs from RDE metadata")

    # 1a: Basic config
    if Config.JIRA_SERVER:
        ok(f"JIRA_SERVER = {Config.JIRA_SERVER}")
    else:
        no("JIRA_SERVER not set")

    if Config.JIRA_USER:
        ok(f"JIRA_USER = {Config.JIRA_USER}")
    else:
        no("JIRA_USER not set")

    # 1b: Show current config vs reality
    info(f"Current .env EPIC_NAME_FIELD_ID = {Config.EPIC_NAME_FIELD_ID or '(not set)'}")
    info(f"Current .env EPIC_LINK_FIELD_ID = {Config.EPIC_LINK_FIELD_ID or '(not set)'}")
    info(f"Current .env TARGET_START_FIELD = {Config.TARGET_START_FIELD}")
    info(f"Current .env TARGET_END_FIELD = {Config.TARGET_END_FIELD}")

    # 1c: Get actual metadata from RDE
    try:
        jira.jql(f"project = {project_key}", limit=1)
        ok(f"Jira connection OK")
    except Exception as e:
        no(f"Jira connection failed: {e}")
        return False

    result = get_create_issue_metadata.invoke({"project_key": project_key})
    data = json.loads(result)

    if not data.get("success"):
        no(f"Metadata fetch failed: {data.get('error', 'unknown')}")
        return False

    issue_types = data.get("data", {}).get("issue_types", [])
    type_names = [it["name"] for it in issue_types]
    info(f"RDE supported types: {', '.join(type_names)}")

    # Check Epic type
    epic_types = [it for it in issue_types if it["name"].lower() == "epic"]
    if not epic_types:
        no(f"{project_key} does NOT support Epic type!")
        return False
    ok(f"{project_key} supports Epic type")

    epic = epic_types[0]
    all_epic_fields = epic.get("required_fields", []) + epic.get("optional_fields", [])

    # Auto-detect Epic Name field
    epic_name_fields = [f for f in all_epic_fields if "epic name" in f.get("name", "").lower()]
    if epic_name_fields:
        detected_fields["epic_name"] = epic_name_fields[0]["key"]
        ok(f"Detected Epic Name field: {detected_fields['epic_name']} ({epic_name_fields[0]['name']})")
        if detected_fields["epic_name"] != Config.EPIC_NAME_FIELD_ID:
            warn(f"MISMATCH: .env has {Config.EPIC_NAME_FIELD_ID}, actual is {detected_fields['epic_name']}")
        else:
            ok("EPIC_NAME_FIELD_ID matches RDE actual")
    else:
        no("Epic Name field not found!")

    # Auto-detect Epic Link field (on Task type)
    task_types = [it for it in issue_types if it["name"].lower() == "task"]
    if task_types:
        task_fields = task_types[0].get("required_fields", []) + task_types[0].get("optional_fields", [])
        epic_link_fields = [f for f in task_fields if "epic link" in f.get("name", "").lower()]
        if epic_link_fields:
            detected_fields["epic_link"] = epic_link_fields[0]["key"]
            ok(f"Detected Epic Link field: {detected_fields['epic_link']} ({epic_link_fields[0]['name']})")
            if detected_fields["epic_link"] != Config.EPIC_LINK_FIELD_ID:
                warn(f"MISMATCH: .env has {Config.EPIC_LINK_FIELD_ID}, actual is {detected_fields['epic_link']}")
            else:
                ok("EPIC_LINK_FIELD_ID matches RDE actual")
        else:
            no("Epic Link field not found on Task!")

    # Auto-detect Target Start / Target End fields
    for target_name, target_label in [
        ("target_start", "Target Start"),
        ("target_end", "Target End"),
    ]:
        matching = [f for f in all_epic_fields if target_name.replace("_", " ") in f.get("name", "").lower()
                    or ("target" in f.get("name", "").lower() and
                        ("start" if "start" in target_name else "end") in f.get("name", "").lower())]
        if matching:
            detected_fields[target_name] = matching[0]["key"]
            config_val = Config.TARGET_START_FIELD if "start" in target_name else Config.TARGET_END_FIELD
            ok(f"Detected {target_label} field: {detected_fields[target_name]} ({matching[0]['name']})")
            if detected_fields[target_name] != config_val:
                warn(f"MISMATCH: .env has {config_val}, actual is {detected_fields[target_name]}")
            else:
                ok(f"{target_label} field ID matches RDE actual")
        else:
            warn(f"{target_label} field not found in Epic metadata (checking Task type...)")
            # Try Task type
            if task_types:
                task_all = task_types[0].get("required_fields", []) + task_types[0].get("optional_fields", [])
                matching = [f for f in task_all if target_name.replace("_", " ") in f.get("name", "").lower()
                            or ("target" in f.get("name", "").lower() and
                                ("start" if "start" in target_name else "end") in f.get("name", "").lower())]
                if matching:
                    detected_fields[target_name] = matching[0]["key"]
                    ok(f"Detected {target_label} on Task: {detected_fields[target_name]} ({matching[0]['name']})")
                else:
                    warn(f"{target_label} not found on Task type either")

    return True


# ============================================================
# Test 2: Create Epic with CORRECT field IDs
# ============================================================
def test_create_epic_correct(project_key):
    section("Test 2: Create Epic with DETECTED field IDs")

    if not detected_fields:
        no("No detected fields available, cannot create Epic")
        return None

    # Build additional_fields with the CORRECT field IDs
    additional = {}
    if "target_start" in detected_fields:
        additional[detected_fields["target_start"]] = "2026-07-01"
    if "target_end" in detected_fields:
        additional[detected_fields["target_end"]] = "2026-08-15"

    # We need to bypass the normal build_issue_fields because it uses Config.EPIC_NAME_FIELD_ID
    # which is wrong for this project. We'll use the Jira client directly.
    epic_name_field = detected_fields.get("epic_name")

    fields = {
        "project": {"key": project_key},
        "summary": "[Test] Epic creation verification v2 - please delete",
        "issuetype": {"name": "Epic"},
        "description": {
            "type": "doc",
            "version": 1,
            "content": [{"type": "paragraph", "content": [{"type": "text", "text": "Auto-created by test_epic_live2.py for RDE Epic verification."}]}],
        },
    }

    if epic_name_field:
        fields[epic_name_field] = "[Test] Epic creation verification v2 - please delete"

    for k, v in additional.items():
        fields[k] = v

    info(f"Creating Epic with fields: project={project_key}, EpicName={epic_name_field}")
    info(f"  Target Start: {detected_fields.get('target_start', 'N/A')}")
    info(f"  Target End: {detected_fields.get('target_end', 'N/A')}")

    try:
        new_issue = jira.create_issue(fields=fields)
        epic_key = new_issue.get("key")
        issue_url = f"{Config.JIRA_SERVER}/browse/{epic_key}"
        ok(f"Epic created: {epic_key} ({issue_url})")
        created_keys.append(epic_key)

        # Verify the created Epic
        try:
            issue = jira.get_issue(epic_key)
            issue_fields = issue.get("fields", {})
            issue_type = issue_fields.get("issuetype", {}).get("name", "")

            if issue_type.lower() == "epic":
                ok(f"Verified: {epic_key} is type 'Epic'")
            else:
                no(f"Type mismatch: expected 'Epic', got '{issue_type}'")

            # Check Epic Name
            if epic_name_field:
                epic_name_val = issue_fields.get(epic_name_field)
                if epic_name_val:
                    ok(f"Epic Name field ({epic_name_field}) set correctly: {epic_name_val}")
                else:
                    no(f"Epic Name field ({epic_name_field}) NOT set!")

            # Check Target dates
            for field_key, label in [
                (detected_fields.get("target_start"), "Target Start"),
                (detected_fields.get("target_end"), "Target End"),
            ]:
                if field_key:
                    val = issue_fields.get(field_key)
                    if val:
                        ok(f"{label} ({field_key}) = {val}")
                    else:
                        warn(f"{label} ({field_key}) not set on created Epic")

            return epic_key
        except Exception as e:
            no(f"Failed to verify created Epic: {e}")
            return epic_key

    except Exception as e:
        no(f"Epic creation failed: {e}")
        return None


# ============================================================
# Test 3: Epic -> Task -> Sub-task with CORRECT field IDs
# ============================================================
def test_hierarchy_correct(project_key, epic_key):
    section("Test 3: Epic -> Task -> Sub-task hierarchy (correct field IDs)")

    if not epic_key:
        warn("No Epic key available, skipping hierarchy test")
        return

    epic_link_field = detected_fields.get("epic_link")

    if not epic_link_field:
        no("Epic Link field not detected, cannot link Task to Epic")
        return

    # 3a: Create Task linked to Epic
    info(f"Creating Task linked to Epic {epic_key} (using field {epic_link_field})...")

    task_fields = {
        "project": {"key": project_key},
        "summary": f"[Test] Task linked to {epic_key} - please delete",
        "issuetype": {"name": "Task"},
        "description": {
            "type": "doc",
            "version": 1,
            "content": [{"type": "paragraph", "content": [{"type": "text", "text": f"Test Task linked to Epic {epic_key}."}]}],
        },
        epic_link_field: epic_key,
    }

    try:
        new_task = jira.create_issue(fields=task_fields)
        task_key = new_task.get("key")
        ok(f"Task created: {task_key}")
        created_keys.append(task_key)

        # Verify Epic Link on Task
        try:
            task_issue = jira.get_issue(task_key)
            task_f = task_issue.get("fields", {})
            linked_epic = task_f.get(epic_link_field)
            if linked_epic == epic_key:
                ok(f"Task {task_key} correctly linked to Epic {epic_key} (via {epic_link_field})")
            else:
                no(f"Epic Link mismatch: expected {epic_key}, got {linked_epic}")
        except Exception as e:
            no(f"Failed to verify Epic Link: {e}")

        # 3b: Create Sub-task under Task
        info(f"Creating Sub-task under {task_key}...")
        sub_fields = {
            "project": {"key": project_key},
            "summary": f"[Test] Sub-task of {task_key} - please delete",
            "issuetype": {"name": "Sub-task"},
            "parent": {"key": task_key},
        }

        try:
            new_sub = jira.create_issue(fields=sub_fields)
            sub_key = new_sub.get("key")
            ok(f"Sub-task created: {sub_key}")
            created_keys.append(sub_key)

            # Verify parent
            try:
                sub_issue = jira.get_issue(sub_key)
                sub_f = sub_issue.get("fields", {})
                parent = sub_f.get("parent", {})
                if parent.get("key") == task_key:
                    ok(f"Sub-task {sub_key} has correct parent: {task_key}")
                else:
                    no(f"Parent mismatch: expected {task_key}, got {parent.get('key')}")
            except Exception as e:
                no(f"Failed to verify parent: {e}")
        except Exception as e:
            no(f"Sub-task creation failed: {e}")

    except Exception as e:
        no(f"Task creation failed: {e}")
        return

    # 3c: Verify Epic -> Sub-task directly is rejected
    info("Verifying Epic -> Sub-task directly is rejected...")
    try:
        invalid_fields = {
            "project": {"key": project_key},
            "summary": "[Test] Invalid: Sub-task directly to Epic",
            "issuetype": {"name": "Sub-task"},
            epic_link_field: epic_key,
        }
        jira.create_issue(fields=invalid_fields)
        no("Epic -> Sub-task should have been REJECTED by Jira!")
    except Exception as e:
        err_str = str(e)
        if "epic" in err_str.lower() or "sub-task" in err_str.lower() or "cannot" in err_str.lower():
            ok(f"Epic -> Sub-task correctly rejected by Jira: {err_str[:120]}")
        else:
            warn(f"Epic -> Sub-task rejected but unexpected error: {err_str[:120]}")


# ============================================================
# Test 4: Verify Epic Link on existing issues
# ============================================================
def test_existing_epic_link(project_key):
    section("Test 4: Verify Epic Link field on existing RDE issues")

    epic_link_field = detected_fields.get("epic_link")
    if not epic_link_field:
        no("Epic Link field not detected")
        return

    info(f"Searching for Tasks with Epic Link ({epic_link_field}) in {project_key}...")
    try:
        jql = f'project = {project_key} AND issuetype = Task AND "{epic_link_field}" IS NOT EMPTY ORDER BY updated DESC'
        issues = jira.jql(jql, limit=5)
        if issues and issues.get("total", 0) > 0:
            count = issues.get("total", 0)
            ok(f"Found {count} Task(s) with Epic Link in {project_key}")
            for iss in issues.get("issues", [])[:3]:
                key = iss.get("key", "?")
                fields = iss.get("fields", {}) or {}
                linked = fields.get(epic_link_field, "N/A")
                info(f"  {key} -> Epic: {linked}")
        else:
            warn(f"No Tasks with Epic Link found in {project_key}")
    except Exception as e:
        no(f"Epic Link query failed: {e}")


# ============================================================
# Test 5: Verify create_issue tool with corrected field IDs
# ============================================================
def test_create_issue_tool_correct(project_key, epic_key):
    section("Test 5: Verify create_issue tool with CORRECT field IDs")

    if not epic_key:
        warn("No Epic key, skipping")
        return

    epic_link_field = detected_fields.get("epic_link")
    epic_name_field = detected_fields.get("epic_name")

    # Monkey-patch Config temporarily for this test
    import tools.task_common
    orig_epic_name = tools.task_common.Config.EPIC_NAME_FIELD_ID
    orig_epic_link = tools.task_common.Config.EPIC_LINK_FIELD_ID

    try:
        # Set correct field IDs for this project
        tools.task_common.Config.EPIC_NAME_FIELD_ID = epic_name_field
        tools.task_common.Config.EPIC_LINK_FIELD_ID = epic_link_field

        # 5a: Create Task via create_issue tool with epic_link_key
        info(f"Creating Task via create_issue tool (epic_link_key={epic_key})...")
        result = create_issue.invoke({
            "project_key": project_key,
            "summary": f"[Test] Tool-created Task for {epic_key} - please delete",
            "issue_type": "Task",
            "description": f"Created by create_issue tool, linked to {epic_key}.",
            "epic_link_key": epic_key,
        })
        info(f"  Result: {result[:250]}")

        task_match = re.search(r"([A-Z]+-\d+)", result)
        if "成功" in result and task_match:
            task_key = task_match.group(1)
            created_keys.append(task_key)
            ok(f"create_issue tool created Task: {task_key}")

            # Verify the Epic Link
            try:
                task_issue = jira.get_issue(task_key)
                task_f = task_issue.get("fields", {})
                linked = task_f.get(epic_link_field)
                if linked == epic_key:
                    ok(f"Tool-created Task {task_key} correctly linked to Epic {epic_key}")
                else:
                    no(f"Tool-created Task Epic Link mismatch: expected {epic_key}, got {linked}")
            except Exception as e:
                no(f"Failed to verify tool-created Task: {e}")

            # 5b: Create Sub-task via create_issue tool
            info(f"Creating Sub-task via create_issue tool (parent={task_key})...")
            sub_result = create_issue.invoke({
                "project_key": project_key,
                "summary": f"[Test] Tool-created Sub-task of {task_key} - please delete",
                "issue_type": "Sub-task",
                "parent_key": task_key,
            })
            info(f"  Result: {sub_result[:250]}")

            sub_match = re.search(r"([A-Z]+-\d+)", sub_result)
            if "成功" in sub_result and sub_match:
                sub_key = sub_match.group(1)
                created_keys.append(sub_key)
                ok(f"create_issue tool created Sub-task: {sub_key}")
            else:
                no("create_issue tool failed to create Sub-task", sub_result[:200])
        else:
            no("create_issue tool failed to create Task", result[:200])

        # 5c: Test that create_issue rejects Epic -> Sub-task
        info("Testing create_issue tool rejects Epic -> Sub-task...")
        invalid_result = create_issue.invoke({
            "project_key": project_key,
            "summary": "[Test] Invalid Sub-task direct to Epic",
            "issue_type": "Sub-task",
            "epic_link_key": epic_key,
        })
        if "失败" in invalid_result and "Epic" in invalid_result:
            ok("create_issue tool correctly rejects Epic -> Sub-task")
        else:
            no("create_issue tool should reject Epic -> Sub-task!", invalid_result[:200])

    finally:
        # Restore original config
        tools.task_common.Config.EPIC_NAME_FIELD_ID = orig_epic_name
        tools.task_common.Config.EPIC_LINK_FIELD_ID = orig_epic_link


# ============================================================
# Cleanup
# ============================================================
def cleanup():
    if not created_keys:
        return
    section("Cleanup: Deleting test issues")
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
        print("Usage: python test_epic_live2.py PROJECT_KEY")
        print("Example: python test_epic_live2.py RDE")
        return 1

    project_key = sys.argv[1].upper().strip()
    print(f"\n{BOLD}Epic Creation Live Verification v2{RESET}")
    print(f"Project: {project_key}")
    print(f"Server:  {Config.JIRA_SERVER}")

    try:
        # Test 1: Config + auto-detect
        if not test_config_and_detect(project_key):
            print(f"\n{RED}Cannot proceed: failed to detect field IDs{RESET}")
            return 1

        # Test 4: Existing Epic Link
        test_existing_epic_link(project_key)

        # Test 2: Create Epic with correct field IDs
        epic_key = test_create_epic_correct(project_key)

        # Test 3: Hierarchy
        if epic_key:
            test_hierarchy_correct(project_key, epic_key)

        # Test 5: create_issue tool with corrected IDs
        if epic_key:
            test_create_issue_tool_correct(project_key, epic_key)

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
