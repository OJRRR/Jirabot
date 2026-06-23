# -*- coding: utf-8 -*-
"""Epic 创建功能检测脚本

测试 Epic 创建的完整链路：
1. 元数据获取 — 确认项目支持 Epic 类型
2. build_issue_fields — 验证 Epic 字段构造逻辑
3. 层级规则 — 验证 Epic → Task → Sub-task 的约束
4. 干跑创建 — 使用 confirmed=False 模式模拟
5. API 测试 — 可选的实际 API 调用（需设置 TEST_CREATE_EPIC=1）

用法:
    # 仅本地逻辑检测（不调用 Jira API）
    python test_epic_creation.py

    # 包含实际 Jira API 调用（会真的创建/删除 Issue）
    python test_epic_creation.py --live KO

输出: 每项检查的通过/失败状态 + 总结
"""
import json
import os
import sys
import argparse
from unittest.mock import patch, MagicMock

# 确保项目根目录在 sys.path 中
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from config import Config
from tools.task_common import build_issue_fields, process_additional_fields

# ── 颜色输出 ──
GREEN = "\033[92m"
RED = "\033[91m"
YELLOW = "\033[93m"
BLUE = "\033[94m"
RESET = "\033[0m"
BOLD = "\033[1m"


def ok(msg: str):
    print(f"  {GREEN}✅ PASS{RESET}  {msg}")


def fail(msg: str, detail: str = ""):
    print(f"  {RED}❌ FAIL{RESET}  {msg}")
    if detail:
        print(f"       {RED}{detail}{RESET}")


def warn(msg: str):
    print(f"  {YELLOW}⚠️  WARN{RESET}  {msg}")


def info(msg: str):
    print(f"  {BLUE}ℹ{RESET}  {msg}")


# ═══════════════════════════════════════════════════════════════
# 检测 1: Config 配置检测
# ═══════════════════════════════════════════════════════════════
def check_config():
    print(f"\n{BOLD}📋 检测 1: 配置检测{RESET}")

    checks = 0
    passed = 0

    # 1a: Jira 连接配置
    if Config.JIRA_SERVER:
        ok(f"JIRA_SERVER = {Config.JIRA_SERVER}")
        passed += 1
    else:
        fail("JIRA_SERVER 未配置")
    checks += 1

    # 1b: EPIC_NAME_FIELD_ID
    if Config.EPIC_NAME_FIELD_ID:
        ok(f"EPIC_NAME_FIELD_ID = {Config.EPIC_NAME_FIELD_ID}")
        passed += 1
    else:
        warn("EPIC_NAME_FIELD_ID 未配置（Epic 创建时不会自动设置 Epic Name）")
    checks += 1

    # 1c: EPIC_LINK_FIELD_ID
    if Config.EPIC_LINK_FIELD_ID:
        ok(f"EPIC_LINK_FIELD_ID = {Config.EPIC_LINK_FIELD_ID}")
        passed += 1
    else:
        warn("EPIC_LINK_FIELD_ID 未配置（创建 Task 时无法关联 Epic）")
    checks += 1

    # 1d: TARGET_START_FIELD / TARGET_END_FIELD
    if Config.TARGET_START_FIELD:
        ok(f"TARGET_START_FIELD = {Config.TARGET_START_FIELD}")
        passed += 1
    else:
        fail("TARGET_START_FIELD 未配置")
    checks += 1

    if Config.TARGET_END_FIELD:
        ok(f"TARGET_END_FIELD = {Config.TARGET_END_FIELD}")
        passed += 1
    else:
        fail("TARGET_END_FIELD 未配置")
    checks += 1

    return passed, checks


# ═══════════════════════════════════════════════════════════════
# 检测 2: build_issue_fields — Epic 字段构造
# ═══════════════════════════════════════════════════════════════
def check_build_issue_fields():
    print(f"\n{BOLD}🔧 检测 2: build_issue_fields — Epic 字段构造{RESET}")

    passed = 0
    checks = 0

    # 2a: 基本 Epic 创建
    fields, err = build_issue_fields("KO", "用户登录模块", "Epic", description="实现登录")
    if err is None and fields["issuetype"] == {"name": "Epic"}:
        ok("基本 Epic 字段构造成功")
        passed += 1
    else:
        fail("基本 Epic 字段构造失败", str(err))
    checks += 1

    # 2b: Epic Name 字段自动设置
    if Config.EPIC_NAME_FIELD_ID:
        epic_name_key = Config.EPIC_NAME_FIELD_ID
        if epic_name_key in fields:
            if fields[epic_name_key] == "用户登录模块":
                ok(f"Epic Name ({epic_name_key}) 自动设为 summary")
                passed += 1
            else:
                fail(f"Epic Name 值不匹配: {fields.get(epic_name_key)}")
        else:
            fail(f"Epic Name 字段 ({epic_name_key}) 未出现在 fields 中")
            info(f"  当前 fields keys: {list(fields.keys())}")
        checks += 1
    else:
        info("跳过（EPIC_NAME_FIELD_ID 未配置）")
        if "parent" not in fields:
            ok("Epic 没有 parent 字段")
            passed += 1
        checks += 1

    # 2c: 描述字段（ADF 格式）
    if "description" in fields:
        desc = fields["description"]
        if desc.get("type") == "doc" and desc.get("version") == 1:
            ok("描述使用 ADF 格式")
            passed += 1
        else:
            fail("描述格式不正确")
        checks += 1

    # 2d: Epic + Target 日期
    fields2, err2 = build_issue_fields(
        "KO", "带日期的Epic", "Epic",
        additional_fields={
            Config.TARGET_START_FIELD: "2026-07-01",
            Config.TARGET_END_FIELD: "2026-08-15",
        },
    )
    if err2 is None:
        start_ok = fields2.get(Config.TARGET_START_FIELD) == "2026-07-01"
        end_ok = fields2.get(Config.TARGET_END_FIELD) == "2026-08-15"
        if start_ok and end_ok:
            ok("Epic + Target Start/End 日期正确")
            passed += 1
        else:
            fail(f"日期字段不匹配: start={fields2.get(Config.TARGET_START_FIELD)}, end={fields2.get(Config.TARGET_END_FIELD)}")
        checks += 1

    # 2e: 日期别名映射
    fields3, err3 = build_issue_fields(
        "KO", "日期别名Epic", "Epic",
        additional_fields={"Target start": "2026-07-01", "Target end": "2026-08-15"},
    )
    if err3 is None:
        if fields3.get(Config.TARGET_START_FIELD) == "2026-07-01":
            ok("日期别名映射 (Target start → customfield ID) 正确")
            passed += 1
        else:
            fail(f"日期别名映射失败: {fields3.get(Config.TARGET_START_FIELD)}")
        checks += 1

    return passed, checks


# ═══════════════════════════════════════════════════════════════
# 检测 3: 层级规则验证
# ═══════════════════════════════════════════════════════════════
def check_hierarchy_rules():
    print(f"\n{BOLD}🏗️  检测 3: 层级规则验证{RESET}")

    passed = 0
    checks = 0

    # 3a: Epic → Sub-task 应被拒绝
    fields, err = build_issue_fields("KO", "子任务", "Sub-task", epic_link_key="KO-100")
    if fields is None and err is not None and "Epic" in err:
        ok("Epic → Sub-task 被正确拒绝")
        passed += 1
    else:
        fail("Epic → Sub-task 未被拒绝（应报错）", f"err={err}, fields={fields}")
    checks += 1

    # 3b: Task → Epic 关联（正常）
    with patch.object(Config, "EPIC_LINK_FIELD_ID", "customfield_10002"):
        fields, err = build_issue_fields("KO", "设计任务", "Task", epic_link_key="KO-200")
    if err is None and fields.get("customfield_10002") == "KO-200":
        ok("Task → Epic 关联正确")
        passed += 1
    else:
        fail("Task → Epic 关联失败", str(err))
    checks += 1

    # 3c: Sub-task → Task 父子关系
    fields, err = build_issue_fields("KO", "子任务", "Sub-task", parent_key="KO-201")
    if err is None and fields.get("parent") == {"key": "KO-201"}:
        ok("Sub-task → Task 父子关系正确")
        passed += 1
    else:
        fail("Sub-task → Task 父子关系失败", str(err))
    checks += 1

    # 3d: Epic 不应有 parent
    fields, err = build_issue_fields("KO", "顶层Epic", "Epic")
    if err is None and "parent" not in fields:
        ok("Epic 无 parent 字段（正确）")
        passed += 1
    else:
        fail("Epic 不应有 parent 字段", str(err))
    checks += 1

    return passed, checks


# ═══════════════════════════════════════════════════════════════
# 检测 4: create_issue 工具层检测
# ═══════════════════════════════════════════════════════════════
def check_create_issue_tool():
    print(f"\n{BOLD}🛠️  检测 4: create_issue 工具层检测{RESET}")

    from tools.task_tools import create_issue

    passed = 0
    checks = 0

    # 4a: 缺少 issue_type
    result = create_issue.invoke({"project_key": "KO", "summary": "测试"})
    if "失败" in result and "issue_type" in result.lower():
        ok("缺少 issue_type 时正确报错")
        passed += 1
    else:
        fail("缺少 issue_type 时未正确报错", result[:200])
    checks += 1

    # 4b: Epic 创建（mock）
    with patch("tools.task_tools.jira") as mock_jira:
        mock_jira.create_issue.return_value = {"key": "KO-999"}
        result = create_issue.invoke({
            "project_key": "KO",
            "summary": "功能检测Epic",
            "issue_type": "Epic",
            "description": "用于功能检测的Epic",
        })
        if "成功" in result and "KO-999" in result:
            ok("Epic 创建（mock）成功")
            passed += 1
        else:
            fail("Epic 创建（mock）失败", result[:200])
    checks += 1

    # 4c: Epic → Sub-task 层级校验（通过 create_issue）
    result = create_issue.invoke({
        "project_key": "KO",
        "summary": "违规子任务",
        "issue_type": "Sub-task",
        "epic_link_key": "KO-100",
    })
    if "失败" in result and "Epic" in result:
        ok("create_issue 层 Epic→Sub-task 层级校验正确")
        passed += 1
    else:
        fail("create_issue 层层级校验未生效", result[:200])
    checks += 1

    # 4d: 批量创建 Epic
    from tools.task_tools import batch_create_issues
    with patch("tools.task_tools.jira") as mock_jira:
        mock_jira.bulk_create_issues.return_value = {
            "created": [{"key": "KO-300"}, {"key": "KO-301"}],
            "errors": [],
        }
        tasks_json = json.dumps({
            "tasks": [
                {"project_key": "KO", "summary": "Epic A", "issue_type": "Epic"},
                {"project_key": "KO", "summary": "Epic B", "issue_type": "Epic"},
            ]
        })
        result = batch_create_issues.invoke({"issues_json": tasks_json})
        if "成功: 2" in result:
            ok("批量创建 Epic 成功")
            passed += 1
        else:
            fail("批量创建 Epic 失败", result[:200])
    checks += 1

    return passed, checks


# ═══════════════════════════════════════════════════════════════
# 检测 5: 元数据获取（项目是否支持 Epic）
# ═══════════════════════════════════════════════════════════════
def check_metadata(project_key: str = None):
    print(f"\n{BOLD}📊 检测 5: 项目元数据 — 确认 Epic 类型支持{RESET}")

    if not project_key:
        info("未指定项目，跳过（使用 --live PROJECT_KEY 启用）")
        return 0, 0

    from tools.task_tools import get_create_issue_metadata

    result = get_create_issue_metadata.invoke({"project_key": project_key})
    data = json.loads(result)

    passed = 0
    checks = 0

    if data.get("success"):
        ok(f"项目 {project_key} 元数据获取成功")
        passed += 1
        checks += 1

        issue_types = data.get("data", {}).get("issue_types", [])
        type_names = [it["name"] for it in issue_types]
        info(f"支持的问题类型: {', '.join(type_names)}")

        # 检查是否支持 Epic
        epic_types = [it for it in issue_types if it["name"].lower() == "epic"]
        if epic_types:
            epic = epic_types[0]
            ok("项目支持 Epic 类型")
            passed += 1

            # 显示 Epic 的必填字段
            required = [f["name"] for f in epic.get("required_fields", [])]
            optional = [f["name"] for f in epic.get("optional_fields", [])]
            info(f"Epic 必填字段: {required}")
            info(f"Epic 可选字段 ({len(optional)} 个)")

            # 检查 Epic Name 字段是否在必填中
            epic_name_fields = [f for f in epic.get("required_fields", []) if "epic name" in f.get("name", "").lower()]
            if epic_name_fields:
                ok(f"Epic Name 字段已识别: {epic_name_fields[0]['key']}")
                passed += 1
            else:
                # 可能在可选字段中
                epic_name_fields = [f for f in epic.get("optional_fields", []) if "epic name" in f.get("name", "").lower()]
                if epic_name_fields:
                    warn(f"Epic Name 在可选字段中: {epic_name_fields[0]['key']}")
                else:
                    warn("未找到 Epic Name 字段（可能 Jira 会自动处理）")
            checks += 1

            # 检查 Target Start/End
            all_fields = epic.get("required_fields", []) + epic.get("optional_fields", [])
            target_start = [f for f in all_fields if "target start" in f.get("name", "").lower()]
            target_end = [f for f in all_fields if "target end" in f.get("name", "").lower()]
            if target_start:
                ok(f"Target Start 字段: {target_start[0]['key']}")
                passed += 1
            else:
                warn("未找到 Target Start 字段")
            checks += 1
            if target_end:
                ok(f"Target End 字段: {target_end[0]['key']}")
                passed += 1
            else:
                warn("未找到 Target End 字段")
            checks += 1

        else:
            fail(f"项目 {project_key} 不支持 Epic 类型")
            checks += 1
    else:
        fail(f"元数据获取失败: {data.get('error', '未知错误')}")
        checks += 1

    return passed, checks


# ═══════════════════════════════════════════════════════════════
# 检测 6: 实际 Jira API 调用（可选，需 --live）
# ═══════════════════════════════════════════════════════════════
def check_live_api(project_key: str):
    """实际调用 Jira API 创建并删除 Epic（完整生命周期测试）"""
    print(f"\n{BOLD}🌐 检测 6: 实际 Jira API 调用 — Epic 生命周期{RESET}")

    if not project_key:
        info("未指定项目，跳过（使用 --live PROJECT_KEY 启用）")
        return 0, 0

    from tools._lazy import LazyJira
    from tools.task_tools import create_issue, delete_issue, get_create_issue_metadata

    jira = LazyJira()

    # 检查连接
    try:
        jira.jql("project = " + project_key, limit=1)
        ok(f"Jira 连接正常 ({Config.JIRA_SERVER})")
    except Exception as e:
        fail(f"Jira 连接失败: {e}")
        return 0, 1

    passed = 0
    checks = 0
    created_keys = []

    try:
        # 6a: 创建 Epic
        print(f"\n  {BLUE}→ 创建 Epic...{RESET}")
        epic_result = create_issue.invoke({
            "project_key": project_key,
            "summary": f"[功能检测] 测试Epic - 请删除",
            "issue_type": "Epic",
            "description": "这是自动化功能检测创建的 Epic，可以安全删除。",
            "additional_fields": {
                "Target start": "2026-07-01",
                "Target end": "2026-08-15",
            },
        })
        print(f"    {epic_result[:200]}")

        if "成功" in epic_result:
            # 提取 Issue Key
            import re
            match = re.search(r"([A-Z]+-\d+)", epic_result)
            if match:
                epic_key = match.group(1)
                created_keys.append(epic_key)
                ok(f"Epic 创建成功: {epic_key}")
                passed += 1

                # 6b: 创建关联的 Task
                print(f"\n  {BLUE}→ 创建 Task 并关联到 Epic...{RESET}")
                task_result = create_issue.invoke({
                    "project_key": project_key,
                    "summary": f"[功能检测] 测试Task - 关联{epic_key}",
                    "issue_type": "Task",
                    "description": f"这是关联到 {epic_key} 的测试 Task。",
                    "epic_link_key": epic_key,
                })
                print(f"    {task_result[:200]}")

                task_match = re.search(r"([A-Z]+-\d+)", task_result)
                if "成功" in task_result and task_match:
                    task_key = task_match.group(1)
                    created_keys.append(task_key)
                    ok(f"Task 创建成功: {task_key} (关联 {epic_key})")
                    passed += 1

                    # 6c: 创建 Sub-task
                    print(f"\n  {BLUE}→ 创建 Sub-task 挂在 Task 下...{RESET}")
                    subtask_result = create_issue.invoke({
                        "project_key": project_key,
                        "summary": f"[功能检测] 测试Subtask - 父{task_key}",
                        "issue_type": "Sub-task",
                        "parent_key": task_key,
                    })
                    print(f"    {subtask_result[:200]}")

                    subtask_match = re.search(r"([A-Z]+-\d+)", subtask_result)
                    if "成功" in subtask_result and subtask_match:
                        subtask_key = subtask_match.group(1)
                        created_keys.append(subtask_key)
                        ok(f"Sub-task 创建成功: {subtask_key} (父: {task_key})")
                        passed += 1
                    else:
                        fail("Sub-task 创建失败", subtask_result[:200])
                    checks += 1
                else:
                    fail("Task 创建失败", task_result[:200])
                checks += 1
            else:
                fail("无法从结果中提取 Epic Key", epic_result[:200])
            checks += 1
        else:
            fail("Epic 创建失败", epic_result[:200])
        checks += 1

        # 6d: 验证 Epic → Sub-task 直接关联被拒绝
        print(f"\n  {BLUE}→ 验证 Epic → Sub-task 被拒绝...{RESET}")
        invalid_result = create_issue.invoke({
            "project_key": project_key,
            "summary": "[功能检测] 违规子任务",
            "issue_type": "Sub-task",
            "epic_link_key": epic_key if created_keys else f"{project_key}-99999",
        })
        if "失败" in invalid_result and "Epic" in invalid_result:
            ok("Epic → Sub-task 直接关联被正确拒绝")
            passed += 1
        else:
            fail("Epic → Sub-task 未被拒绝（层级校验失效）", invalid_result[:200])
        checks += 1

    finally:
        # 清理：删除创建的所有 Issue
        if created_keys:
            print(f"\n  {YELLOW}🧹 清理: 删除创建的测试 Issue...{RESET}")
            for key in created_keys:
                try:
                    delete_result = delete_issue.invoke({
                        "issue_key": key,
                        "confirmed": True,
                        "delete_subtasks": True,
                    })
                    if "成功" in delete_result:
                        print(f"    ✅ 已删除 {key}")
                    else:
                        print(f"    ⚠️ 删除 {key} 可能失败: {delete_result[:100]}")
                except Exception as e:
                    print(f"    ❌ 删除 {key} 异常: {e}")

    return passed, checks


# ═══════════════════════════════════════════════════════════════
# 主入口
# ═══════════════════════════════════════════════════════════════
def main():
    parser = argparse.ArgumentParser(description="Epic 创建功能检测")
    parser.add_argument("--live", type=str, metavar="PROJECT_KEY",
                        help="指定项目 KEY 以执行实际 Jira API 测试（会创建并自动删除测试 Issue）")
    args = parser.parse_args()

    print(f"\n{BOLD}{'='*60}{RESET}")
    print(f"{BOLD}🔍 Epic 创建功能检测{RESET}")
    print(f"{BOLD}{'='*60}{RESET}")
    print(f"项目: {Config.JIRA_SERVER}")
    print(f"模型: {Config.MODEL_NAME}")
    print(f"实时测试: {'是 (' + args.live + ')' if args.live else '否（仅逻辑检测）'}")

    total_passed = 0
    total_checks = 0

    # 所有检测项
    detectors = [
        ("配置检测", check_config),
        ("build_issue_fields — Epic 字段构造", check_build_issue_fields),
        ("层级规则验证", check_hierarchy_rules),
        ("create_issue 工具层检测", check_create_issue_tool),
        ("项目元数据", lambda: check_metadata(args.live)),
    ]

    if args.live:
        detectors.append(("实际 API 调用", lambda: check_live_api(args.live)))

    for name, detector in detectors:
        try:
            p, c = detector()
            total_passed += p
            total_checks += c
        except Exception as e:
            import traceback
            print(f"\n  {RED}💥 检测崩溃: {name}{RESET}")
            traceback.print_exc()
            total_checks += 1

    # ── 总结 ──
    print(f"\n{BOLD}{'='*60}{RESET}")
    if total_checks == 0:
        print(f"{YELLOW}⚠️  没有执行任何检测项{RESET}")
    elif total_passed == total_checks:
        print(f"{GREEN}✅ 全部通过！{total_passed}/{total_checks}{RESET}")
    else:
        print(f"{RED}❌ 部分未通过: {total_passed}/{total_checks}{RESET}")
        print(f"   失败: {total_checks - total_passed} 项")

    print(f"{BOLD}{'='*60}{RESET}\n")
    return 0 if total_passed == total_checks else 1


if __name__ == "__main__":
    sys.exit(main())
