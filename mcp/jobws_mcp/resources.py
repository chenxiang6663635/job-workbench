# -*- coding: utf-8 -*-
"""只读资源（批 8）：把工作台数据以 MCP resources 暴露——按需读取、不预载。

设计（与调研结论对齐）：
- **两步**：list_resources 只列 URI 与描述（不含数据）；read_resource(uri)
  才取内容。宿主不要全量预载——那既贵又慢。
- **URI 固定**：全部是 workspace 级常量（`jobws://workspace/...`），不接受路径
  参数、不拼用户输入——从根上排除路径穿越；未知 URI 一律拒绝（返回错误说明）。
- **只读**：全部经 tools_readonly 的同一份口径转发，不重写业务逻辑
  （见该模块开头的三条纪律）。
- **大对象**：简历 PDF 等二进制**不在这里出现**——塞进上下文既贵又无用；
  二进制走"文件路径 + 元数据"，由调用方自行决定要不要读。

宿主用法：先 list 看有哪些资源，再按需 read。
"""

from __future__ import annotations

import io
import json
import os

from . import tools_readonly

# 资源清单：uri → (名称, 说明)。loader 在 read_resource 里按 uri 分派——
# 保持"清单"与"读取"分开，list 永远不会触发数据读取。
_RESOURCES = (
    ("jobws://workspace/applications", "投递记录",
     "投递追踪表的精简视图：公司 / 岗位 / 阶段 / 下次动作（只读）"),
    ("jobws://workspace/jobs", "岗位池",
     "岗位池目录与解析卡评分、投递状态（只读）"),
    ("jobws://workspace/dashboard", "看板摘要",
     "漏斗分布 / 近 7 天待办 / 静默提醒 / 转化率与失败归因（只读）"),
)


# 静态资源的条数上限：与工具的默认 limit 一致——**资源没有参数可调**，写死就必须
# 保守。返回体带 total：宿主看到 total > returned 就知道该改用对应工具翻页，
# 而不是以为"就这么多"。此前写死 200，与"控制体积"这条纪律自相矛盾。
_RESOURCE_LIMIT = 20


def list_resources(workspace):
    """资源清单（**不含数据**）——按需读取的第一步。"""
    del workspace  # 清单是静态的：不读任何文件，也不受工作区内容影响
    return [
        {
            "uri": uri,
            "name": name,
            "description": description,
            "mimeType": "application/json",
        }
        for uri, name, description in _RESOURCES
    ]


def read_resource(workspace, uri):
    """读一个资源（第二步）。返回 (文本内容, 错误说明)；两者必有一个为 None。"""
    if uri == "jobws://workspace/applications":
        data = tools_readonly.list_applications(workspace, limit=_RESOURCE_LIMIT)
    elif uri == "jobws://workspace/jobs":
        data = tools_readonly.list_jobs(workspace, limit=_RESOURCE_LIMIT)
    elif uri == "jobws://workspace/dashboard":
        data = tools_readonly.dashboard_summary(workspace)
    else:
        return None, ("未知资源：%s —— 先调 list_resources 看有哪些可用。" % uri)
    return json.dumps(data, ensure_ascii=False, indent=2), None


# --- 岗位正文（批 8 补缺）：两个**带参数**的模板资源 -------------------------
#
# 为什么是模板而不是塞进静态清单：静态 URI 是常量（list 不读任何文件），而 JD
# 原文按岗位不同——把每个岗位都列进清单等于"list 就要扫工作区"，违背按需读取。
# 模板的 job_name 只接受**单个目录名**（不含斜杠），目录解析复用
# tools_readonly._job_dir 的同一份判据，不在这里写第二套。

# 正文体积上限：超出即截断并附"完整内容见 <相对路径>"——既不撑爆宿主上下文，
# 也不假装完整（截断必须说出来，否则模型会当成全文引用）。
JD_TEXT_MAX_BYTES = 20 * 1024

# kind → (展示名, 文件名)。文件名与 tools_readonly 的常量同源（不另写字面量）。
_JOB_TEXT_KINDS = {
    "jd": ("JD 原文", tools_readonly.JD_FILE),
    "card": ("解析卡", tools_readonly.CARD_FILE),
}

# 只收正文本身：二进制（简历 PDF / 图片）与凭证文件一律不进资源。
_TEXT_SUFFIX = (".md", ".txt")


def read_job_text(workspace, job_name, kind):
    """读岗位正文（jd / card）。返回 (文本, 错误说明)；两者必有一个为 None。

    校验链（顺序即优先级）：
      1. kind 白名单；
      2. 目录名解析——**复用** `tools_readonly._job_dir`：只接受单个目录名，
         拒绝对路径 / 含分隔符 / `..` / 盘符相对路径，且目录必须真实存在；
      3. realpath 双重确认落在工作区内（符号链接 / junction 会读穿出去）；
      4. 扩展名白名单（只给 .md / .txt 正文）；
      5. 体积截断（见 JD_TEXT_MAX_BYTES）。

    文件不存在给**明确错误**而不是空成功——返回空字符串会让模型以为"JD 就是这样"，
    那是比报错更坏的结局（与"永不编造"红线同一条）。
    """
    if kind not in _JOB_TEXT_KINDS:
        return None, ("未知正文类型：%s（可选：%s）"
                      % (kind, " / ".join(sorted(_JOB_TEXT_KINDS))))
    label, filename = _JOB_TEXT_KINDS[kind]

    job_dir, error = tools_readonly._job_dir(workspace, job_name)
    if error:
        return None, error

    path = os.path.join(job_dir, filename)
    real = os.path.realpath(path)
    ws_real = os.path.realpath(workspace)
    if not (real == ws_real or real.startswith(ws_real + os.sep)):
        return None, "正文路径越出工作区：%s" % job_name
    if os.path.splitext(real)[1].lower() not in _TEXT_SUFFIX:
        return None, "只提供 Markdown / 纯文本正文：%s" % filename
    if not os.path.isfile(real):
        return None, ("岗位「%s」下没有%s（文件名应为 %s）" % (job_name, label, filename))

    with io.open(real, "r", encoding="utf-8", errors="replace") as handle:
        text = handle.read()
    if len(text.encode("utf-8")) > JD_TEXT_MAX_BYTES:
        rel = os.path.relpath(real, workspace).replace("\\", "/")
        text = text[:JD_TEXT_MAX_BYTES] + "\n\n…（已截断，完整内容见工作区 %s）" % rel
    return text, None
