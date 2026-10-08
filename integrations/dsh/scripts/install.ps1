## =============================================================================
# job-workbench × DeepSeek Harness（DSH）——一键安装 / 迁移脚本（#271 P2-3）
#
# 通过官方 CLI 安装 npm 包并自动挂载：
#   dsh plugin --profile <p> add dsh-job-workbench[@版本]
# 包内声明 dsh.bundle.patch（cordis.patch.yml）：CLI 的 bundle 协调会把它写进
# profile 的 dsh.profile.bundles，下次启动即挂载——无需手改 profile 的 patch 文件。
#
# 另做两件「安装体验」保障（均幂等，可反复跑）：
#   1) 预写 pnpm-workspace.yaml 的 minimumReleaseAgeExclude（pnpm 11 对发布不足 24h
#      的版本执行隔离——首发当日安装会被拦；放行本包与平台子包，免「重跑一次才成功」。
#      依据：本机 dsh-better-sidebar 同款先例（scripts/install.ps1，0.24.1）。
#   2) 幂等移除第一阶段（bundle 通道之前）手抄进 profile cordis.patch.yml 的
#      mcp-jobws / preset-jobws 挂载行——否则与 bundle 双挂载（同 serverName
#      注册两次）。删除前先写 .bak-<时间戳> 备份；没有旧行时不做任何事。
#
# 用法（任选其一）：
#   # 默认装到 desktop profile、装最新版：
#   $script = (irm 'https://raw.githubusercontent.com/chenxiang6663635/job-workbench/main/integrations/dsh/scripts/install.ps1').TrimStart([char]0xFEFF)
#   & ([scriptblock]::Create($script))
#   # 指定版本 / profile / 只看计划：
#   & ([scriptblock]::Create($script)) -Version 26.11.0 -Profile web -DryRun
#   # 本地保存后运行：
#   powershell -ExecutionPolicy Bypass -File install.ps1 -Profile desktop
#
# 参数：
#   -Version     npm 版本号（缺省 latest，由 pnpm 解析）
#   -Profile     目标 profile 名（缺省 desktop）
#   -DryRun      只打印将要执行的操作，不写任何文件
#   -SkipInstall 只做「工作区放行 + 旧挂载行迁移清理」，不装包
#
# 环境变量（均可省略）：
#   DSH_HOME  默认 %USERPROFILE%\.dsh（本机实际以环境变量为准）
#   DSH_CMD   指定 dsh 可执行文件；缺省优先 PATH 上的 dsh，回退
#             npx -y --package @deepseek-ai/dsh
#
# 两处纪律（照抄本仓库 scripts/build_*.ps1 的经验，并有 2026-10-07 实证）：
#   - 不设 $ErrorActionPreference = Stop：PS 5.1 下原生命令的 stderr 会以
#     NativeCommandError 终止脚本，人话提示永远走不到；一律显式检查 $LASTEXITCODE。
#   - 不用 exit 关键字结束：scriptblock 形态（上面的 irm 用法）下 exit 会**终止整个
#     用户会话**（实证）。改为 throw + 顶层 catch——-File 形态置非零退出码，
#     scriptblock 形态只中止脚本块、不杀会话。($PSScriptRoot 仅用于区分这两种形态。)
## =============================================================================
param(
  [string]$Version = '',
  [string]$Profile = 'desktop',
  [switch]$DryRun,
  [switch]$SkipInstall
)

$PKG = 'dsh-job-workbench'
$PKG_PLATFORM = 'dsh-job-workbench-win32-x64'

function Say([string]$m)  { Write-Host "[install] $m" -ForegroundColor Green }
function Warn([string]$m) { Write-Host "[warn] $m" -ForegroundColor Yellow }
function Die([string]$m)  { Write-Host "[error] $m" -ForegroundColor Red; throw 'installer-die' }

# --- 解析 DSH_HOME / profile 路径 -------------------------------------------
if ($env:DSH_HOME) {
  $DSH_HOME = $env:DSH_HOME
} elseif ($env:USERPROFILE) {
  $DSH_HOME = Join-Path $env:USERPROFILE '.dsh'
} else {
  $DSH_HOME = Join-Path $HOME '.dsh'
}
$PROFILE_DIR = Join-Path $DSH_HOME "profiles\$Profile"
$WS_YML = Join-Path $PROFILE_DIR 'pnpm-workspace.yaml'
$PATCH_YML = Join-Path $PROFILE_DIR 'cordis.patch.yml'
$PKG_JSON = Join-Path $PROFILE_DIR 'package.json'

# --- 解析 dsh CLI（env DSH_CMD > PATH 上的 dsh > npx 回退） ------------------
function Get-DshCli {
  if ($env:DSH_CMD) {
    $found = Get-Command $env:DSH_CMD -ErrorAction SilentlyContinue
    if ($found) { return [string]$env:DSH_CMD }
    Warn "环境变量 DSH_CMD 指向的命令不存在：$env:DSH_CMD（忽略，继续探测）"
  }
  if (Get-Command dsh -ErrorAction SilentlyContinue) { return 'dsh' }
  if (Get-Command npx -ErrorAction SilentlyContinue) { return 'npx' }
  return $null
}

# --- 步骤 1：minimumReleaseAgeExclude（幂等）--------------------------------
function Ensure-MinimumReleaseAgeExclude {
  if (-not (Test-Path $WS_YML)) { return 'missing' }
  $raw = [IO.File]::ReadAllText($WS_YML)
  $nl = "`n"
  if ($raw.Contains("`r`n")) { $nl = "`r`n" }
  $lines = @($raw -split "`r?`n")

  $present = @{}
  foreach ($l in $lines) {
    if ($l -match '^\s*-\s*(dsh-job-workbench(?:-win32-x64)?)(?:@\S+)?\s*$') {
      $present[$Matches[1]] = $true
    }
  }
  $need = @()
  foreach ($n in @($PKG, $PKG_PLATFORM)) {
    if (-not $present.ContainsKey($n)) { $need += $n }
  }
  if ($need.Count -eq 0) { return 'ready' }
  if ($DryRun) { return ('would-add:' + ($need -join ',')) }

  $out = New-Object System.Collections.Generic.List[string]
  $inserted = $false
  foreach ($l in $lines) {
    $out.Add($l)
    if (-not $inserted -and $l -match '^\s*minimumReleaseAgeExclude:\s*$') {
      foreach ($n in $need) { $out.Add('  - ' + $n) }
      $inserted = $true
    }
  }
  if (-not $inserted) {
    while ($out.Count -gt 0 -and $out[$out.Count - 1] -eq '') { $out.RemoveAt($out.Count - 1) }
    $out.Add('')
    $out.Add('minimumReleaseAgeExclude:')
    foreach ($n in $need) { $out.Add('  - ' + $n) }
    $out.Add('')
  }
  [IO.File]::WriteAllText($WS_YML, ($out -join $nl), (New-Object System.Text.UTF8Encoding $false))
  return ('updated:' + ($need -join ','))
}

# --- 步骤 3：幂等移除旧挂载行（带备份）--------------------------------------
function Remove-LegacyJobwsMounts {
  if (-not (Test-Path $PATCH_YML)) { return 'missing' }
  $raw = [IO.File]::ReadAllText($PATCH_YML)
  $nl = "`n"
  if ($raw.Contains("`r`n")) { $nl = "`r`n" }
  $lines = @($raw -split "`r?`n")

  $out = New-Object System.Collections.Generic.List[string]
  $removed = 0
  $i = 0
  while ($i -lt $lines.Count) {
    $line = $lines[$i]
    if ($line -match '^[ \t]*- insert:\s*$') {
      # 收集本 insert 块：到空行或下一个顶层 `- ` 项为止
      $j = $i + 1
      $block = New-Object System.Collections.Generic.List[string]
      $block.Add($line)
      while ($j -lt $lines.Count -and $lines[$j].Trim() -ne '' -and $lines[$j] -notmatch '^-\s') {
        $block.Add($lines[$j])
        $j++
      }
      $isLegacy = $false
      foreach ($bl in $block) {
        if ($bl -match 'id:\s*(mcp-jobws|preset-jobws)\b') { $isLegacy = $true; break }
      }
      if ($isLegacy) {
        # 收敛块上方紧邻的 jobws 相关注释行（保守匹配，避免误删用户的无关注释）
        while ($out.Count -gt 0 -and
               $out[$out.Count - 1] -match '^[ \t]*#' -and
               $out[$out.Count - 1] -match 'jobws|job-workbench|求职') {
          $out.RemoveAt($out.Count - 1)
        }
        $i = $j
        $removed++
        continue
      }
    }
    $out.Add($line)
    $i++
  }

  if ($removed -eq 0) {
    # 残留探测：文件里仍提到旧行标识但没匹配到可移除的 insert 块 → 交人工检查
    if ($raw -match 'mcp-jobws|preset-jobws') { return 'residual' }
    return 'none'
  }
  if ($DryRun) { return ('would-remove:' + $removed) }

  $bak = $PATCH_YML + '.bak-' + (Get-Date -Format 'yyyyMMdd-HHmmss')
  [IO.File]::Copy($PATCH_YML, $bak, $false)
  $text = $out -join $nl
  $text = [regex]::Replace($text, '(\r?\n){3,}', ($nl + $nl))
  [IO.File]::WriteAllText($PATCH_YML, $text, (New-Object System.Text.UTF8Encoding $false))
  return ('removed:' + $removed + ':' + $bak)
}

# ================================ 主流程 ====================================
try {
  Write-Host "=== job-workbench × DSH 安装脚本 ===" -ForegroundColor Cyan
  Write-Host "DSH_HOME : $DSH_HOME"
  Write-Host "profile  : $Profile"
  if ($DryRun) { Warn 'dry-run 模式：只打印计划，不写任何文件' }

  if (-not (Test-Path $PROFILE_DIR)) {
    Die "找不到 profile 目录：$PROFILE_DIR（先用 DSH 桌面端或 dsh web 跑过一次，让 profile 初始化）"
  }

  $cli = Get-DshCli
  if (-not $SkipInstall -and -not $cli) {
    Die '未找到 dsh 或 npx：请先用 DSH 桌面端装好命令（或安装 Node.js 以便走 npx 回退，或用 DSH_CMD 指定 dsh 路径）'
  }
  $spec = $PKG
  if ($Version) { $spec = $PKG + '@' + $Version }
  Say "目标：$cli plugin --profile $Profile add $spec（profile: $PROFILE_DIR）"

  # --- 步骤 1：工作区放行 ----------------------------------------------------
  $wsState = Ensure-MinimumReleaseAgeExclude
  if ($wsState -eq 'missing') {
    Warn "未找到 $WS_YML：跳过 minimumReleaseAge 放行。若稍后安装被 24h 隔离政策拦截，把 $PKG 与 $PKG_PLATFORM 加进该文件的 minimumReleaseAgeExclude 后重试"
  } elseif ($wsState -eq 'ready') {
    Say 'minimumReleaseAgeExclude 已就绪，跳过'
  } elseif ($wsState -eq 'updated') {
    Say "已写入 minimumReleaseAgeExclude（$($wsState.Substring(8))）"
  } elseif ($wsState -like 'would-add:*') {
    Say "[dry-run] 将写入 minimumReleaseAgeExclude：$($wsState.Substring(10))"
  }

  # --- 步骤 2：官方 CLI 安装 + 挂载注册 -------------------------------------
  if ($SkipInstall) {
    Warn '已指定 -SkipInstall：跳过装包（只做工作区放行与迁移清理）'
  } elseif ($DryRun) {
    Say "[dry-run] 步骤 2：执行 $cli plugin --profile $Profile add $spec（安装 + bundle 自动注册）"
  } else {
    if ($cli -eq 'npx') {
      & npx -y --package '@deepseek-ai/dsh' dsh plugin --profile $Profile add $spec
    } else {
      & $cli plugin --profile $Profile add $spec
    }
    if ($LASTEXITCODE -ne 0) {
      Warn 'dsh plugin add 失败。已预写 minimumReleaseAgeExclude；仍失败的可能原因：'
      Warn '  - 网络 / registry 不可达；'
      Warn "  - pnpm 依赖冲突：可手动重试 cd $PROFILE_DIR; pnpm install"
      Die '安装未完成'
    }
    # 校验挂载注册（bundle 生效的判据）
    $pkgJson = $null
    try { $pkgJson = Get-Content -Raw $PKG_JSON -Encoding UTF8 | ConvertFrom-Json } catch { }
    $bundles = @()
    if ($pkgJson -and $pkgJson.dsh -and $pkgJson.dsh.profile -and $pkgJson.dsh.profile.bundles) {
      $bundles = @($pkgJson.dsh.profile.bundles)
    }
    if ($bundles -notcontains $PKG) {
      Die "$PKG 未出现在 dsh.profile.bundles 中——挂载未注册，请检查上面的 pnpm 输出后重跑"
    }
    Say "bundle 已注册：dsh.profile.bundles 包含 $PKG（重启 DSH 后装载）"
  }

  # --- 步骤 3：幂等迁移（旧手工挂载行）--------------------------------------
  $migState = Remove-LegacyJobwsMounts
  if ($migState -eq 'missing') {
    Say "无 $PATCH_YML（没有手工挂载行，跳过迁移）"
  } elseif ($migState -eq 'none') {
    Say '无旧手动挂载行，跳过'
  } elseif ($migState -eq 'residual') {
    Warn "$PATCH_YML 里仍提到 mcp-jobws / preset-jobws，但没匹配到可移除的 insert 块——请人工检查该文件，避免与 bundle 双挂载"
  } elseif ($migState -like 'would-remove:*') {
    Say "[dry-run] 将从 cordis.patch.yml 移除 $(($migState -split ':')[1]) 个旧的手工挂载 insert 块（未写入）"
  } elseif ($migState -like 'removed:*') {
    # Split 限 3 段：备份路径含盘符冒号，不能全切
    $parts = $migState.Split(':', 3)
    Say "已从 cordis.patch.yml 移除 $($parts[1]) 个旧手工挂载块（bundle 通道接管挂载）"
    Say "备份：$($parts[2])"
  }

  # --- 收尾提示 --------------------------------------------------------------
  if ($DryRun) {
    Say 'dry-run 结束：以上是完整计划'
  } else {
    Say "安装完成：$spec"
    Say '下一步：重启 DSH（桌面端退出重开；web 形态 pm2 restart dsh-web 或重启 dsh web），让新 bundle 装载'
    Say '验收：会话里应能看到含 jobws 的工具；技能清单出现 9 个 jwb-*（详见本目录 README 验收清单）'
    Say '卸载：dsh plugin --profile <p> remove dsh-job-workbench（数据零影响）'
  }
} catch {
  if ($_.Exception.Message -ne 'installer-die') {
    Write-Host "[error] 未预期错误：$($_.Exception.Message)" -ForegroundColor Red
  }
  if ($PSScriptRoot) {
    exit 1
  }
  Write-Host '[install] 已中止（scriptblock 形态不设进程退出码；需要退出码请用 -File 运行）' -ForegroundColor Yellow
}
