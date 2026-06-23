"""task_tools 的共享 helper - 不含 @tool 装饰的纯函数

被 task_tools / report_tools / risk_extractor 共用。
"""
import json
import logging
from config import Config
from ._lazy import LazyJira

_logger = logging.getLogger("jira_bot.task_tools")
jira = LazyJira()

# Target Start / Target End 常见显示名 → 映射到 Config 中的 customfield ID
_TARGET_START_ALIASES = frozenset({
    "targetstart", "target start", "target_start",
    "start date", "startdate", "start",
    "planned start", "planned start date",
    "开始日期", "开始时间", "开始",
})
_TARGET_END_ALIASES = frozenset({
    "targetend", "target end", "target_end",
    "end date", "enddate", "end",
    "due date", "duedate",
    "planned end", "planned completed date", "planned end date",
    "结束日期", "结束时间", "结束", "截止",
})

# 显示名 → 字段KEY 缓存（由 get_create_issue_metadata 注册）
# 例如: {"epic name": ("customfield_10011", "string"), "role name": ("customfield_10012", "option")}
_field_name_cache: dict = {}


def register_field_name_mapping(name: str, key: str, schema_type: str = "") -> None:
    """注册显示名到字段KEY的映射（供 get_create_issue_metadata 调用）"""
    _field_name_cache[name.strip().lower()] = (key, schema_type)


def _normalize_field_key(key: str) -> str:
    """把 Target Start/End 的显示名或别名映射为 customfield ID。
    同时也查找 _field_name_cache（由 get_create_issue_metadata 注册的显示名→KEY映射）。
    """
    if not key:
        return key
    if key.startswith("customfield_"):
        return key

    # 1) Target Start/End 别名匹配
    normalized = " ".join(key.strip().lower().replace("-", " ").replace("_", " ").split())
    if normalized in _TARGET_START_ALIASES:
        return Config.TARGET_START_FIELD
    if normalized in _TARGET_END_ALIASES:
        return Config.TARGET_END_FIELD

    # 2) 在元数据缓存中查找（如 "Epic Name" → "customfield_10011"）
    name_lower = key.strip().lower()
    if name_lower in _field_name_cache:
        return _field_name_cache[name_lower][0]  # (key, schema_type) → key

    return key


def _resolve_fields_via_meta(additional_fields: dict, project_key: str) -> dict:
    """通过项目元数据查找字段显示名 → customfield ID，不使用全局别名。

    解决多项目场景下全局 TARGET_START_FIELD/TARGET_END_FIELD 与特定项目不匹配的问题。
    例如 RDE 使用 "Planned Start" (customfield_10306)，而全局配置为 customfield_16519。
    同时处理 datetime 类型字段的值格式（需 ISO 8601 格式而非 YYYY-MM-DD）。
    """
    import re as _re
    if not additional_fields or not project_key:
        return process_additional_fields(additional_fields)  # 没项目KEY时回退全局别名
    processed = {}
    try:
        # 延迟导入避免循环依赖
        from tools.task_query import _get_create_meta_cached
        meta_str = _get_create_meta_cached(project_key)
        meta = json.loads(meta_str)
        if meta.get("success"):
            # 建立显示名（小写）→ (field_key, schema_type) 的映射
            name_to_key = {}
            key_to_type = {}
            for it in meta["data"]["issue_types"]:
                for f in it.get("optional_fields", []) + it.get("required_fields", []):
                    fname = f.get("name", "").lower().strip()
                    fkey = f.get("key", "")
                    ftype = f.get("type", "")
                    if fname and fkey.startswith("customfield_"):
                        name_to_key[fname] = fkey
                        key_to_type[fkey] = ftype
            # 为 Target Start/End 别名做扩展匹配
            for fname, fkey in list(name_to_key.items()):
                if fname in _TARGET_START_ALIASES:
                    for alias in _TARGET_START_ALIASES:
                        name_to_key[alias] = fkey
                if fname in _TARGET_END_ALIASES:
                    for alias in _TARGET_END_ALIASES:
                        name_to_key[alias] = fkey
            # 用显示名匹配
            for k, v in additional_fields.items():
                key_lower = k.lower().strip()
                cf_id = name_to_key.get(key_lower)
                if not cf_id:
                    # 回退到全局别名
                    normalized = " ".join(
                        key_lower.replace("-", " ").replace("_", " ").split())
                    if normalized in _TARGET_START_ALIASES:
                        cf_id = Config.TARGET_START_FIELD
                    elif normalized in _TARGET_END_ALIASES:
                        cf_id = Config.TARGET_END_FIELD
                if cf_id:
                    # 检查是否为 datetime 类型 → 需要 ISO 8601
                    ftype = key_to_type.get(cf_id, "")
                    if ftype == "datetime":
                        date_str = str(v).strip()
                        if _re.match(r"^\d{4}-\d{2}-\d{2}$", date_str):
                            processed[cf_id] = f"{date_str}T00:00:00.000+0800"
                        else:
                            processed[cf_id] = date_str
                    else:
                        processed[cf_id] = v
                else:
                    _logger.warning("无法映射字段 %s (值=%s)，项目 %s 元数据中未找到",
                                    k, v, project_key)
            return processed
    except (json.JSONDecodeError, KeyError, TypeError, AttributeError) as e:
        _logger.warning("通过元数据解析字段失败: %s，回退全局别名", e)
    return process_additional_fields(additional_fields)


def _is_date_custom_field(key: str) -> bool:
    return key in (Config.TARGET_START_FIELD, Config.TARGET_END_FIELD)


def process_additional_fields(additional_fields: dict) -> dict:
    """
    把 additional_fields 转成 Jira API 接受的格式：
    - Target Start/End 显示名自动映射为 customfield ID，日期值用 YYYY-MM-DD 字符串
    - 其他 customfield_* 的字符串值包成 {"value": "..."}（Jira 选项型字段要求）
    - 显示名（如 "Epic Name"）通过 _normalize_field_key → _field_name_cache 映射为 KEY
    - 无法映射的字段名 → 跳过并 warning

    之前在 task_tools.py 里 _build_issue_fields / create_issue / update_issue 三处重复
    出现同一段循环，抽到此处。
    """
    if not additional_fields:
        return {}
    processed = {}
    for k, v in additional_fields.items():
        field_key = _normalize_field_key(k)

        # 如果 _normalize_field_key 返回了原 key（非 customfield_ 且不在缓存中），
        # 尝试在 _field_name_cache 中查找；找不到则原样透传（兼容 Jira 内置字段如 priority、labels）
        if not field_key.startswith("customfield_"):
            name_lower = k.strip().lower()
            if name_lower in _field_name_cache:
                field_key = _field_name_cache[name_lower][0]
            else:
                # 原样透传（用于 Jira 内置字段和 _resolve_fields_via_meta 跳过的字段）
                processed[k] = v
                continue

        # 查询该字段的 schema 类型，决定值格式
        schema_type = ""
        for name_lower, (cached_key, st) in _field_name_cache.items():
            if cached_key == field_key:
                schema_type = st
                break

        if _is_date_custom_field(field_key) and isinstance(v, str):
            # 已知的日期自定义字段 → 直接传日期字符串
            processed[field_key] = v
        elif field_key.startswith("customfield") and isinstance(v, str):
            # string/number/any 类型字段 → 直接传值（Epic Name 属于此类）
            if schema_type in ("string", "number", "any"):
                processed[field_key] = v
            else:
                # 尝试探测是否是日期字段：值匹配 YYYY-MM-DD 或带 T 的 ISO 格式
                import re as _re
                if _re.match(r'^\d{4}-\d{2}-\d{2}', v):
                    processed[field_key] = v
                else:
                    processed[field_key] = {"value": v}
        else:
            processed[field_key] = v
    return processed


def build_issue_fields(project_key: str, summary: str, issue_type: str,
                       description: str = "", parent_key: str = None,
                       epic_link_key: str = None,
                       additional_fields: dict = None) -> tuple:
    """
    构造 Jira Issue fields dict。
    :return: (fields_dict, error_message) - error_message 不为空时表示校验失败
    """
    if not project_key or not summary or not issue_type:
        return None, "缺少必填字段 (project_key/summary/issue_type)"

    if epic_link_key and issue_type.lower() == "sub-task":
        return None, "Epic 不能直接关联 Sub-task，层级关系为 Epic → Task → Sub-task"

    fields = {
        "project": {"key": project_key},
        "summary": summary,
        "issuetype": {"name": issue_type},
    }

    if description:
        # 使用纯文本描述而非 ADF 格式，避免 Epic 创建时 "Operation value must be a string" 错误
        fields["description"] = description

    if parent_key:
        fields["parent"] = {"key": parent_key}

    # Epic 类型需要 Epic Name 字段（Jira 的 Epic 类型必填）
    if issue_type.lower() == "epic":
        epic_name_field = Config.EPIC_NAME_FIELD_ID
        if not epic_name_field:
            # 兜底：从 _field_name_cache 中查找 "Epic Name" 对应的 customfield
            # （LazyFieldDetector 可能尚未执行完，_field_name_cache 由 get_create_issue_metadata 注册）
            for name_lower, (cached_key, _) in _field_name_cache.items():
                if "epic name" in name_lower:
                    epic_name_field = cached_key
                    _logger.debug("Epic Name 字段兜底匹配: %s → %s", name_lower, epic_name_field)
                    break
        if epic_name_field:
            fields[epic_name_field] = summary

    if epic_link_key and Config.EPIC_LINK_FIELD_ID:
        fields[Config.EPIC_LINK_FIELD_ID] = epic_link_key

    fields.update(process_additional_fields(additional_fields))

    return fields, None


def build_task_dict(issue, include_assignee: bool = True) -> dict:
    """构建统一的 task 字典"""
    fields = issue.get("fields", {}) or {}
    status = fields.get("status", {}) or {}
    priority = fields.get("priority", {}) or {}
    assignee = fields.get("assignee", {}) or {}

    task = {
        "key": issue.get("key"),
        "summary": fields.get("summary"),
        "status": status.get("name"),
        "priority": priority.get("name"),
        "target_start": fields.get(Config.TARGET_START_FIELD),
        "target_end": fields.get(Config.TARGET_END_FIELD)
    }
    if include_assignee:
        task["assignee"] = assignee.get("displayName", "未分配")
    return task
