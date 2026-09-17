---
allowed-tools: Bash(jobws track interview list:*), Bash(jobws report --stdout:*)
description: 面试复盘：汇总面试记录 → 表现要点与改进项（只读）
---

## 数据来源

- 面试记录（轮次 / 形式 / 问题 / 自评）：!`jobws track interview list`
- 阶段时间线与停留时长：!`jobws report --stdout`

## 你的任务

按三段式输出（**只读，不要写任何文件**）：

1. **事实摘要**：面了哪些场、每场的轮次与形式、时间线。
2. **暴露的问题**：反复被问到但答不好的方向、阶段停留异常的记录。
3. **改进项**：下一次面试前可执行的具体动作（每个问题配一条）。

要落盘复盘结论文本时，先给用户看，再走工作区的两段式写入。
