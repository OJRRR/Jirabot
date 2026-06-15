"""配置管理模块（重构版）"""
import os
import re
from datetime import datetime, timedelta
from dotenv import load_dotenv

load_dotenv()


class Config:
    """全局配置类"""

    # ── Jira 配置 ──────────────────────────────
    JIRA_SERVER = os.getenv("JIRA_SERVER")
    JIRA_USER = os.getenv("JIRA_USER")
    JIRA_TOKEN = os.getenv("JIRA_TOKEN")

    # ── 目录配置（必须放在最前面）─────────────
    BASE_DIR = os.path.dirname(os.path.abspath(__file__))
    REPORTS_DIR = os.getenv("REPORTS_DIR", os.path.join(BASE_DIR, "reports"))
    TEMPLATE_DIR = os.path.join(BASE_DIR, "templates")
    LOG_DIR = os.path.join(BASE_DIR, "logs")
    LOG_FILE = os.path.join(LOG_DIR, "jira_bot.log")

    os.makedirs(REPORTS_DIR, exist_ok=True)
    os.makedirs(TEMPLATE_DIR, exist_ok=True)
    os.makedirs(LOG_DIR, exist_ok=True)

    # ── 模型配置 ──────────────────────────────
    MODEL_API_BASE = os.getenv("MODEL_API_BASE")
    MODEL_API_KEY = os.getenv("MODEL_API_KEY")
    MODEL_NAME = os.getenv("MODEL_NAME")
    AI_TEMPERATURE = float(os.getenv("AI_TEMPERATURE", "0.5"))

    # ── 上传目录 ──────────────────────────────
    UPLOAD_DIR = os.path.join(BASE_DIR, "uploads")
    os.makedirs(UPLOAD_DIR, exist_ok=True)

    # ── 项目配置 ──────────────────────────────
    PROJECTS_CONFIG = os.getenv("PROJECTS", "").strip()
    TARGET_PROJECTS = None
    if PROJECTS_CONFIG and PROJECTS_CONFIG.upper() != "ALL":
        # 同时支持半角 "," 和全角 "，"（避免 .env 误用全角逗号导致整个项目被吞）
        TARGET_PROJECTS = [
            p.strip().upper()
            for p in re.split(r"[,，]\s*", PROJECTS_CONFIG)
            if p.strip()
        ]

    # ── 自定义字段ID ──────────────────────────
    TARGET_START_FIELD = os.getenv("TARGET_START_FIELD", "customfield_12914")
    TARGET_END_FIELD = os.getenv("TARGET_END_FIELD", "customfield_12915")
    EPIC_LINK_FIELD_ID = os.getenv("EPIC_LINK_FIELD_ID")

    # ── 查询限制 ──────────────────────────────
    MAX_TASKS_PER_TOOL = int(os.getenv("MAX_TASKS_PER_TOOL", "50"))
    JQL_PAGE_SIZE = int(os.getenv("JQL_PAGE_SIZE", "100"))

    # ── 风险评分配置（可调）──────────────────
    RISK_PROGRESS_LOW = int(os.getenv("RISK_PROGRESS_LOW", "30"))     # 低于此值判定严重滞后
    RISK_PROGRESS_MED = int(os.getenv("RISK_PROGRESS_MED", "50"))     # 低于此值判定滞后
    RISK_PROGRESS_HIGH = int(os.getenv("RISK_PROGRESS_HIGH", "70"))   # 低于此值判定偏慢

    RISK_OVERDUE_HIGH = int(os.getenv("RISK_OVERDUE_HIGH", "5"))      # 超期任务≥此值→较多
    RISK_OVERDUE_LOW = int(os.getenv("RISK_OVERDUE_LOW", "1"))        # 超期任务≥此值→存在

    RISK_HIGH_PRIORITY_HIGH = int(os.getenv("RISK_HIGH_PRIORITY_HIGH", "10"))
    RISK_HIGH_PRIORITY_LOW = int(os.getenv("RISK_HIGH_PRIORITY_LOW", "5"))

    RISK_BLOCKED_HIGH = int(os.getenv("RISK_BLOCKED_HIGH", "3"))
    RISK_BLOCKED_LOW = int(os.getenv("RISK_BLOCKED_LOW", "1"))

    RISK_SCORE_HIGH = int(os.getenv("RISK_SCORE_HIGH", "60"))         # ≥此值→高风险
    RISK_SCORE_MED = int(os.getenv("RISK_SCORE_MED", "30"))           # ≥此值→中风险

    # ── 报告清理策略 ──────────────────────────
    REPORT_MAX_AGE_DAYS = int(os.getenv("REPORT_MAX_AGE_DAYS", "30"))  # 报告保留天数

    @classmethod
    def get_build_jql(cls, base_jql: str) -> str:
        """根据配置的项目添加过滤"""
        if cls.TARGET_PROJECTS:
            # 给 KEY 加引号，防止含特殊字符的项目破 JQL
            project_filter = "project IN (" + ",".join(f'"{k}"' for k in cls.TARGET_PROJECTS) + ")"
            return f"{base_jql} AND {project_filter}"
        return base_jql

    @classmethod
    def cleanup_old_reports(cls) -> int:
        """清理超过 REPORT_MAX_AGE_DAYS 天的旧报告文件，返回删除数量"""
        import glob  # 仅在调用时引入，避免模块导入期加载
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
        if cls.EPIC_LINK_FIELD_ID:
            print(f"🔗 Epic Link字段: {cls.EPIC_LINK_FIELD_ID}")
        print(f"📊 查询限制: 单次最多 {cls.MAX_TASKS_PER_TOOL} 条")
        print(f"🗑  报告保留: {cls.REPORT_MAX_AGE_DAYS} 天")