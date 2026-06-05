"""Jira API 客户端封装"""
from atlassian import Jira
from config import Config

class JiraClient:
    """Jira 客户端单例"""
    
    _instance = None
    
    def __new__(cls):
        if cls._instance is None:
            cls._instance = super().__new__(cls)
            cls._instance._init_client()
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
        print("✅ Jira 连接成功")
    
    def get_client(self):
        """获取 Jira 客户端实例"""
        return self.client
    
    def query(self, jql: str):
        """执行 JQL 查询"""
        return self.client.jql(jql)
    
    def get_issue(self, key: str):
        """获取单个 Issue"""
        return self.client.issue(key)
    
    def get_all_projects(self):
        """获取所有项目"""
        return self.client.get_all_projects()
    
    def create_issue(self, fields: dict):
        """创建 Issue"""
        return self.client.create_issue(fields=fields)