# G2 五项制品级验收（Desktop B 组）
#
# 设计约束（来自 2026-10-26 维护者裁决）：
#   · 只消费**已构建成功**的 Artifact，不重新构建（避免字节差异与过期风险）
#   · 安装前完成输入闸门：来源 run / artifact / SHA256 / size / latest.yml
#   · 全部在隔离的 GitHub Windows Runner 上执行，不碰日常系统
#   · APPDATA 与 JOBWS_DATA_DIR **都要隔离**（快照位置不完全跟随后者）
#   · 每项独立记录 PASS / FAIL / NOT_EXECUTED / INFRA_ERROR，不用「脚本没抛异常」代替
#   · 环境前置不满足（如无 Chrome）记 INFRA_ERROR，**不得**判成产品缺陷
#
# 用法（由 g2-acceptance.yml 调用）：
#   pwsh -File scripts/g2-acceptance.ps1 -Action All -OutDir <dir> `
#        -RunId 40437650451 -ArtifactName installer `
#        -ExpectedSha256 7d986df4… -ExpectedSize 138039688
[CmdletBinding()]
param(
    [ValidateSet('Preflight','Install','VerifyPem','BuildPdf','DataRoots','Snapshot','Uninstall',
                 'Cleanup','State','Records','All')]
    [string]$Action = 'State',
    [string]$OutDir = '',
    # GitHub run id 是 64 位（如 40437650451 > Int32.Max），必须 [long]
    [long]$RunId = 0,
    [string]$ArtifactName = 'installer',
    [string]$ExpectedSha256 = '',
    [long]$ExpectedSize = 0,
    [string]$ExpectedPemSha = '50f79f98dac192b20dbf73f35c56f0b0c557ab267ff5199d1117cc1180b70785',
    [string]$BackendPort = '8765',
    # 本机自检用：跳过 gh 下载，直接用已有目录
    [string]$PreDownloadedDir = ''
)

$ErrorActionPreference = 'Stop'
Set-StrictMode -Version 2.0

if (-not $OutDir) { throw '必须指定 -OutDir' }
New-Item -ItemType Directory -Force -Path $OutDir | Out-Null
$StateFile = Join-Path $OutDir 'state.json'
$RecordsFile = Join-Path $OutDir 'records.json'
$ApiBase = "http://127.0.0.1:$BackendPort"

# ── 通用工具 ─────────────────────────────────────────────────────────────
function Get-Prop {
    param($Obj, [string]$Name, $Default = $null)
    if ($null -eq $Obj) { return $Default }
    if ($Obj -is [System.Collections.IDictionary]) {
        if ($Obj.Contains($Name)) { return $Obj[$Name] }
        return $Default
    }
    $p = $Obj.PSObject.Properties[$Name]
    if ($p) { return $p.Value }
    return $Default
}

function Write-Json {
    param([string]$Name, $Obj)
    $p = Join-Path $OutDir $Name
    ($Obj | ConvertTo-Json -Depth 12) | Set-Content -LiteralPath $p -Encoding utf8
    return $p
}

function Get-State {
    if (Test-Path -LiteralPath $StateFile) {
        return (Get-Content -LiteralPath $StateFile -Raw -Encoding utf8 | ConvertFrom-Json)
    }
    return [pscustomobject]@{}
}

function Save-State {
    param($Obj)
    ($Obj | ConvertTo-Json -Depth 8) | Set-Content -LiteralPath $StateFile -Encoding utf8
}

function Add-Record {
    param([string]$Id, [string]$Title, [string]$Status, [string]$Detail = '')
    # Status: PASS / FAIL / NOT_EXECUTED / INFRA_ERROR
    $recs = @()
    if (Test-Path -LiteralPath $RecordsFile) {
        $raw = Get-Content -LiteralPath $RecordsFile -Raw -Encoding utf8
        if ($raw.Trim()) { $recs = @($raw | ConvertFrom-Json) }
    }
    $recs += [pscustomobject]@{
        id = $Id; title = $Title; status = $Status
        detail = $Detail; at = (Get-Date).ToString('o')
    }
    [pscustomobject]$recs | ConvertTo-Json -Depth 6 |
        Set-Content -LiteralPath $RecordsFile -Encoding utf8
    Write-Host ("[{0}] {1} — {2} {3}" -f $Status, $Id, $Title, $(if ($Detail) { "($Detail)" } else { '' }))
}

function Test-Tcp {
    param([string]$HostName, [int]$Port, [int]$TimeoutMs = 1200)
    $c = New-Object System.Net.Sockets.TcpClient
    try {
        $iar = $c.BeginConnect($HostName, $Port, $null, $null)
        if (-not $iar.AsyncWaitHandle.WaitOne($TimeoutMs)) { return $false }
        $c.EndConnect($iar)
        return $true
    } catch { return $false } finally { $c.Close() }
}

function Invoke-Api {
    <# 返回 @{ status; body; error_code } —— 不抛异常，由调用方判读 #>
    param([string]$Method, [string]$Path, $Body = $null, [int]$TimeoutSec = 60)
    $uri = "$ApiBase$Path"
    $res = [ordered]@{ status = 0; body = ''; error_code = ''; exception = '' }
    try {
        $args = @{ Uri = $uri; Method = $Method; TimeoutSec = $TimeoutSec
                   UseBasicParsing = $true }
        if ($null -ne $Body) {
            $args['ContentType'] = 'application/json; charset=utf-8'
            $args['Body'] = ($Body | ConvertTo-Json -Depth 8 -Compress)
        }
        $r = Invoke-WebRequest @args
        $res.status = [int]$r.StatusCode
        $res.body = $r.Content
    } catch {
        $resp = $null
        if ($_.PSObject.Properties.Name -contains 'Response') { $resp = $_.Exception.Response }
        if ($resp) {
            # 兼容 .NET Framework（StatusCode 枚举）与 .NET Core（StatusCode 属性）
            try { $res.status = [int]$resp.StatusCode } catch { $res.status = 0 }
            try {
                $sr = New-Object System.IO.StreamReader($resp.GetResponseStream())
                $res.body = $sr.ReadToEnd()
            } catch { }
        }
        $res.exception = $_.Exception.Message
    }
    if ($res.body -and $res.body.TrimStart().StartsWith('{')) {
        try {
            $j = $res.body | ConvertFrom-Json
            $ec = Get-Prop $j 'error_code'
            if ($ec) { $res.error_code = [string]$ec }
            $d = Get-Prop $j 'detail'
            if (-not $res.error_code -and $d) {
                $ec2 = Get-Prop $d 'error_code'
                if ($ec2) { $res.error_code = [string]$ec2 }
            }
        } catch { }
    }
    return [pscustomobject]$res
}

function Wait-Health {
    param([int]$Seconds = 90)
    $deadline = (Get-Date).AddSeconds($Seconds)
    while ((Get-Date) -lt $deadline) {
        $r = Invoke-Api 'GET' '/api/health' $null 5
        if ($r.status -eq 200) { return $true }
        Start-Sleep -Milliseconds 800
    }
    return $false
}

function Stop-Backend {
    param($Proc)
    if ($null -eq $Proc) { return }
    try { if (-not $Proc.HasExited) { & taskkill /PID $Proc.Id /T /F 2>&1 | Out-Null } } catch { }
    # 等端口释放，避免下一次启动撞车
    for ($i = 0; $i -lt 20; $i++) {
        if (-not (Test-Tcp '127.0.0.1' ([int]$BackendPort))) { return }
        Start-Sleep -Milliseconds 300
    }
}

function Start-Backend {
    <# 启动安装目录内的 frozen 后端；数据根与 APPDATA 都隔离。返回 Process。 #>
    param([string]$BackendExe, [string]$DataRoot, [string]$IsoAppData)
    New-Item -ItemType Directory -Force -Path $DataRoot | Out-Null
    New-Item -ItemType Directory -Force -Path $IsoAppData | Out-Null
    $env:JOBWS_DATA_DIR = $DataRoot
    $env:APPDATA = $IsoAppData
    $env:LOCALAPPDATA = $IsoAppData
    $p = Start-Process -FilePath $BackendExe -PassThru -WindowStyle Hidden `
        -RedirectStandardOutput (Join-Path $OutDir 'backend.stdout.log') `
        -RedirectStandardError (Join-Path $OutDir 'backend.stderr.log')
    $ok = Wait-Health 90
    if (-not $ok) { Write-Host "Start-Backend: health 未就绪（pid=$($p.Id)）" }
    return $p
}

# ── 0. State ─────────────────────────────────────────────────────────────
if ($Action -eq 'State') {
    (Get-State | ConvertTo-Json -Depth 8)
    exit 0
}

if ($Action -eq 'Records') {
    if (Test-Path -LiteralPath $RecordsFile) { Get-Content -LiteralPath $RecordsFile -Raw -Encoding utf8 }
    exit 0
}

# ── 1. Preflight：输入闸门（任何不匹配都必须在安装前失败）────────────────
if ($Action -eq 'Preflight' -or $Action -eq 'All') {
    if ($RunId -le 0) { throw 'Preflight 需要 -RunId' }
    if (-not $ExpectedSha256) { throw 'Preflight 需要 -ExpectedSha256' }
    if ($ExpectedSize -le 0) { throw 'Preflight 需要 -ExpectedSize' }

    $dl = if ($PreDownloadedDir) { $PreDownloadedDir } else { Join-Path $OutDir 'artifact' }
    if (-not $PreDownloadedDir) {
        New-Item -ItemType Directory -Force -Path $dl | Out-Null
        Write-Host "Preflight: 下载 run=$RunId artifact=$ArtifactName"
        & gh run download $RunId -n $ArtifactName -D $dl 2>&1 | Out-Null
        if ($LASTEXITCODE -ne 0) {
            Add-Record 'G2-0' '制品下载' 'INFRA_ERROR' "gh run download exit=$LASTEXITCODE"
        }
    }

    # 递归找安装包（artifact 可能带子目录），并断言**唯一**
    $exes = @(Get-ChildItem $dl -Recurse -File -Filter '*26.10.0-win64.exe' -ErrorAction SilentlyContinue)
    if ($exes.Count -ne 1) {
        Add-Record 'G2-0' '安装包唯一定位' 'FAIL' "找到 $($exes.Count) 个 26.10.0 安装包（必须唯一）"
        exit 20
    }
    $Exe = $exes[0].FullName
    $size = (Get-Item $Exe).Length
    $sha = (Get-FileHash $Exe -Algorithm SHA256).Hash.ToLower()

    $sizeOk = ($size -eq $ExpectedSize)
    $shaOk = ($sha -eq $ExpectedSha256.ToLower())
    Add-Record 'G2-0a' '安装包大小' $(if ($sizeOk) { 'PASS' } else { 'FAIL' }) "$size / 期望 $ExpectedSize"
    Add-Record 'G2-0b' '安装包 SHA256' $(if ($shaOk) { 'PASS' } else { 'FAIL' }) "$sha"

    # latest.yml 交叉核对（size + sha512）
    $yml = Join-Path $dl 'latest.yml'
    if (-not (Test-Path -LiteralPath $yml)) {
        $f = Get-ChildItem $dl -Recurse -File -Filter 'latest.yml' -ErrorAction SilentlyContinue | Select-Object -First 1
        if ($f) { $yml = $f.FullName }
    }
    if (Test-Path -LiteralPath $yml) {
        $txt = Get-Content -LiteralPath $yml -Raw -Encoding utf8
        $mSize = [regex]::Match($txt, '(?m)^\s*size:\s*(\d+)')
        $mVer = [regex]::Match($txt, '(?m)^\s*version:\s*(\S+)')
        $ySize = if ($mSize.Success) { [long]$mSize.Groups[1].Value } else { -1 }
        $yVer = if ($mVer.Success) { $mVer.Groups[1].Value } else { '' }
        Add-Record 'G2-0c' 'latest.yml size 一致' $(if ($ySize -eq $size) { 'PASS' } else { 'FAIL' }) "yml=$ySize exe=$size"
        Add-Record 'G2-0d' 'latest.yml version' $(if ($yVer -eq '26.10.0') { 'PASS' } else { 'FAIL' }) "version=$yVer"
        # sha512 需真算，交 python 端做（PowerShell 无内置 SHA512-b64）
        $py = Get-Command python -ErrorAction SilentlyContinue
        if ($py) {
            $s512 = & python -c "import base64,hashlib,sys;print(base64.b64encode(hashlib.sha512(open(sys.argv[1],'rb').read()).digest()).decode())" $Exe 2>&1
            $y512 = [regex]::Match($txt, '(?m)^\s*sha512:\s*(\S+)').Groups[1].Value
            Add-Record 'G2-0e' 'latest.yml sha512 一致' $(if ($s512.Trim() -eq $y512) { 'PASS' } else { 'FAIL' }) "yml=${y512}`ncalc=$($s512.Trim())"
        } else {
            Add-Record 'G2-0e' 'latest.yml sha512 一致' 'INFRA_ERROR' 'runner 无 python，无法计算 SHA512-b64'
        }
    } else {
        Add-Record 'G2-0c' 'latest.yml 存在' 'FAIL' '未找到 latest.yml'
    }

    Save-State ([pscustomobject]@{ exe = $Exe; run_id = $RunId
            sha256 = $sha; size = $size; download_dir = $dl })
    # 任一门禁失败 → 必须在安装**前**停
    $fail = @()
    if (Test-Path -LiteralPath $RecordsFile) {
        $recs = @(Get-Content -LiteralPath $RecordsFile -Raw -Encoding utf8 | ConvertFrom-Json)
        $fail = @($recs | Where-Object { $_.id -like 'G2-0*' -and $_.status -eq 'FAIL' })
    }
    if ($fail.Count -gt 0) { Write-Host "Preflight: $($fail.Count) 项门禁 FAIL，禁止安装"; exit 21 }
    Write-Host 'Preflight: 全部通过'
    if ($Action -eq 'Preflight') { exit 0 }
}

$st = Get-State
$Exe = Get-Prop $st 'exe'

# ── 2. Install：NSIS 静默安装 + 运行 + PEM ───────────────────────────────
if ($Action -eq 'Install' -or $Action -eq 'All') {
    if (-not $Exe) { throw '需要先跑 Preflight' }
    $proc = Start-Process -FilePath $Exe -ArgumentList '/S' -Wait -PassThru
    Add-Record 'G2-1a' 'NSIS 静默安装' $(if ($proc.ExitCode -eq 0) { 'PASS' } else { 'FAIL' }) "exit=$($proc.ExitCode)"

    $cands = @(
        (Join-Path $env:LOCALAPPDATA 'Programs\Job Workbench'),
        (Join-Path $env:LOCALAPPDATA 'Programs\job-workbench')
    )
    $installDir = $cands | Where-Object { Test-Path $_ } |
        Where-Object { Get-ChildItem $_ -Filter 'Uninstall*.exe' -ErrorAction SilentlyContinue } |
        Select-Object -First 1
    if (-not $installDir) {
        Add-Record 'G2-1b' '安装目录定位' 'FAIL' "候选均无卸载器：$($cands -join '; ')"
        exit 22
    }
    $backendExe = Join-Path $installDir 'resources\backend\job-workbench-backend.exe'
    Add-Record 'G2-1b' '安装目录定位' $(if (Test-Path $backendExe) { 'PASS' } else { 'FAIL' }) "$installDir"
    Save-State ([pscustomobject]@{ exe = $Exe; install_dir = $installDir; backend_exe = $backendExe })

    if (-not (Test-Path $backendExe)) { exit 22 }

    # 启动 frozen 后端（隔离根 A）
    $rootA = Join-Path $OutDir 'roots\A'
    $appA = Join-Path $OutDir 'appdata\A'
    $bp = Start-Backend $backendExe $rootA $appA
    $health = Invoke-Api 'GET' '/api/health' $null 10
    Add-Record 'G2-1c' '安装后端 /api/health' $(if ($health.status -eq 200) { 'PASS' } else { 'FAIL' }) "http=$($health.status)"

    # 进程路径必须来自安装目录（防误连其他服务）
    $ppath = ''
    try { $ppath = (Get-Process -Id $bp.Id).Path } catch { }
    $pathOk = $ppath -and ($ppath -like "$installDir*")
    Add-Record 'G2-1d' '后端进程来自安装目录' $(if ($pathOk) { 'PASS' } else { 'FAIL' }) "pid=$($bp.Id) path=$ppath"

    Save-State ([pscustomobject]@{ exe = $Exe; install_dir = $installDir; backend_exe = $backendExe
            backend_pid = $bp.Id; root_a = $rootA; appdata_a = $appA })

    # ── G2-2 安装目录 PEM（读完再停后端不影响；PEM 是静态文件）──
    $pem = Join-Path $installDir 'resources\backend\_internal\certifi\cacert.pem'
    if (-not (Test-Path $pem)) {
        Add-Record 'G2-2a' '安装目录 PEM 存在' 'FAIL' $pem
    } else {
        $ph = (Get-FileHash $pem -Algorithm SHA256).Hash.ToLower()
        Add-Record 'G2-2a' '安装目录 PEM SHA256' $(if ($ph -eq $ExpectedPemSha.ToLower()) { 'PASS' } else { 'FAIL' }) $ph
        # 受影响根零命中：需要解析 base64 证书
        $py = Get-Command python -ErrorAction SilentlyContinue
        if ($py) {
            $code = @'
import io, sys
try:
    from cryptography import x509
except Exception as e:
    print("NO_CRYPTO:" + str(e)); sys.exit(0)
data = io.open(sys.argv[1], "rb").read()
certs = x509.load_pem_x509_certificates(data)
t = "emSign ECC Root CA - G3"
hit = 0
for c in certs:
    cn = c.subject.get_attributes_for_oid(x509.oid.NameOID.COMMON_NAME)
    if cn and cn[0].value.strip() == t:
        hit += 1
print("CERTS=%d HIT=%d" % (len(certs), hit))
'@
            $tmpPy = Join-Path $OutDir 'check_g3.py'
            $code | Set-Content -LiteralPath $tmpPy -Encoding utf8
            $out = & python $tmpPy $pem 2>&1
            $line = ($out | Where-Object { $_ -match 'CERTS=' }) -join ''
            if ($line -match 'HIT=(\d+)') {
                $hit = [int]$Matches[1]
                Add-Record 'G2-2b' '受影响根 G3 零命中' $(if ($hit -eq 0) { 'PASS' } else { 'FAIL' }) $line.Trim()
            } else {
                Add-Record 'G2-2b' '受影响根 G3 零命中' 'INFRA_ERROR' "无法解析（$($out -join ' ')）；PEM 已逐字节等于冻结基线"
            }
        } else {
            Add-Record 'G2-2b' '受影响根 G3 零命中' 'INFRA_ERROR' '无 python；PEM SHA256 已等于冻结基线'
        }
    }

    Stop-Backend $bp
    if ($Action -eq 'Install') { exit 0 }
}

# ── 3. BuildPdf：通过安装后端的真实生成接口 ──────────────────────────────
if ($Action -eq 'BuildPdf' -or $Action -eq 'All') {
    $st = Get-State
    $installDir = Get-Prop $st 'install_dir'
    $backendExe = Get-Prop $st 'backend_exe'
    if (-not $backendExe) { throw '需要先跑 Install' }

    $rootB = Join-Path $OutDir 'roots\B'
    $appB = Join-Path $OutDir 'appdata\B'
    $wsDir = Join-Path $rootB 'personal'
    New-Item -ItemType Directory -Force -Path (Join-Path $wsDir '02_简历工坊\source') | Out-Null
    New-Item -ItemType Directory -Force -Path (Join-Path $wsDir 'config') | Out-Null

    # 纯虚构简历（内容为虚构，明确不含真实个人数据）
    $resume = [ordered]@{
        meta = [ordered]@{ intent = '虚构后端岗位'; profile = 'g2demo' }
        basics = [ordered]@{ name = '虚构姓名丙'; phone = '000-0000-0002'
            email = 'g2demo@example.invalid'; location = '虚构城市' }
        education = @([ordered]@{ school = '虚构大学'; major = '虚构计算机专业'
            degree = '虚构本科'; period = '2019.09 - 2023.06'
            note = '虚构主修课程；虚构 GPA 数据' })
        projects = @(
            [ordered]@{ title = '虚构项目甲'; tag = '虚构技术栈'
                points = @(
                    '负责虚构接口层的设计与实现，覆盖虚构数量级接口契约，并用自动化用例守护回归',
                    '重构虚构模块的并发处理路径，将虚构指标从虚构基线降低约三成',
                    '排查虚构线上问题若干次，定位虚构缓存失效路径并完成修复'
                ) },
            [ordered]@{ title = '虚构项目乙'; tag = '虚构技术栈'
                points = @(
                    '设计虚构批处理调度方案，支持虚构规模日常任务，失败重试与断点续跑由虚构机制保障',
                    '编写虚构校验规则集合，对虚构输入做前置过滤，减少下游虚构异常的排查成本'
                ) }
        )
        work = @([ordered]@{ org = '虚构公司'; role = '虚构实习岗位'
            period = '2022.07 - 2022.09'
            points = @(
                '参与虚构业务模块的需求评审与实现，独立完成虚构子功能并配合验收',
                '整理虚构接口文档与虚构部署说明，降低后续接手成本'
            ) })
        skills = @(
            [ordered]@{ group = '虚构分类一'; items = '虚构语言、虚构框架、虚构数据库' },
            [ordered]@{ group = '虚构分类二'; items = '虚构构建工具、虚构测试框架、虚构部署方式' },
            [ordered]@{ group = '虚构分类三'; items = '虚构文档能力、虚构协作经验、虚构问题定位方法' }
        )
        extras = [ordered]@{ research = @(); awards = '虚构奖项'; certificates = '虚构证书' }
    }
    ($resume | ConvertTo-Json -Depth 10) | Set-Content -LiteralPath `
        (Join-Path $wsDir '02_简历工坊\source\resume_demo.json') -Encoding utf8
    # 关键事实清单（让第三项检查真正执行，而不是 SKIPPED）
    @('虚构姓名丙', '虚构大学', '虚构项目甲', '虚构公司') |
        Set-Content -LiteralPath (Join-Path $wsDir 'config\ats_required_facts.txt') -Encoding utf8

    $bp = Start-Backend $backendExe $rootB $appB
    $h = Invoke-Api 'GET' '/api/health' $null 10
    if ($h.status -ne 200) {
        Add-Record 'G2-3a' '待测后端就绪' 'FAIL' "http=$($h.status)"
        Stop-Backend $bp
        exit 23
    }
    Add-Record 'G2-3a' '待测后端就绪' 'PASS' "root=$rootB"

    $r = Invoke-Api 'POST' '/api/resume/demo/build?ws=personal' $null 300
    if ($r.status -eq 500 -and $r.error_code -eq 'resume.chromeMissing') {
        # 环境前置不满足 —— 不是产品缺陷
        Add-Record 'G2-3b' 'PDF 生成' 'INFRA_ERROR' 'resume.chromeMissing（runner 无 Chrome/Edge）'
    } elseif ($r.status -eq 200) {
        $j = $r.body | ConvertFrom-Json
        $passed = Get-Prop $j 'passed'
        Add-Record 'G2-3b' 'PDF 生成 passed=true' $(if ($passed -eq $true) { 'PASS' } else { 'FAIL' }) "passed=$passed"
        $pdfPath = Get-Prop $j 'pdf'
        if (-not $pdfPath) { $pdfPath = Get-Prop $j 'path' }
        if ($pdfPath -and (Test-Path $pdfPath)) {
            Add-Record 'G2-3c' 'PDF 文件存在' 'PASS' "$pdfPath ($((Get-Item $pdfPath).Length) B)"
            # 用 pypdf 独立复核：A4 + 1 页 + 提取 >=300
            $g = & python -c @'
import sys
try:
    from pypdf import PdfReader
except Exception as e:
    print("NO_PYPDF:" + str(e)); sys.exit(0)
r = PdfReader(sys.argv[1])
n = len(r.pages)
t = "\n".join((p.extract_text() or "") for p in r.pages)
mb = r.pages[0].mediabox
w, h = float(mb.width), float(mb.height)
a4 = abs(w - 595.28) < 2 and abs(h - 841.89) < 2
print("PAGES=%d CHARS=%d A4=%s W=%.1f H=%.1f" % (n, len(t), a4, w, h))
'@ $pdfPath 2>&1
            $gl = ($g | Where-Object { $_ -match 'PAGES=' }) -join ''
            if ($gl) {
                Add-Record 'G2-3d' 'PDF 页数=1' $(if ($gl -match 'PAGES=1\b') { 'PASS' } else { 'FAIL' }) $gl.Trim()
                Add-Record 'G2-3e' 'PDF A4 纸型' $(if ($gl -match 'A4=True') { 'PASS' } else { 'FAIL' }) $gl.Trim()
                if ($gl -match 'CHARS=(\d+)') {
                    $ch = [int]$Matches[1]
                    Add-Record 'G2-3f' '提取文本 >=300 字符' $(if ($ch -ge 300) { 'PASS' } else { 'FAIL' }) "chars=$ch"
                }
            } else {
                Add-Record 'G2-3d' 'PDF 独立复核' 'INFRA_ERROR' "$($g -join ' ')"
            }
        } else {
            Add-Record 'G2-3c' 'PDF 文件存在' 'FAIL' "响应无有效路径：$($r.body.Substring(0,[Math]::Min(300,$r.body.Length)))"
        }
    } else {
        Add-Record 'G2-3b' 'PDF 生成' 'FAIL' "http=$($r.status) code=$($r.error_code)"
    }
    Stop-Backend $bp
    Save-State ([pscustomobject]@{ install_dir = $installDir; backend_exe = $backendExe
            root_b = $rootB; appdata_b = $appB })
    if ($Action -eq 'BuildPdf') { exit 0 }
}

# ── 4. DataRoots：双根真实写入 + 越界 + 缺根 ─────────────────────────────
if ($Action -eq 'DataRoots' -or $Action -eq 'All') {
    $st = Get-State
    $backendExe = Get-Prop $st 'backend_exe'
    if (-not $backendExe) { throw '需要先跑 Install' }

    $rootA = Join-Path $OutDir 'roots\A'
    $rootB = Join-Path $OutDir 'roots\B'
    $appA = Join-Path $OutDir 'appdata\A'
    $appB = Join-Path $OutDir 'appdata\B'

    # 两个根都要有 personal（各自独立虚构内容）
    foreach ($r in @($rootA, $rootB)) {
        $p = Join-Path $r 'personal'
        New-Item -ItemType Directory -Force -Path (Join-Path $p '05_投递追踪') | Out-Null
    }
    # A 根放一条独有记录，用于后续「A 未被改动」的哈希比对
    $aTracker = Join-Path $rootA 'personal\05_投递追踪\A_ONLY.csv'
    "id,company,role`r`nA001,A公司,A岗位" | Set-Content -LiteralPath $aTracker -Encoding utf8
    $aHash0 = (Get-FileHash $aTracker -Algorithm SHA256).Hash

    # ① 起后端指向 B，做一次真实 PATCH
    $bp = Start-Backend $backendExe $rootB $appB
    $h = Invoke-Api 'GET' '/api/health' $null 10
    Add-Record 'G2-4a' 'B 根后端就绪' $(if ($h.status -eq 200) { 'PASS' } else { 'FAIL' }) "http=$($h.status)"

    $create = Invoke-Api 'POST' '/api/applications?ws=personal' ([ordered]@{
            company = '虚构G2公司'; role = '虚构G2岗位'; status = '已投递'
        })
    Add-Record 'G2-4b' 'B 根创建记录' $(if ($create.status -in 200, 201) { 'PASS' } else { 'FAIL' }) "http=$($create.status) code=$($create.error_code)"
    $appId = ''
    if ($create.body) {
        try { $appId = [string](Get-Prop ($create.body | ConvertFrom-Json) 'id') } catch { }
    }
    if (-not $appId) {
        Add-Record 'G2-4c' 'PATCH 前置 id' 'FAIL' "创建响应无 id：$($create.body.Substring(0,[Math]::Min(200,$create.body.Length)))"
    } else {
        $patch = Invoke-Api 'PATCH' "/api/applications/$appId`?ws=personal" ([ordered]@{ status = '已面试' })
        Add-Record 'G2-4c' 'B 根真实 PATCH' $(if ($patch.status -eq 200) { 'PASS' } else { 'FAIL' }) "http=$($patch.status) code=$($patch.error_code)"
    }
    Stop-Backend $bp

    # ② A 根未被写（A 的独有文件哈希不变）
    $aHash1 = (Get-FileHash $aTracker -Algorithm SHA256).Hash
    Add-Record 'G2-4d' 'A 根未被写入' $(if ($aHash0 -eq $aHash1) { 'PASS' } else { 'FAIL' }) "A_ONLY.csv $($aHash0.Substring(0,16)) -> $($aHash1.Substring(0,16))"

    # ③ 越界必须 400
    $bp = Start-Backend $backendExe $rootB $appB
    $null = Invoke-Api 'GET' '/api/health' $null 10
    $oob = Invoke-Api 'GET' '/api/applications?ws=../../../etc' $null 20
    Add-Record 'G2-4e' '越界返回 400 ws.outOfRange' `
        $(if ($oob.status -eq 400 -and $oob.error_code -eq 'ws.outOfRange') { 'PASS' } else { 'FAIL' }) `
        "http=$($oob.status) code=$($oob.error_code)"
    Stop-Backend $bp

    # ④ 缺根必须 fail-closed（404/503），绝不能 200 + 应用根数据
    $missing = Join-Path $OutDir 'roots\missing-no-such'
    if (Test-Path $missing) { Remove-Item $missing -Recurse -Force }
    $bp = Start-Backend $backendExe $missing $appB
    $null = Wait-Health 20
    $mr = Invoke-Api 'GET' '/api/applications?ws=personal' $null 20
    $mrOk = ($mr.status -in 404, 503)
    Add-Record 'G2-4f' '缺根 fail-closed（404/503）' $(if ($mrOk) { 'PASS' } else { 'FAIL' }) `
        "http=$($mr.status) code=$($mr.error_code)"
    Stop-Backend $bp

    # ⑤ 第三处非预期写入：B 根之外不得出现本次的 company 字符串
    $leak = @()
    foreach ($r in @($rootA)) {
        if (Test-Path $r) {
            $leak += @(Get-ChildItem $r -Recurse -File -ErrorAction SilentlyContinue |
                Where-Object { (Get-Content $_.FullName -Raw -ErrorAction SilentlyContinue) -match '虚构G2公司' })
        }
    }
    Add-Record 'G2-4g' '无第三处写入' $(if ($leak.Count -eq 0) { 'PASS' } else { 'FAIL' }) `
        $(if ($leak.Count -eq 0) { 'A 根零命中' } else { ($leak | ForEach-Object { $_.FullName }) -join '; ' })

    if ($Action -eq 'DataRoots') { exit 0 }
}

# ── 5. Snapshot：backup → preview(零写入) → restore(含回滚点) ─────────────
if ($Action -eq 'Snapshot' -or $Action -eq 'All') {
    $st = Get-State
    $backendExe = Get-Prop $st 'backend_exe'
    if (-not $backendExe) { throw '需要先跑 Install' }
    $rootB = Join-Path $OutDir 'roots\B'
    $appB = Join-Path $OutDir 'appdata\B'
    $probe = Join-Path $rootB 'personal\05_投递追踪\SNAP_PROBE.txt'

    $bp = Start-Backend $backendExe $rootB $appB
    $h = Invoke-Api 'GET' '/api/health' $null 10
    Add-Record 'G2-5a' '快照测试后端就绪' $(if ($h.status -eq 200) { 'PASS' } else { 'FAIL' }) "http=$($h.status)"

    # 先制造一个「已知内容」并备份
    'SNAPSHOT_BASELINE_v1' | Set-Content -LiteralPath $probe -Encoding utf8
    $boom = Invoke-Api 'POST' '/api/system/backup?ws=personal' $null 120
    Add-Record 'G2-5b' 'backup 成功' $(if ($boom.status -eq 200) { 'PASS' } else { 'FAIL' }) "http=$($boom.status) code=$($boom.error_code)"

    $lst = Invoke-Api 'GET' '/api/system/snapshots?ws=personal' $null 30
    $snapName = ''
    if ($lst.status -eq 200) {
        try {
            $lj = $lst.body | ConvertFrom-Json
            $arr = @(Get-Prop $lj 'snapshots')
            if ($arr.Count -gt 0) { $snapName = [string](Get-Prop $arr[0] 'name') }
        } catch { }
    }
    Add-Record 'G2-5c' '快照清单可读' $(if ($snapName) { 'PASS' } else { 'FAIL' }) "name=$snapName"

    # 快照目录应在隔离 APPDATA 下（不跟随 JOBWS_DATA_DIR 的已知事实）
    $snapDir = Get-Prop ($lst.body | ConvertFrom-Json) 'snapshotDir'
    $snapInIso = $snapDir -and ($snapDir -like "$appB*")
    Add-Record 'G2-5d' '快照位于隔离 APPDATA' $(if ($snapInIso) { 'PASS' } else { 'FAIL' }) "snapshotDir=$snapDir"

    if ($snapName) {
        # preview 必须零写入
        'SNAPSHOT_BASELINE_v2' | Set-Content -LiteralPath $probe -Encoding utf8
        $hBefore = (Get-FileHash $probe -Algorithm SHA256).Hash
        $pv = Invoke-Api 'POST' '/api/system/snapshots/preview?ws=personal' ([ordered]@{ name = $snapName }) 60
        $hAfter = (Get-FileHash $probe -Algorithm SHA256).Hash
        Add-Record 'G2-5e' 'preview 零写入' $(if ($pv.status -eq 200 -and $hBefore -eq $hAfter) { 'PASS' } else { 'FAIL' }) `
            "http=$($pv.status) hash_same=$($hBefore -eq $hAfter)"

        # restore 恢复原内容
        $rs = Invoke-Api 'POST' '/api/system/snapshots/restore?ws=personal' ([ordered]@{ name = $snapName }) 120
        $restored = if (Test-Path $probe) { (Get-Content $probe -Raw).Trim() } else { '<missing>' }
        $ok = ($rs.status -eq 200 -and $restored -eq 'SNAPSHOT_BASELINE_v1')
        Add-Record 'G2-5f' 'restore 恢复原内容' $(if ($ok) { 'PASS' } else { 'FAIL' }) `
            "http=$($rs.status) content=$restored"

        # restore 后应产生回滚点（快照数量增加）
        $lst2 = Invoke-Api 'GET' '/api/system/snapshots?ws=personal' $null 30
        $cnt2 = 0
        try { $cnt2 = @(Get-Prop ($lst2.body | ConvertFrom-Json) 'snapshots').Count } catch { }
        Add-Record 'G2-5g' 'restore 前创建回滚点' $(if ($cnt2 -ge 2) { 'PASS' } else { 'FAIL' }) `
            "恢复后快照数=$cnt2（应 >=2：原快照 + 回滚点）"
    }
    Stop-Backend $bp
    if ($Action -eq 'Snapshot') { exit 0 }
}

# ── 6. Uninstall：卸载后程序移除、测试数据保留 ───────────────────────────
if ($Action -eq 'Uninstall' -or $Action -eq 'All') {
    $st = Get-State
    $installDir = Get-Prop $st 'install_dir'
    if (-not $installDir) { throw '需要先跑 Install' }
    $rootB = Join-Path $OutDir 'roots\B'
    $up = Get-ChildItem $installDir -Filter 'Uninstall*.exe' -ErrorAction SilentlyContinue | Select-Object -First 1
    if (-not $up) {
        Add-Record 'G2-6a' '卸载器存在' 'FAIL' $installDir
    } else {
        $u = Start-Process -FilePath $up.FullName -ArgumentList '/S' -Wait -PassThru
        $gone = $false
        for ($i = 0; $i -lt 90; $i++) {
            if (-not (Test-Path $installDir)) { $gone = $true; break }
            Start-Sleep -Seconds 1
        }
        Add-Record 'G2-6a' '卸载后安装目录消失' $(if ($gone) { 'PASS' } else { 'FAIL' }) `
            "exit=$($u.ExitCode) gone=$gone"
    }
    # 测试数据必须保留（证明卸载没删用户数据）
    $probe = Join-Path $rootB 'personal\05_投递追踪\SNAP_PROBE.txt'
    Add-Record 'G2-6b' '卸载后测试数据保留' $(if (Test-Path $probe) { 'PASS' } else { 'FAIL' }) $probe
    if ($Action -eq 'Uninstall') { exit 0 }
}

# ── 7. Cleanup：只终止本次启动的进程，不掩盖前面的失败 ───────────────────
if ($Action -eq 'Cleanup' -or $Action -eq 'All') {
    $st = Get-State
    $pid0 = Get-Prop $st 'backend_pid'
    if ($pid0) {
        try {
            $pr = Get-Process -Id $pid0 -ErrorAction SilentlyContinue
            if ($pr) { & taskkill /PID $pid0 /T /F 2>&1 | Out-Null }
        } catch { }
    }
    $portFree = -not (Test-Tcp '127.0.0.1' ([int]$BackendPort))
    Add-Record 'G2-7a' '端口已释放' $(if ($portFree) { 'PASS' } else { 'FAIL' }) "port=$BackendPort"
    Write-Json 'cleanup.json' ([pscustomobject]@{ at = (Get-Date).ToString('o'); port_free = $portFree })
}

# ── 汇总 ─────────────────────────────────────────────────────────────────
if ($Action -eq 'All') {
    $recs = @()
    if (Test-Path -LiteralPath $RecordsFile) {
        $recs = @(Get-Content -LiteralPath $RecordsFile -Raw -Encoding utf8 | ConvertFrom-Json)
    }
    $p = @($recs | Where-Object { $_.status -eq 'PASS' }).Count
    $f = @($recs | Where-Object { $_.status -eq 'FAIL' }).Count
    $n = @($recs | Where-Object { $_.status -eq 'NOT_EXECUTED' }).Count
    $e = @($recs | Where-Object { $_.status -eq 'INFRA_ERROR' }).Count
    $concl = if ($f -gt 0) { 'G2_FAIL' }
             elseif ($e -gt 0) { 'G2_INCOMPLETE_INFRA' }
             elseif ($n -gt 0) { 'G2_PARTIAL' }
             else { 'G2_RUNNER_FUNCTIONAL_PASS' }
    $receipt = [pscustomobject]@{
        schemaVersion = 1
        at = (Get-Date).ToString('o')
        conclusion = $concl
        summary = [pscustomobject]@{ total = $recs.Count; passed = $p; failed = $f
            not_executed = $n; infra_error = $e }
        identity = [pscustomobject]@{
            run_id = (Get-Prop (Get-State) 'run_id')
            exe_sha256 = (Get-Prop (Get-State) 'sha256')
            exe_size = (Get-Prop (Get-State) 'size')
            install_dir = (Get-Prop (Get-State) 'install_dir')
            backend_exe = (Get-Prop (Get-State) 'backend_exe')
        }
        records = $recs
        known_gaps = @(
            'NSIS 向导 UI / UAC 点击 / SmartScreen 交互：runner 静默安装绕过，未覆盖',
            '真实 Windows 11 桌面体验：runner 为 Windows Server 镜像，未覆盖'
        )
        note = 'G2_RUNNER_FUNCTIONAL_PASS 不等于交互式人工验收；如正式合同要求 GUI 项，应单独记录未执行'
    }
    $rp = Write-Json 'g2-receipt.json' $receipt
    Write-Host ""
    Write-Host "=== G2 汇总 ==="
    Write-Host "  conclusion = $concl"
    Write-Host "  total=$($recs.Count) pass=$p fail=$f not_executed=$n infra_error=$e"
    Write-Host "  receipt    = $rp"
    if ($f -gt 0) { exit 30 } else { exit 0 }
}
