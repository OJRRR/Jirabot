from jira_client import JiraClient
from config import Config
from datetime import datetime

jira = JiraClient().get_client()

def analyze_project(project_key):
    print(f"\n{'='*50}")
    print(f"分析项目: {project_key}")
    print('='*50)
    
    issues_data = jira.jql(f"project = {project_key}")
    if not issues_data:
        print("无法获取数据")
        return
    
    issues = issues_data.get("issues", [])
    print(f"任务总数: {len(issues)}")
    
    # 检查字段值的类型分布
    start_types = {}
    end_types = {}
    start_none = 0
    end_none = 0
    
    for issue in issues:
        fields = issue.get("fields", {})
        start = fields.get(Config.TARGET_START_FIELD)
        end = fields.get(Config.TARGET_END_FIELD)
        
        if start is None:
            start_none += 1
        else:
            start_types[type(start).__name__] = start_types.get(type(start).__name__, 0) + 1
        
        if end is None:
            end_none += 1
        else:
            end_types[type(end).__name__] = end_types.get(type(end).__name__, 0) + 1
    
    print(f"target_start: None数量={start_none}, 类型分布={start_types}")
    print(f"target_end: None数量={end_none}, 类型分布={end_types}")
    
    # 检查日期格式
    print("\n检查日期格式示例:")
    sample_count = 0
    for issue in issues[:5]:
        fields = issue.get("fields", {})
        start = fields.get(Config.TARGET_START_FIELD)
        end = fields.get(Config.TARGET_END_FIELD)
        if start or end:
            print(f"  {issue.get('key')}: start='{start}', end='{end}'")
            sample_count += 1
        if sample_count >= 3:
            break

# 分析两个项目
analyze_project("RDE")
analyze_project("KO")