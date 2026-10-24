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
Check 'Listeners 返回用逗号包数组' ($scriptText.Contains('return ,@(Get-NetTCPConnection')) '空数组被函数返回展开成 $null，.Count 会抛错'

# --- 真机 run 39904842099 暴露的三处 ---
Check '注册表键按 DisplayName 定位' ($scriptText.Contains('function Find-UninstallKey') -and -not $scriptText.Contains("Uninstall\{`$AppId}")) '写死 appId 会读不到 GUID 键'
Check '数据根预建 workspace 目录' ($scriptText.Contains('Join-Path $wsDir $Workspace')) 'v26.10.0 无 #357 自动初始化，缺目录会 404'
Check '位置恢复有非空保护' ($scriptText.Contains('位置恢复无法验证')) 'before/after 都为空时 -ceq 为真 → 假阳性'

# --- 第 4 次真机 run 39909147773 暴露：删字段时漏改引用 ---
Check '不引用已删除的 $before.InstDir' (-not $scriptText.Contains('$before.InstDir')) 'StrictMode 下哈希缺键会抛 property cannot be found'

# --- 第 5 次真机 run 39910385167 暴露：文件名/目录名假设错 ---
Check '卸载器按 Uninstall*.exe 定位' ($scriptText.Contains("Filter 'Uninstall*.exe'")) 'electron-builder 用 Uninstall <ProductName>.exe'
Check '日志措辞不作业强制判据' (-not $scriptText.Contains("Record 'RT-6'")) 'RT-5（监听者进程路径）已提供更强证据'

# --- 第八轮审计四项（P0-1/P0-2/P1-2 + PDF）---
Check 'P0-1 有失败注入开关' ($scriptText.Contains('$FailInjection')) ''
Check 'P0-1 exit 在 finally 内' ($scriptText -match '(?s)finally.*exit \$script:ExitCode') 'return 会跳过 finally 之后的 exit'
Check 'P0-2 收据缺失使 job 失败' ($workflowText.Contains('if-no-files-found: error')) ''
Check 'P1-2 有默认 /S 卸载用例' ($scriptText.Contains("'UN5-1'")) ''
Check 'PDF 提取用例存在（不调模型）' ($scriptText.Contains("'RT-9-1'") -and $scriptText.Contains('127.0.0.1:1')) '用错误码区分抽取与模型阶段'
Check '含端口归属断言' ($scriptText.Contains("'RT-5'")) ''
Check '含 RT-8a' ($scriptText.Contains("'RT-8a-")) ''
Check '含 RT-8b' ($scriptText.Contains("'RT-8b-")) ''
Check '含 RT-8c' ($scriptText.Contains("'RT-8c-")) ''

# --- BLOCKER 回归检查（AUDIT-v2 修复后必须持续成立）---
Check 'B-1 快照名取自 backup.path' ($scriptText.Contains('Split-Path -Leaf ([string]$b.path)')) 'backup 返回无 name 字段'
Check 'B-2 不用 /content 的 text 字段' (-not ($scriptText -match '\$(?:content|c2)\.text\b')) '/content 返回字段是 content'
Check 'B-3 种子写入 workspace' ($scriptText.Contains('$wsPath')) 'dataRoot 是 personal 的父目录'
Check 'B-3 断言 workspace 层级' ($scriptText.Contains("'SE-2b'") -and $scriptText.Contains("'RT-8a-1b'")) '须区分 dataRoot 与 workspace'

# --- 收据质量（全文复审后修的三处）---
Check '收据不写 USERPROFILE' (-not $scriptText.Contains('UserProfile  = $env:USERPROFILE')) '本地跑会泄漏真实用户名路径'
Check '收据用 .NET 无 BOM 写入' ($scriptText.Contains('WriteAllText($ReceiptPath')) ''
Check '无 body 端点不发 {}' (-not $scriptText.Contains("if (`$null -eq `$body) { '{}' }")) ''

# --- MAJOR 修复回归检查 ---
Check 'M-1 用 .NET 无 BOM 写入' ($scriptText.Contains('UTF8Encoding]::new($false)')) ''
Check 'M-2 换行规范化比对' ($scriptText.Contains('Normalize-Text')) ''
Check 'M-4 健康检查只等一次' (-not $scriptText.Contains('Wait-Health $BackendPort 5')) ''
Check 'M-5 gaps 参与裁决' ($scriptText.Contains('PASS_WITH_GAPS')) ''

# --- 2026-10-24 证据边界回归检查（外部审计提出，逐条钉住）---
Check 'UP-4 已删除（不可靠字段的空值假阳性）' (-not $scriptText.Contains("Record 'UP-4'")) 'MainBinaryName 不是 NSIS 保证写入的命名值；前后皆空时 -ceq 为真'
Check 'RT-8c 先破坏种子再恢复' ($scriptText.Contains('TAMPERED-BEFORE-RESTORE') -and $scriptText.Contains("'RT-8c-2b'")) 'restore 前不动文件 → 不能证明恢复能力'
Check 'RT-8c 断言破坏确实生效' ($scriptText.Contains('破坏种子文件失败')) '否则内容未变时后续判据无效'
Check 'RT-9-2 要求 error_code 精确匹配' ($scriptText.Contains('$hitUnreachable')) '502 有 4 个分支，不能只凭状态码判定命中 modelUnreachable'
Check 'RT-9 不再"解析不到就放宽"' (-not $scriptText.Contains("if (`$pdfErr) { `$pdfOk = `$pdfOk -and")) '解析失败应记证据缺口'
Check 'GAP 态存在且不计入 failed' ($scriptText.Contains('function RecordGap') -and -not ($scriptText -match 'failed\s*=\s*@\(\$script:Rows \| Where-Object \{ \$_.status -eq .GAP')) '证据缺口既非失败也非通过'
Check 'GAP 使结论为 PASS_WITH_GAPS' ($scriptText.Contains('$gapRows.Count -gt 0')) '缺口不能被读成全绿'
Check '历史边界与本次缺口分开字段' ($scriptText.Contains('historical_evidence_limitations')) '补跑成功后不得仍显示"需补跑一次"'

# --- 代码审查 MAJOR 回归检查 ---
Check '审查 M1 PEM 用精确路径' ($scriptText.Contains("'CA-0'") -and $scriptText.Contains('resources\backend\_internal\certifi\cacert.pem')) '不用 -First 1 模糊匹配'
Check '审查 M1 PEM 数量断言' ($scriptText.Contains("'CA-0b'")) ''
Check '审查 M2 数据根跨版本比对' ($scriptText.Contains("'RT-8a-5'")) '不用恒真的自比自'
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

Write-Host "`n== 5. 退出码契约（失败注入，P0-1）" -ForegroundColor Cyan
$tmpR = Join-Path ([System.IO.Path]::GetTempPath()) ("jw-inj-" + [guid]::NewGuid().ToString('N'))
New-Item -ItemType Directory -Force -Path $tmpR | Out-Null
try {
  $injReceipt = Join-Path $tmpR 'inj.json'
  # 注入一条非致命 FAIL：脚本必须收尾、写收据、并以非 0 退出
  $null = & pwsh -NoProfile -ExecutionPolicy Bypass -File $ScriptPath `
    -OldExe 'injected-does-not-exist.exe' -NewExe 'injected-does-not-exist.exe' `
    -BaseDir (Join-Path $tmpR 'b') -ReceiptPath $injReceipt -FailInjection 2>&1
  $injExit = $LASTEXITCODE
  Check '注入 FAIL → 退出码非 0' ($injExit -ne 0) "exit=$injExit"

  $conc = '<no-receipt>'
  if (Test-Path -LiteralPath $injReceipt) {
    $ij = Get-Content -LiteralPath $injReceipt -Raw -Encoding utf8 | ConvertFrom-Json
    $conc = [string]$ij.summary.conclusion
  }
  Check '注入 FAIL → 收据结论 = FAIL' ($conc -eq 'FAIL') "conclusion=$conc"
} catch {
  Check '失败注入测试可执行' $false $_.Exception.Message
} finally {
  Remove-Item -LiteralPath $tmpR -Recurse -Force -ErrorAction SilentlyContinue
}

Write-Host ''
if ($failed -gt 0) {
  Write-Host "自检失败：$failed 项" -ForegroundColor Red
  exit 1
}
Write-Host '自检通过：静态契约与纯函数行为均符合预期（不代表安装验收已通过）' -ForegroundColor Green
exit 0
