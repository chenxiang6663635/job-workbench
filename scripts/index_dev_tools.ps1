# 一键为本仓库建立开发辅助工具的代码索引（GitNexus + CodeGraph）
#
# 这些工具是开发期辅助（理解代码结构 / 影响面分析），索引目录是运行时产物，
# 已在 .gitignore 排除，clone 或换机后跑本脚本重建即可。
#
# 用法：powershell -ExecutionPolicy Bypass -File scripts/index_dev_tools.ps1
#
# 依赖（全局安装）：
#   npm i -g gitnexus @colbymchenry/codegraph
# MCP 声明见 .codebuddy/mcp.example.json（需复制到 ~/.codebuddy/mcp.json 并填各自环境）。

$ErrorActionPreference = "Stop"
$root = Split-Path -Parent $PSScriptRoot   # scripts/ 的上级 = 仓库根
Set-Location $root

Write-Host "== GitNexus 索引（analyze）=="
if (-not (Get-Command gitnexus -ErrorAction SilentlyContinue)) {
    Write-Host "未找到 gitnexus，跳过（先 npm i -g gitnexus）"
} else {
    # --index-only 只建索引，不注入 AGENTS.md/CLAUDE.md/skills，避免污染本仓库约定
    gitnexus analyze . --index-only
    Write-Host "已索引。MCP 侧 gitnexus list 应出现 autumn-recruit-workbench。"
}

Write-Host "`n== CodeGraph 索引（init）=="
if (-not (Get-Command codegraph -ErrorAction SilentlyContinue)) {
    Write-Host "未找到 codegraph，跳过（先 npm i -g @colbymchenry/codegraph）"
} else {
    # init 幂等：已有 .codegraph/ 时会复用；损坏可用 codegraph index 重建
    codegraph init
    Write-Host "已索引。codegraph status 可查看统计。"
}

Write-Host "`n== 完成。两个索引目录（.gitnexus/ .codegraph/）已被 .gitignore 排除，不进版本管理 =="
