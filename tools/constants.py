"""Jira 状态/优先级等字面量集中维护

原先散落在 report_tools.py / risk_extractor.py / dependency_tools.py / risk_render.py，
Jira 配置中英文都支持，统一在此维护。新增状态名只需改这里。
"""
from typing import FrozenSet

# ── 状态 ──────────────────────────────────────────────────
DONE_STATUSES: FrozenSet[str] = frozenset(["Done", "Closed", "已关闭", "已完成"])
IN_PROGRESS_STATUSES: FrozenSet[str] = frozenset(["In Progress", "进行中"])
# 报告 / 工具里用作 "未结束" 判定的全集
OPEN_STATUSES: FrozenSet[str] = (
    DONE_STATUSES  # 仅做类型提示；下面反着用更直观
)

# ── 优先级 ────────────────────────────────────────────────
HIGH_PRIORITIES: FrozenSet[str] = frozenset(["Highest", "High", "紧急", "高"])
MEDIUM_PRIORITIES: FrozenSet[str] = frozenset(["Medium", "中"])

# ── 链接类型关键字（小写匹配）─────────────────────────────
BLOCKS_KEYWORDS: FrozenSet[str] = frozenset(["blocks"])


def is_done(status: str) -> bool:
    return (status or "") in DONE_STATUSES


def is_in_progress(status: str) -> bool:
    return (status or "") in IN_PROGRESS_STATUSES


def is_high_priority(priority: str) -> bool:
    return (priority or "") in HIGH_PRIORITIES


def is_medium_priority(priority: str) -> bool:
    return (priority or "") in MEDIUM_PRIORITIES