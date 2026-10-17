# -*- coding: utf-8 -*-
"""筛选校准（E 批，2026-10-16）：把先验的评分筛法与后验的投递结局接起来。

要回答的问题只有一句（设计文档 §一）：*我按评分筛的这一套，测出来的结果支持它吗？*
它**不**回答「该不该海投」，也**不**替用户放宽阈值（§四 反目标）。

三个输出（§二）：
① 按评分档位的转化率——**分母 = 该档位里「投过」的岗位数**（不是全部岗位数：
    把没投的算进去，等于把「我筛掉了它」混进「它转化好不好」）；
② 未投递岗位的记账（只读）——数量与构成（硬门槛合格但没投 / 不合格 / 未评分）；
③ 节点复盘的人话结论——一律「数据显示 + 可能」，**不写祈使句**。

本模块只读：不写配置、不写 tracker、不生成投递动作（§八.4 用工作树逐字节快照钉死）。
岗位池的读取与解析卡合成在 `job_pool`（读/算分离）；档位判定走 `jd_score.verdict`
（边界只有一处定义），样本下限沿用 `report.MIN_CLUSTER_SAMPLES`（不新造数字），
阶段转化口径直接复用 `report.retrospective`（不另写「什么叫通过」）。
"""

from __future__ import print_function

from . import jd_score  # noqa: E402  （档位判定唯一实现）
from . import job_dirs  # noqa: E402  （apply_state：未投递的三态口径）
from . import job_pool  # noqa: E402  （岗位池快照：读/算分离）
from . import report  # noqa: E402  （阶段语义与转化口径的唯一实现）
from . import tracker  # noqa: E402  （read_history：时间线）

# 样本下限：与失败聚类同一个数、同一种理由——样本太少时给百分比比不给更害人
MIN_SAMPLES = report.MIN_CLUSTER_SAMPLES

# 结论句的比较基准：`已投` 档的转化率 = 投出去之后有没有回响
# （设计文档 §三 只借用既有阶段枚举，不新造「通过」的定义）
REPLY_STAGE = "已投"
# 「没有可见差异」的判定带宽（百分点）。刻意宽松：宁可说「可能偏紧」，
# 也不把 3 个百分点的抖动说成「高分档更好」。
NEAR_PCT = 10


def calibrate(rows, job_pool_snapshot, history_rows, today, workspace=None):
    """筛选校准的三个输出 + 已知取舍说明（**纯计算**，不做任何 IO）。

    `rows`：追踪表行（① 的人口与「评分」列的来源）；
    `job_pool_snapshot`：`job_pool.load_job_pool` 的快照（② 的构成来源）；
    `history_rows`：时间线行（转化率按「到达过」而非「当前存量」）；
    `today` / `workspace`：转发给 `report.retrospective`（停留与聚类用）。
    """
    tiers = []
    for low, high, level, action in jd_score.THRESHOLDS:
        bucket = [r for r in rows if _tier_of_row(r) == level]
        entry = {
            "tier": level,
            "range": [low, high],
            "action": action,
            # 分母 = 该档位里投过的岗位数（E-01）
            "applied": len(bucket),
            "shown": False,
            "noteCode": None,
            "noteParams": {},
            "conversion": [],
        }
        if len(bucket) >= MIN_SAMPLES:
            ids = set((r.get("id") or "").strip() for r in bucket)
            scoped = [h for h in (history_rows or [])
                      if (h.get("id") or "").strip() in ids]
            # 口径只有一份：直接复用 report 的阶段转化（不另写「什么叫通过」）
            entry["shown"] = True
            entry["conversion"] = report.retrospective(
                bucket, scoped, today, workspace)["conversion"]
        else:
            entry["noteCode"] = "too_few_samples"
            entry["noteParams"] = {"total": len(bucket), "min": MIN_SAMPLES}
        tiers.append(entry)

    return {
        "tiers": tiers,
        "unapplied": _unapplied(job_pool_snapshot),
        "conclusion": _conclusion(tiers),
        "notes": _notes(),
    }


def calibration_section(rows, today, workspace=None):
    """看板第七节（CLI 专用入口）：取数 + 校准 + 渲染成 Markdown 行列表。

    API 侧走 `calibrate`（自己渲染 JSON）；两端共用同一次读取与同一份数字。
    """
    pool = job_pool.load_job_pool(workspace, rows)
    data = calibrate(rows, pool, tracker.read_history(workspace), today, workspace)
    return render_markdown(data).splitlines()


def calibration_data(rows, today, workspace=None):
    """取数 + 校准（API / MCP 入口）：返回结构化 dict，呈现交给各端自己。

    与 CLI 的 `calibration_section` 共用同一次读取与同一份数字——四端同源
    （设计文档 §八.5）靠的是这一个是同一个函数，而不是三处各写一遍。

    时间线**按 workspace 显式读**：不读全局工作区（Web 层并发下全局不可靠，
    这正是 `dashboard.py` 里同一行注释守的事——四端同源也包括"读哪一份"）。
    """
    pool = job_pool.load_job_pool(workspace, rows)
    return calibrate(rows, pool, tracker.read_history(workspace), today, workspace)


def _tier_of_row(row):
    """追踪表行的评分 → 档位名；空 / 不可解析 → None（未评分，不进任何档）。"""
    raw = (row.get("评分") or "").strip()
    if not raw:
        return None
    try:
        total = float(raw)
    except (TypeError, ValueError):
        return None
    return jd_score.verdict(total)[0]


def _unapplied(job_pool_snapshot):
    """② 未投递岗位的记账：数量 + 构成（四类互斥，优先级 documented）。"""
    buckets = {"unscored": 0, "gatePassed": 0, "gateFailed": 0, "gatePending": 0}
    total = 0
    for item in job_pool_snapshot or []:
        if item.get("applied"):
            continue
        total += 1
        # 优先级：未评分 > 硬门槛结论。卡片半填（拿不到一致总分）算未评分——
        # 它给不出可用档位，硬门槛再完整也无从比较。
        if item.get("score") is None:
            buckets["unscored"] += 1
        elif item.get("gate") == "通过":
            buckets["gatePassed"] += 1
        elif item.get("gate") == "不通过":
            buckets["gateFailed"] += 1
        else:
            buckets["gatePending"] += 1
    out = {"total": total}
    out.update(buckets)
    return out


def _conclusion(tiers):
    """③ 一句结论：一律「数据显示 + 可能」；可比较档位不足时明说样本不足。"""
    basis = []
    for tier in tiers:
        if not tier["shown"]:
            continue
        rate = None
        for conv in tier["conversion"]:
            if conv["stage"] == REPLY_STAGE:
                rate = conv["rate"]
                break
        if rate is not None:
            basis.append({"tier": tier["tier"], "rate": rate,
                          "applied": tier["applied"]})

    if len(basis) < 2:
        return {
            "text": "样本不足：至少两个档位各有 %d 条投递记录才能比较筛法"
                    "（当前 %d 个档位可比较）。" % (MIN_SAMPLES, len(basis)),
            "basis": [],
        }

    hi, lo = basis[0], basis[-1]
    if abs(hi["rate"] - lo["rate"]) <= NEAR_PCT:
        text = ("数据显示：你的 %s 档与 %s 档的投后回响率没有可见差异"
                "（%d%% 对 %d%%，样本各 %d / %d 条）——先评分再投这一套可能偏紧。"
                % (hi["tier"], lo["tier"], hi["rate"], lo["rate"],
                   hi["applied"], lo["applied"]))
    else:
        text = ("数据显示：%s 档的投后回响率 %d%% 高于 %s 档的 %d%%"
                "（样本各 %d / %d 条）——先评分再投这一套测出来是有效果的。"
                % (hi["tier"], hi["rate"], lo["tier"], lo["rate"],
                   hi["applied"], lo["applied"]))
    return {"text": text, "basis": basis}


def _notes():
    """已知取舍（设计文档 §五）：必须随输出给出，不能装作精确。"""
    return [
        "匹配键是目录名首个下划线拆分：公司名自带下划线时会误判「未投递」"
        "（宁可显示未投递，也不猜）。",
        "两套评分互不校验：追踪表「评分」列与解析卡总分各自独立填写，"
        "本特性按追踪表列 join（要 join 的是投递记录）。",
        "「放掉」这个动作没有数据落点：未投递记账只给得出规模与构成，"
        "给不出当时为什么放——要可解释需新增写入口，本批不做。",
    ]


def render_markdown(data):
    """校准结果 → Markdown 小节（CLI 看板第七节；API 前端另渲染，不共用文本）。

    呈现与数据同模块：CLI / MCP / API 三端对同一份数据必须给出同一组数字，
    各自拼文本就会漂移。**不写祈使句**（§四.2）——替用户下判断就是越界。
    """
    out = [
        "## 七、筛选校准", "",
        "> 本节回答一个问题：*我按评分筛的这一套，测出来的结果支持它吗？*", "",
        "### 按评分档位的转化率", "",
        "| 档位 | 投过（分母） | 样本 | 投后回响率 |",
        "|---|---:|---|---:|",
    ]
    for tier in data["tiers"]:
        if not tier["shown"]:
            out.append("| %s | %d | 不足 %d 条，不展示 | — |"
                       % (tier["tier"], tier["applied"], tier["noteParams"]["min"]))
            continue
        rate = "—"
        for conv in tier["conversion"]:
            if conv["stage"] == REPLY_STAGE:
                rate = "%d%%" % conv["rate"] if conv["rate"] is not None else "—"
                break
        out.append("| %s | %d | %d 条 | %s |"
                   % (tier["tier"], tier["applied"], tier["applied"], rate))
    out += ["", "分母 = 该档位里**投过**的岗位数（没投的不算——由下面的记账回答）。", ""]

    un = data["unapplied"]
    out += ["### 未投递岗位的记账", "", "| 构成 | 数量 |", "|---|---:|",
            "| 合计 | %d |" % un["total"],
            "| 硬门槛合格但没投 | %d |" % un["gatePassed"],
            "| 硬门槛不合格 | %d |" % un["gateFailed"],
            "| 硬门槛待确认 | %d |" % un["gatePending"],
            "| 未评分（含半填卡） | %d |" % un["unscored"], ""]

    out += ["### 结论", "", data["conclusion"]["text"], "",
            "### 已知取舍", ""]
    out += ["- %s" % note for note in data["notes"]]
    out.append("")
    return "\n".join(out)
