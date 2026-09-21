# -*- coding: utf-8 -*-
"""投递记录删除的预览端点（2026-09-21 批 D 数据安全网）。

为什么单独成文件：`applications.py` 是登记过水位的存量文件（只许变小），新端点
按 `progress/question_previews.py` 的先例落在兄弟模块——"删除预览"与列表 / 增改
同属投递域，但独立成一个入口。
"""

from __future__ import annotations

from fastapi import APIRouter, Depends

from deps import workspace_dir
from routers.progress._shared import delete_preview_response

router = APIRouter(prefix="/api/applications")


@router.get("/preview-delete")
def preview_application_delete(id: str = "", ws: str = Depends(workspace_dir)):
    """预览删除一条投递记录（**不落盘**）：差异表含「将解绑的关联记录」清单。

    2026-09-21 批 D：删除带**解绑联动**——邮件 / 面试 / 联系人 / 宣讲会 / Offer
    里以「关联记录」指回这条投递的行会被清空外键（记录保留），差异表逐条列明
    （"哪几条"正是判断依据）；时间线不删、追记一条「已删除」。落盘走既有的
    `/api/approvals/apply`（写通道只有一条）。
    """
    from jobws_core.tracker import application_delete
    errors, plan = application_delete.preview_delete_application(id, ws)
    return delete_preview_response("application.delete", errors, plan,
                                   "app.deleteFailed", "投递删除预览失败", ws)
