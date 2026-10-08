# 构建 jobws-mcp.exe（PyInstaller onedir）并落位到 DSH bundle 的平台子包（#271 P2-2）。
#
# 产出：
#   integrations/dsh/platform/win32-x64/bin/          jobws-mcp.exe + _internal/...（不入库，见该目录 .gitignore）
#   integrations/dsh/platform/win32-x64/prebuilds.json  全量文件 sha256 清单（入库，发布对账用）
#
# 构建环境（独立 venv，一次配好；不要用开发用的 jobws-mcp venv——它刻意是 editable）：
#   <任意 3.12 解释器> -m venv D:\tools\venvs\jobws-mcp-build
#   D:\tools\venvs\jobws-mcp-build\Scripts\python.exe -m pip install "pyinstaller<7" .\packages\jobws-core .\mcp certifi
#
# 用法：powershell -ExecutionPolicy Bypass -File scripts/build_mcp_exe.ps1 [-Py "<构建解释器>"]
#      默认探测顺序：-Py > env:JOBWS_MCP_BUILD_PY > D:\tools\venvs\jobws-mcp-build > PATH python
param(
    [string]$Py = ""
)

$ErrorActionPreference = "Stop"
$root = Split-Path -Parent $PSScriptRoot
$mcpDir = Join-Path $root "mcp"
$outDir = Join-Path $root "integrations\dsh\platform\win32-x64"
$binDir = Join-Path $outDir "bin"

if (-not $Py) { $Py = $env:JOBWS_MCP_BUILD_PY }
$convention = "D:\tools\venvs\jobws-mcp-build\Scripts\python.exe"
if (-not $Py -and (Test-Path $convention)) { $Py = $convention }
if (-not $Py) { $Py = "python" }

Write-Host "=== 构建 jobws-mcp.exe（DSH bundle 随包运行时）===" -ForegroundColor Cyan
Write-Host "使用解释器: $Py" -ForegroundColor DarkGray

# 构建前校验（局部 EAP 降级：ImportError 走 stderr，PS 5.1 下 Stop 会直接终止脚本，
# 人话提示永远走不到——与 build_backend_exe.ps1 同款处理）。
$prevEap = $ErrorActionPreference
$ErrorActionPreference = "Continue"
& $Py -c "import sys, PyInstaller, mcp, mcp_types, jobws_core, jobws_mcp; assert sys.version_info[:2] >= (3, 12), sys.version" 2>$null
$checkCode = $LASTEXITCODE
$ErrorActionPreference = $prevEap
if ($checkCode -ne 0) {
    Write-Host "构建环境不合格（缺 PyInstaller / mcp SDK / jobws-core / jobws-mcp，或 Python < 3.12）。" -ForegroundColor Red
    Write-Host "请先配好独立构建 venv（不要复用开发用的 editable 环境）：" -ForegroundColor Yellow
    Write-Host "  <3.12 解释器> -m venv D:\tools\venvs\jobws-mcp-build"
    Write-Host "  D:\tools\venvs\jobws-mcp-build\Scripts\python.exe -m pip install `"pyinstaller<7`" .\packages\jobws-core .\mcp certifi"
    exit 1
}

# 领域包必须**非 editable**（与后端打包同一纪律：editable 是链接树；判据 PEP 610/660
# 的 direct_url.json.dir_info.editable）。
$prevEap = $ErrorActionPreference
$ErrorActionPreference = "Continue"
& $Py -c "import sys, json, pathlib, importlib.metadata as m; p = pathlib.Path(m.distribution('jobws-core').locate_file('')); f = p / 'direct_url.json'; bad = f.exists() and json.loads(f.read_text(encoding='utf-8')).get('dir_info', {}).get('editable') is True; sys.exit(1 if bad else 0)" 2>$null
$pkgCode = $LASTEXITCODE
$ErrorActionPreference = $prevEap
if ($pkgCode -ne 0) {
    Write-Host "领域包 jobws-core 是 editable 形态（打包不接受）。" -ForegroundColor Red
    Write-Host "请在构建 venv 里覆盖为 wheel：$Py -m pip install --force-reinstall --no-deps .\packages\jobws-core" -ForegroundColor Yellow
    exit 1
}

# 平台子包版本必须与主包一致（落章时一起 bump；不一致直接拦，防静默漂移）
$mainVersion = (Get-Content (Join-Path $root "integrations\dsh\package.json") -Encoding UTF8 -Raw | ConvertFrom-Json).version
$platformVersion = (Get-Content (Join-Path $outDir "package.json") -Encoding UTF8 -Raw | ConvertFrom-Json).version
if ($mainVersion -ne $platformVersion) {
    Write-Host "平台子包版本（$platformVersion）与主包（$mainVersion）不一致——先对齐再构建。" -ForegroundColor Red
    exit 1
}

# 1. PyInstaller 打包（cwd = mcp/）
Write-Host "PyInstaller 打包（onedir）..." -ForegroundColor Yellow
Push-Location $mcpDir
& $Py -m PyInstaller --clean --noconfirm pyinstaller.spec
$buildCode = $LASTEXITCODE
Pop-Location
if ($buildCode -ne 0) { Write-Host "PyInstaller 打包失败" -ForegroundColor Red; exit 1 }

# 2. 落位到平台子包（先清旧 bin/，幂等）
$distDir = Join-Path $mcpDir "dist\jobws-mcp"
if (-not (Test-Path (Join-Path $distDir "jobws-mcp.exe"))) {
    Write-Host "产物缺失：$distDir\jobws-mcp.exe" -ForegroundColor Red; exit 1
}
if (Test-Path $binDir) { Remove-Item $binDir -Recurse -Force }
New-Item -ItemType Directory -Path $binDir | Out-Null
Copy-Item (Join-Path $distDir "*") $binDir -Recurse

# 3. prebuilds.json：相对平台子包根的全量 sha256 清单（libreoffice-kit 模板；
#    生成器是 Python——哈希遍排交给 scripts/mcp_prebuilds.py 一处实现）
& $Py (Join-Path $root "scripts\mcp_prebuilds.py") $outDir $mainVersion
if ($LASTEXITCODE -ne 0) { Write-Host "prebuilds.json 生成失败" -ForegroundColor Red; exit 1 }

# 4. 报告
$total = Get-ChildItem $binDir -Recurse -File | Measure-Object -Property Length -Sum
Write-Host "=== 构建完成 ===" -ForegroundColor Green
Write-Host ("产物: {0}（{1} 个文件，{2:N1} MB）" -f $binDir, $total.Count, ($total.Sum / 1MB))
Write-Host "冒烟: python scripts\smoke_mcp_exe.py"
