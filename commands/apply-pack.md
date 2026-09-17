---
allowed-tools: Bash(jobws jd:*), Bash(jobws resume:*), Bash(jobws track add --preview:*), Bash(jobws apply:*)
description: 投递包：按 JD 调整简历 → 归档 → 记入追踪表（写入走两段式）
---

## 流程（技能 `jwb-apply` 是完整准则，按其执行）

1. **评估匹配度（只读）**：`jobws jd <岗位目录>/解析卡.md --gap --resume <简历版本>`
2. **生成简历 PDF**：`jobws resume --version <版本名> --out <输出目录>`
   （版式与占位符约定见技能 `jwb-resume`；参数细节以 `jobws resume --help` 为准）
3. **准备投递记录（先预览）**：`jobws track add --company … --role … --preview`
4. **展示 → 确认 → 落盘**：把预览的 diff 给用户看，用户点头后才 `jobws apply <token>`

## 红线

- 落盘一律两段式（preview → 用户确认 → apply），不要跳步、不要绕过令牌直接改 CSV。
- 归档目录遵循工作区既有约定（`01_岗位池/<公司>-<岗位>/`），不要另起结构。
