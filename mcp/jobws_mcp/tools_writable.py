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

import approval
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

    diff = ["| 状态 | 行 | 公司 | 岗位 |", "|---|---|---|---|"]
    for item in preview["ok"]:
        diff.append("| 将新增 | %d | %s | %s |" % (
            item["line"], item["row"].get("公司", ""), item["row"].get("岗位", "")))
    result = approval.preview(
        "track.import", workspace, {"preview": preview},
        "导入 %d 条投递记录" % len(preview["ok"]), diff,
        tracker._tracking_targets(workspace))
    return {
        "ok": True,
        "token": result["token"],
        "summary": result["summary"],
        "diff": diff,
        "duplicates": len(preview["duplicate"]),
        "expires_at": result["expires_at"],
        "unknown_columns": unknown,
        "next_step": _NEXT_STEP,
    }


def apply_approval(workspace, token):
    """凭令牌执行已确认的写入（两段式的第二步）。

    令牌不可用（过期 / 已用过 / 绑定别的工作区 / 载荷被改过）时返回 ok=False，
    不抛异常——宿主拿到的是可读的拒绝理由，而不是栈。
    """
    try:
        result = approval.apply(token, workspace=workspace)
    except approval.ApprovalError as exc:
        return {"ok": False, "errors": [str(exc)]}
    return {
        "ok": True,
        "summary": result.get("summary"),
        "id": result.get("id"),
        "written": result.get("written"),
    }
