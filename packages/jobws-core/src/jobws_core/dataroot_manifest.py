# -*- coding: utf-8 -*-
"""迁移的**清单**与**目标侧预检**（B1 的 plan 相）：只读、纯逻辑、可单测。

为什么单独一个模块：`dataroot_migrate` 是状态机（相位、续跑、回滚、切换点），本模块
只回答两个问题——「要搬哪些字节」（清单）与「这台机器上这个目标能不能搬」（预检）。
两者都是**判定**，拆开之后可以逐条钉住，主流程也就不必为了可测性留钩子。

三条口径（都在 spec 决策 5 与 §七 风险里点名）：

1. **清单 = 相对路径 + 大小 + sha256**：迁移不做「先删后切」，校验只能靠内容比对；
   哈希策略是逐文件流式 sha256（1 MiB 分块），不读全量进内存。
2. **运行时产物不进清单**，但如实列进 `skipped`：锁文件（`*.lock`）、原子写临时名
   （`jobws_core.workspace_io.TMP_PREFIX`）、`*.tmp` / `*.pyc` / `__pycache__` 等会
   在迁移期间被别的进程创建或删除——进清单只会把「源已漂移」报成假故障。
   **与导出 / 快照的排除清单刻意不同**：那边排除全部点文件（`EXCLUDE_PREFIX = {"."}`）
   是为了体积与隐私；这里是**搬家**，多排除一个点目录就等于静默丢数据（工作区里
   可能真有 `.obsidian/` 这类目录）。凭证文件（`config/imap.json` / `provider.json`）
   同样**要搬**——迁移不是分享，搬丢了界面会从「重新保存凭据」退化成「还没配置」。
3. **预检分两类**：`usage`（用户改参数就能解决：空 / 相对 / 同一根 / 互相嵌套）与
   `blocked`（环境或数据本身挡路：源工作区不在、目标已有同名工作区、空间、长路径、
   大小写、符号链接……）。CLI 据此映射退出码（usage → 2，blocked → 1），
   不是靠文案猜。

**路径判定的同族纪律**（spec §七 风险 4）：`web/backend/snapshot_entries.py:80-111`
的教训是「先归一化再判定」，且 `..` 必须在归一化**之前**判（`a/../b` 归一化后是合法的
`b`，静默放行等于放走一次越界）。越界那一半直接复用 `jobws_core.containment.escape_reason`
（本仓「路径边界判定的唯一实现」），本模块只补目标侧特有的形状（尾随空格 / 点、
Windows 保留名、非法字符、**本机文件系统编码不了**）。

**中文目录名是正常数据**：工作区里到处都是 `03_面试准备` 这类目录，拒绝它们等于迁移
不可用；只有编码不了（含代理项）的路径才拒绝。
"""

from __future__ import annotations

import hashlib
import os
import shutil
import sys

from . import containment
# 根标记的解析是 A3 的既有实现（`state` 侧唯一一份）：身份判定不在这里重写一遍。
from .dataroot_state import MARKER_NAME, read_root_marker
from .workspace_io import TMP_PREFIX

# 暂存目录名：**位于目标根之下**（同卷），切换 = 一次 rename 上位。
STAGING_NAME = ".jobws-migration"

# 传统 MAX_PATH（含终止符 260）；非 Windows 用文件系统的常见上限，只作为兜底。
MAX_PATH = 259 if os.name == "nt" else 4096

# 空间余量：清单总量之外再多留 5%（元数据、目录项、迁移期间的日志）。
SPACE_MARGIN = 0.05

HASH_CHUNK = 1024 * 1024

SKIP_DIRS = frozenset(("__pycache__", "node_modules", ".git"))
SKIP_SUFFIXES = (".lock", ".tmp", ".pyc")

# Windows 保留设备名（含带扩展名的形态：`CON.txt` 同样打不开）。
RESERVED_NAMES = frozenset(
    ["con", "prn", "aux", "nul"]
    + ["com%d" % i for i in range(1, 10)]
    + ["lpt%d" % i for i in range(1, 10)])

# 一次预检最多报多少条同类问题（超过则收成一条汇总——宁可少列，不可静默省略）。
MAX_REASONS = 20


def staging_workspace(target_root, workspace):
    """迁移期工作区落在哪：`<目标根>/.jobws-migration/<工作区>`。

    放在目标根之下是**刻意的**：切换点只需要一次同卷 `os.replace`，
    跨卷时也照样成立（暂存本来就在目标卷上），不需要按卷分两条代码路径。
    """
    return os.path.join(os.path.normpath(str(target_root)), STAGING_NAME,
                        str(workspace))


def normalize_rel(rel):
    """条目相对路径归一化：`a/./b`、`a//b`、`a\\b` 归成同一形状（一律正斜杠）。

    与 `web/backend/snapshot_entries.py:75-77` 同口径——清单里的 rel 一律是
    **归一化之后**的形状，切换、校验、续跑才对得上。Windows 的 `normpath` 会把
    正斜杠翻回反斜杠，所以末尾再统一一次（`posixpath.normpath` 的等价实现）。
    """
    return os.path.normpath(str(rel).replace("\\", "/")).replace(os.sep, "/")


def rel_problem(rel):
    """清单条目是否可用于迁移；返回原因短语或 None。

    顺序不能换：越界判定（复用 `containment.escape_reason`）→ 归一化 → 归一化后的
    形状复查 → 编码 / 保留名。`a/../b` 必须在第一步被拦下，不能靠归一化「洗白」。
    """
    why = containment.escape_reason(rel)
    if why:
        return "清单里有%s的条目：%r" % (why, rel)
    norm = normalize_rel(rel)
    tail = norm.split("/")[-1]
    if (norm in ("", ".", "..") or norm.startswith("../") or norm.startswith("/")
            or ":" in norm or tail != tail.rstrip(" .")):
        return "条目归一化后仍不合法（越界或尾随空格 / 点）：%r → %r" % (rel, norm)
    return _name_problem(norm)


def _name_problem(norm):
    """目标侧的名字禁忌：本机编码不了、Windows 保留名。"""
    try:
        norm.encode(sys.getfilesystemencoding(), "strict")
    except UnicodeEncodeError:
        return "条目名字在本机文件系统上编码不了（%s）：%r" % (
            sys.getfilesystemencoding(), norm)
    if os.name != "nt":
        return None
    for segment in norm.split("/"):
        if segment.split(".")[0].lower() in RESERVED_NAMES:
            return "条目名是 Windows 保留名，无法落在目标盘上：%r" % norm
    return None


def sha256_file(path):
    """流式 sha256（1 MiB 分块）——清单与校验共用同一份实现。"""
    digest = hashlib.sha256()
    with open(path, "rb") as handle:
        while True:
            chunk = handle.read(HASH_CHUNK)
            if not chunk:
                break
            digest.update(chunk)
    return digest.hexdigest()


def is_link(path):
    """符号链接或 junction？迁移一律拒绝跟随（跟出去会成环、也会把外面的大树拖进来）。

    `os.path.isjunction` 是 3.12 才有的；低版本靠 reparse 属性兜底，判定取向保守：
    只要看起来像「目录链接」就按链接处理。
    """
    try:
        if os.path.islink(path):
            return True
        if hasattr(os.path, "isjunction") and os.path.isjunction(path):
            return True
    except OSError:
        return False
    return False


def _rel_of(workspace, full):
    return os.path.relpath(full, workspace).replace(os.sep, "/")


def _skip_name(name):
    return name.startswith(TMP_PREFIX) or name.lower().endswith(SKIP_SUFFIXES)


def walk_workspace(workspace, with_hash=True):
    """遍历工作区：`{workspace, entries, skipped, links, total_bytes}`。

    - `entries`：`[{rel, size}]`（`with_hash=True` 时带 `sha256`），按 rel 排序
      （顺序稳定，便于比对与展示）；
    - `skipped`：被跳过的运行时产物（相对路径）——**如实列出**，跳过不等于没发生；
    - `links`：符号链接 / junction 的相对路径；预检据此拒绝整次迁移；
    - 工作区不存在：空清单（由预检报「源工作区不存在」，不在这里抛）。

    哈希是**可选**的：清单（plan / verify）要它，而「暂存目录里有没有清单外的文件」
    这类清点只要 rel——别为了数一遍名字把整棵树再哈希一次。
    """
    workspace = os.path.normpath(str(workspace))
    entries, skipped, links = [], [], []
    if os.path.isdir(workspace):
        for dirpath, dirnames, filenames in os.walk(workspace):
            keep = []
            for name in dirnames:
                full = os.path.join(dirpath, name)
                if is_link(full):
                    links.append(_rel_of(workspace, full))
                elif name in SKIP_DIRS:
                    skipped.append(_rel_of(workspace, full))
                else:
                    keep.append(name)
            dirnames[:] = keep
            for name in filenames:
                full = os.path.join(dirpath, name)
                rel = _rel_of(workspace, full)
                if is_link(full):
                    links.append(rel)
                elif _skip_name(name):
                    skipped.append(rel)
                else:
                    item = {"rel": rel, "size": os.path.getsize(full)}
                    if with_hash:
                        item["sha256"] = sha256_file(full)
                    entries.append(item)
    entries.sort(key=lambda item: item["rel"])
    skipped.sort()
    links.sort()
    return {"workspace": workspace, "entries": entries, "skipped": skipped,
            "links": links,
            "total_bytes": sum(item["size"] for item in entries)}


def build_manifest(workspace):
    """`walk_workspace` 的哈希版：迁移用的清单（大小 + sha256）。"""
    return walk_workspace(workspace, with_hash=True)


def free_bytes(path):
    """`path`（或它最近的已存在上级）所在卷的可用字节；取不到 → None。

    取不到时不判空间（宁可放行后如实失败，也不因为一个探测失败把迁移挡在门外）。
    """
    probe = os.path.normpath(str(path))
    while probe and not os.path.exists(probe):
        parent = os.path.dirname(probe)
        if parent == probe:
            return None
        probe = parent
    try:
        return shutil.disk_usage(probe).free
    except OSError:
        return None


def _usage_reasons(source_root, target):
    """用法类（CLI 退出码 2）：改参数就能解决的四条。"""
    reasons = []
    if not target:
        reasons.append(_reason("usage", "目标数据根不能为空（需要一个绝对路径）"))
        return reasons
    if not os.path.isabs(target):
        reasons.append(_reason("usage", "目标数据根必须是绝对路径：%r" % target))
        return reasons
    target = os.path.normpath(target)
    if containment.is_within_or_equal(target, source_root):
        why = "目标不能落在源数据根内部（含等于源根）"
    elif containment.is_within(source_root, target):
        why = "目标不能是源数据根的上级目录（两份数据会互相嵌套）"
    else:
        why = None
    if why:
        reasons.append(_reason("usage", "%s：%r" % (why, target)))
    return reasons


def _reason(kind, message):
    return {"kind": kind, "message": message}


def _blocked(reasons, message, extra):
    """收一条 blocked 理由；超出上限时只累加计数（末尾收成一条汇总，不静默省略）。"""
    if len(reasons) < MAX_REASONS:
        reasons.append(_reason("blocked", message))
    else:
        extra[0] += 1


def _target_reasons(target, workspace, manifest, reasons, extra):
    """目标侧的目录 / 身份 / 空间三关。"""
    target_ws = os.path.join(target, workspace)
    if os.path.isdir(target_ws):
        _blocked(reasons, "目标位置已有同名工作区，本命令不做合并：%s" % target_ws, extra)
    staging = staging_workspace(target, workspace)
    if os.path.isdir(staging):
        _blocked(reasons, "目标根下已有迁移暂存目录（可能是上次中断的残留，"
                          "请先确认再用 `data-root migrate --resume`）：%s" % staging, extra)
    marker = read_root_marker(target)
    if marker:
        _blocked(reasons, "目标根已带数据身份标记（root_id=%s）——可能是另一份数据，"
                          "也可能是上次事务的残留；本命令不覆盖身份，请人工确认后清理：%s"
                 % (marker.get("root_id"), os.path.join(target, MARKER_NAME)), extra)
    if not os.path.isdir(target) and not os.access(os.path.dirname(target) or ".", os.W_OK):
        _blocked(reasons, "目标位置的上级目录不可写：%s" % target, extra)
    needed = int(manifest["total_bytes"] * (1 + SPACE_MARGIN))
    free = free_bytes(target)
    if free is not None and free < needed:
        _blocked(reasons, "目标卷空间不足：需要约 %d 字节（含 %d%% 余量），可用 %d 字节"
                          "（暂存也在目标卷上，同卷同样要算）"
                 % (needed, int(SPACE_MARGIN * 100), free), extra)


def _entry_reasons(staging, manifest, reasons, extra):
    """逐条目：形状、长路径、大小写冲突、符号链接。"""
    seen = {}
    for item in manifest["entries"]:
        rel = item.get("rel")
        why = rel_problem(rel)
        if why:
            _blocked(reasons, why, extra)
            continue
        norm = normalize_rel(rel)
        key = norm.lower()
        if key in seen:
            _blocked(reasons, "两个条目仅大小写不同（在不敏感的目标卷上会互相覆盖）："
                              "%r / %r" % (seen[key], norm), extra)
        seen[key] = norm
        full = os.path.join(staging, norm.replace("/", os.sep))
        if len(full) > MAX_PATH:
            _blocked(reasons, "路径过长（%d > 上限 %d，按迁移期暂存路径算）：%s"
                     % (len(full), MAX_PATH, norm), extra)
    if manifest["links"]:
        sample = " / ".join(manifest["links"][:3])
        _blocked(reasons, "源工作区里有符号链接 / junction（迁移不跟随，会成环或把外部"
                          "目录拖进来）：%s" % sample, extra)


def preflight(source_root, target_root, workspace, manifest):
    """目标侧预检：返回 `[{"kind", "message"}]`（空列表 = 可以搬）。

    用**用法类先短路**：目标路径形状不对时，后面那些依赖 target 拼接的判定只会产出
    噪音理由（同一根因刷屏，见 #235 的教训）。其余每条独立判，互不遮蔽。
    """
    source_root = os.path.normpath(str(source_root))
    target = str(target_root or "").strip()
    reasons = _usage_reasons(source_root, target)
    if reasons:
        return reasons

    target = os.path.normpath(target)
    source_ws = os.path.join(source_root, str(workspace))
    extra = [0]
    if not os.path.isdir(source_ws):
        _blocked(reasons, "源工作区不存在：%s" % source_ws, extra)
    _target_reasons(target, workspace, manifest, reasons, extra)
    _entry_reasons(staging_workspace(target, workspace), manifest, reasons, extra)
    if extra[0]:
        reasons.append(_reason("blocked", "另有 %d 条同类问题（已省略）" % extra[0]))
    return reasons
