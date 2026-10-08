# 打包 DSH bundle（#271 P2-1）：技能镜像同步 → 校验 → （可选）npm pack 预演
#
# 产出/保证：
#   integrations/dsh/skills/   随包技能镜像（唯一真源 = 仓库 skills/，--prune 清旧件）
#   校验三件套                skills check（合规 + 版本一致）/ four-ends（镜像零漂移）
#
# 用法：powershell -ExecutionPolicy Bypass -File scripts/build_dsh_bundle.ps1 [-Pack]
#      需要指定 Python 时用 -Py "D:\path\to\python.exe"（默认 env:JOBWS_PYTHON → PATH python）
param(
    [string]$Py = "",
    [switch]$Pack
)

$ErrorActionPreference = "Stop"
# scripts/ 的上一级即仓库根
$root = Split-Path -Parent $PSScriptRoot
$pkg = Join-Path $root "integrations\dsh"

if (-not $Py) { $Py = $env:JOBWS_PYTHON }
if (-not $Py) { $Py = "python" }

Write-Host "=== DSH bundle 构建（dsh-job-workbench）===" -ForegroundColor Cyan

# 1. 技能镜像：唯一真源 skills/ → 随包镜像 integrations/dsh/skills/。
#    --prune 把真源已删的旧技能从镜像清掉（多出/缺件/漂移另有 four-ends 检查兜底）。
Write-Host "[1/3] 同步技能镜像（skills/ -> integrations/dsh/skills/）"
& $Py (Join-Path $root "tools\jobws.py") skills install --target dsh --prune
if ($LASTEXITCODE -ne 0) { throw "技能镜像同步失败（exit=$LASTEXITCODE）" }

# 2. 校验：技能合规 / 插件清单与 DSH bundle 版本一致 / 镜像与真源零漂移。
Write-Host "[2/3] 校验（skills check + four-ends 镜像）"
& $Py (Join-Path $root "tools\jobws.py") skills check
if ($LASTEXITCODE -ne 0) { throw "skills check 失败" }
& $Py (Join-Path $root "tools\jobws.py") lint four-ends
if ($LASTEXITCODE -ne 0) { throw "four-ends 镜像检查失败" }

# 3. （可选）npm pack 预演：打出 tarball 清单供人工核对随包文件（不真正发布）。
if ($Pack) {
    Write-Host "[3/3] npm pack 预演（--dry-run）"
    Push-Location $pkg
    try {
        npm pack --dry-run 2>&1 | Select-Object -Last 40
    } finally {
        Pop-Location
    }
} else {
    Write-Host "[3/3] 跳过 npm pack（加 -Pack 预演）"
}

Write-Host "OK：bundle 已就绪（$pkg）" -ForegroundColor Green
