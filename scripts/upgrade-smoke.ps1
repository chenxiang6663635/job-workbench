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
  [string] $ReceiptPath = ''
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
$UninstKey    = "HKCU:\Software\Microsoft\Windows\CurrentVersion\Uninstall\{$AppId}"
$AppKey       = "HKCU:\Software\$AppId"
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

function Get-RegDefault([string] $key) {
  if (-not (Test-Path -LiteralPath $key)) { return $null }
  (Get-Item -LiteralPath $key).GetValue('', $null, 'DoNotExpandEnvironmentNames')
}
function Get-RegValue([string] $key, [string] $name) {
  if (-not (Test-Path -LiteralPath $key)) { return $null }
  $item = Get-Item -LiteralPath $key
  if ($item.GetValueNames() -notcontains $name) { return $null }
  $item.GetValue($name, $null, 'DoNotExpandEnvironmentNames')
}

function Get-Listeners([int] $port) {
  @(Get-NetTCPConnection -LocalPort $port -State Listen -ErrorAction SilentlyContinue)
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
  $u = Join-Path $dir 'uninstall.exe'
  Require (Test-Path -LiteralPath $u) "找不到卸载器：$u"
  # NSIS：_?= 必须最后、路径不加引号；否则卸载器 fork 到 TEMP 后立即返回
  Invoke-Installer $u @("_?=$dir")
  $deadline = (Get-Date).AddSeconds($InstallerTimeout)
  while (Test-Path -LiteralPath $u) {
    if ((Get-Date) -gt $deadline) { throw '卸载器未在期限内完成' }
    Start-Sleep -Milliseconds 500
  }
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

  $hasUninst = Test-Path -LiteralPath $UninstKey
  $hasAppKey = Test-Path -LiteralPath $AppKey
  $procs = @(Get-Process -Name 'Job Workbench', 'job-workbench-backend' -ErrorAction SilentlyContinue)
  $dirExists = Test-Path -LiteralPath $testDir
  Record 'PF-2' '无既有卸载登记' (-not $hasUninst) $UninstKey
  Record 'PF-3' '无既有 appId 键' (-not $hasAppKey) $AppKey
  Record 'PF-4' '无相关进程' ($procs.Count -eq 0) "count=$($procs.Count)"
  Record 'PF-5' '测试目录事先不存在' (-not $dirExists) $testDir
  Require ((-not $hasUninst) -and (-not $hasAppKey) -and $procs.Count -eq 0 -and (-not $dirExists)) '环境不干净，拒绝运行（fail-closed）'

  New-Item -ItemType Directory -Force -Path $BaseDir, $wsDir, $appData | Out-Null

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
  $installDir = Get-RegValue $UninstKey 'InstallLocation'
  if ([string]::IsNullOrWhiteSpace($installDir) -or -not (Test-Path -LiteralPath $installDir)) { $installDir = $testDir }
  $script:InstallDir = $installDir

  Record 'IN-1' '旧版版本 = 26.10.0' ((Get-RegValue $UninstKey 'DisplayVersion') -eq '26.10.0') (Get-RegValue $UninstKey 'DisplayVersion')
  $oldBackend = Join-Path $installDir 'resources\backend\job-workbench-backend.exe'
  Record 'IN-2' '安装目录含后端 exe' (Test-Path -LiteralPath $oldBackend) $oldBackend
  Require (Test-Path -LiteralPath $oldBackend) '旧版安装缺后端 exe，无法继续（安装包不完整）'

  $before = @{
    InstDir    = Get-RegDefault $AppKey
    InstLoc    = Get-RegValue $UninstKey 'InstallLocation'
    MainBinary = Get-RegValue $UninstKey 'MainBinaryName'
  }
  Write-Host ("  before: InstDir='{0}' InstLoc='{1}'" -f $before.InstDir, $before.InstLoc) -ForegroundColor DarkGray

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
    Record 'SE-4' '旧版 appVersion 已上报' ([string]::IsNullOrWhiteSpace([string]$paths.appVersion) -eq $false) ([string]$paths.appVersion)
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
    InstDir    = Get-RegDefault $AppKey
    InstLoc    = Get-RegValue $UninstKey 'InstallLocation'
    MainBinary = Get-RegValue $UninstKey 'MainBinaryName'
  }
  Record 'UP-2' 'appId 默认值未变（位置恢复）' ($after.InstDir -ceq $before.InstDir) "$($before.InstDir) -> $($after.InstDir)"
  Record 'UP-3' 'InstallLocation 未变' ($after.InstLoc -ceq $before.InstLoc) "$($before.InstLoc) -> $($after.InstLoc)"
  Record 'UP-4' 'MainBinaryName 未变' ($after.MainBinary -ceq $before.MainBinary) "$($before.MainBinary) -> $($after.MainBinary)"
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

    $logPath = Join-Path $appData 'job-workbench\main.log'
    if (Test-Path -LiteralPath $logPath) {
      $log = Get-Content -LiteralPath $logPath -Raw -Encoding utf8
      Record 'RT-6' '日志含 packaged backend' ($log -match 'Using packaged backend:') ''
      Record 'RT-7' '日志不含 python 回退' (-not ($log -match 'Using python backend:')) ''
    } else {
      Record 'RT-6' '日志含 packaged backend' $false "日志不存在：$logPath"
      Record 'RT-7' '日志不含 python 回退' $false '日志不存在'
    }

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
          $null = Post-Api "/api/system/snapshots/restore?ws=$Workspace" @{ name = $snapName }
          $afterRestore = Get-Content -LiteralPath $seedFile -Raw -Encoding utf8
          Record 'RT-8c-3' '快照恢复后数据仍正确（换行已规范化）' ((Normalize-Text $afterRestore) -eq (Normalize-Text $seedBody)) "len=$($afterRestore.Length)"
        } catch {
          Record 'RT-8c-1' '升级前快照仍可见' $false $_.Exception.Message
          Record 'RT-8c-2' '快照演练（preview）通过' $false '未执行'
          Record 'RT-8c-3' '快照恢复后数据仍正确' $false '未执行'
        }
      } else {
        Record 'RT-8c-1' '升级前快照仍可见' $false '基线快照未创建（见 SE-9）'
        Record 'RT-8c-2' '快照演练（preview）通过' $false '未执行'
        Record 'RT-8c-3' '快照恢复后数据仍正确' $false '未执行'
      }
    } else {
      Record 'RT-8a-1' 'dataRoot = 隔离工作区根' $false '后端未就绪'
      Record 'RT-8b-1' '新版 API 列出种子文件' $false '后端未就绪'
      Record 'RT-8c-1' '升级前快照仍可见' $false '后端未就绪'
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
  Record 'UN-1' '卸载项已删除' (-not (Test-Path -LiteralPath $UninstKey)) $UninstKey
  Record 'UN-2' '后端 exe 已删除' (-not (Test-Path -LiteralPath $newBackend)) $newBackend
  Record 'UN-3' '用户数据保留' (Test-Path -LiteralPath $seedFile) $seedFile
  Record 'UN-4' '数据未被迁址' ((Test-Path -LiteralPath $seedFile) -and ((Get-Sha256 $seedFile) -eq $seedHash)) $seedHash

  $script:ExitCode = 0
} catch {
  $script:Fatal = $_.Exception.Message
  Write-Host "`nFATAL($($script:Phase)): $($script:Fatal)" -ForegroundColor Red
} finally {
  # ---------------------------------------------------------------- 兜底清理（各步吞错）
  try { Stop-Tree $BackendPort } catch { }
  try {
    if ($script:InstallDir -and (Test-Path -LiteralPath (Join-Path $script:InstallDir 'uninstall.exe'))) {
      $u = Join-Path $script:InstallDir 'uninstall.exe'
      Start-Process -FilePath $u -ArgumentList @('/S', "_?=$($script:InstallDir)") -Wait -ErrorAction SilentlyContinue
     } } catch { }
  try {
    foreach ($k in @($UninstKey, $AppKey)) {
      if (Test-Path -LiteralPath $k) { Remove-Item -LiteralPath $k -Recurse -Force -ErrorAction SilentlyContinue }
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
      'PDF 导入/文本提取：本版脚本未实现，登记为缺口'
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
    Write-Host "`n收据：$ReceiptPath" -ForegroundColor Cyan
    Write-Host ("结论：{0}（{1}/{2} PASS，fatal={3}）" -f $conclusion, $receipt.summary.passed, $receipt.summary.total, [bool]($null -ne $script:Fatal)) `
      -ForegroundColor $(if ($conclusion -eq 'PASS') { 'Green' } else { 'Red' })
    if ($failed.Count -gt 0) {
      $failed | ForEach-Object { Write-Host ("  - {0} [{1}] {2} :: {3}" -f $_.id, $_.phase, $_.check, $_.detail) -ForegroundColor Red }
    }
  } catch {
    Write-Host "收据写入失败：$($_.Exception.Message)" -ForegroundColor Red
  }
}

exit $script:ExitCode
