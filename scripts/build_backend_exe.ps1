# 一键构建求职工作台后端 exe（PyInstaller onedir）
# 产出：web/backend/dist/job-workbench-backend/
#   job-workbench-backend.exe   后端入口（免 Python）
#   tools/                      后端 import 的脚本（随包，兼容 CLI 探测）
#   dist/                       前端静态产物（同源托管）
#   personal/                   用户工作区（便携模式数据目录）
#   portable.txt                便携标记（允许用 exe 旁目录存数据）
#
# 用法：powershell -ExecutionPolicy Bypass -File scripts/build_backend_exe.ps1

param(
    [string]$Py = "python"
)

$ErrorActionPreference = "Stop"
# scripts/ 的上一级即仓库根
$root = Split-Path -Parent $PSScriptRoot
$backend = Join-Path $root "web\backend"
$frontend = Join-Path $root "web\frontend"

Write-Host "=== 求职工作台 · 构建后端 exe ===" -ForegroundColor Cyan

# 1. 构建前端 dist（若存在 dist 则复用，否则先 build）
$frontendDist = Join-Path $frontend "dist"
if (-not (Test-Path (Join-Path $frontendDist "index.html"))) {
    Write-Host "构建前端 dist..." -ForegroundColor Yellow
    Push-Location $frontend
    & npm.cmd run build
    if ($LASTEXITCODE -ne 0) { Write-Host "前端构建失败" -ForegroundColor Red; Pop-Location; exit 1 }
    Pop-Location
}

# 2. PyInstaller 打包后端（onedir）
Write-Host "PyInstaller 打包后端..." -ForegroundColor Yellow
Push-Location $backend
& $Py -m PyInstaller --clean --noconfirm pyinstaller.spec
if ($LASTEXITCODE -ne 0) { Write-Host "PyInstaller 打包失败" -ForegroundColor Red; Pop-Location; exit 1 }
Pop-Location

# 3. 整理产物
$exeDir = Join-Path $backend "dist\job-workbench-backend"
$targetDist = Join-Path $exeDir "dist"

# 拷贝前端 dist 到 exe 同级
if (Test-Path $targetDist) { Remove-Item $targetDist -Recurse -Force }
Copy-Item $frontendDist $targetDist -Recurse

# 便携标记
if (-not (Test-Path (Join-Path $exeDir "portable.txt"))) {
    Set-Content -Path (Join-Path $exeDir "portable.txt") -Value "portable mode: personal/ lives next to exe"
}

# 空 personal 目录（首次运行由后端初始化；存在即用）
if (-not (Test-Path (Join-Path $exeDir "personal"))) {
    New-Item -ItemType Directory -Path (Join-Path $exeDir "personal") | Out-Null
}

Write-Host "=== 构建完成 ===" -ForegroundColor Green
Write-Host "产物目录: $exeDir"
$sizeMB = (Get-ChildItem $exeDir -Recurse | Measure-Object -Property Length -Sum).Sum / 1MB
Write-Host ("大小: {0:N1} MB" -f $sizeMB)
Write-Host "验证: 运行 $exeDir\job-workbench-backend.exe，访问 http://127.0.0.1:8765"
