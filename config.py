"""配置管理模块"""
import os
from dotenv import load_dotenv

load_dotenv()


class Config:
    """全局配置类"""
    
    # Jira 配置
    JIRA_SERVER = os.getenv("JIRA_SERVER")
    JIRA_USER = os.getenv("JIRA_USER")
    JIRA_TOKEN = os.getenv("JIRA_TOKEN")
    
    # 模型配置
    MODEL_API_BASE = os.getenv("MODEL_API_BASE")
    MODEL_API_KEY = os.getenv("MODEL_API_KEY")
    MODEL_NAME = os.getenv("MODEL_NAME")
    AI_TEMPERATURE = float(os.getenv("AI_TEMPERATURE", "0.5"))
    
    # 项目配置
    PROJECTS_CONFIG = os.getenv("PROJECTS", "").strip()
    TARGET_PROJECTS = None
    if PROJECTS_CONFIG and PROJECTS_CONFIG.upper() != "ALL":
        TARGET_PROJECTS = [p.strip() for p in PROJECTS_CONFIG.split(",") if p.strip()]
    
    # 目录配置
    BASE_DIR = os.path.dirname(os.path.abspath(__file__))
    REPORTS_DIR = os.getenv("REPORTS_DIR", os.path.join(BASE_DIR, "reports"))
    TEMPLATE_DIR = os.path.join(BASE_DIR, "templates")
    
    # 确保目录存在
    os.makedirs(REPORTS_DIR, exist_ok=True)
    os.makedirs(TEMPLATE_DIR, exist_ok=True)
    
    # 自定义字段ID（支持环境变量配置）
    TARGET_START_FIELD = os.getenv("TARGET_START_FIELD", "customfield_12914")
    TARGET_END_FIELD = os.getenv("TARGET_END_FIELD", "customfield_12915")
    # Epic Link 字段ID（可选，用于自动关联Epic）
    EPIC_LINK_FIELD_ID = os.getenv("EPIC_LINK_FIELD_ID")
    
    @classmethod
    def get_build_jql(cls, base_jql: str) -> str:
        """根据配置的项目添加过滤"""
        if cls.TARGET_PROJECTS:
            project_filter = f"project IN ({','.join(cls.TARGET_PROJECTS)})"
            return f"{base_jql} AND {project_filter}"
        return base_jql
    
    @classmethod
    def print_info(cls):
        """打印配置信息"""
        print(f"🧠 模型: {cls.MODEL_NAME}")
        print(f"📁 目标项目: {cls.TARGET_PROJECTS if cls.TARGET_PROJECTS else '所有项目'}")
        print(f"📂 报告目录: {cls.REPORTS_DIR}")
        print(f"📂 模板目录: {cls.TEMPLATE_DIR}")
        print(f"📅 自定义字段: 开始={cls.TARGET_START_FIELD}, 结束={cls.TARGET_END_FIELD}")
        if cls.EPIC_LINK_FIELD_ID:
            print(f"🔗 Epic Link字段: {cls.EPIC_LINK_FIELD_ID}")