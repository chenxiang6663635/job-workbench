---
allowed-tools: Bash(jobws report --stdout:*), Bash(jobws track list:*)
description: 今日待办：从看板摘要挑出今天该做的事（只读）
---

## 今天的待办来源

- 近七天待办与逾期未投：!`jobws track list --due-within 7`
- 看板摘要（漏斗 / 静默提醒 / 转化率）：!`jobws report --stdout`

## 你的任务

1. 从上面输出里挑出**今天该做**的事（最多 5 条）：截止日已过的排最前，
   其次是静默提醒（阶段停留过久）。
2. 每条给出：动作 + 对象（公司 / 岗位）+ 时限。
3. 不要复述无关统计；**不要写任何文件**——要落盘请走 `jobws` 的两段式
   （`--preview` 拿令牌 → 用户确认 → `jobws apply <token>`）。
