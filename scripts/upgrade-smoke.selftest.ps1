<#
.SYNOPSIS
  D′-1 脚本自检（**不安装、不启动、不联网**）。

.DESCRIPTION
  只做两件事：
    1. 静态契约检查：脚本与 workflow 的关键模式是否存在（配合 actionlint）
    2. 纯函数行为测试：哈希计算、JSON 往返、路径规范化

  用途：在真正执行安装冒烟前，先证明"脚本本身没有明显退化"。
  它**不能**替代真实安装验收。

.EXAMPLE
  ./upgrade-smoke.selftest.ps1
#>
[CmdletBinding()]
param(
  [string] $ScriptPath   = (Join-Path $PSScriptRoot 'upgrade-smoke.ps1'),
  [string] $WorkflowPath = ''
)

# 两种布局都要支持：
#   仓库：scripts/upgrade-smoke.ps1 + .github/workflows/upgrade-smoke.yml
#   草案目录：三份文件同目录
if ([string]::IsNullOrWhiteSpace($WorkflowPath)) {
  $repoCandidate = Join-Path (Split-Path $PSScriptRoot -Parent) '.github/workflows/upgrade-smoke.yml'
  $WorkflowPath = if (Test-Path -LiteralPath $repoCandidate) { $repoCandidate }
                  else { Join-Path $PSScriptRoot 'upgrade-smoke.yml' }
}

Set-StrictMode -Version 2.0
$ErrorActionPreference = 'Stop'

$failed = 0
function Check([string] $name, [bool] $ok, [string] $detail = '') {
  if ($ok) { Write-Host "  [ok  ] $name" -ForegroundColor Green }
  else {
    Write-Host "  [FAIL] $name — $detail" -ForegroundColor Red
    $script:failed++
  }
}

Write-Host "`n== 1. 文件与语法" -ForegroundColor Cyan
Check 'upgrade-smoke.ps1 存在' (Test-Path -LiteralPath $ScriptPath) $ScriptPath
Check 'upgrade-smoke.yml 存在' (Test-Path -LiteralPath $WorkflowPath) $WorkflowPath

if (-not (Test-Path -LiteralPath $ScriptPath) -or -not (Test-Path -LiteralPath $WorkflowPath)) {
  Write-Host "`n缺少文件，终止" -ForegroundColor Red
  exit 1
}

$scriptText   = Get-Content -LiteralPath $ScriptPath -Raw -Encoding utf8
$workflowText = Get-Content -LiteralPath $WorkflowPath -Raw -Encoding utf8

$errs = $null
$null = [System.Management.Automation.PSParser]::Tokenize($scriptText, [ref]$errs)
Check 'PowerShell 语法解析' (@($errs).Count -eq 0) "errors=$(@($errs).Count)"

Write-Host "`n== 2. 脚本关键契约" -ForegroundColor Cyan
Check '卸载使用 _?=（不是 ?=）' ($scriptText.Contains('_?=')) 'NSIS 要求 _?='
Check '升级调用不带 /D=' ($scriptText.Contains('Invoke-Installer $NewExe @()')) '带 /D= 会掩盖位置恢复缺陷'
Check '前置 fail-closed 拒绝运行' ($scriptText.Contains('拒绝运行')) ''
Check '含 8765 空闲前置' ($scriptText.Contains("'PF-1'")) ''
Check '含端口归属断言' ($scriptText.Contains("'RT-5'")) ''
Check '含 RT-8a' ($scriptText.Contains("'RT-8a-")) ''
Check '含 RT-8b' ($scriptText.Contains("'RT-8b-")) ''
Check '含 RT-8c' ($scriptText.Contains("'RT-8c-")) ''

# --- BLOCKER 回归检查（AUDIT-v2 修复后必须持续成立）---
Check 'B-1 快照名取自 backup.path' ($scriptText.Contains('Split-Path -Leaf ([string]$b.path)')) 'backup 返回无 name 字段'
Check 'B-2 不用 /content 的 text 字段' (-not ($scriptText -match '\$(?:content|c2)\.text\b')) '/content 返回字段是 content'
Check 'B-3 种子写入 workspace' ($scriptText.Contains('$wsPath')) 'dataRoot 是 personal 的父目录'
Check 'B-3 断言 workspace 层级' ($scriptText.Contains("'SE-2b'") -and $scriptText.Contains("'RT-8a-1b'")) '须区分 dataRoot 与 workspace'

# --- MAJOR 修复回归检查 ---
Check 'M-1 用 .NET 无 BOM 写入' ($scriptText.Contains('UTF8Encoding]::new($false)')) ''
Check 'M-2 换行规范化比对' ($scriptText.Contains('Normalize-Text')) ''
Check 'M-4 健康检查只等一次' (-not $scriptText.Contains('Wait-Health $BackendPort 5')) ''
Check 'M-5 gaps 参与裁决' ($scriptText.Contains('PASS_WITH_GAPS')) ''
Check '收据在 finally 中生成' ($scriptText -match 'finally\s*\{[\s\S]*收据') '失败路径也要留证'
Check '含 known_gaps 登记' ($scriptText.Contains('known_gaps')) ''
Check '脚本无本机硬编码路径' (-not $scriptText.Contains('C:\Users\cx\g2g3-build')) '不应引用本机路径'

Write-Host "`n== 3. Workflow 关键契约" -ForegroundColor Cyan
Check '授予 actions: read' ($workflowText -match '(?m)^\s*actions:\s*read') '跨 run 下载 artifact 必需'
Check '授予 contents: read' ($workflowText -match '(?m)^\s*contents:\s*read') ''
Check '下载使用固定 run-id（显式 --repo）' ($workflowText -match 'gh run download \$runId --repo \$repo') ''
Check '声明失败不得改用其他 run' ($workflowText.Contains('不得改用其他 run')) ''
Check '收据上传 if: always()' ($workflowText -match 'if:\s*always\(\)[\s\S]{0,200}upload-artifact') ''
Check '含 actionlint 步骤' ($workflowText.Contains('actionlint')) ''
Check '含脚本自检步骤' ($workflowText.Contains('upgrade-smoke.selftest.ps1')) ''
Check '有 timeout-minutes' ($workflowText -match 'timeout-minutes') ''
Check 'B-4 PR 也触发 lint' ($workflowText -match '(?m)^\s*pull_request:') '否则「CI 会检查」不成立'
Check 'B-4 真机 job 仅手动触发' ($workflowText -match "if:\s*github\.event_name == 'workflow_dispatch'") ''

Write-Host "`n== 4. 纯函数行为（不安装）" -ForegroundColor Cyan
$tmp = Join-Path ([System.IO.Path]::GetTempPath()) ("jw-selftest-" + [guid]::NewGuid().ToString('N'))
New-Item -ItemType Directory -Force -Path $tmp | Out-Null
try {
  $f = Join-Path $tmp 'sample.bin'
  [System.IO.File]::WriteAllBytes($f, [byte[]](1..32 | ForEach-Object { $_ }))
  $a = (Get-FileHash -LiteralPath $f -Algorithm SHA256).Hash.ToLowerInvariant()
  $b = (Get-FileHash -LiteralPath $f -Algorithm SHA256).Hash.ToLowerInvariant()
  Check 'SHA256 可重复' ($a -eq $b -and $a.Length -eq 64) $a

  $obj = [ordered]@{ kind = 'dprime-1'; rows = @([pscustomobject]@{ id = 'X'; status = 'PASS' }); summary = [ordered]@{ total = 1; passed = 1; failed = 0 } }
  $json = $obj | ConvertTo-Json -Depth 6
  $back = $json | ConvertFrom-Json
  Check 'JSON 往返保真' ($back.kind -eq 'dprime-1' -and $back.rows[0].status -eq 'PASS') ''

  $p1 = [System.IO.Path]::GetFullPath((Join-Path $tmp 'a/../b'))
  Check '路径规范化可用' ($p1 -match 'b$') $p1
} finally {
  Remove-Item -LiteralPath $tmp -Recurse -Force -ErrorAction SilentlyContinue
}

Write-Host ''
if ($failed -gt 0) {
  Write-Host "自检失败：$failed 项" -ForegroundColor Red
  exit 1
}
Write-Host '自检通过：静态契约与纯函数行为均符合预期（不代表安装验收已通过）' -ForegroundColor Green
exit 0
