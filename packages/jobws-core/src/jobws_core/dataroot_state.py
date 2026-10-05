# -*- coding: utf-8 -*-
"""数据根**持久化状态**（A3）：选择文件与根标记的写 / 清 / 读身份。

为什么单独一个模块：`dataroot_probe` 是**只读**探测（状态判定用），A3 的写入
是另一件事——放这里让 probe 保持「绝不写」的纪律，也让 `dataroot.py`（解析
与编排）不再膨胀。读取原语仍在 probe（`selection_file` / `read_selection_document`），
本模块只负责变更与身份。

两件持久化物（spec 决策 2）：
- **选择文件** `<user_data_dir>/state/data-root.json`：位置不依赖应用根（四端
  可共同计算，决策 1.4/6 的前提）；写必须**原子**（同目录临时文件 + `os.replace`），
  并在**切换点**显式 `flush` + `os.fsync`——spec 决策 2 明确承认「不 fsync 即
  无崩溃耐久性」，这里把它补上；
- **根标记** `<root>/.jobws-root.json`：`root_id`（数据身份）随数据走，路径搬家
  id 不变。**不含路径、不含敏感信息**；已存在则一字不动（幂等）。

坏文件纪律：读取侧一律按「未设置」处理（probe）；写侧遇到坏文件不阻塞重写
（生成新身份覆盖），这正是「删文件即回到现状」的回滚形态。
"""

from __future__ import annotations

import io
import json
import os
import uuid
from datetime import datetime

from .dataroot_probe import read_selection_document, selection_file

# 选择文件与根标记各自的格式版本（schema 见 spec 决策 2）。
SELECTION_FORMAT = 1
MARKER_NAME = ".jobws-root.json"
MARKER_FORMAT = 1

# `selected_by` 词表（spec 决策 2）：用户动作 / 迁移事务 / 命令行。
SELECTED_BY = ("user", "migration", "cli")


def now_iso():
    """控制面时间戳（秒级 ISO）：选择文件 / 根标记 / 迁移事务记录共用同一形状。"""
    return datetime.now().isoformat(timespec="seconds")


def same_root(a, b):
    """两个路径是否指向同一数据根（大小写不敏感——Windows 盘符 / 目录大小写）。"""
    if not (isinstance(a, str) and isinstance(b, str) and a.strip() and b.strip()):
        return False
    return (os.path.normcase(os.path.normpath(a.strip()))
            == os.path.normcase(os.path.normpath(b.strip())))


def atomic_write_json(path, data):
    """原子写 JSON：同目录临时文件 → flush + fsync → `os.replace`。

    `newline="\\n"` 固定换行（Windows 上不产出 CRLF）；失败时清掉临时文件，
    不让半成品留在 state/ 里。**控制面里所有 JSON 落盘都走这里**（选择文件、根标记、
    迁移事务记录 `dataroot_migrate`）——一处实现，别处不要再写第二份 temp+replace。
    """
    directory = os.path.dirname(path)
    if directory and not os.path.isdir(directory):
        os.makedirs(directory)
    text = json.dumps(data, ensure_ascii=False, indent=2) + "\n"
    tmp = path + ".tmp-%s" % uuid.uuid4().hex
    try:
        with io.open(tmp, "w", encoding="utf-8", newline="\n") as handle:
            handle.write(text)
            handle.flush()
            os.fsync(handle.fileno())
        os.replace(tmp, path)
    except BaseException:
        if os.path.exists(tmp):
            try:
                os.remove(tmp)
            except OSError:
                pass
        raise


def read_root_marker(root):
    """读 `<root>/.jobws-root.json`；缺失 / 坏 / 缺 `root_id` → None。

    坏标记按「没有标记」处理：诊断的 `root_id` 回落读选择文件，写侧会补写
    新标记——一个读不出的文件不该把换根流程锁死。
    """
    path = os.path.join(os.path.normpath(str(root)), MARKER_NAME)
    try:
        with io.open(path, "r", encoding="utf-8") as handle:
            data = json.load(handle)
    except (OSError, ValueError):
        return None
    if isinstance(data, dict) and isinstance(data.get("root_id"), str) and data["root_id"]:
        return data
    return None


def ensure_root_marker(root, root_id=None):
    """确保根标记存在（幂等）：已存在则不动并返回现有内容。

    `root` 目录不存在时**不创建、不写**、返回 None——标记属于数据本身，
    不能靠写标记把一条不存在的路径"变成"根；选择不存在的路径是用户的权利，
    之后由三态如实报 `unavailable`（决策 4）。
    """
    root = os.path.normpath(str(root))
    if not os.path.isdir(root):
        return None
    marker = read_root_marker(root)
    if marker:
        return marker
    data = {
        "format": MARKER_FORMAT,
        "root_id": root_id or uuid.uuid4().hex,
        "created_at": now_iso(),
        "schema_version": None,
    }
    atomic_write_json(os.path.join(root, MARKER_NAME), data)
    return data


def write_persisted_selection(root, *, source="cli", env=os.environ):
    """记住数据根：写 `<user_data_dir>/state/data-root.json`，返回写入的文档。

    规则（spec 决策 1 / 2）：
    - **只接受绝对路径**：相对 / 空值 → ValueError（fail-fast，不落盘）；
    - `root_id` 身份三级优先：根标记（数据自带身份，搬家不变）→ 既有选择文件
      （同一根则沿用，不无谓换身份）→ 新 `uuid4`（换根换身份）；
    - 写选择前先 `ensure_root_marker`（把身份也钉进数据根，供「搬家后仍是
      同一份数据」判定）；
    - `env` 参数与读取侧同签名（`read_persisted_selection(env)`）；写入内容
      不随 env 变化——env 的优先级判定在 `resolve_data_root`。
    """
    if not isinstance(root, str) or not root.strip():
        raise ValueError("数据根不能为空")
    if not os.path.isabs(root.strip()):
        raise ValueError("数据根必须是绝对路径：%r" % root)
    if source not in SELECTED_BY:
        raise ValueError("selected_by 取值非法：%r（应为 %s）"
                         % (source, " / ".join(SELECTED_BY)))
    root = os.path.normpath(root.strip())

    marker = read_root_marker(root)
    root_id = (marker or {}).get("root_id")
    if not root_id:
        doc = read_selection_document()
        if doc and same_root(doc.get("data_root"), root):
            existing = doc.get("root_id")
            root_id = existing if isinstance(existing, str) and existing else None
    if not root_id:
        root_id = uuid.uuid4().hex
    ensure_root_marker(root, root_id=root_id)

    data = {
        "format": SELECTION_FORMAT,
        "data_root": root,
        "root_id": root_id,
        "selected_at": now_iso(),
        "selected_by": source,
        "migration_state": "idle",  # B 批迁移事务接管前恒为 idle
        "schema_version": None,     # 工作区数据语义版本：B 批写入真实值
    }
    atomic_write_json(selection_file(), data)
    return data


def clear_persisted_selection():
    """删除持久化选择（幂等）：返回是否真的删掉了一份。"""
    try:
        os.remove(selection_file())
        return True
    except FileNotFoundError:
        return False


def resolved_root_id(path, sel):
    """当前数据根的 `root_id`：**根标记优先，其次选择文件**（且须同一根）。

    为什么限定「同一根」：env 显式覆盖（或选择已失效）时，选择文件里记的是
    **另一个数据身份**——报成当前根的 id 就是错认。`sel` 是
    `read_persisted_selection()` 的三键对象。
    """
    marker = read_root_marker(path)
    if marker:
        return marker["root_id"]
    if sel and sel.get("readable") and same_root(sel.get("path"), path):
        doc = read_selection_document()
        root_id = doc.get("root_id") if doc else None
        if isinstance(root_id, str) and root_id:
            return root_id
    return None
