# -*- coding: utf-8 -*-
"""WBS 拆解数据模型 — Pydantic 结构定义"""

from typing import Optional, List
from pydantic import BaseModel, Field


class WBSItem(BaseModel):
    """WBS 树中的单个节点（递归结构）"""

    id: str = Field(..., description="节点标识，如 1、1.1、1.1.2")
    title: str = Field(..., description="节点标题")
    level: int = Field(
        ..., ge=1, le=4, description="层级：1=Epic, 2=Task, 3=Sub-task, 4=Sub-sub-task"
    )
    parent_id: Optional[str] = Field(None, description="父节点 ID")
    children: List["WBSItem"] = Field(
        default_factory=list, description="子节点列表"
    )
    description: Optional[str] = Field(None, description="节点描述")
    acceptance_criteria: Optional[str] = Field(None, description="验收标准")


class WBSDecompositionResult(BaseModel):
    """WBS 拆解完整结果"""

    epic_key: str = Field(..., description="被拆解的 Epic Jira KEY")
    wbs_tree: str = Field(..., description="WBS 树（缩进文本）")
    task_list: str = Field(..., description="任务清单（Markdown 表格）")
    notes: str = Field(..., description="拆解说明（策略、覆盖验证、关键假设、待确认项）")


class WBSDecompositionInput(BaseModel):
    """WBS 拆解输入参数"""

    epic_key: str = Field(..., description="Epic 的 Jira KEY（如 KO-100）")
    project_context: Optional[str] = Field(None, description="项目上下文/额外说明")
    max_depth: int = Field(default=4, ge=2, le=4, description="最大拆解深度（2~4）")
