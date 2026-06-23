# WBS 拆解子 Agent 实现计划

## 概述

将 WBS 拆解功能从主流程中独立为子 Agent，使用 `create_react_agent` 创建专用 Agent，具有独立模型配置和专用提示词。子 Agent 只调用 `suggest_epic_tasks`（只读），不调用任何创建类工具。同时修改主 Agent 提示词，使主 Agent 能自动识别用户的拆解意图并路由到子 Agent。

## 现有代码分析

### main.py 关键结构
- 使用 `ChatOpenAI` 创建 `llm`，模型配置来自 `Config.MODEL_NAME`/`MODEL_API_BASE`/`MODEL_API_KEY`
- 使用 `create_react_agent(model=llm, tools=tools, prompt=system_prompt, checkpointer=checkpointer)` 创建 Agent
- `tools` 列表从 `tools/` 包导入（懒加载），共 22 个工具
- Agent 是全局变量，被 `webapp.py` 直接导入使用

### config.py 关键结构
- `ModelConfig` 类：从 `os.getenv("MODEL_API_BASE")` / `os.getenv("MODEL_API_KEY")` / `os.getenv("MODEL_NAME")` 读取
- `Config` 类统一入口，委托给子配置类

### tools/__init__.py 懒加载机制
- `_LAZY_TOOLS` 字典：工具名 → 子模块名
- `__getattr__` 在首次访问时才 import 对应模块
- 新增工具需要在此登记（但 `call_wbs_agent` 是 main.py 中直接定义的，不走懒加载）

### suggest_epic_tasks 工具
- 位于 `tools/task_tools.py:1121`
- 参数：`epic_key`（Epic 的 KEY）
- 返回 JSON：包含 Epic 标题、描述、项目、现有子任务列表、提示信息

### prompts.py
- `SYSTEM_PROMPT_TEMPLATE`：主 Agent 的系统提示词
- 包含工具列表说明、创建流程、Epic 拆分流程、会议纪要流程等
- **需要新增 WBS 拆解章节**，让主 Agent 知道何时调用 `call_wbs_agent`

## 需要新增/修改的文件

### 新增文件（4个）

#### 1. `agents/__init__.py`
```python
# -*- coding: utf-8 -*-
"""agents 包 — 子 Agent 模块"""
```

#### 2. `agents/wbs_decomposition/__init__.py`
```python
# -*- coding: utf-8 -*-
"""WBS 拆解子 Agent"""
from .agent import wbs_agent, decompose_epic
__all__ = ["wbs_agent", "decompose_epic"]
```

#### 3. `agents/wbs_decomposition/models.py`
Pydantic 数据模型：

- `WBSItem`: 单个 WBS 节点
  - `id: str` — 节点标识（如 "1.1.2"）
  - `title: str` — 节点标题
  - `level: int` — 层级（1=Epic, 2=Task, 3=Sub-task, 4=Sub-sub-task）
  - `parent_id: Optional[str]` — 父节点ID
  - `children: List[WBSItem]` — 子节点列表（递归，默认空列表）
  - `description: Optional[str]` — 节点描述
  - `acceptance_criteria: Optional[str]` — 验收标准

- `WBSDecompositionResult`: 拆解结果
  - `epic_key: str` — 被拆解的 Epic KEY
  - `wbs_tree: str` — WBS 树（缩进文本）
  - `task_list: str` — 任务清单（Markdown 表格）
  - `notes: str` — 拆解说明

#### 4. `agents/wbs_decomposition/prompts.py`
```python
# -*- coding: utf-8 -*-
"""WBS 拆解专用系统提示词"""

WBS_SYSTEM_PROMPT = """你是一个专业的 WBS（工作分解结构）拆解专家。你只做一件事——把 Epic 拆解为可执行的 WBS 任务树。

## 角色边界
- 你只负责拆解，不创建 Jira 任务
- 你只负责分析，不分配资源和排期
- 你只负责输出结构，不估算工时

## 拆解方法（PMI 标准）
1. **100% 覆盖原则**：所有子节点的工作范围之和必须完全等于父节点的范围，不多不少
2. **MECE 原则**：子节点之间相互独立（Mutually Exclusive）、完全穷尽（Collectively Exhaustive）
3. **80 小时法则**：最底层工作包（叶子节点）的预估工作量不超过 80 小时（约 2 人周）

## 拆解策略（按场景选择一种主策略，可辅以其他）
1. **按模块/组件拆解**：适用于产品开发类项目（如"用户模块→登录/注册/权限"）
2. **按技术层级拆解**：适用于技术架构类项目（如"前端→中间件→后端→数据库"）
3. **按阶段/流程拆解**：适用于流程驱动类项目（如"需求→设计→开发→测试→上线"）
4. **按研究维度拆解**：适用于探索性/研究类项目（如"文献调研→方案设计→原型验证→结论"）

## 输出格式（必须严格遵循，用中文输出）

### WBS 树（缩进列表）
```
1. [Epic名称]
  1.1 [Task名称] — 简要说明
    1.1.1 [Sub-task名称] — 简要说明
      1.1.1.1 [Sub-sub-task名称] — 简要说明（仅必要时到第4层）
    1.1.2 [Sub-task名称]
  1.2 [Task名称]
    ...
```

### 任务清单（表格）
| 编号 | 任务名称 | 层级 | 简要描述 | 验收标准 |
|------|---------|------|---------|---------|
| 1 | ... | Epic | ... | ... |
| 1.1 | ... | Task | ... | ... |
| 1.1.1 | ... | Sub-task | ... | ... |

### 拆解说明
- **拆解策略**：说明选用哪种策略及原因
- **覆盖验证**：说明如何保证 100% 覆盖父节点范围
- **关键假设**：列出拆解过程中所做的重要假设
- **待确认项**：标注信息不足、需要用户补充的部分

## 规则（严格遵守）
1. **不猜测**：Epic 信息不足以支撑拆解时，明确标注"待确认"，不编造内容
2. **不超过 4 层**：Epic（第1层）→ Task（第2层）→ Sub-task（第3层）→ Sub-sub-task（第4层）
3. **不分配资源**：不指定负责人、不估算工时、不排期
4. **不创建任务**：只输出拆解方案，不调用任何创建类工具

## 可用工具
你只能调用以下工具：
- **suggest_epic_tasks**: 获取 Epic 的详细信息（标题、描述、现有子任务）。调用参数：epic_key（Epic 的 Jira KEY）

## 工作流程
1. 用户提供 Epic KEY → 调用 suggest_epic_tasks 获取 Epic 详情
2. 根据 Epic 的标题和描述，分析其性质，选择合适的拆解策略
3. 按选定策略逐层拆解，每层检查 MECE 和 100% 覆盖
4. 输出 WBS 树 + 任务清单 + 拆解说明
5. 完成。不做进一步操作。

用中文回复。"""
```

#### 5. `agents/wbs_decomposition/agent.py`
```python
# -*- coding: utf-8 -*-
"""WBS 拆解子 Agent — 创建与调用"""
import os
import logging
from config import Config
from langchain_openai import ChatOpenAI
from langgraph.prebuilt import create_react_agent
from .prompts import WBS_SYSTEM_PROMPT

_logger = logging.getLogger("jira_bot.wbs_agent")


def get_wbs_model_config() -> dict:
    """获取 WBS 子 Agent 的独立模型配置。
    
    优先级：环境变量 WBS_MODEL_* > 主配置 Config.MODEL_*
    """
    return {
        "model": os.getenv("WBS_MODEL_NAME") or Config.MODEL_NAME,
        "api_key": os.getenv("WBS_MODEL_API_KEY") or Config.MODEL_API_KEY,
        "base_url": os.getenv("WBS_MODEL_API_BASE") or Config.MODEL_API_BASE,
    }


def create_wbs_agent():
    """创建 WBS 拆解子 Agent（使用 create_react_agent）"""
    cfg = get_wbs_model_config()
    
    if not cfg["model"] or not cfg["api_key"]:
        _logger.warning("WBS 子 Agent 模型配置不完整，将无法使用")
        return None
    
    llm = ChatOpenAI(
        model=cfg["model"],
        api_key=cfg["api_key"],
        base_url=cfg["base_url"],
        temperature=0.3,  # 低温度，追求确定性输出
        max_tokens=4096,
    )
    
    # 子 Agent 只能调用 suggest_epic_tasks（只读工具）
    from tools.task_tools import suggest_epic_tasks
    wbs_tools = [suggest_epic_tasks]
    
    agent = create_react_agent(
        model=llm,
        tools=wbs_tools,
        prompt=WBS_SYSTEM_PROMPT,
    )
    
    _logger.info("WBS 子 Agent 初始化成功（模型: %s）", cfg["model"])
    return agent


# 全局实例（懒初始化）
wbs_agent = None


def get_wbs_agent():
    """获取或创建 WBS 子 Agent 全局实例"""
    global wbs_agent
    if wbs_agent is None:
        wbs_agent = create_wbs_agent()
    return wbs_agent


async def decompose_epic(epic_key: str) -> str:
    """对指定 Epic 进行 WBS 拆解。
    
    这是子 Agent 的唯一对外接口。
    
    Args:
        epic_key: Epic 的 Jira KEY（如 KO-100）
    
    Returns:
        WBS 拆解结果文本（WBS树 + 任务清单 + 拆解说明）
    """
    agent = get_wbs_agent()
    if agent is None:
        return "❌ WBS 拆解失败：子 Agent 未初始化，请检查模型配置（WBS_MODEL_NAME 等环境变量）。"
    
    prompt = (
        f"请对 Epic {epic_key} 进行 WBS 拆解。\n"
        f"步骤：\n"
        f"1. 先调用 suggest_epic_tasks(epic_key=\"{epic_key}\") 获取 Epic 详情\n"
        f"2. 分析 Epic 的标题和描述，选择合适的拆解策略\n"
        f"3. 按 PMI 标准生成完整的 WBS 拆解（WBS树 + 任务清单 + 拆解说明）"
    )
    
    try:
        response = await agent.ainvoke({"messages": [("user", prompt)]})
        if response and "messages" in response:
            return response["messages"][-1].content or "WBS 拆解完成，但未生成文本内容。"
        return "WBS 拆解失败：未获取到结果。"
    except Exception as e:
        _logger.error("WBS 拆解异常: %s", e)
        return f"❌ WBS 拆解失败: {str(e)}"
```

### 修改文件（2个）

#### 6. `prompts.py` — 新增 WBS 拆解章节

在现有 `SYSTEM_PROMPT_TEMPLATE` 的工具列表中新增 `call_wbs_agent` 的说明，并在流程章节中新增 WBS 拆解流程。

**在"可用工具"列表中新增**（在 `analyze_meeting_for_projects` 之后）：
```
	- call_wbs_agent: 【WBS拆解专家】对 Epic 进行专业的工作分解结构（WBS）拆解。
	  调用独立的 WBS 拆解专家子 Agent，按 PMI 标准（100%覆盖、MECE、80小时法则）生成完整的 WBS 树和任务清单。
	  参数：epic_key（Epic 的 Jira KEY，如 KO-100）。
	  适用场景：用户说"拆解"、"WBS"、"分解 Epic"、"拆分任务"、"任务分解"等。
	  返回：WBS 树（缩进列表）+ 任务清单（Markdown 表格）+ 拆解说明。
	  注意：此工具只做拆解分析，不会创建任何 Jira 任务。如需创建，用户确认拆解方案后，再调用 batch_create_issues。
```

**在流程章节中新增**（在"会议纪要到项目结构流程"之后，在"更新任务的规范"之前）：
```
	**WBS 拆解流程**：
	当用户要求拆解 Epic、做 WBS、分解任务时，按以下流程操作：
	1. 用户必须提供 Epic KEY（如 KO-100）。
	2. 调用 call_wbs_agent(epic_key="KO-100")，等待 WBS 专家子 Agent 完成拆解。
	3. 将子 Agent 返回的拆解结果完整展示给用户。
	4. 询问用户：是否需要将拆解方案中的 Task 和 Sub-task 批量创建到 Jira？
	5. 如果用户确认创建，则按拆解方案调用 batch_create_issues 逐层创建。
	   - 注意遵守 Epic → Task → Sub-task 层级规则。
```

#### 7. `main.py` — 导入子 Agent + 新增工具

**在导入区域新增**（在 `from tools import` 之后，`from langchain_openai` 之前）：
```python
from agents.wbs_decomposition import decompose_epic
```

**在 `tools` 列表定义之前，新增 `call_wbs_agent` 工具函数**：
```python
from langchain.tools import tool as langchain_tool

@langchain_tool
async def call_wbs_agent(epic_key: str = "") -> str:
    """
    【WBS拆解专家】对 Epic 进行专业的工作分解结构（WBS）拆解。
    调用独立的 WBS 拆解专家子 Agent，按 PMI 标准（100%覆盖、MECE、80小时法则）
    生成完整的 WBS 树和任务清单。
    
    参数：
      epic_key - 要拆解的 Epic 的 Jira KEY（如 KO-100）
    
    返回：WBS 树（缩进列表）+ 任务清单（Markdown 表格）+ 拆解说明
    
    注意：此工具只做拆解分析，不会创建任何 Jira 任务。
    """
    if not epic_key:
        return "WBS 拆解失败：请提供 Epic 的 Jira KEY（如 KO-100）。"
    try:
        result = await decompose_epic(epic_key)
        return result
    except Exception as e:
        return f"❌ WBS 拆解失败: {str(e)}"
```

**在 tools 列表中新增**（在 `analyze_meeting_for_projects` 之后）：
```python
    analyze_meeting_for_projects,
    call_wbs_agent,  # WBS 拆解子 Agent
]
```

## 新增 `.env` 配置项

在 `.env` 和 `.env.example` 中新增：
```bash
# ── WBS 子 Agent 模型配置（可选，未设置时回退到主配置 MODEL_NAME / MODEL_API_BASE / MODEL_API_KEY）──
# 如果想让 WBS 拆解使用不同的模型（如更便宜的模型），取消注释并填写：
# WBS_MODEL_NAME=deepseek-v4-flash
# WBS_MODEL_API_BASE=https://ark.cn-beijing.volces.com/api/coding/v3
# WBS_MODEL_API_KEY=ark-xxxxx
```

## 完整交互流程

用户说："帮我拆解 KO-100" →

1. 主 Agent 收到消息，识别到"拆解"关键词
2. 主 Agent 根据提示词中的 WBS 拆解流程，调用 `call_wbs_agent(epic_key="KO-100")`
3. `call_wbs_agent` 内部调用 `decompose_epic("KO-100")`
4. 子 Agent 收到指令，调用 `suggest_epic_tasks("KO-100")` 获取 Epic 详情
5. 子 Agent 分析 Epic 内容，选择拆解策略，生成 WBS 树 + 任务清单 + 拆解说明
6. 结果返回给主 Agent
7. 主 Agent 将拆解结果展示给用户，询问是否需要创建到 Jira

## 不变更内容

- `tools/` 包及其所有工具保持不变
- `webapp.py` 保持不变（它只导入 main.py 的 `agent`，不感知子 Agent）
- `config.py` 保持不变（子 Agent 配置独立读取环境变量）
- `tools/__init__.py` 保持不变（`call_wbs_agent` 是 main.py 中直接定义的 `@tool` 函数，不走懒加载）
- 其他所有文件保持不变

## 文件清单汇总

| 文件 | 操作 | 说明 |
|------|------|------|
| `agents/__init__.py` | 新增 | 包标记 |
| `agents/wbs_decomposition/__init__.py` | 新增 | 导出 wbs_agent、decompose_epic |
| `agents/wbs_decomposition/models.py` | 新增 | Pydantic 数据模型（WBSItem 等） |
| `agents/wbs_decomposition/prompts.py` | 新增 | WBS 专用系统提示词 |
| `agents/wbs_decomposition/agent.py` | 新增 | 子 Agent 创建、配置、decompose_epic 接口 |
| `prompts.py` | **修改** | 新增 call_wbs_agent 工具说明 + WBS 拆解流程章节 |
| `main.py` | **修改** | 导入 decompose_epic，新增 call_wbs_agent 工具，加入 tools 列表 |
