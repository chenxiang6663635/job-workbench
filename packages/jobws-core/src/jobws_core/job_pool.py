# -*- coding: utf-8 -*-
"""岗位池快照：目录扫描 + 解析卡合成 + 与追踪表的匹配（**只读**）。

为什么独立成件（2026-10-16 E 批）：`score_calibration` 既要做校准计算又要做
卡片读取，一个文件冲到 348 行；而这两件事的职责不同——读取随时可能因新的
只读需求变化（筛选、排序、统计），校准口径则应稳定。拆开之后：

- 本模块 = 「岗位池现在有什么」的唯一读取入口（每张解析卡只读一次）；
- `score_calibration` = 「这些数据说明什么」的纯计算。

**为什么 `parse_card` 在这**：解析卡 → (总分, 档位, 硬门槛) 的合成原先内联在
`web/backend/routers/jobs.py` 里，E 批要求 Web / CLI / MCP 三端对同一张卡给出
同一个数（设计文档 §八.5），合成只能有一份且在领域层。web 侧改为委托本函数，
只补它自己需要的 `dimensionsDetail`。
"""

from __future__ import print_function

import os
import re

from . import jd_score  # noqa: E402  （维度/档位/硬门槛解析的唯一实现）
from . import job_dirs  # noqa: E402  （目录名拆分、匹配索引、apply_state）
from . import tracker  # noqa: E402  （工作区解析、dedup_key）
from . import workspace_read  # noqa: E402  （有界读 + 归属判定：四端唯一入口）

CARD_FILE = "解析卡.md"
# 与 routers/jobs.py 的 CARD_FILE 同源（一处改名要同步另一处；有测试钉住）

# 解析卡字节上限：与 `routers/jobs.py` 的 `_read_in_workspace` 同口径（2 MiB）。
# 解析卡是几 KB 的 Markdown，两个数量级的余量只防「被构造的超大文件把接口读爆」；
# 超限按「读不到」给（评分 None），**不截断**——半截卡片会解析成半真半假的分档。
CARD_MAX_BYTES = 2 * 1024 * 1024

_BASIC_INFO_RE = re.compile(r"^##\s*基本信息\s*$(.*?)(?=^##\s|\Z)", re.M | re.S)


def parse_card(text):
    """解析卡原文 → {dimensions, total, level, action, consistent, hardGates}。

    缺失或格式错误时返回 None——卡片是渐进填写的，「读不到」是常态而非异常。
    `consistent` 的判据与 web 原先的内联实现逐字相同：四个维度都能解析、
    且加权和等于总分。档位只在 consistent 时给出（半填卡不给档位）。
    """
    if not text:
        return None
    fields = jd_score.parse_score_section(text)
    if not fields:
        return None

    dims, ok = [], True
    for name, maximum in jd_score.DIMENSIONS:
        num, errs = jd_score.parse_dimension(fields.get(name, ""), name, maximum)
        if errs or num is None:
            ok = False
            break
        dims.append({"name": name, "score": num, "max": maximum})

    total_raw = fields.get("总分", "")
    try:
        total = float(total_raw)
    except (TypeError, ValueError):
        ok = False
        total = None

    level = action = None
    if ok and total is not None and abs(sum(d["score"] for d in dims) - total) < 1e-6:
        level, action = jd_score.verdict(total)
    else:
        ok = False

    return {
        "dimensions": dims, "total": total, "level": level,
        "action": action, "consistent": ok,
        "hardGates": jd_score.parse_hard_gates(text),
    }


def basic_info(text):
    """解析卡「基本信息」段的 (公司, 岗位) 展示名；没填或缺该段返回 None。"""
    if not text:
        return None
    seg = _BASIC_INFO_RE.search(text)
    if not seg:
        return None
    values = {}
    for key in ("公司", "岗位"):
        hit = re.search(r"^%s\s*[:：]\s*(.*)$" % key, seg.group(1), re.M)
        values[key] = (hit.group(1).strip() if hit else "")
    if not values["公司"] or not values["岗位"]:
        return None
    return values["公司"], values["岗位"]


def _read_card(workspace, job_dir):
    """读一张解析卡；读不了（不存在 / 越界 / 超限 / 编码）返回 None，不炸整批。

    走 `workspace_read.read_in_workspace`——归属判定与字节上限的唯一入口，
    不在这边私第二套（四端同源：MCP / Web / CLI 读同一张卡必须同一道闸）。
    """
    return workspace_read.read_in_workspace(
        workspace, job_dir, CARD_FILE, max_bytes=CARD_MAX_BYTES)


def _within(real, base_real):
    """real 是否在 base_real 之内（含自身）。"""
    try:
        return os.path.commonpath([real, base_real]) == base_real
    except ValueError:
        return False


def load_job_pool(workspace=None, rows=None):
    """岗位池快照（**只读**，每张解析卡只读一次）。

    返回 [{dir, company, role, displayCompany, displayRole, score, level,
           gate, state, applied}]：
    - `company`/`role` = 目录名首个下划线拆分的**匹配键**（与追踪表同源）；
      `displayCompany`/`displayRole` = 解析卡「基本信息」优先的展示名；
    - `score`/`level`：只在卡片**一致**时给出，否则 None（半填卡与没卡一样
      给不出可用档位，一并计入「未评分」）；
    - `gate`：硬门槛结论（通过 / 不通过 / 待补档案 / 待确认 / None）；
    - `state`：`job_dirs.apply_state` 的三态（未投递 / 流程中 / 已终态）；
    - `applied`：`state != "未投递"` 的派生布尔——与岗位池列表同一口径，
      空阶段的存量行算未投递（不另立一套判断）。

    `rows` 传已读的追踪表行时不再重读（看板同请求单读，读放大纪律）。
    """
    ws = tracker.resolve_ws(workspace)
    base = os.path.join(ws, job_dirs.DIR_JOBS)
    names = []
    if os.path.isdir(base):
        names = [n for n in sorted(os.listdir(base))
                 if n and not n.startswith("_")
                 and os.path.isdir(os.path.join(base, n))]

    index = job_dirs.applications_by_key(ws, rows) if names else {}
    pool = []
    for name in names:
        job_dir = os.path.join(base, name)
        # 归属判定：链接读穿到工作区外的目录不当成岗位（与 web 的 inside 同原语）
        real = os.path.realpath(job_dir)
        if real != os.path.realpath(base) and not _within(real, os.path.realpath(base)):
            continue
        text = _read_card(ws, job_dir)
        card = parse_card(text)
        company, role = job_dirs.split_dir_name(name)
        display = basic_info(text) or (company, role)
        state = job_dirs.apply_state(index.get(tracker.dedup_key(company, role)))
        usable = bool(card and card["consistent"])
        pool.append({
            "dir": name,
            "company": company,
            "role": role,
            "displayCompany": display[0],
            "displayRole": display[1],
            "score": card["total"] if usable else None,
            "level": card["level"] if usable else None,
            "gate": card["hardGates"]["conclusion"] if card else None,
            "state": state,
            "applied": state != "未投递",
        })
    return pool
