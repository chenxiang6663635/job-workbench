# 一键构建求职工作台后端 exe（PyInstaller onedir）
# 产出：web/backend/dist/job-workbench-backend/
#   job-workbench-backend.exe   后端入口（免 Python）
#   tools/                      后端 import 的脚本（随包，兼容 CLI 探测）
#   dist/                       前端静态产物（同源托管）
#   personal/                   用户工作区（便携模式数据目录）
#   portable.txt                便携标记（允许用 exe 旁目录存数据）
#
# 用法：powershell -ExecutionPolicy Bypass -File scripts/build_backend_exe.ps1
#      需要指定 Python 时用 -Py "D:\path\to\python.exe"

param(
    # 留空则自动探测：项目 .venv > 当前激活的 conda 环境 > PATH python；多环境时建议 -Py 显式指定
    [string]$Py = ""
)

$ErrorActionPreference = "Stop"
# scripts/ 的上一级即仓库根
$root = Split-Path -Parent $PSScriptRoot
$backend = Join-Path $root "web\backend"
$frontend = Join-Path $root "web\frontend"

Write-Host "=== 求职工作台 · 构建后端 exe ===" -ForegroundColor Cyan

# 依赖是否齐（fastapi/uvicorn/pydantic/PyInstaller）。**只在解释器探测里用**，
# 复用下方构建前校验的前提：EAP 局部降为 Continue，只看退出码。
# 别探 filelock：它是仓内模块（web/backend/filelock.py），从仓库根 import 会命中
# 同名 PyPI 包，误报/漏报都出现过。
function Test-PyDeps([string]$pyPath) {
    $prevEap = $ErrorActionPreference
    $ErrorActionPreference = "Continue"
    & $pyPath -c "import fastapi, uvicorn, pydantic, PyInstaller" 2>$null
    $code = $LASTEXITCODE
    $ErrorActionPreference = $prevEap
    return ($code -eq 0)
}

# 0. 解释器探测：脚本内裸调 "python" 会因 PATH 解析差异落到别的环境（教训：base 环境抢跑）。
#    **存在性不等于可用**：本机常见的坏状态是「CONDA_PREFIX 指向 base，PATH 里的 python
#    却在另一个 conda 环境」——按存在性探测会选中 base，然后报「缺少依赖」，把排查引到
#    错误方向（2026-09-13 实测：探测到 base，而依赖在 envs\pytorch）。所以候选逐个
#    **验证依赖**，第一个满足的胜出；全都不满足时再扫 conda 环境列表兜底，并打印用的是谁。
function Resolve-PyPath() {
    $venvPy = Join-Path $root ".venv\Scripts\python.exe"
    $condaPy = if ($env:CONDA_PREFIX) { Join-Path $env:CONDA_PREFIX "python.exe" } else { "" }
    $candidates = @()
    if (Test-Path $venvPy) { $candidates += $venvPy }
    if ($condaPy -and (Test-Path $condaPy)) { $candidates += $condaPy }
    $candidates += "python"   # PATH 解析

    foreach ($cand in $candidates) {
        if (Test-PyDeps $cand) { return $cand }
    }

    # 兜底：扫 conda 环境列表（「base 抢跑、依赖在别的环境」的正解）
    if (Get-Command conda -ErrorAction SilentlyContinue) {
        $prevEap = $ErrorActionPreference
        $ErrorActionPreference = "Continue"
        $envsJson = conda env list --json 2>$null | ConvertFrom-Json
        $ErrorActionPreference = $prevEap
        foreach ($envDir in @($envsJson.envs)) {
            $cand = Join-Path $envDir "python.exe"
            if ((Test-Path $cand) -and (Test-PyDeps $cand)) {
                Write-Host "注：PATH 与当前激活环境都没装齐依赖，自动选用 conda 环境：$envDir" -ForegroundColor Yellow
                return $cand
            }
        }
    }
    return "python"   # 都不满足：交给下方校验段给出「缺什么、怎么装」的人话报错
}

if (-not $Py) {
    $Py = Resolve-PyPath
}
Write-Host "使用解释器: $Py" -ForegroundColor DarkGray

# -Py 显式路径校验：写错时给定位提示，而不是裸 CommandNotFoundException
if ($Py -ne "python" -and -not (Test-Path $Py)) {
    Write-Host "指定的解释器不存在: $Py" -ForegroundColor Red
    exit 1
}

# 构建前校验关键模块，缺依赖给人话提示，而不是 PyInstaller 中途炸。
# 注意：PS 5.1 下 EAP=Stop + 2>$null 会让任何 stderr 行以 NativeCommandError 直接
# 终止脚本（python 的 ImportError 恰好走 stderr）——人话提示永远走不到。
# 故校验段局部降为 Continue，只认 $LASTEXITCODE。
$prevEap = $ErrorActionPreference
$ErrorActionPreference = "Continue"
# 注意：这里**不要**探测 filelock。它是仓内模块（web/backend/filelock.py），不是 pip 依赖；
# 从仓库根执行 `import filelock` 会去命中同名的 PyPI 包——本机恰好装了它就通过，
# 干净环境（CI / 新机器）没装就误报「缺少依赖 fastapi / uvicorn / PyInstaller」，
# 而那句话是假的，会把排查引到错误方向。第三方的同名包反而可能遮蔽仓内模块。
& $Py -c "import fastapi, uvicorn, pydantic, PyInstaller" 2>$null
$checkCode = $LASTEXITCODE
$ErrorActionPreference = $prevEap
if ($checkCode -ne 0) {
    Write-Host "当前解释器缺少依赖（fastapi / uvicorn / PyInstaller）。" -ForegroundColor Red
    Write-Host "请在目标环境执行: $Py -m pip install -r web/backend/requirements.txt -r web/backend/requirements-dev.txt" -ForegroundColor Yellow
    exit 1
}

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
