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

from jobws_core import containment  # 路径包含判定唯一原语（realpath + commonpath）

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
      3. 归属判定——`jobws_core.containment` 原语（realpath 展开）：符号链接 /
         junction 读穿到工作区外一律拒（原语义含「等于工作区」，对应
         is_within_or_equal；2026-10-02 收编批）；
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
    real = os.path.realpath(path)   # 后续扩展名 / 读取 / 截断都用真实路径
    if not containment.is_within_or_equal(path, workspace):
        return None, "正文路径越出工作区：%s" % job_name
    if os.path.splitext(real)[1].lower() not in _TEXT_SUFFIX:
        return None, "只提供 Markdown / 纯文本正文：%s" % filename
    if not os.path.isfile(real):
        return None, ("岗位「%s」下没有%s（文件名应为 %s）" % (job_name, label, filename))

    with io.open(real, "r", encoding="utf-8", errors="replace") as handle:
        text = handle.read()
    # **按字节**截断（独立审查 MINOR-1）：先 encode 再切再 decode——`str` 切片按
    # code point，纯中文时 20K 字符 ≈ 60K 字节，会把"20KB 上限"放大三倍。
    # decode(errors="ignore") 处理恰好切在多字节字符中间的情形（丢半个字符，
    # 不影响可读性）。
    raw = text.encode("utf-8")
    if len(raw) > JD_TEXT_MAX_BYTES:
        rel = os.path.relpath(real, workspace).replace("\\", "/")
        text = (raw[:JD_TEXT_MAX_BYTES].decode("utf-8", "ignore")
                + "\n\n…（已截断，完整内容见工作区 %s）" % rel)
    return text, None


# --- 注册（2026-10-12 从 server.py 移入：原文件撞规模水位，按能力归位）--------


def register(mcp, workspace):
    """把只读资源注册到 mcp：三个静态资源 + 两个岗位正文模板。

    handler 用工厂闭包闭合 uri / kind——顺带避开循环里闭包晚绑定的坑；固定 URI
    的 handler 必须**无参**（SDK 校验签名与 URI 模板变量一致）。
    """
    def _make_reader(uri):
        def _read():
            text, error = read_resource(workspace, uri)
            if text is not None:
                return text
            return json.dumps({"ok": False, "errors": [error]}, ensure_ascii=False)

        return _read

    for _item in list_resources(workspace):
        mcp.resource(_item["uri"], name=_item["name"],
                     description=_item["description"],
                     mime_type=_item["mimeType"])(_make_reader(_item["uri"]))

    # 岗位正文模板：URI 里带 `{job_name}` 时 SDK 注册成 template（不是静态资源），
    # handler 的**参数名必须与模板变量一致**。`job_name` 只接受**单个目录名**
    # （不含斜杠）——目录解析复用 `tools_readonly._job_dir` 的同一份判据。
    def _make_job_reader(kind):
        def _read(job_name: str) -> str:
            text, error = read_job_text(workspace, job_name, kind)
            if text is not None:
                return text
            return json.dumps({"ok": False, "errors": [error]},
                              ensure_ascii=False)

        return _read

    mcp.resource("jobws://job/{job_name}/jd", name="JD 原文",
                 description="某岗位的 JD 原文正文（Markdown；超长会截断并给出文件路径）",
                 mime_type="text/markdown")(_make_job_reader("jd"))
    mcp.resource("jobws://job/{job_name}/card", name="解析卡正文",
                 description="某岗位的解析卡正文（Markdown；超长会截断并给出文件路径）",
                 mime_type="text/markdown")(_make_job_reader("card"))


def register_text_tool(mcp, workspace):
    """注册岗位正文的**工具形态**入口 `read_job_text`（2026-10-12）。

    为什么要有工具形态：DSH 宿主**不桥接 MCP 资源**——官方 `dsh-mcp-client` 的
    README 明写「Tools are the only bridged MCP capability — Resources and Prompts
    have no harness consumption surface and are deferred」，实现里 resource block
    直接丢弃；而三个技能此前把 `jobws://` 当正文唯一读法，那份技能在 DSH 上读不到
    内容。工具形态跨宿主可用。实现**复用** `read_job_text()`：越界拒绝 / 截断注明 /
    明确错误口径只有一份。
    """
    # 懒导入（D1 同款）：本模块其余部分是纯函数、脱 SDK 可测（见
    # mcp/tests/test_resources_prompts.py），只有 register* 跑在 SDK 环境里。
    from . import annotations

    @mcp.tool(name="read_job_text", annotations=annotations.READ_ONLY)
    def read_job_text_tool(job_name: str, kind: str = "jd") -> str:
        """读岗位正文（JD 原文 / 解析卡，只读）。

        job_name 是岗位池里的**单个目录名**（如 云帆_后端，不含斜杠）；
        kind = jd（JD 原文，默认）或 card（解析卡正文）。超过 20 KB 会截断
        并注明完整内容的相对路径；读不到给**明确错误**（ok=false 与理由），
        **不要凭岗位名推断正文**——让用户提供或核对工作区。
        """
        text, error = read_job_text(workspace, job_name, kind)
        if text is not None:
            return text
        return json.dumps({"ok": False, "errors": [error]}, ensure_ascii=False)
