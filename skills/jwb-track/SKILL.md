---
name: jwb-track
description: Use when 用户要查看投递进度、更新面试进展、查询最近待办、按条件筛选投递记录、统计投递情况或生成投递漏斗看板时。English triggers：application tracker, interview progress, pending to-dos, filter applications, application statistics, funnel dashboard.
compatibility: Python 3.12+；jobws 指仓库内的 python tools/jobws.py（在仓库根运行）；工作区已初始化；全本地运行，不上传工作区数据。
license: MIT
metadata:
  version: 26.9.15
allowed-tools: Bash(jobws:*)
---

# 投递追踪表查改与看板

所有操作经由 `jobws track` 与 `jobws report`，**不要直接编辑 CSV**。

以下示例省略了 `--workspace`，默认使用 `personal/`。若用户的文件在其他目录，加上 `--workspace <目录>`。

## 常用操作

```
jobws track list                      # 全部
jobws track list --due-within 7       # 未来 7 天到期（最常用）
jobws track list --stage 笔试         # 按阶段
jobws track list --direction hvac     # 按方向
jobws track list --batch 提前批       # 按批次
jobws track list --company 华为       # 公司名模糊匹配
jobws track show --id A001
jobws track update --id A001 --stage 一面 --next "准备项目口述" --next-date 2026-09-10
jobws track import --file 待导入.csv               # CSV 批量导入（写入前先出差异预览）
jobws track import --file 待导入.csv --dry-run     # 只预览不写入
jobws report                            # 生成 05_投递追踪/看板.md
jobws report --stdout                   # 只打印不写文件
```

看板第六节「周期复盘」含**失败原因聚类**：按 `<工作区>/config/failure_keywords.txt`
（每行「类别=关键词1,关键词2」，改完重跑 report 即生效）把失败原因归成几类；
文件不存在时退化为按「状态原因」原文频次统计；失败记录少于 3 条时明确
:「样本太少，暂不展示」——不要在数据不足时硬凑归因。

`list --due-within N` 按下次动作日期升序，已挂与已放弃排在最后。

## 阶段枚举

正常流转：`待投 → 已投 → 测评 → 笔试 → AI面 → 群面 → 一面 → 二面 → 三面 → HR面 → 终面 → offer → 签约`
终态：`已挂` / `已放弃` / `我拒绝的 offer`

顺序即流转优先级：粘贴邮件解析时只有「更强」的阶段才建议覆盖当前值。
「测评」是投递后的在线测评/性格测试；「AI面 / 群面」在真人单面之前。

## 从属表（面试 / 宣讲会 / 邮件 / 题库）

四张从属表的命令、字段与 Web 入口见 `references/records.md`——它们与主表的关系是
「`关联记录` 外键 + 不改主表结构」，且**都不推进阶段**（阶段一律人工确认）。

## 字段约束

| 字段 | 取值 |
|---|---|
| 方向 | 与工作区 `config/directions/` 下的方向 ID 一致 |
| 批次 | 提前批 / 正式批 / 补录 |
| 来源 | 应届生求职网 / 牛客 / 企业校招官网 / 学校就业网 / 内推 / 宣讲会 / 招聘会 / 其他 |
| 链接 | 岗位页原始 URL（`add --link` / `update --link`，可空） |
| 日期 | YYYY-MM-DD |
| 评分 | 0–100 整数 |

`update` 只能改阶段、状态原因、下次动作、下次动作日期、截止日期、投递日期、备注、评分、链接。**公司与岗位不可改**——需改则新建记录并将原记录标记为已放弃。

`track check` 的自检范围含各表的枚举取值（投递表的「来源」、题库的状态 / 来源 / 难度……）：手改 CSV 填了枚举外的值会在自检里被点名。

## 看板内容

`jobws report` 输出六部分：投递漏斗（含占比条）、按方向统计、按批次统计、近 7 天待办、已过截止日提醒、周期复盘（转化率 / 停留 / 失败归因与聚类）。

## 输出要求

**不要原样复述脚本输出的表格。** 用自然语言说明：有几家在流程中、最近要处理什么、有没有异常（如已过截止日仍在待投）。
