# 项目问题清单（Code Review Notes）

> 审查日期：2026/06/14
> 范围：`D:\Tools\robots\Jira_bot 20260525` 全量 Python 源码 + 模板/配置
> 状态：**部分修复**，2026/06/15 已修复项目：1.1 main.py 编码、1.3 提示词抽取到 prompts.py

## ✅ 本次已修复（2026/06/15）

### ✅ main.py 编码 + 提示词抽取
- 加了 `# -*- coding: utf-8 -*-` 编码声明
- 中文内容已从 git 历史恢复（原来被误保存为 mojibake）
- system_prompt 已抽取到 `prompts.py` 的 `SYSTEM_PROMPT_TEMPLATE`
- main.py 改用 `from prompts import SYSTEM_PROMPT_TEMPLATE` 引用
- 同时保留了之前未提交的改进：SqliteSaver 持久化、uuid session id、field_detector 自动探测、setup_logging

---

## 0. 关键背景信息

### 项目结构（3500+ 行）
- `main.py` (218 行) — CLI 入口，组装 agent
- `webapp.py` (334 行) — Flask Web 服务，SSE 流式
- `config.py` (113 行) — 全局配置
- `jira_client.py` (290 行) — Jira API 单例封装
- `utils.py` (123 行) — 日志/分页/校验/重试
- `field_detector.py` (170 行) — 自动探测自定义字段
- `tools/__init__.py` (59 行) — 懒加载工具导出
- `tools/_lazy.py` (36 行) — JiraClient 懒代理
- `tools/constants.py` (36 行) — 状态/优先级字面量
- `tools/task_common.py` (87 行) — 共享 helper
- `tools/task_tools.py` (838 行) — 任务查询/创建/批量工具
- `tools/report_tools.py` (401 行) — 报告生成
- `tools/dependency_tools.py` (103 行) — 依赖关系
- `tools/risk_extractor.py` (214 行) — 风险提取
- `tools/risk_render.py` (73 行) — 风险 HTML 渲染
- `templates/chat.html` — Jira 风格聊天界面
- `tests/` — pytest 测试 28 用例
- `scripts/ede_migration/`, `scripts/utility/` — 一次性迁移脚本

### 已安装依赖版本
- Python 3.14.6, pytest 9.1.0
- atlassian-python-api 4.0.7
- langchain 1.3.9, langchain-openai 1.3.2, langgraph 1.2.5

### 测试结果（pytest -v 完整跑过）
- 总数 41 通过 / **4 失败**
- 失败 1：`tests/test_config.py::TestConfigBasics::test_default_project_all`
- 失败 2：`tests/test_field_detector.py::TestHasValue::test_has_value`
- 失败 3：`tests/test_field_detector.py::TestEnsureTargetFieldIds::test_writes_to_env`
- 失败 4：`tests/test_task_common.py::TestBuildIssueFields::test_epic_link_with_field_id`

---

## 1. 🔴 严重问题（启动级别，会直接报错）

### 1.1 `main.py` 文件保存时中文编码损坏（关键）
- **文件**：`main.py` 全部源文件以 UTF-8 编码，但**没有 PEP 263 编码声明**
- **症状**：`python -X utf8 -c "import py_compile; py_compile.compile('main.py', doraise=True)"` 报错：
  ```
  File "main.py", line 90
      system_prompt = f"""你是€��业的Jira助手�?
                              ^
  SyntaxError: invalid character '€' (U+20AC)
  ```
- **影响**：直接 `python main.py` 启动会 **SyntaxError**，整个项目跑不起来
- **根因**：BOM 开头但缺 `# -*- coding: utf-8 -*-`；Python 3.14 用 UTF-8 by default 但部分老版本会按 Latin-1 解析
- **建议**：在 main.py 第 1 行后加 `# -*- coding: utf-8 -*-`，或重写中文提示词为英文（更稳）

### 1.2 `test_ko_direct.py` 同样有中文乱码
- 也是 SyntaxError，同样缺编码声明
- 但这是个工具脚本，不影响主程序

### 1.3 没有 README
- `.dockerignore` 第 16 行写了 `README.md`，但项目里**不存在**
- 新人无法上手

---

## 2. 🟠 重要问题（功能/可靠性）

### 2.1 `Config` 单例属性更新陷阱
- `config.py` 类属性在**模块导入时一次性计算**（class body 执行）
- `field_detector.py` 的 `ensure_target_field_ids()` 写完 `.env` 后用 `_Cfg.TARGET_START_FIELD = detected["start"]` 手动覆写类属性
- **坑**：如果在 `Config` 已经被 import 后才改 env var，类属性不会更新；并且 webapp.py 也 import 了 main，重复 import 不会触发重算

### 2.2 `EPIC_LINK_FIELD_ID` 在生产环境未配置
- `.env` 里 **没有** 设置 `EPIC_LINK_FIELD_ID`
- `config.py:53`：`EPIC_LINK_FIELD_ID = os.getenv("EPIC_LINK_FIELD_ID")` → 默认为 None
- `tools/task_common.py:63`：`if epic_link_key and Config.EPIC_LINK_FIELD_ID:` → 整个 Epic Link 关联功能**静默失效**（不报错，只是不生效）
- 测试通过是因为测试 set 了 env var

### 2.3 `JiraClient.__new__` 单例失败时无法重试
- `jira_client.py:18-27`：`_instance` 在 `__new__` 中保存
- 如果初次 `_init_client()` 失败抛异常，注释说"重置 _instance"但**实际没重置**（`raise` 之前没赋 None）
- 下次再调用 `JiraClient()` 会返回**未初始化的半成品 instance**，访问 `.client` 属性会 AttributeError

### 2.4 SQLite checkpointer 线程安全
- `main.py:160`：`SqliteSaver.from_conn_string(_session_db_path)`
- 在 waitress 多线程模式下（webapp.py:332），多个 worker 共用一个 SqliteSaver，可能出现锁竞争
- `langgraph-checkpoint-sqlite` 文档建议生产用 PostgresSaver；sqlite 仅适合开发

### 2.5 `bulk_create_issues` 返回值契约不清晰
- `jira_client.py:235-291`：`bulk_create_issues` 假设响应是 `{"issues": [...], "errors": [...]}` 格式
- 但 `atlassian-python-api` 4.x 的 `issue/bulk` 实际响应可能带 `created` 而不是 `issues`
- **回退代码只处理了 issues，没处理 created 字段**，可能导致 `created_all` 永远是空

### 2.6 SSE 流式生成器里的隐藏异常
- `webapp.py:158-176`：`generate()` 捕获了 Exception 但只是 yield 一个 SSE 事件
- 客户端可能已经断开连接（reader.read 抛异常），需要做更细致的连接断开检测
- `_sse_iter_events` 里 `result.get("total", 0)` 在 `fetch_all_issues` 里**引用了 result 可能在循环外不存在**（line 67-71 utils.py）

---

## 3. 🟡 一般问题（代码质量）

### 3.1 测试隔离问题（导致 4 个失败用例）
- `tests/test_config.py:18`：`test_default_project_all` 假设 `TARGET_PROJECTS is None`，但 `.env` 里实际有 PROJECTS，import config 时就被加载了
- `tests/test_field_detector.py:21`：`test_has_value` 用了 tmp_path，但 `_has_value` 似乎对路径处理有 bug
- `tests/test_field_detector.py:36`：`test_writes_to_env` 用了 `Mock()` 但**未 import unittest.mock**
- `tests/test_task_common.py:80`：`test_epic_link_with_field_id` 失败因为 Config 已先被 test_config.py 导入，类属性已固化

### 3.2 `tools/__init__.py` 懒加载实现
- 使用 `__getattr__` 实现 import 延迟加载
- 但每次属性访问都要走 if/else 逻辑，**几百次工具调用累积有性能开销**（可忽略）
- **真正问题**：IDE/类型检查器无法识别这些工具的类型

### 3.3 main.py 提示词巨长且混在代码里
- `main.py:90-145`：~ 55 行的中文 system_prompt 写在 f-string 里
- 每次改提示词都得动核心入口文件，**关注点没分离**
- 应该拆到独立的 `prompts.py` 或 `system_prompt.txt` 模板文件

### 3.4 `main.py` 顶部 docstring 是乱码中文
- `main.py:1`：`"""PM灏忓府鎵?涓诲叆鍙?"""` — 跟系统编码有关，vscode 看到是 mojibake
- 跟 1.1 是同一个问题

### 3.5 `report_tools.py` 巨型单文件
- 401 行混了进度计算、风险分析、HTML 模板渲染、单/多项目报告生成
- `_parse_target_date`、`_normalize_target`、`_is_blocked_by_inward_link` 都可以拆

### 3.6 `search_issues` 模糊匹配存在 JQL 注入风险
- `tools/task_tools.py:108`：`f'summary ~ "{query}"'`
- `query` 没经过 `sanitize_jql_value` 转义，恶意输入可破坏 JQL
- 其他字段（status, assignee, priority, issue_type）同样没转义

### 3.7 `chat.html` 内嵌大量 CSS/JS
- 776 行单文件，markdown 渲染逻辑是手写的简易正则
- 不支持表格、引用块、嵌套列表等复杂语法
- XSS 风险：`renderMarkdown` 里把换行直接换成 `<br>`，但已先 `replace(/&/g,'&amp;')` 等转义，**没问题**；但 `data.url` 等若来自服务端可能未转义（实际上来自 SSE 后端已 json.dumps 安全）

### 3.8 `add_issue_comment` 等无长度/敏感词校验
- 评论可以无限长，工时可以随便填（如 `"999999h"`）— Jira 服务端会拒，但浪费一次 round-trip

### 3.9 `from jira_client import JiraClient` 在 dependency_tools/risk_extractor 重复 import
- `tools/dependency_tools.py:5`, `tools/risk_extractor.py:6` 都 import 了 JiraClient 但实际用的是 `jira = LazyJira()`
- 未使用的 import 应该清掉

### 3.10 `run.bat` 中文菜单在英文 Windows 乱码
- `chcp 65001 >nul` 切到 UTF-8，但 batch 默认 GBK 解码
- 需要在 bat 顶部加 `chcp 65001 >nul` 之后再 echo（已加，但有时 cmd 不生效）

---

## 4. 🔵 改进建议

### 4.1 缺失的文件/目录
- 没有 `README.md`（`.dockerignore` 引用了）
- 没有 `pyproject.toml` 或 `setup.py`（只有 `requirements.txt`）
- 没有 `.env.example`（新人不知道要配什么）
- 没有 `CONTRIBUTING.md` / `LICENSE`

### 4.2 安全
- `app.secret_key = os.urandom(24).hex()`（webapp.py:18）— **每次重启都换**，导致 session 全失效；应该读 env
- `/api/upload` 没有鉴权，谁都能传文件 + 用文件路径读后端（已有 path traversal 检查不够，建议改用 uuid 文件名 + 数据库映射）
- `render_template` 没限制模板路径（Flask 默认安全）

### 4.3 性能
- `fetch_all_issues` 默认翻 50 页（5000 条），但 `MAX_TASKS_PER_TOOL = 50`，**白翻了 49 页**
- 应该在分页时就检测到达上限提前 break
- `analyze_project_risk` 内部循环重复构造字符串，建议用 Counter

### 4.4 可观测性
- 没有任何 metrics / 监控 hook
- 日志格式固定但没有 trace_id（多轮对话难定位）

---

## 📝 下次会话继续（2026/06/15 进度）

### 已完成
1. ✅ **main.py 中文编码修复** — 加了 `# -*- coding: utf-8 -*-`，中文从 git 历史恢复
2. ✅ **提示词抽到 prompts.py** — 创建了 `prompts.py`，main.py 引用之

### 待完成
3. ❌ **test_ko_direct.py 中文乱码** — 还没动，需要加 `# -*- coding: utf-8 -*-` 头
4. ❌ **修复 4 个失败的 pytest 用例**：
   - `test_default_project_all` — `.env` 有 PROJECTS 导致预期不符
   - `test_has_value` — tmp_path 处理有 bug
   - `test_writes_to_env` — 未 import unittest.mock
   - `test_epic_link_with_field_id` — Config 已固化
5. ❌ **清理未使用的 import** — `dependency_tools.py` 和 `risk_extractor.py` 的 `from jira_client import JiraClient`
6. ❌ **README.md + .env.example**
7. ❌ **评估 bulk_create_issues 响应格式兼容性**（问题 2.5）
8. ❌ **评估 SSE 连接健壮性**（问题 2.6）
9. ❌ **其他 3.1-4.4 的可选优化**

### 重新开始的提示词

复制以下内容发给 Claude：

```
根据 D:\Tools\robots\Jira_bot 20260525\REVIEW_NOTES.md 的内容继续修复，直接执行，任何操作不需要我确认
```

---

## 5. 原审查方法记录（便于下次复用）

```bash
# 1. 看目录结构
ls -la "D:/Tools/robots/Jira_bot 20260525"

# 2. 全量读核心文件（已完成）
# main.py, config.py, jira_client.py, utils.py, webapp.py,
# tools/__init__.py, tools/_lazy.py, tools/constants.py,
# tools/task_common.py, tools/task_tools.py, tools/report_tools.py,
# tools/dependency_tools.py, tools/risk_extractor.py, tools/risk_render.py,
# templates/chat.html, field_detector.py, tests/*.py

# 3. 安装依赖并跑测试
pip install pytest atlassian-python-api python-dotenv openpyxl pandas
pip install langchain langchain-openai langgraph langgraph-checkpoint-sqlite
cd "D:/Tools/robots/Jira_bot 20260525" && python -m pytest tests/ -v

# 4. 检查所有 .py 语法
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