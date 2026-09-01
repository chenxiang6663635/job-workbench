# 求职工作台 Web 一键启动脚本
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

Write-Host "=== 求职工作台 Web 启动 ===" -ForegroundColor Cyan

# 端口若已占用则先释放，避免"Address already in use"
foreach ($port in 8765, 5173) {
    $conns = Get-NetTCPConnection -LocalPort $port -State Listen -ErrorAction SilentlyContinue
    foreach ($c in $conns) {
        Write-Host "  释放端口 $port (PID $($c.OwningProcess))" -ForegroundColor Yellow
        try {
            Stop-Process -Id $c.OwningProcess -Force -ErrorAction Stop
        } catch {
            Write-Host "  无法释放端口 $port：$($_.Exception.Message)" -ForegroundColor Red
            Write-Host "  端口可能被其他程序占用。请关闭占用该端口的程序后重试，或修改端口配置。" -ForegroundColor Red
            exit 1
        }
    }
}
Start-Sleep -Seconds 1

# 依赖预检：后端需 python，前端需 node/npm。缺失时给出明确提示而非裸报错。
Write-Host "检查运行依赖..." -ForegroundColor Cyan
if (-not (Get-Command "python" -ErrorAction SilentlyContinue)) {
    Write-Host "错误：未找到 python。请安装 Python 3.8+ 并加入 PATH。" -ForegroundColor Red
    exit 1
}
if (-not (Get-Command "node" -ErrorAction SilentlyContinue)) {
    Write-Host "错误：未找到 node。前端（Vite）依赖 Node.js，请先安装 Node.js 18+。" -ForegroundColor Red
    exit 1
}
if (-not (Get-Command "npm.cmd" -ErrorAction SilentlyContinue) -and -not (Get-Command "npm" -ErrorAction SilentlyContinue)) {
    Write-Host "错误：未找到 npm。前端依赖 npm 启动，请确认 Node.js 安装完整。" -ForegroundColor Red
    exit 1
}

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
    Write-Host "错误：后端（FastAPI 8765）启动失败或超时。" -ForegroundColor Red
    # 检查端口是否又被占用
    $occ = Get-NetTCPConnection -LocalPort 8765 -State Listen -ErrorAction SilentlyContinue
    if ($occ) {
        Write-Host "  端口 8765 被占用（PID $($occ.OwningProcess)）。若被其他服务占用，请先关闭它再重试。" -ForegroundColor Red
    }
    Write-Host "  手动排查：cd web\backend && python -m uvicorn main:app --port 8765" -ForegroundColor Yellow
    exit 1
}

# 等待前端就绪
$frontendReady = $false
for ($i = 0; $i -lt 30; $i++) {
    Start-Sleep -Seconds 1
    try {
        $r = Invoke-WebRequest "http://127.0.0.1:5173/" -TimeoutSec 2 -UseBasicParsing
        if ($r.StatusCode -eq 200) { $frontendReady = $true; break }
    } catch {}
}

if (-not $frontendReady) {
    Write-Host "错误：前端（Vite 5173）启动失败或超时。" -ForegroundColor Red
    # 区分失败原因
    $occF = Get-NetTCPConnection -LocalPort 5173 -State Listen -ErrorAction SilentlyContinue
    if ($occF) {
        Write-Host "  端口 5173 被占用（PID $($occF.OwningProcess)）。请关闭占用该端口的程序后重试。" -ForegroundColor Red
    } else {
        Write-Host "  端口 5173 未监听。可能原因：" -ForegroundColor Yellow
        Write-Host "    1) npm install 未执行（首次运行需在 web/frontend 下执行 npm install）" -ForegroundColor Yellow
        Write-Host "    2) Vite 编译报错（切换到 web/frontend 手动运行 npm run dev 查看错误）" -ForegroundColor Yellow
        Write-Host "    3) node 版本过低（需 Node.js 18+）" -ForegroundColor Yellow
    }
    exit 1
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
