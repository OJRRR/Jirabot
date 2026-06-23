"""配置管理模块（按职责拆分，保持向后兼容）

Config 作为统一入口，将各类配置委托给子配置类：
  - JiraConfig:   Jira 连接凭证、字段ID
  - PathConfig:   目录路径（报告/模板/日志/上传）
  - ModelConfig:  LLM 模型配置
  - QueryConfig:  查询分页限制、并发数
  - RiskConfig:   风险评分阈值
  - ProjectConfig: 目标项目列表、JQL 构建
  - ReportConfig: 报告清理策略

所有子配置通过 Config 类属性访问，保持旧代码兼容。
"""
import os
import re
from datetime import datetime, timedelta
from dotenv import load_dotenv

load_dotenv()

_BASE_DIR = os.path.dirname(os.path.abspath(__file__))


# ── 子配置类 ──────────────────────────────────────────────────

class JiraConfig:
    """Jira 连接凭证与字段配置"""
    SERVER   = os.getenv("JIRA_SERVER")
    USER     = os.getenv("JIRA_USER")
    TOKEN    = os.getenv("JIRA_TOKEN")
    TARGET_START_FIELD = os.getenv("TARGET_START_FIELD", "customfield_16519")
    TARGET_END_FIELD   = os.getenv("TARGET_END_FIELD",   "customfield_16520")
    EPIC_NAME_FIELD_ID = os.getenv("EPIC_NAME_FIELD_ID")
    EPIC_LINK_FIELD_ID = os.getenv("EPIC_LINK_FIELD_ID")


class PathConfig:
    """目录路径配置"""
    BASE_DIR     = _BASE_DIR
    REPORTS_DIR  = os.getenv("REPORTS_DIR", os.path.join(_BASE_DIR, "reports"))
    TEMPLATE_DIR = os.path.join(_BASE_DIR, "templates")
    LOG_DIR      = os.path.join(_BASE_DIR, "logs")
    LOG_FILE     = os.path.join(LOG_DIR, "jira_bot.log")
    LOG_LEVEL    = os.getenv("LOG_LEVEL", "INFO").upper()
    UPLOAD_DIR   = os.path.join(_BASE_DIR, "uploads")

    # 启动时自动创建必要目录
    os.makedirs(REPORTS_DIR,  exist_ok=True)
    os.makedirs(TEMPLATE_DIR, exist_ok=True)
    os.makedirs(LOG_DIR,      exist_ok=True)
    os.makedirs(UPLOAD_DIR,   exist_ok=True)


class ModelConfig:
    """LLM 模型配置"""
    API_BASE    = os.getenv("MODEL_API_BASE")
    API_KEY     = os.getenv("MODEL_API_KEY")
    NAME        = os.getenv("MODEL_NAME")
    TEMPERATURE = float(os.getenv("AI_TEMPERATURE", "0.5"))


class QueryConfig:
    """查询分页限制与并发配置"""
    MAX_TASKS_PER_TOOL    = int(os.getenv("MAX_TASKS_PER_TOOL",    "50"))
    JQL_PAGE_SIZE         = int(os.getenv("JQL_PAGE_SIZE",        "100"))
    ISSUE_FETCH_LIMIT     = int(os.getenv("ISSUE_FETCH_LIMIT",    "5000"))
    REPORT_PARALLEL_WORKERS = int(os.getenv("REPORT_PARALLEL_WORKERS", "5"))


class RiskConfig:
    """风险评分阈值（可通过环境变量调参）"""
    PROGRESS_LOW  = int(os.getenv("RISK_PROGRESS_LOW",  "30"))
    PROGRESS_MED  = int(os.getenv("RISK_PROGRESS_MED",  "50"))
    PROGRESS_HIGH = int(os.getenv("RISK_PROGRESS_HIGH", "70"))

    OVERDUE_HIGH  = int(os.getenv("RISK_OVERDUE_HIGH", "5"))
    OVERDUE_LOW   = int(os.getenv("RISK_OVERDUE_LOW",  "1"))

    HIGH_PRIORITY_HIGH = int(os.getenv("RISK_HIGH_PRIORITY_HIGH", "10"))
    HIGH_PRIORITY_LOW  = int(os.getenv("RISK_HIGH_PRIORITY_LOW",  "5"))

    BLOCKED_HIGH = int(os.getenv("RISK_BLOCKED_HIGH", "3"))
    BLOCKED_LOW  = int(os.getenv("RISK_BLOCKED_LOW",  "1"))

    SCORE_HIGH = int(os.getenv("RISK_SCORE_HIGH", "60"))
    SCORE_MED  = int(os.getenv("RISK_SCORE_MED",  "30"))


class ReportConfig:
    """报告清理策略"""
    MAX_AGE_DAYS = int(os.getenv("REPORT_MAX_AGE_DAYS", "30"))


class ProjectConfig:
    """目标项目配置"""
    _raw = os.getenv("PROJECTS", "").strip()
    TARGET = None
    if _raw and _raw.upper() != "ALL":
        TARGET = [
            p.strip().upper()
            for p in re.split(r"[,，]\s*", _raw)
            if p.strip()
        ]

    @classmethod
    def build_jql(cls, base_jql: str) -> str:
        """根据目标项目过滤 JQL"""
        if cls.TARGET:
            project_filter = "project IN (" + ",".join(f'"{k}"' for k in cls.TARGET) + ")"
            return f"{base_jql} AND {project_filter}"
        return base_jql


# ── 统一入口（动态委托，不再静态复制）───────────────────────

class _ConfigMeta(type):
    """元类：让 Config.TARGET_START_FIELD 等类属性访问动态委托给子配置类。
    解决了旧代码在模块加载时复制值、后续 JiraConfig 更新无法反映的问题。
    """
    _delegates = {
        "TARGET_START_FIELD":  lambda: JiraConfig.TARGET_START_FIELD,
        "TARGET_END_FIELD":    lambda: JiraConfig.TARGET_END_FIELD,
        "EPIC_NAME_FIELD_ID":  lambda: JiraConfig.EPIC_NAME_FIELD_ID,
        "EPIC_LINK_FIELD_ID":  lambda: JiraConfig.EPIC_LINK_FIELD_ID,
    }

    def __getattr__(cls, name):
        if name in cls._delegates:
            return cls._delegates[name]()
        raise AttributeError(f"type object 'Config' has no attribute {name!r}")


class Config(metaclass=_ConfigMeta):
    """全局配置入口 — 委托给子配置类，保持旧属性名兼容"""

    # ── Jira ──
    JIRA_SERVER         = JiraConfig.SERVER
    JIRA_USER           = JiraConfig.USER
    JIRA_TOKEN          = JiraConfig.TOKEN

    # ── 目录 ──
    BASE_DIR     = PathConfig.BASE_DIR
    REPORTS_DIR  = PathConfig.REPORTS_DIR
    TEMPLATE_DIR = PathConfig.TEMPLATE_DIR
    LOG_DIR      = PathConfig.LOG_DIR
    LOG_FILE     = PathConfig.LOG_FILE
    LOG_LEVEL    = PathConfig.LOG_LEVEL
    UPLOAD_DIR   = PathConfig.UPLOAD_DIR

    # ── 模型 ──
    MODEL_API_BASE = ModelConfig.API_BASE
    MODEL_API_KEY  = ModelConfig.API_KEY
    MODEL_NAME     = ModelConfig.NAME
    AI_TEMPERATURE = ModelConfig.TEMPERATURE

    # ── 查询 ──
    MAX_TASKS_PER_TOOL      = QueryConfig.MAX_TASKS_PER_TOOL
    JQL_PAGE_SIZE           = QueryConfig.JQL_PAGE_SIZE
    ISSUE_FETCH_LIMIT       = QueryConfig.ISSUE_FETCH_LIMIT
    REPORT_PARALLEL_WORKERS = QueryConfig.REPORT_PARALLEL_WORKERS

    # ── 风险评分 ──
    RISK_PROGRESS_LOW       = RiskConfig.PROGRESS_LOW
    RISK_PROGRESS_MED       = RiskConfig.PROGRESS_MED
    RISK_PROGRESS_HIGH      = RiskConfig.PROGRESS_HIGH
    RISK_OVERDUE_HIGH       = RiskConfig.OVERDUE_HIGH
    RISK_OVERDUE_LOW        = RiskConfig.OVERDUE_LOW
    RISK_HIGH_PRIORITY_HIGH = RiskConfig.HIGH_PRIORITY_HIGH
    RISK_HIGH_PRIORITY_LOW  = RiskConfig.HIGH_PRIORITY_LOW
    RISK_BLOCKED_HIGH       = RiskConfig.BLOCKED_HIGH
    RISK_BLOCKED_LOW        = RiskConfig.BLOCKED_LOW
    RISK_SCORE_HIGH         = RiskConfig.SCORE_HIGH
    RISK_SCORE_MED          = RiskConfig.SCORE_MED

    # ── 报告 ──
    REPORT_MAX_AGE_DAYS = ReportConfig.MAX_AGE_DAYS

    # ── 项目 ──
    TARGET_PROJECTS = ProjectConfig.TARGET

    # ── 类方法（保持兼容）──────────────────────────

    @classmethod
    def get_build_jql(cls, base_jql: str) -> str:
        # 使用 Config.TARGET_PROJECTS 而非 ProjectConfig.TARGET，
        # 这样测试中 monkeypatch 可以覆盖
        targets = cls.TARGET_PROJECTS
        if targets:
            project_filter = "project IN (" + ",".join(f'"{k}"' for k in targets) + ")"
            # 将 project filter 插入到 ORDER BY 之前（ORDER BY 必须最后）
            if " ORDER BY " in base_jql.upper():
                parts = base_jql.split(" ORDER BY ", 1)
                return f"{parts[0]} AND {project_filter} ORDER BY {parts[1]}"
            return f"{base_jql} AND {project_filter}"
        return base_jql

    @classmethod
    def cleanup_old_reports(cls) -> int:
        """清理超过 REPORT_MAX_AGE_DAYS 天的旧报告文件，返回删除数量"""
        import glob
        cutoff = datetime.now() - timedelta(days=cls.REPORT_MAX_AGE_DAYS)
        deleted = 0
        pattern = os.path.join(cls.REPORTS_DIR, "*.html")
        for filepath in glob.glob(pattern):
            mtime = datetime.fromtimestamp(os.path.getmtime(filepath))
            if mtime < cutoff:
                os.remove(filepath)
                deleted += 1
        return deleted

    @classmethod
    def print_info(cls):
        """打印配置信息"""
        print(f"🧠 模型: {cls.MODEL_NAME}")
        print(f"📁 目标项目: {cls.TARGET_PROJECTS if cls.TARGET_PROJECTS else '所有项目'}")
        print(f"📂 报告目录: {cls.REPORTS_DIR}")
        print(f"📂 模板目录: {cls.TEMPLATE_DIR}")
        print(f"📂 日志文件: {cls.LOG_FILE}")
        print(f"📅 自定义字段: 开始={cls.TARGET_START_FIELD}, 结束={cls.TARGET_END_FIELD}")
        if cls.EPIC_NAME_FIELD_ID:
            print(f"🏷  Epic Name字段: {cls.EPIC_NAME_FIELD_ID}")
        if cls.EPIC_LINK_FIELD_ID:
            print(f"🔗 Epic Link字段: {cls.EPIC_LINK_FIELD_ID}")
        print(f"📊 查询限制: 单次最多 {cls.MAX_TASKS_PER_TOOL} 条")
        print(f"🗑  报告保留: {cls.REPORT_MAX_AGE_DAYS} 天")


# ── 模块加载后自动确保 Epic 字段已探测 ──────────────────────────
# 在 config.py 被 import 完成后，如果 EPIC_NAME_FIELD_ID / EPIC_LINK_FIELD_ID
# 未在环境变量中配置，则通过 LazyFieldDetector 按需探测（单例 + 缓存）。
# 这样无论从 main.py、webapp.py 还是直接 import 工具模块进入，都能自动探测。

def _ensure_epic_fields():
    """模块加载后自动探测 Epic 字段（仅当未配置时触发，探测结果写入 .env）。"""
    try:
        # 延迟导入避免循环依赖
        from field_detector import LazyFieldDetector
        detector = LazyFieldDetector()

        for attr_name in ("EPIC_NAME_FIELD_ID", "EPIC_LINK_FIELD_ID"):
            current = getattr(JiraConfig, attr_name, None)
            if current:
                continue  # 已配置，跳过
            val = detector.get(attr_name)
            if val:
                # 更新 JiraConfig 类属性（Config 通过 @property 自动反映变更）
                setattr(JiraConfig, attr_name, val)
                # 写入 os.environ 供其他模块直接 os.getenv() 读取
                os.environ[attr_name] = val
    except Exception:
        pass  # 探测失败不阻塞启动


_ensure_epic_fields()
