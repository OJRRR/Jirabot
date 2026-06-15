"""EDE 项目批量写入 Planned Start/End（customfield_10306/10902）

日期表与 update_target_dates.py 完全一致（共用 data/ede_plan.json），
但目标字段从 customfield_12914/12915（EDE 不可写）改为 10306/10902（EDE 实际可写）。

用法：
    python scripts/ede_migration/update_target_dates_v2.py            # 默认 dry_run
    python scripts/ede_migration/update_target_dates_v2.py --apply    # 实际写入
"""
import sys, os, json, argparse
_BASE_DIR = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
sys.path.insert(0, _BASE_DIR)

from jira_client import JiraClient

# ── EDE 实际可写的字段（来自 createmeta 探测）──
PLANNED_START = "customfield_10306"
PLANNED_END = "customfield_10902"

# ── 从共享 JSON 读取日期表（与 update_target_dates.py 共用同一份数据）──
_PLAN_PATH = os.path.join(_BASE_DIR, "data", "ede_plan.json")
with open(_PLAN_PATH, "r", encoding="utf-8") as _f:
    task_dates = json.load(_f)["tasks"]


def to_jira_dt(date_str: str) -> str:
    """纯日期 YYYY-MM-DD → Jira datetime 格式（带 +0800 时区）"""
    return f"{date_str}T00:00:00.000+0800"


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--apply", action="store_true", help="实际写入 Jira（默认 dry-run）")
    args = parser.parse_args()
    apply_mode = args.apply

    jira = JiraClient().get_client()

    print(f"=== 查询 EDE 项目所有 Task ===")
    print(f"=== 目标字段: {PLANNED_START} (Planned Start) / {PLANNED_END} (Planned End) ===")
    print(f"=== 模式: {'APPLY 实际写入' if apply_mode else 'DRY-RUN（不会改 Jira）'} ===\n")

    resp = jira.jql("project = EDE AND issuetype = Task ORDER BY key ASC",
                    fields=["summary", PLANNED_START, PLANNED_END])
    issues = resp.get("issues", [])
    print(f"找到 {len(issues)} 个 Task\n")

    success = 0
    fail = 0
    skipped = 0

    for issue in issues:
        key = issue["key"]
        f = issue.get("fields", {})
        summary = f.get("summary", "")

        if summary not in task_dates:
            skipped += 1
            continue

        start_date, end_date = task_dates[summary]
        start_iso = to_jira_dt(start_date)
        end_iso = to_jira_dt(end_date)

        curr_start = f.get(PLANNED_START)
        curr_end = f.get(PLANNED_END)

        # 已有值相同则跳过（start 可能为空字符串，规范化比较）
        def norm(v):
            if not v: return None
            return v[:10] if isinstance(v, str) else v
        if norm(curr_start) == start_date and norm(curr_end) == end_date:
            print(f"  ⏭️  {key}: {summary} (日期已正确)")
            skipped += 1
            continue

        print(f"  🔧 {key}: {summary}")
        print(f"      旧: start={curr_start} end={curr_end}")
        print(f"      新: start={start_iso} end={end_iso}")

        if not apply_mode:
            print(f"      [DRY-RUN] 跳过实际写入\n")
            continue

        try:
            jira.update_issue_field(key, {
                PLANNED_START: start_iso,
                PLANNED_END: end_iso,
            })
            print(f"      ✅ 写入成功\n")
            success += 1
        except Exception as e:
            print(f"      ❌ 失败: {e}\n")
            fail += 1

    print(f"{'='*60}")
    print(f"完成！成功: {success}, 失败: {fail}, 跳过: {skipped}")
    if not apply_mode:
        print(f"→ 这是 dry-run。加 --apply 参数实际写入，例如：")
        print(f"   python scripts/ede_migration/update_target_dates_v2.py --apply")


if __name__ == "__main__":
    main()