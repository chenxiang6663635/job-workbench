# -*- coding: utf-8 -*-
"""写入类工具：两段式（先预览拿令牌，再凭令牌落盘）。

与只读工具相同的纪律（见 `tools_readonly.py` 开头），另加一条**最要紧**的：

> **这些函数本身绝不落盘**——`preview_*` 只登记令牌并返回差异；真正写入只发生在
> `apply_approval(token)`，而令牌必须来自**同一个工作区**（令牌里绑着绝对路径）。

为什么在 MCP 侧更要两段式：宿主是把工具当手用的，模型看一遍 summary 就调
apply 的成本几乎为零——所以「给用户看过」这一步必须在协议上留痕（令牌里的
diff 就是给用户看的原文），而不是靠提示词约束。

宿主侧的正确用法是三步，工具的 docstring 里都写了：
    preview_* → 把 summary/diff 展示给用户 → 用户点头后 apply_approval(token)
"""

import os

import approval
import question_bank
import tracker

# 落盘后给宿主的一句话指引：让模型知道"刚才发生了什么、下一步是什么"。
_NEXT_STEP = ("把 summary 与 diff 展示给用户；用户确认之后，用同一个 token 调用 "
              "apply_approval 落盘。令牌一次性、10 分钟内有效。")


def preview_add_application(workspace, **fields):
    """预览新增一条投递记录（**不写入**），返回令牌与将要写入的字段。"""
    errors, plan = tracker.preview_add_fields(fields, workspace)
    if errors:
        return {"ok": False, "errors": errors}
    result = approval.preview("track.add", workspace, plan["payload"],
                              plan["summary"], plan["diff"], plan["targets"])
    return {
        "ok": True,
        "token": result["token"],
        "summary": result["summary"],
        "diff": result["diff"],
        "targets": result["targets"],
        "expires_at": result["expires_at"],
        "next_step": _NEXT_STEP,
    }


def preview_import_applications(workspace, csv_text):
    """预览批量导入（**不写入**）：先按同一口径逐行校验，全部可导入才给令牌。"""
    try:
        csv_rows, unknown = tracker.parse_import_csv(csv_text)
    except ValueError as exc:
        return {"ok": False, "errors": [str(exc)]}

    preview = tracker.preview_import(csv_rows, workspace=workspace)
    if preview["error"]:
        return {
            "ok": False,
            "errors": ["存在错误行，未生成令牌：请修正后重新预览。"],
            "error_rows": [{"line": item["line"], "errors": item["errors"]}
                           for item in preview["error"]],
        }

    # 载荷与差异表的构造只此一份（tracker.plan_import）——CLI / 网页端 / 本工具
    # 共用，避免三处各拼一份之后「预览说 X、落盘写 Y」（独立审查 M2）。
    plan = tracker.plan_import(preview, workspace)
    result = approval.preview(
        "track.import", workspace, plan["payload"],
        plan["summary"], plan["diff"], plan["targets"])
    return {
        "ok": True,
        "token": result["token"],
        "summary": result["summary"],
        "diff": plan["diff"],
        "duplicates": len(preview["duplicate"]),
        "expires_at": result["expires_at"],
        "unknown_columns": unknown,
        "next_step": _NEXT_STEP,
    }


def preview_update_application(workspace, app_id, changes):
    """预览更新一条投递记录（**不写入**），返回令牌与逐字段差异表。

    与 preview_add_application 同款三步用法：preview → 展示 diff → 用户确认后
    apply_approval(token)。只列**要改**的字段（changes 里没有的字段不动）；
    载荷校验与差异表由 tracker.preview_update_fields 统一构造（CLI / 网页端同源，
    避免三处各拼一份之后「预览说 X、落盘写 Y」）。
    """
    errors, plan = tracker.preview_update_fields(
        {"id": app_id, "changes": dict(changes or {})}, workspace)
    if errors:
        return {"ok": False, "errors": errors}
    result = approval.preview("track.update", workspace, plan["payload"],
                              plan["summary"], plan["diff"], plan["targets"])
    return {
        "ok": True,
        "token": result["token"],
        "summary": result["summary"],
        "diff": result["diff"],
        "targets": result["targets"],
        "expires_at": result["expires_at"],
        "next_step": _NEXT_STEP,
    }


def _preview(operation, workspace, plan):
    """「登记令牌 → 组装返回体」的公共尾部（批 4.7 的四个新工具共用）。

    载荷与差异表由领域层构造（tracker / question_bank 的 preview_*），这里只负责
    登记令牌并把给宿主看的东西组装齐——不重写判据，避免「预览说 X、落盘写 Y」。
    """
    result = approval.preview(operation, workspace, plan["payload"],
                              plan["summary"], plan["diff"], plan["targets"])
    return {
        "ok": True,
        "token": result["token"],
        "summary": result["summary"],
        "diff": plan["diff"],
        "targets": result["targets"],
        "expires_at": result["expires_at"],
        "next_step": _NEXT_STEP,
    }


def preview_add_interview(workspace, **fields):
    """预览新增一条面试记录（**不写入**），返回令牌与将要写入的字段。

    fields 用中文列名（关联记录 / 公司 / 岗位 / 轮次 / 面试时间 / 形式 / 链接 /
    面试官 / 问题记录 / 我的回答要点 / 复盘与改进 / 结果）。给了关联记录时，
    公司与岗位从主表带出（与 CLI 同口径）。
    """
    errors, plan = tracker.preview_interview_add_fields(fields, workspace)
    if errors:
        return {"ok": False, "errors": errors}
    return _preview("interview.add", workspace, plan)


def preview_update_interview(workspace, interview_id, changes):
    """预览更新一条面试记录（**不写入**），返回令牌与逐字段差异表。

    只列**要改**的字段（changes 里没有的不动）；面试 id / 关联记录 / 公司 不在
    可更新集合里——改归属要另建一条，避免把时间线接错。
    """
    errors, plan = tracker.preview_interview_update_fields(
        {"id": interview_id, "changes": dict(changes or {})}, workspace)
    if errors:
        return {"ok": False, "errors": errors}
    return _preview("interview.update", workspace, plan)


def preview_add_question(workspace, **fields):
    """预览新增一道题库题目（**不写入**），返回令牌与将要写入的字段。

    fields 用中文列名（题目 / 领域 / 科目 / 标签 / 难度 / 答案要点 / 来源 /
    关联公司 / 关联岗位 / 状态 / 备注）——与 `bank add` 的参数表同一套。
    """
    errors, plan = question_bank.preview_add_fields(fields, workspace)
    if errors:
        return {"ok": False, "errors": errors}
    return _preview("question.add", workspace, plan)


def preview_import_questions(workspace, module_dir=None):
    """预览从 `03_面试准备` 导入题目（**不写入**），返回令牌与逐条差异。

    module_dir 必须是**工作区内的相对目录**：绝对路径会被 os.path.join 当成新根，
    `..` 能翻出工作区——两者都先拒（与 CLI 的 `bank import` 同一道门）。
    """
    target = module_dir or question_bank.MODULE_DIR
    if os.path.isabs(target) or ".." in target.replace("\\", "/").split("/"):
        return {"ok": False,
                "errors": ["module_dir 必须是工作区内的相对目录（不能是绝对路径或含 ..）"]}
    errors, plan = question_bank.preview_import(workspace, target)
    if errors:
        return {"ok": False, "errors": errors}
    return _preview("question.import", workspace, plan)


def apply_approval(workspace, token):
    """凭令牌执行已确认的写入（两段式的第二步）。

    令牌不可用（过期 / 已用过 / 绑定别的工作区 / 载荷被改过）时返回 ok=False，
    不抛异常——宿主拿到的是可读的拒绝理由，而不是栈。
    """
    try:
        result = approval.apply(token, workspace=workspace)
    except approval.ApprovalError as exc:
        # code 是稳定判据（批 8）：宿主据此区分 重放（not_found）/ 过期（expired）/
        # 指纹不符（fingerprint）/ 绑定不符（binding）等——不要解析中文文案。
        return {"ok": False, "errors": [str(exc)],
                "code": getattr(exc, "code", "invalid")}
    return {
        "ok": True,
        "summary": result.get("summary"),
        "id": result.get("id"),
        "written": result.get("written"),
    }
