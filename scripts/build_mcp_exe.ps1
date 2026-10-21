# 构建 jobws-mcp.exe（PyInstaller onedir）并落位到 DSH bundle 的平台子包（#271 P2-2）。
#
# 产出：
#   integrations/dsh/platform/win32-x64/bin/          jobws-mcp.exe + _internal/...（不入库，见该目录 .gitignore）
#   integrations/dsh/platform/win32-x64/prebuilds.json  全量文件 sha256 清单（入库，发布对账用）
#
# 构建环境（独立 venv，一次配好；不要用开发用的 jobws-mcp venv——它刻意是 editable）：
#   <任意 3.12 解释器> -m venv D:\tools\venvs\jobws-mcp-build
#   D:\tools\venvs\jobws-mcp-build\Scripts\python.exe -m pip install "pyinstaller<7" .\packages\jobws-core .\mcp "certifi>=2026.10.19"
#
# certifi 下界不是版本偏好：PYSEC-2026-4320（emSign 中间 CA 密钥泄露）影响
# >=2019.03.09, <2026.10.19；本脚本把「构建环境版本」与「随包 PEM 内容」都做成硬门禁，
# 镜像滞后或旧 venv 复用时直接失败，而不是静默打出受影响 CA。
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
$manifestPath = Join-Path $outDir "prebuilds.json"
$staleManifestPath = Join-Path $outDir "prebuilds.json.stale"

# 失败产物失效保护（2026-10-21 审计 P0）：**在任何可能失败的步骤之前**先让旧清单失效。
# 任何一步失败（环境不合格/CERTIFI 不达标/打包失败/CA 门禁拒绝），prebuilds.json 都不存在，
# 于是 `npm pack` 会缺清单、`scripts\verify_mcp_prebuilds.py` 会拒绝——不可能把旧 bin/
# 连同旧清单当新制品发出去。旧清单改名保留（不销毁历史证据），成功后由生成器重建。
if (Test-Path $manifestPath) { Move-Item $manifestPath $staleManifestPath -Force }

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
    Write-Host "  D:\tools\venvs\jobws-mcp-build\Scripts\python.exe -m pip install `"pyinstaller<7`" .\packages\jobws-core .\mcp `"certifi>=2026.10.19`""
    exit 1
}

# certifi 安全下界硬门禁（2026-10-21，G1 例外 #3 / PYSEC-2026-4320）：
# 受影响 >=2019.03.09, <2026.10.19。构建环境版本不达标 → 直接失败（镜像滞后/旧 venv 复用
# 会在这一步被拦住，而不是打出含受影响 CA 的 EXE 才被发现）。
$CertifiMin = "2026.10.19"
$CertifiSafePemSha = "50F79F98DAC192B20DBF73F35C56F0B0C557AB267FF5199D1117CC1180B70785"
$prevEap = $ErrorActionPreference
$ErrorActionPreference = "Continue"
$certifiVer = (& $Py -c "import importlib.metadata as m; print(m.version('certifi'))" 2>$null)
$certifiCode = $LASTEXITCODE
$ErrorActionPreference = $prevEap
if ($certifiCode -ne 0 -or -not $certifiVer) {
    Write-Host "构建环境缺 certifi（MCP 运行时随包 CA 清单必需）。" -ForegroundColor Red
    Write-Host "  $Py -m pip install `"certifi>=2026.10.19`"" -ForegroundColor Yellow
    exit 1
}
$certifiVer = $certifiVer.Trim()
$prevEap = $ErrorActionPreference
$ErrorActionPreference = "Continue"
& $Py -c "import sys; from importlib.metadata import version; v=tuple(int(x) for x in version('certifi').split('.')[:3]); sys.exit(0 if v >= (2026,10,19) else 1)" 2>$null
$verOk = $LASTEXITCODE
$ErrorActionPreference = $prevEap
if ($verOk -ne 0) {
    Write-Host "certifi 版本 $certifiVer 低于安全下界 ${CertifiMin}（PYSEC-2026-4320）。" -ForegroundColor Red
    Write-Host "请先升级构建 venv：$Py -m pip install --upgrade `"certifi>=2026.10.19`"" -ForegroundColor Yellow
    Write-Host "受影响区间 >=2019.03.09, <2026.10.19（emSign ECC Root CA - G3 中间 CA 密钥泄露）。" -ForegroundColor DarkGray
    exit 1
}
Write-Host "certifi = $certifiVer（>= ${CertifiMin}，安全下界通过）" -ForegroundColor Green

# 领域包必须**非 editable**（与后端打包同一纪律：editable 是链接树；判据 PEP 610/660
# 的 direct_url.json.dir_info.editable）。
$prevEap = $ErrorActionPreference
$ErrorActionPreference = "Continue"
& $Py -c "import sys, json, importlib.metadata as m; d = m.distribution('jobws-core'); t = (d.read_text('direct_url.json') if any(f.name == 'direct_url.json' for f in (d.files or [])) else None); sys.exit(1 if (t and json.loads(t).get('dir_info', {}).get('editable') is True) else 0)" 2>$null
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

# 2.5 产物侧 CA 硬门禁（G1 例外 #3，2026-10-21）：随包 PEM 必须存在、必须不含
# 受影响的 emSign ECC Root CA - G3、且完整 SHA256 等于已知安全清单。
# 与「构建环境版本检查」是两道独立门禁——环境对但产物被旧缓存污染时，这一条兜底。
$pemFile = Get-ChildItem $distDir -Recurse -File -Filter "cacert.pem" -ErrorAction SilentlyContinue |
    Where-Object { $_.FullName -match "certifi" } | Select-Object -First 1
if (-not $pemFile) {
    Write-Host "产物缺少随包 CA 清单（_internal/certifi/cacert.pem）。" -ForegroundColor Red
    Write-Host "检查 mcp/pyinstaller.spec 的 collect_data_files(\"certifi\") 是否仍生效。" -ForegroundColor Yellow
    exit 1
}
$pemSha = (Get-FileHash $pemFile.FullName -Algorithm SHA256).Hash.ToUpper()
$g3Hits = (Select-String -Path $pemFile.FullName -Pattern "emSign ECC Root CA - G3" -SimpleMatch | Measure-Object).Count
Write-Host "随包 PEM: $($pemFile.FullName)" -ForegroundColor DarkGray
Write-Host "随包 PEM SHA256: $pemSha" -ForegroundColor DarkGray
if ($g3Hits -ne 0) {
    Write-Host "产物含受影响的 emSign ECC Root CA - G3（$g3Hits 处）——拒绝产出。" -ForegroundColor Red
    Write-Host "PYSEC-2026-4320：请确认构建 venv certifi >= 2026.10.19 且无旧 PyInstaller 缓存（--clean 已开）。" -ForegroundColor Yellow
    exit 1
}
if ($pemSha -ne $CertifiSafePemSha) {
    Write-Host "随包 PEM SHA256 与已知安全清单（$CertifiSafePemSha）不一致——拒绝产出。" -ForegroundColor Red
    Write-Host "若 certifi 官方发布了更新的安全清单，同步更新本脚本的 `$CertifiSafePemSha 与下界。" -ForegroundColor Yellow
    exit 1
}

# 固定 PEM 哈希的兼容策略（2026-10-21 审计要求，写死在注释里防未来误改）：
# - 这里的 $CertifiSafePemSha 是 **26.11.0 发行审核基线**（certifi 2026.10.19 的 CA 清单，
#   120 证书、已移除受影响的 emSign ECC Root CA - G3）。
# - 与 `certifi>=2026.10.19` 下界**不等价**：下界只保证版本号，哈希锁定已审核的信任集合；
#   未来 certifi 正常更新 CA 清单时，本门禁会拒绝构建——**这是有意的 fail-closed**。
# - 升级 certifi 时必须：审核新版 cacert.pem 内容（证书增删是否合理）→ 同步更新本脚本的
#   `$CertifiSafePemSha` 与 `$CertifiMin` → 记录审核时间与依据；**不得绕过或放宽检查**。
Write-Host "产物 CA 门禁通过（无 G3，PEM = 安全清单）" -ForegroundColor Green
if (Test-Path $binDir) { Remove-Item $binDir -Recurse -Force }
New-Item -ItemType Directory -Path $binDir | Out-Null
Copy-Item (Join-Path $distDir "*") $binDir -Recurse

# 3. prebuilds.json：相对平台子包根的全量 sha256 清单（libreoffice-kit 模板；
#    生成器是 Python——哈希遍排交给 scripts/mcp_prebuilds.py 一处实现）
& $Py (Join-Path $root "scripts\mcp_prebuilds.py") $outDir $mainVersion
if ($LASTEXITCODE -ne 0) { Write-Host "prebuilds.json 生成失败" -ForegroundColor Red; exit 1 }

# 3.5 清掉失效标记：走到这里说明清单已由成功构建重建（失败路径会留下 .stale 供排查）
if (Test-Path $staleManifestPath) { Remove-Item $staleManifestPath -Force }

# 3.6 全链路校验（npm pack 前置门禁；与 .stale 检查同一条判据，作为成功路径的最终闸）
& $Py (Join-Path $root "scripts\verify_mcp_prebuilds.py")
if ($LASTEXITCODE -ne 0) { Write-Host "预构建清单/CA 校验失败——不得打包" -ForegroundColor Red; exit 1 }

# 4. 报告
$total = Get-ChildItem $binDir -Recurse -File | Measure-Object -Property Length -Sum
Write-Host "=== 构建完成 ===" -ForegroundColor Green
Write-Host ("产物: {0}（{1} 个文件，{2:N1} MB）" -f $binDir, $total.Count, ($total.Sum / 1MB))
Write-Host "冒烟: python scripts\smoke_mcp_exe.py"
Write-Host "打包前校验: python scripts\verify_mcp_prebuilds.py"
