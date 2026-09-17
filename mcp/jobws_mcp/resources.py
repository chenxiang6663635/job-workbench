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

import json

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
        data = tools_readonly.list_applications(workspace, limit=200)
    elif uri == "jobws://workspace/jobs":
        data = tools_readonly.list_jobs(workspace, limit=200)
    elif uri == "jobws://workspace/dashboard":
        data = tools_readonly.dashboard_summary(workspace)
    else:
        return None, ("未知资源：%s —— 先调 list_resources 看有哪些可用。" % uri)
    return json.dumps(data, ensure_ascii=False, indent=2), None
