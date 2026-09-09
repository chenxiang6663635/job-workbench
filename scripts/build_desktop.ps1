# 一键构建 Windows 桌面安装包（求职工作台 Setup *.exe）
# 链路：前端 dist → PyInstaller 后端 exe（含前端同源托管组装）→ electron-builder NSIS
# 产物：web/electron/dist/求职工作台 Setup <版本>.exe（+ blockmap）
# 前置：目标 Python 环境需含 fastapi/uvicorn/PyInstaller（探测逻辑同 build_backend_exe.ps1）
# 用法：powershell -ExecutionPolicy Bypass -File scripts/build_desktop.ps1 [-Py "D:\path\python.exe"]
# 冒烟：Setup.exe /S /D=<目录> 静默安装 → 启动 → 验证 http://127.0.0.1:8765 → Uninstall /S
param(
    [string]$Py = ""
)

$ErrorActionPreference = "Stop"
$root = Split-Path -Parent $PSScriptRoot

Write-Host "=== 求职工作台 · 桌面安装包构建 ===" -ForegroundColor Cyan

# 1. 后端 exe（脚本内部：前端 dist 复用/构建 → PyInstaller → 组装 portable 目录）
& powershell -ExecutionPolicy Bypass -File (Join-Path $PSScriptRoot "build_backend_exe.ps1") -Py $Py
if ($LASTEXITCODE -ne 0) {
    Write-Host "后端 exe 构建失败，终止" -ForegroundColor Red
    exit 1
}

# 2. electron-builder NSIS（首次运行会下载 NSIS/winCodeSign 资源）
Push-Location (Join-Path $root "web\electron")
& npm.cmd run dist
$code = $LASTEXITCODE
Pop-Location
if ($code -ne 0) {
    Write-Host "electron-builder 打包失败，终止" -ForegroundColor Red
    Write-Host "已知坑：winCodeSign 缓存解压因 darwin 符号链接失败（非管理员无建链权限）——" -ForegroundColor Yellow
    Write-Host "用自带 7za 手动解压 %LOCALAPPDATA%\electron-builder\Cache\winCodeSign\<hash>.7z 到 winCodeSign-2.6.0/ 即可跳过" -ForegroundColor Yellow
    exit 1
}

# 3. 产物清单
Write-Host "=== 桌面安装包构建完成 ===" -ForegroundColor Green
Get-ChildItem (Join-Path $root "web\electron\release") -Filter "*.exe" |
    ForEach-Object { Write-Host ("  {0}  ({1:N1} MB)" -f $_.Name, ($_.Length / 1MB)) }
