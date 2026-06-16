"""为EDE项目所有Task填写Target start / Target end字段

日期表从 data/ede_plan.json 读取（与 update_target_dates_v2.py 共享同一份数据）。
用法：
    python scripts/ede_migration/update_target_dates.py            # 默认 dry-run
    python scripts/ede_migration/update_target_dates.py --apply    # 实际写入
"""
import sys, os, json, argparse
# 让 BASE_DIR 可被 import（jira_client / config 都在 BASE_DIR）
_BASE_DIR = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
sys.path.insert(0, _BASE_DIR)

from jira_client import JiraClient
from config import Config

jira = JiraClient().get_client()

TARGET_START = Config.TARGET_START_FIELD  # customfield_16519
TARGET_END   = Config.TARGET_END_FIELD    # customfield_16520

# ── 从共享 JSON 读取日期表（与 v2 共用同一份数据）──
_PLAN_PATH = os.path.join(_BASE_DIR, "data", "ede_plan.json")
with open(_PLAN_PATH, "r", encoding="utf-8") as _f:
    task_dates = json.load(_f)["tasks"]


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--apply", action="store_true", help="实际写入 Jira（默认 dry-run）")
    args = parser.parse_args()
    apply_mode = args.apply

    print(f"=== 查询 EDE 项目现有 Task ===")
    print(f"=== 目标字段: {TARGET_START} (Target Start) / {TARGET_END} (Target End) ===")
    print(f"=== 模式: {'APPLY 实际写入' if apply_mode else 'DRY-RUN（不会改 Jira）'} ===\n")

    resp = jira.jql("project = EDE AND issuetype = Task ORDER BY key ASC",
                    fields=["summary", TARGET_START, TARGET_END])
    issues = resp.get("issues", [])
    print(f"找到 {len(issues)} 个 Task\n")

    success = 0
    fail = 0
    skipped = 0

    for issue in issues:
        key = issue["key"]
        summary = issue["fields"]["summary"]

        if summary not in task_dates:
            skipped += 1
            continue

        start_date, end_date = task_dates[summary]

        # 检查当前值
        curr_start = issue["fields"].get(TARGET_START)
        curr_end   = issue["fields"].get(TARGET_END)

        # 如果已有相同值则跳过
        if curr_start == start_date and curr_end == end_date:
            print(f"  ⏭️  {key}: {summary} (Target 日期已正确)")
            skipped += 1
            continue

        print(f"  🔧 {key}: {summary}")
        print(f"      旧: start={curr_start} end={curr_end}")
        print(f"      新: start={start_date} end={end_date}")

        if not apply_mode:
            print(f"      [DRY-RUN] 跳过实际写入\n")
            continue

        try:
            jira.update_issue_field(key, {
                TARGET_START: start_date,
                TARGET_END:   end_date,
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
        print(f"   python scripts/ede_migration/update_target_dates.py --apply")


if __name__ == "__main__":
    main()