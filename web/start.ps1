# 秋招工作台 Web 一键启动脚本
#
# 用法（PowerShell）：
#   cd <仓库目录>\web
#   .\start.ps1
#
# 同时启动后端（FastAPI 8765）与前端（Vite 5173），等待就绪后自动打开浏览器。
# 关闭脚本窗口会终止两个服务。

# param 必须是脚本第一条可执行语句（PowerShell 语法要求），不能放在赋值之后
param([string]$RepoRoot = "")

$ErrorActionPreference = "Continue"

# ── 仓库根定位 ──────────────────────────────────────────────
# 三层回退：-RepoRoot 参数 → $PSScriptRoot → 从当前目录向上找 AGENTS.md。
# 必须做多级回退：$PSScriptRoot 在 Start-Job 等调用方式下可能为空；
# $MyInvocation.MyCommand.Definition 更不可靠（曾返回脚本全文导致 Join-Path 崩溃）。

function Find-RepoRoot {
    # 1) 显式参数
    if ($RepoRoot -and (Test-Path (Join-Path $RepoRoot "AGENTS.md"))) {
        return $RepoRoot
    }
    # 2) 脚本所在目录的上一级（start.ps1 在 web/ 下）
    if ($PSScriptRoot) {
        $candidate = Split-Path -Parent $PSScriptRoot
        if (Test-Path (Join-Path $candidate "AGENTS.md")) { return $candidate }
    }
    # 3) 从当前目录逐级向上找 AGENTS.md（仓库标记文件）
    $dir = (Get-Location).Path
    while ($dir) {
        if (Test-Path (Join-Path $dir "AGENTS.md")) { return $dir }
        $parent = Split-Path -Parent $dir
        if ($parent -eq $dir) { break }
        $dir = $parent
    }
    return $null
}

$root = Find-RepoRoot
if (-not $root) {
    Write-Host "错误：无法定位仓库根（未找到 AGENTS.md 标记文件）。" -ForegroundColor Red
    Write-Host "请在仓库目录内运行本脚本，或用 -RepoRoot <路径> 指定仓库位置。" -ForegroundColor Red
    exit 1
}
# Find-RepoRoot 返回仓库根；后端与前端在 web/ 子目录下
$backend = Join-Path $root "web\backend"
$frontend = Join-Path $root "web\frontend"

if (-not (Test-Path (Join-Path $backend "main.py"))) {
    Write-Host "错误：在 $backend 下找不到 main.py" -ForegroundColor Red
    exit 1
}

Write-Host "=== 秋招工作台 Web 启动 ===" -ForegroundColor Cyan

# 端口若已占用则先释放，避免"Address already in use"
foreach ($port in 8765, 5173) {
    $conns = Get-NetTCPConnection -LocalPort $port -State Listen -ErrorAction SilentlyContinue
    foreach ($c in $conns) {
        Write-Host "  释放端口 $port (PID $($c.OwningProcess))" -ForegroundColor Yellow
        Stop-Process -Id $c.OwningProcess -Force -ErrorAction SilentlyContinue
    }
}
Start-Sleep -Seconds 1

# 启动后端
Write-Host "启动后端 FastAPI (8765)..." -ForegroundColor Cyan
$backendProc = Start-Process -FilePath "python" `
    -ArgumentList "-m", "uvicorn", "main:app", "--host", "127.0.0.1", "--port", "8765" `
    -WorkingDirectory $backend -PassThru -WindowStyle Minimized

# 启动前端（Windows 下必须用 npm.cmd，直接跑 npm 会静默失败）
Write-Host "启动前端 Vite (5173)..." -ForegroundColor Cyan
$frontendProc = Start-Process -FilePath "npm.cmd" `
    -ArgumentList "run", "dev" `
    -WorkingDirectory $frontend -PassThru -WindowStyle Minimized

# 等待后端就绪
Write-Host "等待服务就绪..." -ForegroundColor Cyan
$ready = $false
for ($i = 0; $i -lt 30; $i++) {
    Start-Sleep -Seconds 1
    try {
        $r = Invoke-WebRequest "http://127.0.0.1:8765/api/health" -TimeoutSec 2 -UseBasicParsing
        if ($r.StatusCode -eq 200) { $ready = $true; break }
    } catch {}
}

if (-not $ready) {
    Write-Host "后端启动失败，请手动检查：cd web\backend && python -m uvicorn main:app --port 8765" -ForegroundColor Red
    exit 1
}

# 等待前端就绪
for ($i = 0; $i -lt 30; $i++) {
    Start-Sleep -Seconds 1
    try {
        $r = Invoke-WebRequest "http://127.0.0.1:5173/" -TimeoutSec 2 -UseBasicParsing
        if ($r.StatusCode -eq 200) { break }
    } catch {}
}

Write-Host ""
Write-Host "=== 启动完成 ===" -ForegroundColor Green
Write-Host "  前端界面: http://localhost:5173" -ForegroundColor Green
Write-Host "  后端接口: http://localhost:8765" -ForegroundColor Green
Write-Host "  API 文档: http://localhost:8765/docs" -ForegroundColor Green
Write-Host ""
Write-Host "关闭本窗口将终止两个服务。" -ForegroundColor Yellow

Start-Process "http://localhost:5173"

Write-Host "按 Ctrl+C 或关闭窗口停止服务..." -ForegroundColor Gray
try {
    Wait-Process -Id $backendProc.Id, $frontendProc.Id
} catch {
    Write-Host "服务已停止。" -ForegroundColor Yellow
}
