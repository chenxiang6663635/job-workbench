---
name: track
description: Use when 用户要查看投递进度、更新面试进展、查询最近待办、按条件筛选投递记录、统计投递情况或生成投递漏斗看板时。
---

# 投递追踪表查改与看板

所有操作经由 `tools/tracker.py` 与 `tools/report.py`，**不要直接编辑 CSV**。

以下示例省略了 `--workspace`，默认使用 `personal/`。若用户的文件在其他目录，加上 `--workspace <目录>`。

## 常用操作

```
python tools/tracker.py list                      # 全部
python tools/tracker.py list --due-within 7       # 未来 7 天到期（最常用）
python tools/tracker.py list --stage 笔试         # 按阶段
python tools/tracker.py list --direction hvac     # 按方向
python tools/tracker.py list --batch 提前批       # 按批次
python tools/tracker.py list --company 华为       # 公司名模糊匹配
python tools/tracker.py show --id A001
python tools/tracker.py update --id A001 --stage 一面 --next "准备项目口述" --next-date 2026-09-10
python tools/tracker.py import --file 待导入.csv               # CSV 批量导入（写入前先出差异预览）
python tools/tracker.py import --file 待导入.csv --dry-run     # 只预览不写入
python tools/report.py                            # 生成 05_投递追踪/看板.md
python tools/report.py --stdout                   # 只打印不写文件
```

看板第六节「周期复盘」含**失败原因聚类**：按 `<工作区>/config/failure_keywords.txt`
（每行「类别=关键词1,关键词2」，改完重跑 report 即生效）把失败原因归成几类；
文件不存在时退化为按「状态原因」原文频次统计；失败记录少于 3 条时明确
「样本太少，暂不展示」——不要在数据不足时硬凑归因。

`list --due-within N` 按下次动作日期升序，已挂与已放弃排在最后。

## 阶段枚举

正常流转：`待投 → 已投 → 笔试 → 一面 → 二面 → 三面 → HR面 → offer → 签约`
终态：`已挂` / `已放弃`

## 面试记录

面试与岗位是一对多，存独立文件 `05_投递追踪/interviews.csv`（`面试id` 从 I001 起，`关联记录` 外键指回 tracker.csv），**不改主表结构**。记录面试会自动在主表时间线入账一条「面试」变更。

```
python tools/tracker.py interview add --app A001 --round 一面 --when "2026-09-08 14:00" --form 视频 --interviewer 张工 --questions "..." --answers "..." --retro "..."
python tools/tracker.py interview add --company 某内推公司 --role 热力仿真 --round 笔试   # 未投递的面试也可记录
python tools/tracker.py interview list                    # 时间倒序
python tools/tracker.py interview list --app A001         # 只看某岗位的面试
python tools/tracker.py interview show --id I001
python tools/tracker.py interview update --id I001 --result 通过 --retro "..."
```

- 轮次：笔试 / 一面 / 二面 / 三面 / HR面 / 终面 / 其他；形式：现场 / 视频 / 电话 / 其他；结果：待定 / 通过 / 未通过 / 取消
- 关联了记录时公司/岗位自动从主表带出，不必重复输入
- Web 端「进展」页可录入面试并导出 `.ics` 日程（提前 1 小时提醒）

## 字段约束

| 字段 | 取值 |
|---|---|
| 方向 | 与工作区 `config/directions/` 下的方向 ID 一致 |
| 批次 | 提前批 / 正式批 / 补录 |
| 来源 | 应届生求职网 / 牛客 / 企业校招官网 / 学校就业网 / 内推 / 其他 |
| 日期 | YYYY-MM-DD |
| 评分 | 0–100 整数 |

`update` 只能改阶段、下次动作、下次动作日期、截止日期、投递日期、备注、评分。**公司与岗位不可改**——需改则新建记录并将原记录标记为已放弃。

## 看板内容

`tools/report.py` 输出五部分：投递漏斗（含占比条）、按方向统计、按批次统计、近 7 天待办、已过截止日提醒。

## 输出要求

**不要原样复述脚本输出的表格。** 用自然语言说明：有几家在流程中、最近要处理什么、有没有异常（如已过截止日仍在待投）。
