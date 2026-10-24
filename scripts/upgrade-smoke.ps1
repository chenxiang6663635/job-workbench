<#
.SYNOPSIS
  D′-1：26.10.1 一次性 Windows CI 安装器升级合同（草案）。

.DESCRIPTION
  在**一次性 GitHub 托管 Windows runner** 上验证：
    官方 26.10.0 → 固定 RC 26.10.1 的覆盖升级、位置恢复、数据语义、
    打包后端自举（五重联合判据）、PEM 安全基线、卸载语义。

  本脚本**不含自动更新测试**（那属 D′-2，见 DESIGN.md §5：原 α 的
  `api.github.com` 前提已被上游 6.8.9 源码证伪）。

  设计：DESIGN.md。**草案：未 push、未 dispatch。**

  审计修正（本轮）：
    P0-2 RT-8 拆 8a/8b/8c，按 Hotfix 真实 API（`/api/system/paths` 等）实现
    P1   收据在**任何失败路径**都生成（主体包 try/finally，写收据本身不抛错）

.PARAMETER OldExe
  官方 26.10.0 安装包（SHA256 必须 = 197fe105…）。

.PARAMETER NewExe
  26.10.1 RC 安装包（SHA256 必须 = fbc6bbee…）。

.PARAMETER BaseDir
  测试根（一次性 runner 上默认 RUNNER_TEMP）。

.PARAMETER ReceiptPath
  收据输出路径；默认 `<BaseDir 的父目录>/jw-smoke-receipt.json`。
#>
[CmdletBinding()]
param(
  [Parameter(Mandatory = $true)][string] $OldExe,
  [Parameter(Mandatory = $true)][string] $NewExe,
  [string] $BaseDir = (Join-Path $env:RUNNER_TEMP 'jw-smoke'),
  [string] $ReceiptPath = '',
  # 失败注入（仅供 selftest）：注入一条非致命 FAIL 后立即收尾，
  # 用来证明「断言 FAIL → 退出码非 0」这条链路真的成立。正式运行不传。
  [switch] $FailInjection
)

Set-StrictMode -Version 2.0
$ErrorActionPreference = 'Stop'

# ---------------------------------------------------------------- 产品事实（勿改）
$AppId        = 'com.jobworkbench.app'          # 不可改：electron-builder 由它派生升级 GUID
$BackendPort  = 8765
$ApiBase      = "http://127.0.0.1:$BackendPort"
$Workspace    = 'personal'
$OldSha256    = '197fe10593eb50b127c87aaa690ad575aee7dc38b001110de5421e4df52ca954'
$NewSha256    = 'fbc6bbeebbc0e9af6c592e78591c3328f4adc9a7898208244b7bcfe1e75615c7'
$SafePemSha   = '50F79F98DAC192B20DBF73F35C56F0B0C557AB267FF5199D1117CC1180B70785'
# 注册表键名**不是** appId：electron-builder 用 UUID.v5(appId, NS_UUID) 派生 GUID
# （NsisTarget.js:174-175 → guid = UUID.v5(appInfo.id, ...); uninstallAppKey = guid），
# 于是 INSTALL_REGISTRY_KEY = "Software\<GUID>"、UNINSTALL_REGISTRY_KEY = "...\Uninstall\<GUID>"。
# 硬编码 "{appId}" 的后果（2026-10-23 真机 run 39904842099 实测）：DisplayVersion 读不到 →
# IN-1 FAIL、before 全空 → UP-2/3/4 两边都是 $null 时 -ceq 为真 → **假阳性**。
# 因此改为安装后按 DisplayName 枚举定位（见 Find-UninstallKey）。
$UninstKey    = $null
$AppKey       = $null
$InstallerTimeout = 600

if ([string]::IsNullOrWhiteSpace($ReceiptPath)) {
  $ReceiptPath = Join-Path (Split-Path $BaseDir -Parent) 'jw-smoke-receipt.json'
}

# ---------------------------------------------------------------- 状态
$script:Rows      = [System.Collections.Generic.List[object]]::new()
$script:Phase     = 'init'
$script:ExitCode  = 1
$script:Fatal     = $null
$script:OldHash   = $null
$script:NewHash   = $null
$script:InstallDir= $null
$script:RunnerInfo= $null
$script:DataRoot  = $null   # MAJOR-2：旧版自报的数据根，供升级后比对（跨阶段）
# 退出码判据（P0-1）：只有「主流程走完 + 无 FAIL + 无 fatal + 收据已写出」才允许 exit 0
$script:MainFlowCompleted = $false
$script:ReceiptWritten    = $false
# 早期即失败（如 -FailInjection、身份校验 throw）时 preflight 尚未执行，
# 这些变量不存在 → finally 里的引用会在 Set-StrictMode 下抛错。统一先初始化为 $null。
$testDir = $null; $wsDir = $null; $appData = $null; $wsPath = $null; $ws2 = $null
$seedFile = $null; $seedHash = $null; $newBackend = $null; $installDir = $null

function Record([string] $id, [string] $what, [bool] $ok, [string] $detail = '') {
  $row = [pscustomobject]@{
    id     = $id
    check  = $what
    status = $(if ($ok) { 'PASS' } else { 'FAIL' })
    detail = $detail
    phase  = $script:Phase
  }
  $script:Rows.Add($row)
  $tag = if ($ok) { 'ok  ' } else { 'FAIL' }
  $color = if ($ok) { 'Green' } else { 'Red' }
  Write-Host ("  [{0}] {1} — {2}" -f $tag, $what, $detail) -ForegroundColor $color
}
function Step([string] $t, [string] $phase) {
  $script:Phase = $phase
  Write-Host "`n== $t" -ForegroundColor Cyan
}
function Require([bool] $cond, [string] $msg) { if (-not $cond) { throw $msg } }

function Get-Sha256([string] $p) { (Get-FileHash -LiteralPath $p -Algorithm SHA256).Hash.ToLowerInvariant() }

# M-2：换行规范化后再比对。实测（2026-10-22）：当前写入即 LF、读回相等；
# 但文件一旦被工具改成 CRLF（或恢复路径转换换行），直接 -eq 会假阴性。
function Normalize-Text([string] $s) {
  if ($null -eq $s) { return '' }
  ($s -replace "`r`n", "`n").Trim()
}

function Get-RegValue([string] $key, [string] $name) {
  if (-not (Test-Path -LiteralPath $key)) { return $null }
  $item = Get-Item -LiteralPath $key
  if ($item.GetValueNames() -notcontains $name) { return $null }
  $item.GetValue($name, $null, 'DoNotExpandEnvironmentNames')
}

function Find-UninstallKey {
  # 在 HKCU Uninstall 下按 DisplayName 找 Job Workbench 的键，返回其 PSPath；找不到返回 $null。
  # 不用固定 GUID：guid 由 UUID.v5(appId, NS_UUID) 派生，改 appId 就会变，硬编码必然腐化。
  $root = 'HKCU:\Software\Microsoft\Windows\CurrentVersion\Uninstall'
  if (-not (Test-Path -LiteralPath $root)) { return $null }
  foreach ($k in Get-ChildItem -LiteralPath $root -ErrorAction SilentlyContinue) {
    $dn = $null
    try { $dn = (Get-ItemProperty -LiteralPath $k.PSPath -ErrorAction Stop).DisplayName } catch { }
    if ($dn -and $dn -like 'Job Workbench*') { return $k.PSPath }
  }
  return $null
}

function Get-Listeners([int] $port) {
  # 逗号包一层：函数**返回**空数组时，PowerShell 的管道语义会把它展开成 $null，
  # 调用方 `$x.Count` 在 Set-StrictMode 下直接抛 "property 'Count' cannot be found"。
  # （2026-10-23 真机 run 39903820189 在 preflight 第一行实测到；本地复现确认。）
  return ,@(Get-NetTCPConnection -LocalPort $port -State Listen -ErrorAction SilentlyContinue)
}

function Invoke-Installer([string] $path, [string[]] $extra) {
  $argv = @('/S') + $extra
  Write-Host "  > $(Split-Path $path -Leaf) $($argv -join ' ')" -ForegroundColor DarkGray
  $p = Start-Process -FilePath $path -ArgumentList $argv -PassThru
  $null = $p.Handle
  if (-not $p.WaitForExit($InstallerTimeout * 1000)) {
    try { $p.Kill() } catch { }
    throw "$path 在 $InstallerTimeout 秒内未结束"
  }
  if ($p.ExitCode -ne 0) { throw "$path 退出码 $($p.ExitCode)" }
}

function Invoke-Uninstaller([string] $dir) {
  # electron-builder 的卸载器名是 "Uninstall ${PRODUCT_FILENAME}.exe"（common.nsh:17），
  # 即 `Uninstall Job Workbench.exe` —— 不是 uninstall.exe（2026-10-23 真机 run 39910385167 实测）。
  $u = (Get-ChildItem -LiteralPath $dir -File -Filter 'Uninstall*.exe' -ErrorAction SilentlyContinue |
        Select-Object -First 1).FullName
  if (-not $u) { $u = Join-Path $dir 'uninstall.exe' }
  Require (Test-Path -LiteralPath $u) "找不到卸载器（Uninstall*.exe / uninstall.exe）：$dir"
  # NSIS：_?= 必须最后、路径不加引号；否则卸载器 fork 到 TEMP 后立即返回
  # `_?=<dir>` 让卸载器在原地运行（不 fork 到 TEMP），Start-Process -Wait 因而能真正等到
  # 卸载流程结束。代价是它**无法删除自己**（正占用自己的文件），所以不能再等「文件消失」——
  # 那会永远等下去（2026-10-23 真机 run 39912512403 正是 601 秒超时）。
  # 卸载是否成功由 UN-1（注册表项消失）与 UN-2（主程序消失）断言。
  Invoke-Installer $u @("_?=$dir")
}

function Wait-Health([int] $port, [int] $seconds = 90) {
  $deadline = (Get-Date).AddSeconds($seconds)
  while ((Get-Date) -lt $deadline) {
    try {
      $r = Invoke-WebRequest -Uri "$ApiBase/api/health" -TimeoutSec 2 -UseBasicParsing
      if ($r.StatusCode -eq 200 -and $r.Content -match 'ok') { return $true }
    } catch { }
    Start-Sleep -Milliseconds 500
  }
  return $false
}

function Get-Api([string] $path) {
  Invoke-RestMethod -Uri "$ApiBase$path" -TimeoutSec 10 -Method Get
}
function Post-Api([string] $path, $body) {
  # $body = $null 表示该端点**没有 body 参数**（如 /api/system/backup）——不要凭空发 "{}"，
  # 那会让"有没有 body"这件事在证据里变得含糊。
  if ($null -eq $body) {
    return Invoke-RestMethod -Uri "$ApiBase$path" -TimeoutSec 60 -Method Post
  }
  Invoke-RestMethod -Uri "$ApiBase$path" -TimeoutSec 60 -Method Post `
    -ContentType 'application/json' -Body ($body | ConvertTo-Json -Compress)
}

function Stop-Tree([int] $port) {
  foreach ($l in Get-Listeners $port) {
    try { Stop-Process -Id $l.OwningProcess -Force -ErrorAction SilentlyContinue } catch { }
  }
  foreach ($n in @('Job Workbench', 'job-workbench-backend')) {
    Get-Process -Name $n -ErrorAction SilentlyContinue | Stop-Process -Force -ErrorAction SilentlyContinue
  }
}

# ================================================================ 主体（失败也写收据）
try {
  # 失败注入（仅 selftest）：在任何断言之前模拟「注入一条非致命 FAIL，主流程正常收尾」。
  # 用于证明 P0-1 的修复真的成立——即 Record FAIL 必须让退出码非 0。
  if ($FailInjection) {
    Step 'FailInjection（selftest）' 'fail-injection'
    Record 'SELFTEST-INJ' '注入非致命 FAIL（自检用）' $false 'forced by -FailInjection'
    $script:MainFlowCompleted = $true
    return
  }

  # -------------------------------------------------------------- 0. 身份
  Step 'Identity' 'identity'
  Require (Test-Path -LiteralPath $OldExe) "旧版安装包不存在：$OldExe"
  Require (Test-Path -LiteralPath $NewExe) "新版安装包不存在：$NewExe"
  $script:OldHash = Get-Sha256 $OldExe
  $script:NewHash = Get-Sha256 $NewExe
  Record 'ID-1' '旧版 26.10.0 SHA256' ($script:OldHash -eq $OldSha256) $script:OldHash
  Record 'ID-2' '新版 26.10.1 SHA256' ($script:NewHash -eq $NewSha256) $script:NewHash
  Require ($script:OldHash -eq $OldSha256 -and $script:NewHash -eq $NewSha256) '安装包身份不符，拒绝继续'

  # -------------------------------------------------------------- 1. 前置（fail-closed）
  Step 'Preflight（任一不满足即拒绝运行）' 'preflight'
  $testDir = Join-Path $BaseDir 'Job Workbench'   # 故意带空格：复刻真实路径
  $wsDir   = Join-Path $BaseDir 'ws'
  $appData = Join-Path $BaseDir 'appdata'

  $listeners = Get-Listeners $BackendPort
  Record 'PF-1' "端口 $BackendPort 无监听" ($listeners.Count -eq 0) "listeners=$($listeners.Count)"
  Require ($listeners.Count -eq 0) "端口 $BackendPort 已被占用——会绕过被测安装，拒绝运行"

  $existingUninst = Find-UninstallKey
  $hasUninst = $null -ne $existingUninst
  $procs = @(Get-Process -Name 'Job Workbench', 'job-workbench-backend' -ErrorAction SilentlyContinue)
  $dirExists = Test-Path -LiteralPath $testDir
  Record 'PF-2' '无既有卸载登记' (-not $hasUninst) $(if ($hasUninst) { $existingUninst } else { '<none>' })
  Record 'PF-4' '无相关进程' ($procs.Count -eq 0) "count=$($procs.Count)"
  Record 'PF-5' '测试目录事先不存在' (-not $dirExists) $testDir
  Require ((-not $hasUninst) -and $procs.Count -eq 0 -and (-not $dirExists)) '环境不干净，拒绝运行（fail-closed）'

  # v26.10.0 **没有** #357 自动初始化：数据根下必须预先存在 <workspace> 目录，
  # 否则 /api/system/paths 解析工作区时返回 404（2026-10-23 真机 run 39904842099 实测）。
  New-Item -ItemType Directory -Force -Path $BaseDir, $wsDir, $appData, (Join-Path $wsDir $Workspace) | Out-Null

  # 三处路径分别隔离：工作区 JOBWS_DATA_DIR；快照/偏好 APPDATA
  $env:JOBWS_DATA_DIR = $wsDir
  $env:APPDATA        = $appData
  Remove-Item Env:\JOBWS_PYTHON -ErrorAction SilentlyContinue   # 不让 Python 回退被当成通过

  # 不写 USERPROFILE：本地跑会落真实用户名路径。用「是否托管 runner」替代，信息量足够。
  $script:RunnerInfo = [ordered]@{
    ImageOS        = $env:ImageOS
    ImageVersion   = $env:ImageVersion
    OSVersion      = [System.Environment]::OSVersion.VersionString
    Architecture   = $env:PROCESSOR_ARCHITECTURE
    PSVersion      = $PSVersionTable.PSVersion.ToString()
    IsHostedRunner = [bool]$env:GITHUB_ACTIONS
  }
  Write-Host ($script:RunnerInfo | ConvertTo-Json -Compress) -ForegroundColor DarkGray

  # -------------------------------------------------------------- 2. 安装旧版
  Step 'Install 26.10.0 (/S /D=)' 'install-old'
  Invoke-Installer $OldExe @("/D=$testDir")
  # 安装后按 DisplayName 定位真实键（GUID 形态），拿不到就拒绝继续——
  # 否则后续断言全在空值上做，会得出假 PASS。
  $UninstKey = Find-UninstallKey
  Require ($null -ne $UninstKey) '安装后未找到 Job Workbench 卸载登记——无法验证版本与安装位置（不得据此判 PASS）'
  $AppKey = 'HKCU:\Software\' + (Split-Path $UninstKey -Leaf)
  # InstallLocation 写在 INSTALL_REGISTRY_KEY（Software\<GUID>），**不在** Uninstall 键下
  # （installer.nsh:104 WriteRegStr ... ${INSTALL_REGISTRY_KEY} InstallLocation "$INSTDIR"）。
  # 早先从 Uninstall 键读它，结果恒空。
  $installDir = Get-RegValue $AppKey 'InstallLocation'
  if ([string]::IsNullOrWhiteSpace($installDir) -or -not (Test-Path -LiteralPath $installDir)) { $installDir = $testDir }
  $script:InstallDir = $installDir

  Record 'IN-1' '旧版版本 = 26.10.0' ((Get-RegValue $UninstKey 'DisplayVersion') -eq '26.10.0') (Get-RegValue $UninstKey 'DisplayVersion')
  $oldBackend = Join-Path $installDir 'resources\backend\job-workbench-backend.exe'
  Record 'IN-2' '安装目录含后端 exe' (Test-Path -LiteralPath $oldBackend) $oldBackend
  Require (Test-Path -LiteralPath $oldBackend) '旧版安装缺后端 exe，无法继续（安装包不完整）'

  $before = @{
    InstLoc    = Get-RegValue $AppKey 'InstallLocation'      # 在 Software\<GUID> 下
    MainBinary = Get-RegValue $UninstKey 'MainBinaryName'    # 在 Uninstall\<GUID> 下
  }
  Write-Host ("  before: InstLoc='{0}' MainBinary='{1}'" -f $before.InstLoc, $before.MainBinary) -ForegroundColor DarkGray

  # -------------------------------------------------------------- 3. 经真实 API 建立数据 + 快照
  Step 'Seed data via real API (RT-8a/8b 前置) + snapshot' 'seed'
  $backendProc = $null
  $seedRel  = 'SMOKE_SEED.md'
  $seedBody = "# smoke seed`nid: SMOKE-001`nvalue: 26.10.0-baseline`n"
  $snapName = $null
  try {
    $backendProc = Start-Process -FilePath $oldBackend -PassThru -WorkingDirectory (Split-Path $oldBackend -Parent)
    # M-4：只等一次，布尔值复用（原实现 60s 后再等 5s，且失败信息不指向真因）
    $healthy = Wait-Health $BackendPort 60
    Record 'SE-1' '旧版后端健康检查' $healthy "$ApiBase/api/health"
    Require $healthy '旧版后端未就绪（60s 内无健康响应：可能是漏打包 backend，或运行时缺失）'

    # RT-8a（旧版基线）：dataRoot / snapshotDir 分别落在两个隔离根
    $paths = Get-Api "/api/system/paths?ws=$Workspace"
    $dataRoot = [System.IO.Path]::GetFullPath([string]$paths.dataRoot)
    $script:DataRoot = $dataRoot   # MAJOR-2：保留旧版自报值，升级后用同一来源比对
    $snapDir  = [System.IO.Path]::GetFullPath([string]$paths.snapshotDir)
    $expData  = [System.IO.Path]::GetFullPath($wsDir)
    $expSnapParent = [System.IO.Path]::GetFullPath($appData)
    Record 'SE-2' 'dataRoot = 隔离工作区根' ($dataRoot -ieq $expData) "actual=$dataRoot"
    Record 'SE-3' 'snapshotDir 位于隔离 APPDATA 下' ($snapDir.StartsWith($expSnapParent, 'OrdinalIgnoreCase')) "actual=$snapDir"
    # 原 SE-4（旧版 appVersion 非空）已删除：直接起 backend exe 时**没有应用壳注入**
    # JOBWS_APP_VERSION，packaged 形态也读不到 package.json —— 该字段本来就该为空。
    # 版本真值由 RT-8a-3 验证（那是经应用壳启动的进程）。
    Record 'SE-5' 'telemetry = false' ($paths.telemetry -eq $false) ([string]$paths.telemetry)

    # 写入虚构文件（local-first 形态），随后必须能被新版应用读出。
    # 审计 B-3：dataRoot 是「personal/ 的父目录」，事实库在 **workspace** 内——必须用 API 回报的 workspace。
    $wsPath  = [System.IO.Path]::GetFullPath([string]$paths.workspace)
    $expWs   = [System.IO.Path]::GetFullPath((Join-Path $wsDir $Workspace))
    Record 'SE-2b' 'workspace = dataRoot\personal' ($wsPath -ieq $expWs) "actual=$wsPath expected=$expWs"
    $factsDir = Join-Path $wsPath '00_事实库'
    New-Item -ItemType Directory -Force -Path $factsDir | Out-Null
    $seedFile = Join-Path $factsDir $seedRel
    # M-1：用 .NET 显式无 BOM 写入——消除「Set-Content -Encoding utf8」在 5.1/7.x 行为差异。
    # 实测（2026-10-22）：pwsh 7 两者字节一致；5.1 的 utf8 会带 BOM，令读回内容多出 \ufeff。
    [System.IO.File]::WriteAllText($seedFile, $seedBody, [System.Text.UTF8Encoding]::new($false))
    $seedHash = Get-Sha256 $seedFile
    Record 'SE-6' '种子文件已写入工作区' (Test-Path -LiteralPath $seedFile) $seedFile

    # 走 API 读回（证明旧版能解析，为升级后"语义仍可读"建立基线）
    # 审计 B-2：/content 的字段名是 content，不是 text。
    $list = Get-Api "/api/library/facts?ws=$Workspace"
    $listed = @($list.items | Where-Object { $_.name -eq $seedRel }).Count -gt 0
    Record 'SE-7' '旧版 API 能列出种子文件' $listed "total=$($list.total)"
    $content = Get-Api "/api/library/facts/content?ws=$Workspace&rel=$seedRel"
    Record 'SE-8' '旧版 API 能读回内容' ([string]$content.content -match 'SMOKE-001') ''

    # 建快照（升级后要能列出并恢复）
    # 审计 B-1：backup 返回 {ok,path,files,size,kept,removed,snapshotDir}，**没有 name**——从 path 取文件名。
    try {
      $b = Post-Api "/api/system/backup?ws=$Workspace" $null
      if ($null -ne $b.path -and -not [string]::IsNullOrWhiteSpace([string]$b.path)) {
        $snapName = Split-Path -Leaf ([string]$b.path)
      }
    } catch {
      Record 'SE-9' '创建基线快照' $false $_.Exception.Message
    }
    if ($null -ne $snapName -and $snapName -ne '') {
      Record 'SE-9' '创建基线快照' $true $snapName
    }
  } finally {
    if ($null -ne $backendProc -and -not $backendProc.HasExited) { try { $backendProc.Kill() } catch { } }
    Start-Sleep -Seconds 2
    Stop-Tree $BackendPort
  }

  # -------------------------------------------------------------- 4. 覆盖升级（不带 /D=）
  Step 'Upgrade to 26.10.1 (/S，不带 /D=)' 'upgrade'
  Invoke-Installer $NewExe @()
  $newVersion = Get-RegValue $UninstKey 'DisplayVersion'
  Record 'UP-1' '升级后版本 = 26.10.1' ($newVersion -eq '26.10.1') $newVersion

  $after = @{
    InstLoc    = Get-RegValue $AppKey 'InstallLocation'
    MainBinary = Get-RegValue $UninstKey 'MainBinaryName'
  }
  # 防假阳性：InstLoc 若为空，-ceq 会为真——那不是"位置恢复了"，是"根本没读到"。
  Require (($null -ne $before.InstLoc) -and ($null -ne $after.InstLoc)) '安装位置注册项缺失（InstallLocation 为空）——位置恢复无法验证，不得判 PASS'
  # 原 UP-2（比较 appId 键默认值）已删除：installer.nsh 只写 InstallLocation 命名值，
  # 不保证写默认值；拿不可靠的字段做断言只会制造噪声或假阳性。位置恢复由 UP-3 承担。
  Record 'UP-3' 'InstallLocation 未变（位置恢复）' ($after.InstLoc -ceq $before.InstLoc) "$($before.InstLoc) -> $($after.InstLoc)"
  # 原 UP-4（比较 MainBinaryName）已删除，2026-10-23 审计纠正：与 UP-2 同源的不可靠字段。
  # 实证：run 39914715729 的收据 detail 为 " -> "——升级前后**都没读到**该值，
  # 两个空串 -ceq 相等，于是记成 PASS。那不是"主程序名未变"，是"根本没读到"。
  # MainBinaryName 同样不是 installer.nsh 保证写入的命名值（同 UP-2 的理由）。
  # 若将来 NSIS 确实写该值，应同时补上与 UP-3 同款的空值守卫再恢复此断言。
  Record 'UP-5' '种子文件仍在且哈希未变' ((Test-Path -LiteralPath $seedFile) -and (Get-Sha256 $seedFile) -eq $seedHash) $seedHash

  # -------------------------------------------------------------- 5. 自举（五重）+ RT-8
  Step 'Bundled backend bootstrap (5-way) + RT-8a/8b/8c' 'runtime'
  $newBackend = Join-Path $installDir 'resources\backend\job-workbench-backend.exe'
  Record 'RT-1' '新版安装目录含后端 exe' (Test-Path -LiteralPath $newBackend) $newBackend

  $pre = Get-Listeners $BackendPort
  Record 'RT-2' '启动前端口空闲' ($pre.Count -eq 0) "listeners=$($pre.Count)"

  $appProc = $null
  try {
    $appProc = Start-Process -FilePath (Join-Path $installDir 'Job Workbench.exe') -PassThru
    $healthy = Wait-Health $BackendPort 90
    Record 'RT-3' '健康检查通过' $healthy "$ApiBase/api/health"

    $post = Get-Listeners $BackendPort
    Record 'RT-4' '8765 有监听者' ($post.Count -gt 0) "listeners=$($post.Count)"
    if ($post.Count -gt 0) {
      $owningPid = ($post | Select-Object -First 1).OwningProcess
      $owner = Get-Process -Id $owningPid -ErrorAction SilentlyContinue
      $expected = [System.IO.Path]::GetFullPath($newBackend)
      $actual   = if ($null -ne $owner -and $owner.Path) { [System.IO.Path]::GetFullPath($owner.Path) } else { $null }
      Record 'RT-5' '监听者 = 本次安装的后端 exe' ($null -ne $actual -and $actual -ieq $expected) "owner=$actual"
    } else {
      Record 'RT-5' '监听者 = 本次安装的后端 exe' $false '无监听者'
    }

    # 原 RT-6/RT-7（读 main.log 判断是否走了 Python 回退）已删除：
    # ① RT-5 已经用「8765 监听者的进程路径 == 本次安装的后端 exe」证明未走回退——这比日志措辞更强；
    # ② 日志目录存在两套命名并存（Electron userData 用 productName，pathres 用 job-workbench），
    #    位置不稳定的证据不该当强制判据（两次真机分别因为路径与措辞判 FAIL）。
    # 该缺口记入收据 known_gaps。

    if ($healthy) {
      # RT-8a：新版运行时自报数据根 / 快照根 / 版本
      $p2 = Get-Api "/api/system/paths?ws=$Workspace"
      # M-3 说明（实测 2026-10-22）：这里用 GetFullPath 而**不是** Resolve-Path——
      # 后者对不存在的路径会 throw，而 dataRoot/snapshotDir 在断言时未必存在。
      # 前提：这三个路径都由 JOBWS_DATA_DIR / APPDATA 直接生成，不经 junction/符号链接。
      $dr = [System.IO.Path]::GetFullPath([string]$p2.dataRoot)
      $sd = [System.IO.Path]::GetFullPath([string]$p2.snapshotDir)
      $ws2 = [System.IO.Path]::GetFullPath([string]$p2.workspace)
      Record 'RT-8a-1' 'dataRoot = 隔离数据根（JOBWS_DATA_DIR）' ($dr -ieq $expData) "actual=$dr"
      Record 'RT-8a-1b' 'workspace = dataRoot\personal（两级不同）' ($ws2 -ieq $expWs) "actual=$ws2"
      Record 'RT-8a-2' 'snapshotDir 位于隔离 APPDATA 下' ($sd.StartsWith($expSnapParent, 'OrdinalIgnoreCase')) "actual=$sd"
      Record 'RT-8a-3' 'appVersion = 26.10.1' ([string]$p2.appVersion -eq '26.10.1') ([string]$p2.appVersion)
      Record 'RT-8a-4' 'telemetry = false' ($p2.telemetry -eq $false) ([string]$p2.telemetry)
      # MAJOR-2：升级前后数据根一致性——两边都由各自版本的应用自报，非同源自比
      Record 'RT-8a-5' '升级前后数据根一致' ($dr -ieq [string]$script:DataRoot) "$($script:DataRoot) -> $dr"

      # RT-8b：新版 API 能列出并逐字读回升级前写入的内容
      # 审计 B-2：/content 返回字段是 content（不是 text）。
      try {
        $l2 = Get-Api "/api/library/facts?ws=$Workspace"
        $seen = @($l2.items | Where-Object { $_.name -eq $seedRel }).Count -gt 0
        Record 'RT-8b-1' '新版 API 列出种子文件' $seen "total=$($l2.total)"
        $c2 = Get-Api "/api/library/facts/content?ws=$Workspace&rel=$seedRel"
        $body2 = [string]$c2.content
        # M-2：换行规范化后比对（CRLF/LF 差异不应判失败）
        Record 'RT-8b-2' '新版 API 读回内容一致（换行已规范化）' ((Normalize-Text $body2) -eq (Normalize-Text $seedBody)) "len=$($body2.Length)"
      } catch {
        Record 'RT-8b-1' '新版 API 列出种子文件' $false $_.Exception.Message
        Record 'RT-8b-2' '新版 API 读回内容逐字一致' $false '未执行（列表失败）'
      }

      # RT-8c：升级前的快照仍可见、可演练、可恢复
      if ($null -ne $snapName -and $snapName -ne '') {
        try {
          $snaps = Get-Api "/api/system/snapshots?ws=$Workspace"
          $found = @($snaps.snapshots | Where-Object { $_.name -eq $snapName }).Count -gt 0
          Record 'RT-8c-1' '升级前快照仍可见' $found "name=$snapName count=$($snaps.count)"
          $prev = Post-Api "/api/system/snapshots/preview?ws=$Workspace" @{ name = $snapName }
          Record 'RT-8c-2' '快照演练（preview）通过' ($null -ne $prev) ''
          # 先破坏种子文件，再 restore（2026-10-23 审计纠正）。
          # 原判据在 restore 前不动文件，于是"恢复后内容正确"只证明"文件本来就没被改过"——
          # run 39914715729 的 detail 是 len=51（= 原始内容），restore 即使什么都没做也会 PASS。
          # 现在先把内容改成明显不同的值并确认改动生效，restore 后才可能证明恢复能力。
          $tampered = "# smoke seed`nid: SMOKE-001`nvalue: TAMPERED-BEFORE-RESTORE`n"
          Set-Content -LiteralPath $seedFile -Value $tampered -Encoding utf8 -NoNewline
          $tamperedNow = Get-Content -LiteralPath $seedFile -Raw -Encoding utf8
          if ((Normalize-Text $tamperedNow) -eq (Normalize-Text $seedBody)) {
            throw '破坏种子文件失败：内容未实际改变——后续恢复判据无效，不得判 PASS'
          }
          Record 'RT-8c-2b' '种子文件已被破坏（恢复判据前置）' $true "len=$($tamperedNow.Length)"
          $null = Post-Api "/api/system/snapshots/restore?ws=$Workspace" @{ name = $snapName }
          $afterRestore = Get-Content -LiteralPath $seedFile -Raw -Encoding utf8
          $restoredOk = ((Normalize-Text $afterRestore) -eq (Normalize-Text $seedBody))
          Record 'RT-8c-3' '快照恢复后数据回到原内容（换行已规范化）' $restoredOk "len=$($afterRestore.Length)"
          if (-not $restoredOk) {
            # 恢复失败必须留下现场内容，便于判断是 restore 没生效还是内容被改写
            Record 'RT-8c-3b' '恢复失败现场' $false ("got=" + ((Normalize-Text $afterRestore) -replace "\s+", ' '))
          }
        } catch {
          Record 'RT-8c-1' '升级前快照仍可见' $false $_.Exception.Message
          Record 'RT-8c-2' '快照演练（preview）通过' $false '未执行'
          Record 'RT-8c-2b' '种子文件已被破坏（恢复判据前置）' $false '未执行'
          Record 'RT-8c-3' '快照恢复后数据回到原内容' $false '未执行'
        }
      } else {
        Record 'RT-8c-1' '升级前快照仍可见' $false '基线快照未创建（见 SE-9）'
        Record 'RT-8c-2' '快照演练（preview）通过' $false '未执行'
        Record 'RT-8c-2b' '种子文件已被破坏（恢复判据前置）' $false '未执行'
        Record 'RT-8c-3' '快照恢复后数据回到原内容' $false '未执行'
      }

      # RT-9：打包后端的 PDF 文本提取（pypdf）——**不调用任何模型**。
      # 判据设计：/api/resume/import 先本地抽取（resume_import._extract_pdf，纯 pypdf）
      # 再调 BYOK 模型。把 provider 指向本机不可达端口 http://127.0.0.1:1，则：
      #   抽取成功 → 停在模型调用 → 502 resume.modelUnreachable
      #   抽取失败 → 422 resume.extractFailed
      # 因此「502 且错误码为 modelUnreachable」即证明 pypdf 在打包后端里可用，且全程零外发。
      try {
        $pdfPath = Join-Path $appData 'smoke-resume.pdf'
        $pdfB64 = 'JVBERi0xLjQKMSAwIG9iajw8L1R5cGUvQ2F0YWxvZy9QYWdlcyAyIDAgUj4+ZW5kb2JqCjIgMCBvYmo8PC9UeXBlL1BhZ2VzL0tpZHNbMyAwIFJdL0NvdW50IDE+PmVuZG9iagozIDAgb2JqPDwvVHlwZS9QYWdlL1BhcmVudCAyIDAgUi9NZWRpYUJveFswIDAgNTk1IDg0Ml0vUmVzb3VyY2VzPDwvRm9udDw8L0YxIDQgMCBSPj4+Pi9Db250ZW50cyA1IDAgUj4+ZW5kb2JqCjQgMCBvYmo8PC9UeXBlL0ZvbnQvU3VidHlwZS9UeXBlMS9CYXNlRm9udC9IZWx2ZXRpY2E+PmVuZG9iago1IDAgb2JqPDwvTGVuZ3RoIDc4Pj5zdHJlYW0KQlQgL0YxIDEyIFRmIDcyIDcyMCBUZCAoSm9iIFdvcmtiZW5jaCBzbW9rZSBKT0JXUy1TTU9LRS1QREYtTUFSS0VSLTIwMjYpIFRqIEVUCmVuZHN0cmVhbWVuZG9iagp4cmVmCjAgNgowMDAwMDAwMDAwIDY1NTM1IGYgCjAwMDAwMDAwMDkgMDAwMDAgbiAKMDAwMDAwMDA1MiAwMDAwMCBuIAowMDAwMDAwMTAxIDAwMDAwIG4gCjAwMDAwMDAyMTEgMDAwMDAgbiAKMDAwMDAwMDI3MiAwMDAwMCBuIAp0cmFpbGVyPDwvU2l6ZSA2L1Jvb3QgMSAwIFI+PgpzdGFydHhyZWYKMzk1CiUlRU9GCg=='
        [System.IO.File]::WriteAllBytes($pdfPath, [Convert]::FromBase64String($pdfB64))
        $cfgDir = Join-Path $ws2 'config'
        New-Item -ItemType Directory -Force -Path $cfgDir | Out-Null
        $cfgJson = '{"base_url":"http://127.0.0.1:1","api_key":"smoke-not-a-real-key","model":"smoke-model"}'
        [System.IO.File]::WriteAllText((Join-Path $cfgDir 'provider.json'), $cfgJson, [System.Text.UTF8Encoding]::new($false))
        $body = @{ filename = 'smoke-resume.pdf'; content_base64 = $pdfB64; model = 'smoke-model' } | ConvertTo-Json -Compress
        $pdfStatus = 0; $pdfErr = ''
        try {
          $null = Invoke-RestMethod -Uri "$ApiBase/api/resume/import?ws=$Workspace" -Method Post `
            -ContentType 'application/json' -Body $body -TimeoutSec 30
          $pdfStatus = 200
        } catch {
          $resp = $_.Exception.Response
          if ($null -ne $resp) {
            $pdfStatus = [int]$resp.StatusCode
            # 读响应体要兼容两代 PowerShell：
            #   PS 7  → HttpResponseMessage，只能 Content.ReadAsStringAsync()
            #   PS 5.1 → WebResponse，GetResponseStream()
            # 先前只写后者，导致 PS 7 上 error_code 恒为空（run 39943987140 实测）。
            $txt = ''
            try {
              $contentProp = $resp.PSObject.Properties['Content']
              if ($null -ne $contentProp -and $null -ne $contentProp.Value) {
                $txt = $contentProp.Value.ReadAsStringAsync().GetAwaiter().GetResult()
              }
            } catch { }
            if (-not $txt) {
              try {
                $stream = $resp.GetResponseStream()
                if ($null -ne $stream) {
                  $sr = New-Object System.IO.StreamReader($stream)
                  $txt = $sr.ReadToEnd(); $sr.Close()
                }
              } catch { }
            }
            # ApiError 响应体是 {"detail","error_code","error_params"?}（main.py:67）
            if ($txt) {
              try {
                $oj = $txt | ConvertFrom-Json
                $prop = $oj.PSObject.Properties['error_code']
                if ($null -ne $prop) { $pdfErr = [string]$prop.Value }
              } catch { }
            }
          }
        }
        # 判据：502 = 已越过本地抽取、停在模型阶段（抽取失败会是 422）。
        # 假端点是 127.0.0.1:1（连接被拒 → URLError），因此 502 只可能是 modelUnreachable；
        # 若能解析出 error_code 再收紧比对，解析不到不判失败（否则解析器差异会变成假阴性）。
        $pdfOk = ($pdfStatus -eq 502)
        if ($pdfErr) { $pdfOk = $pdfOk -and ($pdfErr -eq 'resume.modelUnreachable') }
        $pdfDetail = "http=$pdfStatus error_code=" + $(if ($pdfErr) { $pdfErr } else { '<unparsed>' })
        Record 'RT-9-1' 'PDF 文本提取通过（pypdf 在打包后端可用）' $pdfOk $pdfDetail
      } catch {
        Record 'RT-9-1' 'PDF 文本提取通过（pypdf 在打包后端可用）' $false $_.Exception.Message
      }
    } else {
      Record 'RT-8a-1' 'dataRoot = 隔离工作区根' $false '后端未就绪'
      Record 'RT-8b-1' '新版 API 列出种子文件' $false '后端未就绪'
      Record 'RT-8c-1' '升级前快照仍可见' $false '后端未就绪'
      Record 'RT-8c-2b' '种子文件已被破坏（恢复判据前置）' $false '后端未就绪'
      Record 'RT-8c-3' '快照恢复后数据回到原内容' $false '后端未就绪'
      # RT-9-1：后端未就绪时同样必须留痕——不能因为它"没跑"就从收据里消失
      # （2026-10-23 审计：D'-1 用的 3379bf3 版本脚本没有 RT-9 段，导致 pypdf 路径
      #  在 45/45 的收据里毫无痕迹，被误读成"已覆盖"）
      Record 'RT-9-1' 'PDF 文本提取通过（pypdf 在打包后端可用）' $false '后端未就绪'
    }
  } finally {
    if ($null -ne $appProc -and -not $appProc.HasExited) { try { $appProc.Kill() } catch { } }
    Stop-Tree $BackendPort
    Start-Sleep -Seconds 2
  }

  # -------------------------------------------------------------- 6. PEM 基线
  Step 'Bundled CA baseline' 'ca'
  # MAJOR-1：原实现 `-Filter 'cacert.pem' | Select-Object -First 1` 是「取到哪个算哪个」——
  # 当前安装包内只有 1 个（resources\backend\_internal\certifi\cacert.pem，实测 238,856 B），
  # 但布局一旦变化就会静默取错对象。这里改为**精确路径**，并额外枚举全部匹配项做数量断言。
  $pemPath = Join-Path $installDir 'resources\backend\_internal\certifi\cacert.pem'
  $pemExists = Test-Path -LiteralPath $pemPath
  Record 'CA-0' '后端 PEM 精确路径存在' $pemExists $pemPath

  $allPems = @(Get-ChildItem -LiteralPath $installDir -Recurse -File -Filter 'cacert.pem' -ErrorAction SilentlyContinue)
  Record 'CA-0b' '安装目录仅含 1 个 cacert.pem' ($allPems.Count -eq 1) "count=$($allPems.Count)"

  if ($pemExists) {
    $pemSha = (Get-FileHash -LiteralPath $pemPath -Algorithm SHA256).Hash.ToUpperInvariant()
    $g3 = (Select-String -LiteralPath $pemPath -Pattern 'emSign ECC Root CA - G3' -SimpleMatch | Measure-Object).Count
    Record 'CA-1' '安装目录 PEM = 安全基线' ($pemSha -eq $SafePemSha) $pemSha
    Record 'CA-2' '不含受影响 G3 根' ($g3 -eq 0) "g3_hits=$g3"
  } else {
    Record 'CA-1' '安装目录 PEM = 安全基线' $false "未找到 $pemPath"
    Record 'CA-2' '不含受影响 G3 根' $false "未找到 $pemPath"
  }

  # -------------------------------------------------------------- 7. 卸载
  Step 'Uninstall (/S _?=)' 'uninstall'
  Invoke-Uninstaller $installDir
  Record 'UN-1' '卸载项已删除' ($null -eq (Find-UninstallKey)) $UninstKey
  Record 'UN-2' '后端 exe 已删除' (-not (Test-Path -LiteralPath $newBackend)) $newBackend
  Record 'UN-3' '用户数据保留' (Test-Path -LiteralPath $seedFile) $seedFile
  Record 'UN-4' '数据未被迁址' ((Test-Path -LiteralPath $seedFile) -and ((Get-Sha256 $seedFile) -eq $seedHash)) $seedHash

  # -------------------------------------------------------------- 8. 默认 /S 卸载（P1-2）
  # 上面用的是 `_?=<dir>` 原地模式（可同步等待，但卸载器无法自删）。
  # 这里补测**用户实际使用的默认模式**：不带 _?=，卸载器 fork 到 TEMP 后自删。
  # 判据分级：注册表/主程序/数据必须过；安装目录是否有空目录残留只记录不判失败。
  Step 'Reinstall + default /S uninstall (P1-2)' 'uninstall-default'
  Invoke-Installer $NewExe @("/D=$testDir")
  $u2 = (Get-ChildItem -LiteralPath $testDir -File -Filter 'Uninstall*.exe' -ErrorAction SilentlyContinue |
         Select-Object -First 1).FullName
  Require ($null -ne $u2 -and $u2 -ne '') '重装后未找到卸载器，无法测默认卸载'
  Start-Process -FilePath $u2 -ArgumentList @('/S') | Out-Null   # 默认模式：立即 fork，不阻塞
  $dl = (Get-Date).AddSeconds(180)
  while ($null -ne (Find-UninstallKey)) {
    if ((Get-Date) -gt $dl) { break }
    Start-Sleep -Seconds 2
  }
  Record 'UN5-1' '默认 /S：卸载登记消失' ($null -eq (Find-UninstallKey)) ''
  Record 'UN5-2' '默认 /S：主程序消失' (-not (Test-Path -LiteralPath (Join-Path $installDir 'Job Workbench.exe'))) $installDir
  Record 'UN5-3' '默认 /S：用户数据保留' ((Test-Path -LiteralPath $seedFile) -and ((Get-Sha256 $seedFile) -eq $seedHash)) $seedHash
  $residual = @(Get-ChildItem -LiteralPath $installDir -File -ErrorAction SilentlyContinue | Select-Object -ExpandProperty Name)
  Record 'UN5-4' '默认 /S：安装目录残留清单已记录（允许空目录，逐条列出）' $true `
    ("residual=" + $(if ($residual.Count -gt 0) { $residual -join ',' } else { '<none>' }))

  # P0-1：这里**不再**无条件置 ExitCode=0——退出码由 finally 依据
  # 「无 FAIL / 无 fatal / 收据已写出 / 主流程走完」统一裁决。
  $script:MainFlowCompleted = $true
} catch {
  $script:Fatal = $_.Exception.Message
  Write-Host "`nFATAL($($script:Phase)): $($script:Fatal)" -ForegroundColor Red
} finally {
  $failed = @()   # 先定义，保证下面的退出码裁决不会因 StrictMode 报「变量未定义」
  # ---------------------------------------------------------------- 兜底清理（各步吞错）
  try { Stop-Tree $BackendPort } catch { }
  try {
    # 清理阶段不依赖卸载器文件名（可能是 "Uninstall Job Workbench.exe"），
    # 直接删本脚本创建的测试目录（PF-5 已断言它事先不存在，删除安全）。
    # 注意：只删 $testDir，不动注册表里的 InstallLocation（那是产品的真实安装位置）。
    if ($testDir -and (Test-Path -LiteralPath $testDir)) {
      Remove-Item -LiteralPath $testDir -Recurse -Force -ErrorAction SilentlyContinue
    }
  } catch { }
  try {
    foreach ($k in @($UninstKey, $AppKey)) {
      # $UninstKey 在失败路径上可能仍是 $null（StrictMode 下 Test-Path $null 会抛）
      if ($k -and (Test-Path -LiteralPath $k)) { Remove-Item -LiteralPath $k -Recurse -Force -ErrorAction SilentlyContinue }
    }
  } catch { }

  # ---------------------------------------------------------------- 收据（必须生成）
  try {
    $failed = @($script:Rows | Where-Object { $_.status -eq 'FAIL' })
    # M-5：known_gaps 必须参与**裁决**，不能只是注释文字——有缺口时结论不能是纯 PASS。
    $knownGaps = @(
      'NSIS 向导 UI / UAC 提权 / SmartScreen：未覆盖（静默安装绕过）',
      '真实 Windows 11 客户端体验：未覆盖（runner 为 Windows Server 镜像）',
      'electron-updater 端到端（发现→下载→安装→重启）：未覆盖，属 D′-2，见 DESIGN.md §5',
      '升级中断后的产品恢复行为：未覆盖（重跑 job ≠ 产品回滚）',
      '日志措辞（packaged / python fallback）：未验证——以 RT-5 的「监听者进程路径 == 安装目录后端 exe」作为更强替代证据',
      # 2026-10-23 审计登记：**历史收据的证据边界**（不是当前脚本的缺口，别混读）
      'pypdf/PDF 路径：RT-9-1 已在本脚本实现，但 D′-1 收据（run 39914715729）所用的
       3379bf3 版本脚本没有该段，故那次 45/45 不含 pypdf 证据——需用本脚本补跑一次',
      'D′-1 收据（run 39914715729）的两条判据弱点，本次已修但历史收据仍带此记录：
       UP-4 为空值假阳性（detail " -> "，前后均未读到 MainBinaryName，该断言已删除）；
       RT-8c-3 未先破坏种子文件即 restore（不能证明恢复能力，已改为先破坏后恢复）'
    )
    $conclusion = if ($null -ne $script:Fatal) { 'ERROR' }
                  elseif ($failed.Count -gt 0) { 'FAIL' }
                  elseif ($knownGaps.Count -gt 0) { 'PASS_WITH_GAPS' }
                  else { 'PASS' }
    $receipt = [ordered]@{
      kind         = 'dprime-1-upgrade-installer'
      generated_at = (Get-Date).ToUniversalTime().ToString('o')
      phase_at_end = $script:Phase
      fatal_error  = $script:Fatal
      runner       = $script:RunnerInfo
      inputs       = [ordered]@{ old_sha256 = $script:OldHash; new_sha256 = $script:NewHash }
      install_dir  = $script:InstallDir
      rows         = $script:Rows
      summary      = [ordered]@{
        total      = $script:Rows.Count
        passed     = @($script:Rows | Where-Object { $_.status -eq 'PASS' }).Count
        failed     = $failed.Count
        conclusion = $conclusion
      }
      known_gaps   = $knownGaps
    }
    $dir = Split-Path $ReceiptPath -Parent
    if ($dir -and -not (Test-Path -LiteralPath $dir)) { New-Item -ItemType Directory -Force -Path $dir | Out-Null }
    # 收据自身也必须无 BOM：与 seed 文件同理（M-1）——5.1 的 `-Encoding utf8` 会写 BOM，
    # 下游 JSON 解析器读到 \ufeff 会失败。
    $json = $receipt | ConvertTo-Json -Depth 8
    [System.IO.File]::WriteAllText($ReceiptPath, $json, [System.Text.UTF8Encoding]::new($false))
    $script:ReceiptWritten = $true   # P0-2：收据没写出 = 证据链断裂 = 正式验收失败
    Write-Host "`n收据：$ReceiptPath" -ForegroundColor Cyan
    Write-Host ("结论：{0}（{1}/{2} PASS，fatal={3}）" -f $conclusion, $receipt.summary.passed, $receipt.summary.total, [bool]($null -ne $script:Fatal)) `
      -ForegroundColor $(if ($conclusion -eq 'PASS') { 'Green' } else { 'Red' })
    if ($failed.Count -gt 0) {
      $failed | ForEach-Object { Write-Host ("  - {0} [{1}] {2} :: {3}" -f $_.id, $_.phase, $_.check, $_.detail) -ForegroundColor Red }
    }
  } catch {
    Write-Host "收据写入失败：$($_.Exception.Message)" -ForegroundColor Red
    $script:ReceiptWritten = $false
  }

  # ---------------------------------------------------------------- P0-1 退出码裁决
  # 「PASS_WITH_GAPS」是**有明确已知缺口的成功**，允许 exit 0；
  # 但任一 FAIL / fatal / 收据缺失 / 主流程未走完，正式验收必须失败。
  if ($null -ne $script:Fatal) { $script:ExitCode = 1 }
  elseif ($failed.Count -gt 0) { $script:ExitCode = 1 }
  elseif (-not $script:ReceiptWritten) { $script:ExitCode = 1 }
  elseif (-not $script:MainFlowCompleted) { $script:ExitCode = 1 }
  else { $script:ExitCode = 0 }
  Write-Host ("退出码：{0}（FAIL={1} fatal={2} receipt={3} completed={4}）" -f `
    $script:ExitCode, $failed.Count, [bool]($null -ne $script:Fatal), $script:ReceiptWritten, $script:MainFlowCompleted) `
    -ForegroundColor $(if ($script:ExitCode -eq 0) { 'Green' } else { 'Red' })

  # exit 必须在 finally **内部**：`return`（-FailInjection 走那条路）会让控制流跳过
  # finally 之后的语句，退出码就退回默认 0——失败注入自检正是靠这条抓到过。
  exit $script:ExitCode
}
