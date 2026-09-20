---
allowed-tools: Bash(jobws bank:*), Bash(jobws apply:*)
description: 题库：查题与筛选、加题、从面试准备导入、删题与撤回（写入走两段式）
---

## 先摸清现状（只读）

- 题库概览：!`jobws bank list`
- 可按领域 / 科目 / 状态 / 关键词缩小范围（参数细节以 `jobws bank list --help` 为准）

## 你的任务

按用户意图走其中一条：

1. **查题 / 复习**：`jobws bank list --domain 技术面 --subject 算法 --status 未看 --keyword 动态规划`
   把命中的题目按「领域 → 科目」分组列出；用户要细节时再逐条展开答案要点。
2. **加一道题**（写入）：`jobws bank add --title "…" --domain … --subject … --answer "…"`
   该命令会**先给预览**（摘要 + 逐字段差异），把预览展示给用户，用户确认后
   `jobws apply <token>` 落盘。
3. **从面试准备导入**（写入）：`jobws bank import --module-dir 03_面试准备`
   同样先预览逐条差异（含跳过的坏文件），展示给用户，确认后 `jobws apply <token>`。
4. **删题 / 撤回导入**（写入）：`jobws bank delete --id Q012` 删单题；
   `jobws bank delete --origin 导入 --today` 批量撤回**今天导入的那批**（也可按
   `--domain` / `--subject` / `--keyword` / `--company` 组合）。`--id` 与筛选条件
   互斥；同样先预览"将删哪几行"，确认后 `jobws apply <token>`。

## 红线

- 写入一律两段式：`bank add` / `bank import` / `bank delete` 只给预览与令牌，
  落盘只能走 `jobws apply`。不要直接改 `05_投递追踪/questions.csv`。
- `bank delete` 落盘前会把**整表快照**写到工作区之外，确切路径由 `jobws apply` 打印
  （默认 `<快照根>/<工作区名>/question-deletes/questions-before-delete-<时间戳>.csv`）；
  **恢复 = 回到删除前一刻的整表状态**：把那份 CSV 复制回 `05_投递追踪/questions.csv`
  （删除之后的其它改动会一并被冲掉，先另存）。删错的兜底是这份快照，不是"再导入一遍"。
- `bank delete` 落盘前还会**核对行指纹**（`题目id` + 题目 + 领域 + 科目 + 创建日期）：
  题目 id 会被复用（编号 = max+1），只按 id 匹配会出现"预览删 A、落盘删 B"——指纹不符
  就整体拒绝、要求重新预览。CSV 里有重复 id 时预览阶段就拒绝（一次删除会带走多行）。
- `--module-dir` 只能是**工作区内的相对目录**（绝对路径或含 `..` 会被拒绝）。
- 参数细节以 `jobws bank --help` 为准；不要凭空编造参数名。
