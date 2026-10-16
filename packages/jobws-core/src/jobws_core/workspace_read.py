# -*- coding: utf-8 -*-
"""共享读取原语：工作区内有界读 + 归属判定（与 `workspace_io` 对偶，四端唯一入口）。

为什么单独一个模块（2026-10-16，#307 领域层读取与追加边界收口）：
岗位文件一族此前已收口（MCP `paths.read_in_workspace` 与 Web
`routers/jobs._read_in_workspace` 各一份），而领域层还有三族裸露——
tracker 主表 / 时间线的 `io.open` 无界直读、`gap_analysis` 的四类输入
（JD / 简历 / 词典 / 母版 / 事实库）同样自己读、`append_history` 的
`"a"` 模式跟随链接写穿。三端（CLI / MCP / Web）各补一遍就是第四份漂移，
故判据与读法下沉领域层，协议层只留转译。

**不放 `containment`**：它 109 行纯判据、在 `pathres → jd_score/tracker`
导入链主干上、被 17 个文件 import，且**没有任何「无 IO」断言**——往里加读，
破坏发生时一条测试都不会红。**不放 `workspace_io`**（写侧原语，300 行水位
贴死）；**不放 `csv_cells`**（职责是单元格策略 + 读一份表）。

三个口径（与 MCP 既有实现逐字一致，改动必须两边一起看）：
1. **两边都 real()**：`resolve_ws` 只 `abspath`，工作区自身是 junction 时
   只归一一侧会误判（`containment` 的原始论证）；
2. **字节上限 + 超限拒绝**（None）：不取「字符 + 截断」——截断后的正文会被
   解析成半真半假的结果（评分段落可能正好被切掉），比「读不到」更坏；
3. **换行归一并进原语**：CRLF / CR 统一成 LF（与 Web 文本模式 universal
   newlines 同源），协议层各自补的那段归一篇幕（`resources.read_job_text`）
   删除。

**TOCTOU 如实写明**：判定与打开之间，链接可被换成另一个目标（判定时区内、
读取时区外）。本工具是本地单用户工作台，链接拓扑由用户维护、不是对抗性
并发——判据钉住的是「读取那一刻的展开结果」，不是「永久不可能变」。写侧
（`assert_within` + `open("a")`）同理：它防的是「目录被做成链接」这类常态
拓扑，不防判定后的瞬时换靶。
"""

from __future__ import annotations

import io
import os

from . import containment


class WorkspaceBoundaryError(RuntimeError):
    """目标路径越出工作区（读穿 / 写穿防护的显式拒绝）。

    领域层只抛它；协议层转译成各自错误面——方向是单向的（与 `ConflictError`
    同款范式，领域代码不必知道 HTTP 状态码 / 退出码）：
    - Web：`boundary.register` 映射 400 `path.escape`（与 `deps.safe_join`
      的越界分支同一个码，前端语言包不必新增键）；
    - CLI：`jobws.py` 主入口译成退出码 2 + 可读文案（与越界工作区同档）；
    - MCP：`tools_readonly` / `tools_writable` 译成 `{"ok": False, ...}`。

    消息**面向用户**：会经协议层原样透出，必须写清「哪个路径、越到哪去了、
    大概为什么」——只带异常原文的消息等于把排障成本转嫁给用户。
    """


def normalise_newlines(text):
    """CRLF / CR 归一成 LF（先 CRLF 后 CR，顺序不可颠倒——反了会把 CRLF 折成两行）。"""
    return text.replace("\r\n", "\n").replace("\r", "\n")


def is_in_workspace(workspace, *parts):
    """`workspace/parts...` 的归属校验（realpath 展开）；**不要求路径存在**。

    语义 = `containment.is_within_or_equal`（含「等于工作区」——浏览与拼接场景
    的既有语义）。两点刻意取舍：
    - **不要求存在**：调用方要判「将要读的文件」的归属（差距分析的锚点预检）；
    - **链接目标仍在工作区内时不做限制**：用户把工作区分片放在同步盘再链进来
      是合法用法（`resolve_workspace` 同样只对「读穿到外面」动手）。

    契约：**parts 须是单段相对名**（拼绝对路径 / `..` 段会重置根，判据 fail-closed
    兜住——那不是漏判）。
    """
    return containment.is_within_or_equal(os.path.join(workspace, *parts), workspace)


def exists_in_workspace(workspace, *parts):
    """工作区内是否存在该文件：**归属校验通过之后**才算存在。

    不能直接用 `os.path.isfile`：它**跟随链接**——目录是 junction 时，
    「有解析卡」 / 「有 tracker.csv」 这类布尔会正判定出一个工作区外的文件，
    而这个布尔本身就是泄漏（调用方据此能探测工作区外有没有某个文件）。
    越界一律按「不存在」给；指向**工作区内**的链接照旧为 True。
    """
    return (is_in_workspace(workspace, *parts)
            and os.path.isfile(os.path.join(workspace, *parts)))


def assert_within(workspace, path):
    """归属校验；越界抛 `WorkspaceBoundaryError`（不返 bool）。返回原 path。

    写侧为什么用「抛」而不是「跳过」：静默跳过等于吞账——界面显示「没投过」、
    时间线少一条，而用户不知道自己刚做了什么。显式拒绝让协议层转译成
    可读错误面，代价由出错的那一次调用承担。
    """
    if not containment.is_within_or_equal(path, workspace):
        raise WorkspaceBoundaryError(
            "路径越出工作区（多是符号链接 / junction 指向了外部）：%s"
            "（工作区：%s）——请把数据放回工作区内，或移除该链接后重试。"
            % (path, workspace))
    return path


def read_in_workspace(workspace, *parts, max_bytes=None):
    """读工作区内的文本：realpath 归属校验（+可选字节上限）；越界 / 读不到返回 None。

    fail-closed：越界、不是普通文件、打不开、读不了**一律 None**，不抛错——调用方
    要的是「给不出正文」这一件事，把文件系统的异常类别透出去只是噪声。
    链接跳转照旧：归属判的是**链接目标**，目标在工作区内就照读。

    `max_bytes` 给定时是**二进制**有界读：文本模式的 `read(n)` 数的是**字符**，
    纯中文时 n 个字符 ≈ 3n 字节。给定上限且文件超过它时**返回 None（拒绝）而不是
    截断**——截断后的正文会被解析成「半真半假」的结果，比明确的「读不到」更坏。
    需要「截断并注明」的调用方自己读（见 MCP `resources.read_job_text`）。
    **不传上限是无界全读**——只在确定文件体量可控时才省略。
    """
    full = os.path.join(workspace, *parts)
    if not containment.is_within_or_equal(full, workspace):
        return None
    try:
        with io.open(full, "rb") as handle:
            raw = handle.read() if max_bytes is None else handle.read(max_bytes + 1)
    except (OSError, ValueError):
        return None
    if max_bytes is not None and len(raw) > max_bytes:
        return None
    return normalise_newlines(raw.decode("utf-8", "replace"))
