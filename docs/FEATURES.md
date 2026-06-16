# PM小帮手 功能列表

> 基于 LangGraph + Jira REST API 的智能项目管理助手
> 最后更新：2026-06-15

---

## 📋 任务查询

| 功能 | 入口 | 说明 |
|------|------|------|
| 我的任务 | `get_my_tasks` | 查当前用户所有未完成任务 |
| 项目任务 | `get_project_tasks` | 按项目 KEY 查所有任务 |
| 搜索任务 | `search_issues` | 多条件组合搜索（项目/状态/负责人/优先级/类型/关键词） |

## ✨ 任务创建

| 功能 | 入口 | 说明 |
|------|------|------|
| 创建 Issue | `create_issue` | 支持 Task / Sub-task / Epic / Risk，可设父任务、Epic 关联、自定义字段 |
| 批量创建 | `batch_create_issues` | JSON 传入任务数组，Jira bulk API，≤50 条/批 |
| Excel 导入 | `import_from_excel` | 上传 xlsx 自动解析列名 → 批量创建，支持 dry_run 预览 |
| 图片识别 | Web 上传 | 上传表格截图，AI 识别内容后创建任务 |

## ✏️ 任务更新

| 功能 | 入口 | 说明 |
|------|------|------|
| 更新字段 | `update_issue` | 摘要/描述/优先级/自定义字段（Target Start/End 等） |
| 状态转换 | `get_issue_transitions` | 查看可用转换，引导用户操作 |
| 分配任务 | `assign_issue` | 将 Issue 分配给指定用户 |
| 批量更新日期 | `batch_update_dates` | JSON 传入，批量改开始/结束日期（维护 Jira Plan） |
| 添加评论 | `add_issue_comment` | 给 Issue 添加评论 |
| 记录工时 | `add_issue_worklog` | 记录时间花费（支持 2h / 1d 30m 等格式） |

## 🔗 依赖管理

| 功能 | 入口 | 说明 |
|------|------|------|
| 查看依赖 | `get_issue_links` | 查询 Issue 的 incoming/outgoing 链接 |
| 依赖风险 | `get_task_dependencies` | 分析阻塞风险（依赖未完成 / 被依赖受影响） |
| 创建链接 | `create_issue_link` | 在两 Issue 间建立 blocks / relates to 等关系 |

## ⚠️ 风险分析

| 功能 | 入口 | 说明 |
|------|------|------|
| 提取风险 | `extract_issue_risks` | 提取 Issue Type=Risk 的条目，按优先级/状态分布总结 |
| 项目集报告 | `generate_portfolio_report` | 全项目汇总 HTML 报告（进度/风险/阻塞/超期），含风险明细表 |
| 单项目报告 | `generate_report` | 单个项目的 HTML 进度报告 |

## 🗑️ 其他操作

| 功能 | 入口 | 说明 |
|------|------|------|
| 删除 Issue | `delete_issue` | 二次确认后删除（可连带子任务） |
| 批量删除 | `batch_delete_issues` | 批量删除多个 Issue，二次确认，逐条容错 |
| 元数据查询 | `get_create_issue_metadata` | 查项目支持的问题类型及必填字段，带缓存 |

---

## 🌐 交互界面

| 界面 | 说明 |
|------|------|
| **Web 聊天** (`webapp.py`) | Jira 风格 UI，SSE 流式响应，可看到 AI 调用工具的过程 |
| **CLI** (`main.py`) | 命令行交互，支持持续对话（SQLite 持久化会话） |
| **文件上传** | Web 上传 Excel/图片，拖拽支持 |
| **快捷命令** | 侧边栏预设 + 用户自定义（localStorage 持久化） |
| **会话重置** | 清空当前对话上下文 |

---

## 🔧 基础设施

| 能力 | 说明 |
|------|------|
| 自动字段探测 | 启动时自动匹配 Jira 的 Target Start/End 字段 ID |
| 离线降级 | Jira/LLM 不可达时 webapp 仍可启动（返回 503 提示） |
| 会话持久化 | SQLite 落盘，重启不丢对话 |
| 速率限制 | API 调用最小间隔 0.5s，防触发限流 |
| 重试机制 | 网络异常自动重试（3 次指数退避） |
| 报告清理 | 启动时自动删超过 N 天的旧报告 |
| Docker 部署 | `docker-compose up` 一键启动 |

---

## 📊 统计

- **Jira 操作工具**：15 个
- **交互方式**：Web 聊天 + CLI 命令行
- **测试覆盖**：154 个测试全通过
- **支持的项目**：FCCLMIG, KO, FU2526, MCKINLEY, TISP, S4MIG, RDE, EDE（可配置）
