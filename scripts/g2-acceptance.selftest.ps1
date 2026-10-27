# G2 验收脚本的离线自检
#
# 分两类：
#   A. 静态断言 —— 主脚本里必须存在的关键判据（防止「加了一半」）
#   B. 反向验证 —— 输入闸门必须真的会拒（不是恒真）
#
# **不安装任何东西、不下载、不联网。** PR 阶段跑。
[CmdletBinding()]
param()

$ErrorActionPreference = 'Stop'
Set-StrictMode -Version 2.0

$root = Split-Path -Parent $PSScriptRoot
$ps1 = Join-Path $root 'scripts/g2-acceptance.ps1'
$wf = Join-Path $root '.github/workflows/g2-acceptance.yml'

if (-not (Test-Path $ps1)) { throw "缺少 $ps1" }
if (-not (Test-Path $wf)) { throw "缺少 $wf" }

$src = Get-Content -LiteralPath $ps1 -Raw -Encoding utf8
$wfs = Get-Content -LiteralPath $wf -Raw -Encoding utf8

$pass = 0
$fail = 0
$failMsgs = @()

function Rep {
    param([string]$Name, [bool]$Cond, [string]$Why)
    if ($Cond) {
        $script:pass++
        Write-Host "  PASS  $Name"
    } else {
        $script:fail++
        $script:failMsgs += "$Name — $Why"
        Write-Host "  FAIL  $Name"
        Write-Host "        $Why"
    }
}

Write-Host '=== A. 静态断言：关键判据必须在 ==='

Rep 'G2 五项动作齐全' (
    ($src -match "ValidateSet\('Preflight'" ) -and
    ($src -match "'Install'") -and ($src -match "'BuildPdf'") -and
    ($src -match "'DataRoots'") -and ($src -match "'Snapshot'") -and
    ($src -match "'Uninstall'")
) '五个验收入口缺一'

Rep 'Preflight 校验 SHA256 与 size' (
    ($src -match '\$shaOk = ') -and ($src -match '\$sizeOk = ')
) '输入闸门未同时校验哈希与字节数'

Rep '输入闸门失败必须在安装前停' (
    $src -match 'exit 21'
) '没有「门禁 FAIL 即退出」，会带着错误制品继续安装'

Rep '安装包必须唯一定位' (
    $src -match '\$exes\.Count -ne 1'
) '多份同名 EXE 时可能装错包'

Rep 'G2-1 断言后端进程来自安装目录' (
    ($src -match 'Get-Process -Id \$bp\.Id\)\.Path') -and ($src -match '\$ppath -like "\$installDir\*"')
) '未断言进程路径，可能误连其他服务'

Rep 'G2-2 断言安装目录 PEM 的 SHA256' (
    $src -match '\$ph = \(Get-FileHash \$pem'
) '未从**安装目录**回读 PEM'

Rep 'G2-2 受影响根检查不可解析时记 INFRA_ERROR' (
    ($src -match "Add-Record 'G2-2b'.*INFRA_ERROR") -and ($src -match 'emSign ECC Root CA - G3')
) '把环境问题误判成产品缺陷，或漏检 G3 根'

Rep 'G2-3 用产品自身接口生成 PDF' (
    $src -match "/api/resume/demo/build\?ws=personal"
) '未走 /api/resume/{version}/build，可能用测试脚本自造的 PDF 冒充'

Rep 'G2-3 chromeMissing 记 INFRA_ERROR 而非 FAIL' (
    ($src -match 'resume\.chromeMissing') -and ($src -match "INFRA_ERROR' 'resume\.chromeMissing")
) '环境缺浏览器会被误判成产品缺陷'

Rep 'G2-3 独立复核 A4 / 页数 / 字符数' (
    ($src -match 'PAGES=') -and ($src -match 'A4=') -and ($src -match 'CHARS=')
) '只信产品返回的 passed，没有独立复核'

Rep 'G2-4 越界必须 400 ws.outOfRange' (
    $src -match "ws\.outOfRange"
) '越界判据缺失'

Rep 'G2-4 缺根必须 fail-closed（404/503）' (
    $src -match '\(\$mr\.status -in 404, 503\)'
) '缺根可能被当成 200 正常返回'

Rep 'G2-4 断言 A 根未被写入' (
    ($src -match '\$aHash0') -and ($src -match '\$aHash1')
) '只验 B 变化、没验 A 未变'

Rep 'G2-4 检查无第三处写入' (
    $src -match "G2-4g"
) '缺少「A 根零命中」的反向检查'

Rep 'G2-5 preview 必须零写入' (
    ($src -match '\$hBefore') -and ($src -match '\$hAfter')
) 'preview 前未比对文件哈希'

Rep 'G2-5 断言 restore 后产生回滚点' (
    $src -match 'G2-5g'
) '未验证回滚点'

Rep 'G2-6 卸载后测试数据保留' (
    $src -match "G2-6b"
) '只验了卸载，没验数据保留'

Rep 'APPDATA 与 JOBWS_DATA_DIR 都隔离' (
    ($src -match '\$env:APPDATA = \$IsoAppData') -and ($src -match '\$env:JOBWS_DATA_DIR = \$DataRoot')
) '快照位置不完全跟随后者，只隔离其一会污染真实目录'

Rep 'Cleanup 只杀本次启动的进程' (
    ($src -match 'Get-Prop \$st .backend_pid.')
) '可能误杀无关进程'

Rep '结论区分 PASS / FAIL / NOT_EXECUTED / INFRA_ERROR' (
    ($src -match "'G2_RUNNER_FUNCTIONAL_PASS'") -and
    ($src -match "'G2_INCOMPLETE_INFRA'") -and
    ($src -match "'G2_FAIL'")
) '三态未分离，环境问题与产品缺陷会混读'

Rep '收据含 known_gaps（GUI/UAC 未覆盖）' (
    ($src -match 'NSIS 向导 UI') -and ($src -match 'SmartScreen')
) 'runner 能验的功能被误当成完整 G2 验收'

Write-Host ''
Write-Host '=== B. 反向验证：输入闸门必须真的会拒 ==='

$tmp = Join-Path ([System.IO.Path]::GetTempPath()) ("g2st-" + [guid]::NewGuid().ToString('N').Substring(0, 8))
New-Item -ItemType Directory -Force -Path $tmp | Out-Null
try {
    # 造一个假安装包（内容任意，只要文件名匹配）
    $fakeDir = Join-Path $tmp 'dl'
    New-Item -ItemType Directory -Force -Path $fakeDir | Out-Null
    $fakeExe = Join-Path $fakeDir 'job-workbench-setup-26.10.0-win64.exe'
    'fake-installer-bytes-for-selftest' | Set-Content -LiteralPath $fakeExe -Encoding ascii -NoNewline
    $fakeSize = (Get-Item $fakeExe).Length
    $fakeSha = (Get-FileHash $fakeExe -Algorithm SHA256).Hash.ToLower()

    # B-1：故意给错的 SHA256 → 必须 exit 21，且 G2-0b 记 FAIL
    $out1 = Join-Path $tmp 'o1'
    $wrongSha = ('0' * 64)
    & pwsh -NoProfile -ExecutionPolicy Bypass -File $ps1 -Action Preflight -OutDir $out1 `
        -RunId 1 -ArtifactName installer -ExpectedSha256 $wrongSha `
        -ExpectedSize $fakeSize -PreDownloadedDir $fakeDir 2>&1 | Out-Null
    $rc1 = $LASTEXITCODE
    Rep 'B-1 假 SHA256 被拒（exit 21）' ($rc1 -eq 21) "实际 exit=$rc1（期望 21）"
    $rec1 = Join-Path $out1 'records.json'
    $b1 = ''
    if (Test-Path $rec1) {
        $rs = @(Get-Content $rec1 -Raw -Encoding utf8 | ConvertFrom-Json)
        $hit = $rs | Where-Object { $_.id -eq 'G2-0b' } | Select-Object -First 1
        if ($hit) { $b1 = $hit.status }
    }
    Rep 'B-1 G2-0b 记为 FAIL' ($b1 -eq 'FAIL') "实际 status='$b1'"

    # B-2：故意给错 size → 必须 exit 21，且 G2-0a 记 FAIL
    $out2 = Join-Path $tmp 'o2'
    & pwsh -NoProfile -ExecutionPolicy Bypass -File $ps1 -Action Preflight -OutDir $out2 `
        -RunId 1 -ArtifactName installer -ExpectedSha256 $fakeSha `
        -ExpectedSize ($fakeSize + 123) -PreDownloadedDir $fakeDir 2>&1 | Out-Null
    $rc2 = $LASTEXITCODE
    Rep 'B-2 假 size 被拒（exit 21）' ($rc2 -eq 21) "实际 exit=$rc2（期望 21）"

    # B-3：SHA 与 size 都对，但缺 latest.yml → G2-0c FAIL → 仍须 exit 21
    $out3 = Join-Path $tmp 'o3'
    & pwsh -NoProfile -ExecutionPolicy Bypass -File $ps1 -Action Preflight -OutDir $out3 `
        -RunId 1 -ArtifactName installer -ExpectedSha256 $fakeSha `
        -ExpectedSize $fakeSize -PreDownloadedDir $fakeDir 2>&1 | Out-Null
    $rc3 = $LASTEXITCODE
    Rep 'B-3 缺 latest.yml 被拒（exit 21）' ($rc3 -eq 21) "实际 exit=$rc3（期望 21）"

    # B-4：补齐正确的 latest.yml → 应放行（exit 0），证明闸门不是「恒拒」
    $out4 = Join-Path $tmp 'o4'
    $sha512b64 = [Convert]::ToBase64String(
        [System.Security.Cryptography.SHA512]::Create().ComputeHash(
            [System.IO.File]::ReadAllBytes($fakeExe)))
    @(
        'version: 26.10.0'
        'files:'
        '  - url: job-workbench-setup-26.10.0-win64.exe'
        "    sha512: $sha512b64"
        "    size: $fakeSize"
        'path: job-workbench-setup-26.10.0-win64.exe'
        "sha512: $sha512b64"
    ) | Set-Content -LiteralPath (Join-Path $fakeDir 'latest.yml') -Encoding utf8
    & pwsh -NoProfile -ExecutionPolicy Bypass -File $ps1 -Action Preflight -OutDir $out4 `
        -RunId 1 -ArtifactName installer -ExpectedSha256 $fakeSha `
        -ExpectedSize $fakeSize -PreDownloadedDir $fakeDir 2>&1 | Out-Null
    $rc4 = $LASTEXITCODE
    Rep 'B-4 全部匹配时放行（exit 0）' ($rc4 -eq 0) "实际 exit=$rc4（期望 0，证明闸门非恒拒）"
} finally {
    Remove-Item $tmp -Recurse -Force -ErrorAction SilentlyContinue
}

Write-Host ''
Write-Host "=== 自检结果：$pass passed / $fail failed ==="
if ($fail -gt 0) {
    Write-Host ''
    Write-Host '失败项：'
    $failMsgs | ForEach-Object { Write-Host "  - $_" }
    exit 1
}
exit 0
