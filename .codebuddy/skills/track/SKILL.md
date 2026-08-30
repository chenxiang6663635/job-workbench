---
name: track
description: Use when 用户要查看投递进度、更新面试进展、查询最近待办、按条件筛选投递记录、统计投递情况或生成投递漏斗看板时。
---

# 投递追踪表查改与看板

所有操作经由 `tools/tracker.py` 与 `tools/report.py`，**不要直接编辑 CSV**。

## 常用操作

```
python tools/tracker.py list                      # 全部
python tools/tracker.py list --due-within 7       # 未来 7 天到期（最常用）
python tools/tracker.py list --stage 笔试         # 按阶段
python tools/tracker.py list --direction datacenter
python tools/tracker.py list --batch 提前批
python tools/tracker.py list --company 华为       # 公司名模糊匹配
python tools/tracker.py show --id A001
python tools/tracker.py update --id A001 --stage 一面 --next "准备项目二口述" --next-date 2026-09-10
python tools/report.py                            # 生成 05_投递追踪/看板.md
python tools/report.py --stdout                   # 只打印不写文件
```

`list --due-within N` 按下次动作日期升序，已挂与已放弃排在最后。

## 阶段枚举

正常流转：`待投 → 已投 → 笔试 → 一面 → 二面 → 三面 → HR面 → offer → 签约`
终态：`已挂` / `已放弃`

## 字段约束

| 字段 | 取值 |
|---|---|
| 方向 | datacenter / hvac / other |
| 批次 | 提前批 / 正式批 / 补录 |
| 来源 | 应届生求职网 / 牛客 / 企业校招官网 / 学校就业网 / 内推 / 其他 |
| 日期 | YYYY-MM-DD |
| 评分 | 0–100 整数 |

`update` 只能改阶段、下次动作、下次动作日期、截止日期、投递日期、备注、评分。**公司与岗位不可改**——需改则新建记录并将原记录标记为已放弃。

## 看板内容

`tools/report.py` 输出五部分：投递漏斗（含占比条）、按方向统计、按批次统计、近 7 天待办、已过截止日提醒。

## 输出要求

**不要原样复述脚本输出的表格。** 用自然语言说明：有几家在流程中、最近要处理什么、有没有异常（如已过截止日仍在待投）。
