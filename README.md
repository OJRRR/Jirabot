# Jira Bot — Jira 项目管理助手

基于 LangGraph 和 Jira REST API 的智能项目管理助手，支持自然语言查询、创建任务、批量操作、风险分析、依赖管理等功能。

## 功能概览

- **任务查询** — 按项目、状态、负责人、关键字等条件搜索 Jira 任务
- **任务创建** — 单个或批量创建 issue，支持子任务、Epic 关联
- **任务更新** — 更新状态、负责人、优先级、自定义字段
- **依赖管理** — 创建/查询阻塞关系（blocks / depends on）
- **批量填写** — 批量更新自定义字段（Target Start / Target End）
- **风险分析** — 自动分析项目进度、超期、阻塞等风险并生成报告
- **Web 界面** — 内建 Flask Web 服务，Jira 风格聊天界面，SSE 流式响应
- **CLI 模式** — 命令行直接交互

## 快速开始

### 环境要求

- Python 3.14+
- 可访问的 Jira 实例
- LLM API Key（支持 OpenAI 兼容接口）

### 安装

```bash
# 克隆仓库
git clone <repo-url>
cd Jira_bot

# 安装依赖
pip install -r requirements.txt
```

### 配置

复制环境变量模板并填写：

```bash
cp .env.example .env
```

必须配置的项：

| 变量 | 说明 |
|------|------|
| `JIRA_SERVER` | Jira 服务器地址 |
| `JIRA_USER` | Jira 用户名/邮箱 |
| `JIRA_TOKEN` | Jira API Token（[如何获取](https://id.atlassian.com/manage/api-tokens)） |
| `MODEL_API_BASE` | LLM API 地址 |
| `MODEL_API_KEY` | LLM API Key |
| `MODEL_NAME` | 模型名称 |

可选配置见 `.env.example`。

### 运行

**CLI 模式：**
```bash
python main.py
```

**Web 模式：**
```bash
python webapp.py
# 或使用生产级服务器
waitress-serve --port 8080 webapp:app
```

**Windows 一键启动：**
```bash
run.bat
```

## 项目结构

```
├── main.py                      # CLI 入口
├── webapp.py                    # Flask Web 服务
├── config.py                    # 全局配置
├── jira_client.py               # Jira API 单例封装
├── utils.py                     # 工具函数（日志/分页/校验/重试）
├── field_detector.py            # 自动探测自定义字段
├── prompts.py                   # AI 提示词模板
├── tools/
│   ├── task_tools.py            # 任务查询/创建/批量工具
│   ├── report_tools.py          # 报告生成
│   ├── dependency_tools.py      # 依赖关系
│   ├── risk_extractor.py        # 风险提取
│   ├── risk_render.py           # 风险 HTML 渲染
│   ├── task_common.py           # 共享 helper
│   ├── _lazy.py                 # JiraClient 懒代理
│   └── constants.py             # 状态/优先级字面量
├── templates/
│   └── chat.html                # Jira 风格聊天界面
├── tests/                       # pytest 测试
└── scripts/                     # 一次性迁移脚本
```

## 开发

```bash
# 运行测试
pytest tests/ -v

# 语法检查
python -X utf8 -c "
import py_compile
files = ['main.py', 'config.py', 'jira_client.py', 'utils.py', 'field_detector.py', 'webapp.py',
         'tools/__init__.py', 'tools/_lazy.py', 'tools/constants.py', 'tools/task_common.py',
         'tools/task_tools.py', 'tools/report_tools.py', 'tools/dependency_tools.py',
         'tools/risk_extractor.py', 'tools/risk_render.py']
for f in files:
    try:
        py_compile.compile(f, doraise=True)
        print(f, 'OK')
    except py_compile.PyCompileError:
        print(f, 'FAIL')
"
```

## 依赖

- Python 3.14.6
- atlassian-python-api 4.0.7
- langchain 1.3.9, langchain-openai 1.3.2, langgraph 1.2.5
- flask, waitress
- openpyxl, pandas
- pytest 9.1.0

## 许可证

MIT
