"""自定义字段自动探测

启动时通过 Jira REST API 列出全部字段，按名称模糊匹配找到 "Target Start" / "Target End"
对应的 customfield_xxx，并在 .env 中未显式配置时写回。这样新环境只需要 JIRA_SERVER/USER/TOKEN
就能跑起来，不用再手动查字段 ID。

设计：
- 默认开启（环境变量 AUTO_DETECT_FIELDS=0 可关闭）
- 已有值（TARGET_START_FIELD / TARGET_END_FIELD 已显式设置）→ 不覆盖
- 探测失败 → 不报错，仅打 WARNING，沿用 .env 默认值（避免启动失败）
"""
import os
import logging
from typing import Optional, Dict

from dotenv import load_dotenv

_logger = logging.getLogger("jira_bot.field_detector")

# 名称模式（中英文都覆盖，按优先级匹配）
START_PATTERNS = [
    "target start", "target start date", "start date", "plan start",
    "计划开始", "目标开始", "开始日期",
]
END_PATTERNS = [
    "target end", "target end date", "due date", "end date", "plan end",
    "计划结束", "目标结束", "结束日期", "截止日期",
]


def _normalize(s: str) -> str:
    return (s or "").strip().lower()


def _match_any(name: str, patterns: list) -> bool:
    n = _normalize(name)
    return any(_normalize(p) in n for p in patterns)


def detect_target_fields(jira_client) -> Dict[str, Optional[str]]:
    """
    调用 Jira REST API 列出全部字段，返回 {"start": "customfield_xxx" or None, "end": ...}.
    优先匹配名称含 "target" 的字段；若没有，再退化到 "start date" / "end date"。
    """
    try:
        fields = jira_client.get_all_fields()
    except Exception as e:
        _logger.warning("调用 Jira get_all_fields 失败: %s", e)
        return {"start": None, "end": None}

    if not isinstance(fields, list):
        _logger.warning("get_all_fields 返回非列表: %s", type(fields))
        return {"start": None, "end": None}

    start_id = None
    end_id = None
    # 第一轮：必须含 "target"
    for f in fields:
        if not isinstance(f, dict):
            continue
        fid = f.get("id") or ""
        name = f.get("name") or ""
        if not fid.startswith("customfield_"):
            continue
        if start_id is None and "target" in _normalize(name) and "start" in _normalize(name):
            start_id = fid
        if end_id is None and "target" in _normalize(name) and "end" in _normalize(name):
            end_id = fid
    # 第二轮：兜底，不要求 "target"
    if start_id is None:
        for f in fields:
            if not isinstance(f, dict):
                continue
            fid = f.get("id") or ""
            name = f.get("name") or ""
            if not fid.startswith("customfield_"):
                continue
            if start_id is None and _match_any(name, START_PATTERNS):
                start_id = fid
    if end_id is None:
        for f in fields:
            if not isinstance(f, dict):
                continue
            fid = f.get("id") or ""
            name = f.get("name") or ""
            if not fid.startswith("customfield_"):
                continue
            if end_id is None and _match_any(name, END_PATTERNS):
                end_id = fid

    return {"start": start_id, "end": end_id}


def _read_env_file(env_path: str) -> str:
    if not os.path.exists(env_path):
        return ""
    with open(env_path, "r", encoding="utf-8") as f:
        return f.read()


def _has_value(env_text: str, key: str) -> bool:
    """检查 .env 文本里 key 是否有非空非默认占位的值"""
    for line in env_text.splitlines():
        s = line.strip()
        if not s or s.startswith("#"):
            continue
        if "=" not in s:
            continue
        k, _, v = s.partition("=")
        if k.strip() == key:
            val = v.strip()
            if val and val.lower() not in ("none", "null", ""):
                return True
    return False


def _write_env_kv(env_path: str, key: str, value: str):
    """在 .env 末尾追加 KEY=VALUE（如果不存在）"""
    if not value:
        return
    text = _read_env_file(env_path)
    if _has_value(text, key):
        return
    sep = "" if (not text or text.endswith("\n")) else "\n"
    with open(env_path, "a", encoding="utf-8") as f:
        f.write(f"{sep}# 自动探测写入\n{key}={value}\n")


def ensure_target_field_ids(jira_client, env_path: Optional[str] = None,
                            reload_after: bool = True) -> Dict[str, Optional[str]]:
    """
    入口：检测并按需写回 .env。
    :param jira_client: 已初始化的 JiraClient 实例
    :param env_path: .env 路径，默认 <BASE_DIR>/.env
    :param reload_after: 写回后是否重新 load_dotenv
    :return: {"start": ..., "end": ..., "wrote": bool}
    """
    from config import Config  # noqa: F401  仅为确认 Config 已加载

    env_path = env_path or os.path.join(
        Config.BASE_DIR, ".env"
    )

    detected = detect_target_fields(jira_client)
    wrote = False

    # 仅当 .env 没显式配置时写回
    text = _read_env_file(env_path)
    if detected["start"] and not _has_value(text, "TARGET_START_FIELD"):
        _write_env_kv(env_path, "TARGET_START_FIELD", detected["start"])
        wrote = True
    if detected["end"] and not _has_value(text, "TARGET_END_FIELD"):
        _write_env_kv(env_path, "TARGET_END_FIELD", detected["end"])
        wrote = True

    if wrote and reload_after:
        load_dotenv(env_path, override=True)
        # 让 Config 类属性下次访问时拿到新值（类变量是模块级 import 时算的，这里手动同步）
        from config import Config as _Cfg
        if detected["start"]:
            _Cfg.TARGET_START_FIELD = detected["start"]
        if detected["end"]:
            _Cfg.TARGET_END_FIELD = detected["end"]
        _logger.info("字段自动探测已写回 .env: start=%s end=%s",
                     detected["start"], detected["end"])
    else:
        _logger.info("字段自动探测结果: start=%s end=%s（%s）",
                     detected["start"], detected["end"],
                     "已写回 .env" if wrote else "未改动")

    return {"start": detected["start"], "end": detected["end"], "wrote": wrote}