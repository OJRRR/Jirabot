"""Jira API 客户端封装（重构版 - 重试 + 速率限制）"""
import time
import logging
from atlassian import Jira
from config import Config
from utils import retry_on_failure

_logger = logging.getLogger("jira_bot.client")


class JiraClient:
    """Jira 客户端单例"""

    _instance = None
    _last_call_time = 0
    _min_interval = 0.5  # 最小调用间隔（秒）

    def __new__(cls):
        if cls._instance is None:
            instance = super().__new__(cls)
            try:
                instance._init_client()
                cls._instance = instance
            except Exception:
                # 初始化失败时重置 _instance，允许下次重试
                raise
        return cls._instance

    def _init_client(self):
        """初始化 Jira 连接"""
        self.client = Jira(
            url=Config.JIRA_SERVER,
            username=Config.JIRA_USER,
            token=Config.JIRA_TOKEN,
            cloud=False
        )
        # 测试连接
        self.client.jql("assignee = currentUser()")
        _logger.info("Jira 连接成功 (%s)", Config.JIRA_SERVER)

    def _rate_limit(self):
        """速率限制：确保 API 调用间隔不小于 _min_interval"""
        elapsed = time.time() - self._last_call_time
        if elapsed < self._min_interval:
            time.sleep(self._min_interval - elapsed)
        self._last_call_time = time.time()

    def get_client(self):
        """获取原始 Jira 客户端实例"""
        return self.client

    def jql(self, jql: str, start=0, start_at=None, limit=100):
        """jql 查询别名，兼容 jira_client.jql(q, start=0, limit=100) 调用方式"""
        if start_at is not None:
            start = start_at
        return self.query(jql, start=start, limit=limit)

    @retry_on_failure(max_retries=3, backoff=1.0)
    def query(self, jql: str, start=0, start_at=None, limit=100):
        """执行 JQL 查询（带重试和速率限制）"""
        if start_at is not None:
            start = start_at
        self._rate_limit()
        _logger.debug("JQL查询: %s (start=%d limit=%d)", jql[:100], start, limit)
        return self.client.jql(jql, start=start, limit=limit)

    @retry_on_failure(max_retries=3, backoff=1.0)
    def get_issue(self, key: str):
        """获取单个 Issue"""
        self._rate_limit()
        _logger.debug("获取Issue: %s", key)
        return self.client.issue(key)

    @retry_on_failure(max_retries=2, backoff=1.0)
    def get_all_projects(self):
        """获取所有项目"""
        self._rate_limit()
        return self.client.get_all_projects()

    @retry_on_failure(max_retries=2, backoff=1.0)
    def get_all_fields(self):
        """获取全部自定义字段（field_detector 需要）"""
        self._rate_limit()
        return self.client.get_all_fields()

    @retry_on_failure(max_retries=2, backoff=1.0)
    def get_issue_createmeta(self, project_key: str):
        """获取项目创建元数据（使用新版 createmeta API）"""
        self._rate_limit()
        # 第一步：获取项目的问题类型列表
        issuetypes_data = self.client.issue_createmeta_issuetypes(project_key)
        issuetypes = issuetypes_data.get("values", [])

        # 第二步：对每种问题类型获取字段元数据
        issue_type_list = []
        for it in issuetypes:
            it_id = it.get("id")
            it_name = it.get("name")
            it_subtask = it.get("subtask", False)
            # 获取该问题类型的字段定义
            fields_data = self.client.issue_createmeta_fieldtypes(project_key, it_id)
            field_values = fields_data.get("values", [])
            fields_dict = {}
            for f in field_values:
                field_key = f.get("fieldId")
                if not field_key:
                    continue
                allowed = f.get("allowedValues", None)
                # allowedValues 可能是列表或 None
                allowed_values = None
                if allowed:
                    values = []
                    for v in allowed:
                        if isinstance(v, str):
                            values.append(v)
                        elif isinstance(v, dict):
                            values.append(v.get("value") or v.get("name") or v.get("id") or str(v))
                    allowed_values = values
                fields_dict[field_key] = {
                    "name": f.get("name"),
                    "required": f.get("isRequired", False),
                    "schema": {"type": f.get("schema", {}).get("type", "string")},
                }
                if allowed_values:
                    fields_dict[field_key]["allowedValues"] = allowed_values
            issue_type_list.append({
                "name": it_name,
                "subtask": it_subtask,
                "fields": fields_dict,
            })

        # 包装为兼容旧版格式的返回结构
        return {
            "projects": [
                {
                    "key": project_key,
                    "issuetypes": issue_type_list,
                }
            ]
        }

    @retry_on_failure(max_retries=2, backoff=1.0)
    def create_issue(self, fields: dict):
        """创建 Issue"""
        self._rate_limit()
        _logger.info("创建Issue: %s / %s", fields.get("project", {}).get("key"), fields.get("summary"))
        return self.client.create_issue(fields=fields)

    @retry_on_failure(max_retries=2, backoff=1.0)
    def create_issue_link(self, data: dict):
        """创建 Issue 链接"""
        self._rate_limit()
        return self.client.create_issue_link(data)

    # ── 新增：更新 Issue 字段 ────────────────────

    @retry_on_failure(max_retries=2, backoff=1.0)
    def update_issue_field(self, key: str, fields: dict, notify_users: bool = True):
        """更新 Issue 字段（支持 summary、description、priority、自定义字段等）"""
        self._rate_limit()
        _logger.info("更新Issue: %s", key)
        return self.client.update_issue_field(key, fields=fields, notify_users=notify_users)

    @retry_on_failure(max_retries=2, backoff=1.0)
    def get_issue_transitions(self, issue_key: str) -> list:
        """获取 Issue 可用的状态转换"""
        self._rate_limit()
        _logger.debug("获取转换: %s", issue_key)
        return self.client.get_issue_transitions(issue_key)

    @retry_on_failure(max_retries=2, backoff=1.0)
    def transition_issue(self, issue_key: str, status_name: str):
        """将 Issue 转换到指定状态"""
        self._rate_limit()
        _logger.info("转换状态: %s -> %s", issue_key, status_name)
        return self.client.set_issue_status(issue_key, status_name)

    # ── 新增：评论与工时 ────────────────────

    @retry_on_failure(max_retries=2, backoff=1.0)
    def add_comment(self, issue_key: str, comment: str):
        """给 Issue 添加评论"""
        self._rate_limit()
        _logger.info("添加评论: %s", issue_key)
        return self.client.issue_add_comment(issue_key, comment)

    @retry_on_failure(max_retries=2, backoff=1.0)
    def add_worklog(self, issue_key: str, time_spent: str, comment: str = None, started: str = None):
        """
        记录工时。
        :param time_spent: 可读格式如 "2h 30m"、"1d"
        :param started: 开始时间，如 "2026-06-08T10:00:00.000+0800"
        """
        self._rate_limit()
        _logger.info("记录工时: %s %s", issue_key, time_spent)
        data = {"timeSpent": time_spent}
        if comment:
            data["comment"] = comment
        if started:
            data["started"] = started
        return self.client.issue_add_json_worklog(key=issue_key, worklog=data)

    # ── 新增：分配任务 ────────────────────

    @retry_on_failure(max_retries=2, backoff=1.0)
    def assign_issue(self, issue_key: str, account_id: str):
        """将 Issue 分配给指定用户（Server版用username）"""
        self._rate_limit()
        _logger.info("分配任务: %s -> %s", issue_key, account_id)
        return self.client.assign_issue(issue_key, account_id)

    @retry_on_failure(max_retries=2, backoff=1.0)
    def get_assignable_users(self, issue_key: str, username: str = None) -> list:
        """获取可分配给 Issue 的用户列表"""
        self._rate_limit()
        _logger.debug("获取可分配用户: %s", issue_key)
        result = self.client.get_assignable_users_for_issue(issue_key, username=username)
        if isinstance(result, list):
            return result
        return []

    # ── 新增：删除 Issue ────────────────────

    @retry_on_failure(max_retries=2, backoff=1.0)
    def delete_issue(self, issue_key: str, delete_subtasks: bool = True):
        """删除 Issue（支持同时删除子任务）"""
        self._rate_limit()
        _logger.warning("删除Issue: %s (delete_subtasks=%s)", issue_key, delete_subtasks)
        return self.client.delete_issue(issue_key, delete_subtasks=delete_subtasks)

    # ── 批量创建 Issue（bulk API）───────────────────

    BULK_CHUNK_SIZE = 50  # Jira /issue/bulk 单次上限

    def bulk_create_issues(self, fields_list: list) -> dict:
        """
        通过 Jira bulk API 批量创建 Issue。
        :param fields_list: list[dict]，每个 dict 是一个 Issue 的 fields（不含 issuetype.name 之外的结构差异）
        :return: dict 形如 {"created": [...], "errors": [...], "chunks": int}

        行为说明：
        - 按 BULK_CHUNK_SIZE 自动分片
        - 每片独立 try/except，单片失败不阻塞后续片
        - 仍走 _rate_limit 限流
        """
        if not fields_list:
            return {"created": [], "errors": [], "chunks": 0}

        created_all = []
        errors_all = []
        chunks = 0
        size = self.BULK_CHUNK_SIZE

        for start in range(0, len(fields_list), size):
            chunk = fields_list[start:start + size]
            chunks += 1
            self._rate_limit()
            _logger.info("bulk 创建第 %d 片: %d 条", chunks, len(chunk))
            try:
                # Jira REST: POST /rest/api/2/issue/bulk
                # body: {"issueUpdates": [{"fields": {...}}, ...]}
                # 响应: {"issues": [...], "errors": [...]}
                resp = self.client.post("issue/bulk", data={"issueUpdates": [{"fields": f} for f in chunk]})
                if isinstance(resp, str):
                    import json as _json
                    resp = _json.loads(resp)
                # atlassian-python-api 内部可能直接返回 list，也做一次兜底
                issues = []
                errs = []
                if isinstance(resp, list):
                    issues = resp
                elif isinstance(resp, dict):
                    # atlassian-python-api 4.x 的 /issue/bulk 响应可能带 "issues" 或 "created"
                    issues = resp.get("issues", None)
                    if issues is None:
                        issues = resp.get("created", []) or []
                    else:
                        issues = issues or []
                    errs = resp.get("errors", []) or []
                for it in issues:
                    if it:
                        created_all.append(it)
                if errs:
                    errors_all.extend(errs)
            except Exception as e:
                _logger.error("bulk 第 %d 片失败: %s", chunks, e)
                # 把这一片每条都标记为失败，保留原始字段供上层排查
                for i, f in enumerate(chunk):
                    errors_all.append({
                        "index": start + i,
                        "status": -1,
                        "error": str(e),
                        "summary": (f or {}).get("summary", ""),
                    })

        return {"created": created_all, "errors": errors_all, "chunks": chunks}