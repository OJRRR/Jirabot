"""公共工具模块 - 日志、分页查询、输入校验"""
import logging
import re
import time
from functools import wraps
from logging.handlers import RotatingFileHandler

# ── 日志配置 ─────────────────────────────────────────────
LOG_FORMAT = "%(asctime)s [%(levelname)s] %(name)s:%(lineno)d - %(message)s"

_logger_initialized = False


def setup_logging(log_file: str = None, level: int = logging.INFO):
    """初始化日志系统（应用启动时调用一次即可）"""
    global _logger_initialized
    if _logger_initialized:
        return
    root = logging.getLogger()
    root.setLevel(level)
    root.handlers.clear()

    # 控制台输出
    ch = logging.StreamHandler()
    ch.setFormatter(logging.Formatter(LOG_FORMAT))
    root.addHandler(ch)

    # 文件输出（带轮转）
    if log_file:
        fh = RotatingFileHandler(log_file, maxBytes=5 * 1024 * 1024, backupCount=3, encoding="utf-8")
        fh.setFormatter(logging.Formatter(LOG_FORMAT))
        root.addHandler(fh)

    _logger_initialized = True

_logger = logging.getLogger("jira_bot")


def get_logger(name: str = None) -> logging.Logger:
    return logging.getLogger(name or "jira_bot")


# ── 分页查询（消除 3 处重复定义）────────────────────────────
def fetch_all_issues(jira_client, jql_query: str, max_results: int = 100,
                     max_pages: int = 50) -> list:
    """分页获取所有 Issue（统一入口，消除各模块重复代码）

    :param jira_client: JiraClient / LazyJira 代理
    :param jql_query: JQL 字符串
    :param max_results: 每页大小（Jira 单页上限 100）
    :param max_pages: 最多翻多少页（默认 50 = 5000 条）；防止误写全公司 JQL 拖到天荒地老
    """
    all_issues = []
    start_at = 0
    page = 0
    while page < max_pages:
        page += 1
        _logger.debug("分页查询 page=%d/%d start=%d jql=%s", page, max_pages, start_at, jql_query)
        result = jira_client.jql(jql_query, start=start_at, limit=max_results)
        issues = result.get("issues", [])
        if not issues:
            break
        all_issues.extend(issues)
        start_at += max_results
        if start_at >= result.get("total", 0):
            break
    if page >= max_pages and start_at < result.get("total", 0):
        _logger.warning(
            "分页查询触及 max_pages=%d 上限（已返回 %d 条，可能被截断），请收敛 JQL 或调大 max_pages",
            max_pages, len(all_issues),
        )
    _logger.debug("分页查询完成: 共 %d 条", len(all_issues))
    return all_issues


# ── 输入校验 ──────────────────────────────────────────────
JIRA_KEY_PATTERN = re.compile(r'[A-Z]+-\d+', re.IGNORECASE)
SAFE_PROJECT_KEY_PATTERN = re.compile(r'^[A-Z][A-Z0-9_]*$', re.IGNORECASE)


def extract_issue_key(user_input: str) -> str | None:
    """从用户输入中提取 Jira Issue Key（如 KO-29）"""
    if not user_input:
        return None
    match = JIRA_KEY_PATTERN.search(user_input)
    return match.group(0).upper() if match else None


def validate_project_key(project_key: str) -> str:
    """校验并清洗 project_key，防止无效字符进入 JQL，返回大写的合法值"""
    if not project_key or not project_key.strip():
        raise ValueError("项目KEY不能为空")
    cleaned = project_key.strip().upper()
    if not SAFE_PROJECT_KEY_PATTERN.match(cleaned):
        raise ValueError(f"无效的项目KEY: {project_key}（仅允许字母、数字、下划线）")
    return cleaned


def sanitize_jql_value(value: str) -> str:
    """转义 JQL 字符串中的特殊字符"""
    return value.replace('"', '\\"').replace("'", "\\'")


# ── 重试机制 ──────────────────────────────────────────────
def retry_on_failure(max_retries: int = 3, backoff: float = 1.0):
    """装饰器：请求失败时自动重试（指数退避）"""
    def decorator(func):
        @wraps(func)
        def wrapper(*args, **kwargs):
            last_error = None
            for attempt in range(max_retries):
                try:
                    return func(*args, **kwargs)
                except Exception as e:
                    last_error = e
                    wait = backoff * (2 ** attempt)
                    _logger.warning(
                        "调用 %s 失败 (attempt %d/%d): %s，%0.1fs 后重试",
                        func.__name__, attempt + 1, max_retries, e, wait
                    )
                    time.sleep(wait)
            raise last_error
        return wrapper
    return decorator