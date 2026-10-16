# -*- coding: utf-8 -*-
"""岗位目录下两个正文文件（解析卡 / JD 原文）的读取、存在性与解析。

2026-10-16 从 `tools_readonly` 搬出（同 `dashboard_sections.py` 2026-10-09 的处置）。

为什么独立成模块：`tools_readonly.py` 是登记过的水位文件（只许变小），而本批要给
卡片读取补**三级归属防护 + 字节上限**、并把「展示名与评分各读一次」的读放大收成
一次读——这些逻辑塞进原文件只会抬水位（`dashboard_sections.py` 同款处置：只搬不改
行为，2026-10-09）。

三条口径（与 `web/backend/routers/jobs.py` 同源，改动必须两边一起看）：
- **读**只走 `paths.read_in_workspace`：realpath 归属（岗位池根 / 岗位子目录 /
  `解析卡.md` 文件本身的链接读穿都拦下）+ 字节上限（`limits.MAX_CARD_BYTES`）；
- **解析**函数收「已读到的正文」而不是路径（与 Web 的 `_parse_card(..., text=)` 同款）
  ——这样调用方读一次就能喂给两个解析器；
- 「基本信息」给的是**展示名**（卡片优先、读不到回退目录名切分），关联键一律用目录名
  （见 `tools_readonly.list_jobs`）。
"""

import re

from . import paths
from .limits import MAX_CARD_BYTES
from .paths import DIR_JOBS

# 领域层 import 必须排在 `paths` 之后：它在导入期求值 `ROOT`，而应用根由
# `paths` 在导入期注入（同 `tools_readonly.py` 顶部那条注释）。
from jobws_core import jd_score  # noqa: E402

# 解析卡 / JD 原文的文件名（`resources.read_job_text` 与 `tools_readonly` 共用同源常量）
CARD_FILE = "解析卡.md"
JD_FILE = "JD原文.md"


def read(workspace, job_name):
    """读岗位目录下的解析卡：**归属校验 + 字节上限**的单一入口，读不到返回 None。

    三条缺口在这里收口（2026-10-16 外部审计 P1-A / P2-A）：此前是自持的 `_read_text`
    ——无 realpath 归属（岗位目录 / 卡片被掉包成指向工作区外的链接就直读出去）、
    无界 `read()`、且为展示名与评分各读一次。
    """
    return paths.read_in_workspace(workspace, DIR_JOBS, job_name, CARD_FILE,
                                   max_bytes=MAX_CARD_BYTES)


def has_card(workspace, job_name):
    """工作区内是否真的有这张卡（`有解析卡` 字段的取值口径）。

    不能直接用 `os.path.isfile`：它**跟随链接**——岗位目录是 junction 时，
    `有解析卡` 会正判定出一个工作区外文件，而这个布尔本身就是泄漏。
    """
    return paths.exists_in_workspace(workspace, DIR_JOBS, job_name, CARD_FILE)


def has_jd(workspace, job_name):
    """工作区内是否真的有 JD 原文（`有JD原文` 字段的取值口径，同 `has_card`）。"""
    return paths.exists_in_workspace(workspace, DIR_JOBS, job_name, JD_FILE)


def basic_info(card):
    """解析卡「基本信息」段的公司/岗位；没填、缺该段或读不到时返回 None。

    与 `routers/jobs.py:140` 同口径。入参是**已读到的正文**：归属与上限在读取处判掉，
    本函数只管解析。
    """
    if not card:
        return None
    seg = re.search(r"^##\s*基本信息\s*$(.*?)(?=^##\s|\Z)", card, re.M | re.S)
    if not seg:
        return None
    values = {}
    for key in ("公司", "岗位"):
        m = re.search(r"^%s\s*[:：]\s*(.*)$" % key, seg.group(1), re.M)
        values[key] = (m.group(1).strip() if m else "")
    if not values["公司"] or not values["岗位"]:
        return None
    return values["公司"], values["岗位"]


def score(card):
    """解析卡的总分与结论，与 `routers/jobs.py` 的 `_parse_card` 同口径。

    关键一致点：**四维之和必须等于总分**才给档位（level / action）——解析卡是
    渐进填写的，填到一半时给一个算错的分档比不给更糟。总分照常返回，由
    `consistent` 标明是否自洽（后端同样处理）。
    """
    if not card:
        return None
    fields = jd_score.parse_score_section(card)
    if not fields:
        return None
    dims, ok = [], True
    for name, maximum in jd_score.DIMENSIONS:
        num, errs = jd_score.parse_dimension(fields.get(name, ""), name, maximum)
        if errs or num is None:
            ok = False
            break
        dims.append(num)
    try:
        total = float((fields.get("总分") or "").strip())
    except (TypeError, ValueError):
        total = None
        ok = False
    level = action = None
    if ok and total is not None and abs(sum(dims) - total) < 1e-6:
        level, action = jd_score.verdict(total)
    else:
        ok = False
    return {"total": total, "level": level, "action": action, "consistent": ok}
