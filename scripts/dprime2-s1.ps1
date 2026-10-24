<#
.SYNOPSIS
  D'-2 S1 更新发现探针编排器（合同 v3）。只在一次性 runner 上运行。

.DESCRIPTION
  动作：Preflight / VerifyRc / NewCert / Tls1 / InstallCa / StartMock /
        PatchHosts / Tls2 / InstallAndRun / Verdict / Restore / CleanupVerify

  红线（与合同 §八 一致）：不改客户端二进制、不关 TLS 校验、不用 ignore-certificate-errors、
  不碰正式 Release、不接收任何凭据、不在日常 Windows 运行。
  所有状态落在 -OutDir，供后续动作与收据使用。
#>
[CmdletBinding()]
param(
    [Parameter(Mandatory)][ValidateSet(
        'Preflight','VerifyRc','UpstreamProbe','NewCert','Tls1','PrepareFixtures','InstallCa',
        'StartMock','PatchHosts','Tls2','InstallAndRun','MarkBoundary','TlsNegative','Verdict',
        'Restore','CleanupVerify')]
    [string]$Action,
    [string]$OutDir = $(if ($env:RUNNER_TEMP) { Join-Path $env:RUNNER_TEMP 'dprime2-s1' } else { $PWD.Path }),
    [string]$Setup,
    [string]$RcRoot,
    [string]$Python = 'python',
    [int]$Port = 443,
    [int]$WindowSeconds = 45,
    # 负例阶段：装+启动+等待+**停掉**客户端，用于证明"未信任测试 CA 时真实客户端会被拒"
    # （S1-G3 硬门禁）。与正例共用同一 mock、同一域名、同一夹具，唯一差别是 CA 是否已导入。
    [switch]$Negative,
    # MarkBoundary 的标签（用于在 mock 日志里划分负例/正例阶段）
    [string]$Label = ''
)

$ErrorActionPreference = 'Stop'
Set-StrictMode -Version Latest

$OWNER = 'chenxiang6663635'
$REPO = 'job-workbench'
$TAG = 'v26.10.1'
$EXPECT_CLIENT_SHA256 = '197fe10593eb50b127c87aaa690ad575aee7dc38b001110de5421e4df52ca954'
$EXPECT_RC_SHA256 = 'fbc6bbeebbc0e9af6c592e78591c3328f4adc9a7898208244b7bcfe1e75615c7'
$EXPECT_YML_SHA256 = 'aa4d819719639c35bdd87a92e7ee3fcf1317ac8d17bdb7c0347a9dc68a23dc7b'
$REQUIRED_PATHS = @(
    "/$OWNER/$REPO/releases.atom",
    "/$OWNER/$REPO/releases/latest",
    "/$OWNER/$REPO/releases/download/$TAG/latest.yml"
)

New-Item -ItemType Directory -Force -Path $OutDir | Out-Null
$StatePath = Join-Path $OutDir 'state.json'

function Get-State {
    if (Test-Path $StatePath) {
        return (Get-Content $StatePath -Raw | ConvertFrom-Json)
    }
    return [pscustomobject]@{}
}

function Save-State([pscustomobject]$State) {
    $State | ConvertTo-Json -Depth 6 | Set-Content -Path $StatePath -Encoding utf8
}

function Write-Json($Name, $Obj) {
    $p = Join-Path $OutDir $Name
    $Obj | ConvertTo-Json -Depth 8 | Set-Content -Path $p -Encoding utf8
    return $p
}

# StrictMode 下访问缺失属性会抛错；跨动作读 state 必须走这个助手
function Get-Prop($Obj, [string]$Name) {
    if ($null -eq $Obj) { return $null }
    $p = $Obj.PSObject.Properties[$Name]
    if ($p) { return $p.Value }
    return $null
}

function Get-Sha256([string]$Path) {
    return (Get-FileHash -Path $Path -Algorithm SHA256).Hash.ToLower()
}

function Get-Base64Sha512([string]$Path) {
    $sha = [System.Security.Cryptography.SHA512]::Create()
    try {
        $fs = [System.IO.File]::OpenRead($Path)
        try {
            return [Convert]::ToBase64String($sha.ComputeHash($fs))
        } finally { $fs.Dispose() }
    } finally { $sha.Dispose() }
}

function Test-Tcp([string]$HostName, [int]$P) {
    try {
        $c = [System.Net.Sockets.TcpClient]::new()
        try {
            $c.Connect($HostName, $P)
            return $c.Connected
        } finally { $c.Dispose() }
    } catch { return $false }
}

# ── 0. 环境预检（P0-2：代理 / DNS / IPv6）────────────────────────────────
if ($Action -eq 'Preflight') {
    $r = [ordered]@{
        at = (Get-Date).ToString('o'); action = 'Preflight'
        proxy = [ordered]@{}; dns = [ordered]@{}; ports = [ordered]@{}
        install = [ordered]@{}; verdict = 'PROCEED'; blockers = @()
    }

    # 代理探测（Chromium/net 会考虑系统代理与 PAC）
    $r.proxy.env_http = $env:HTTP_PROXY; $r.proxy.env_https = $env:HTTPS_PROXY
    $r.proxy.env_no = $env:NO_PROXY
    try {
        $r.proxy.winhttp = ((netsh winhttp show proxy) -join "`n")
    } catch { $r.proxy.winhttp = 'n/a' }
    try {
        $ie = Get-ItemProperty 'HKCU:\Software\Microsoft\Windows\CurrentVersion\Internet Settings' -ErrorAction Stop
        $r.proxy.ie_enable = $ie.ProxyEnable; $r.proxy.ie_server = $ie.ProxyServer
        $r.proxy.ie_autoconfig = $ie.AutoConfigURL
    } catch {
        $r.proxy.ie_enable = $null; $r.proxy.ie_server = $null; $r.proxy.ie_autoconfig = $null
    }
    $proxyDetected = ($r.proxy.env_http -or $r.proxy.env_https -or
        ($r.proxy.ie_enable -eq 1 -and $r.proxy.ie_server) -or
        ($r.proxy.winhttp -and $r.proxy.winhttp -notmatch '直接访问|Direct access'))
    $r.proxy.detected = [bool]$proxyDetected

    # DNS（改 hosts 前）
    try {
        $d = Resolve-DnsName github.com -Type A -ErrorAction Stop
        $r.dns.github_before = ($d | Where-Object IPAddress | ForEach-Object IPAddress) -join ','
    } catch { $r.dns.github_before = 'resolve-failed' }
    try {
        $d6 = Resolve-DnsName github.com -Type AAAA -ErrorAction Stop
        $r.dns.github_aaaa = ($d6 | Where-Object IPAddress | ForEach-Object IPAddress) -join ','
    } catch { $r.dns.github_aaaa = 'none' }
    $r.dns.loopback = (Resolve-DnsName 127.0.0.1 -ErrorAction SilentlyContinue | Out-String)

    $r.ports.p8765 = (Test-Tcp '127.0.0.1' 8765)
    $r.ports.p443 = (Test-Tcp '127.0.0.1' $Port)
    if ($r.ports.p8765) { $r.blockers += '8765 已被占用（旧安装可能正在运行）' }
    if ($r.ports.p443) { $r.blockers += "$Port 已被占用" }

    # 既有安装
    $r.install.dirs = @()
    foreach ($d in @("$env:LOCALAPPDATA\Programs\job-workbench",
                     "$env:ProgramFiles\job-workbench",
                     "${env:ProgramFiles(x86)}\job-workbench")) {
        if (Test-Path $d) { $r.install.dirs += $d }
    }
    if ($r.install.dirs.Count -gt 0) { $r.blockers += '检测到既有安装目录：' + ($r.install.dirs -join ';') }

    $r.python = (Get-Command $Python -ErrorAction SilentlyContinue).Source
    if (-not $r.python) { $r.blockers += "找不到 python（$Python）" }

    $r.ps = $PSVersionTable.PSVersion.ToString()
    if ($r.blockers.Count -gt 0) { $r.verdict = 'ABORT' }
    $p = Write-Json 'preflight.json' $r
    Write-Host "Preflight: $($r.verdict) -> $p"
    if ($r.verdict -eq 'ABORT') { $r.blockers | ForEach-Object { Write-Host "  BLOCKER: $_" } ; exit 3 }
    exit 0
}

# ── 1. RC 元数据身份（P0-3）──────────────────────────────────────────────
if ($Action -eq 'VerifyRc') {
    if (-not $RcRoot) { throw 'VerifyRc 需要 -RcRoot（含 latest.yml 与目标 exe）' }
    $yml = Join-Path $RcRoot 'latest.yml'
    if (-not (Test-Path $yml)) { throw "缺 latest.yml：$yml" }
    $rows = @()
    function AddRow($id, $ok, $detail) {
        $script:rows += [pscustomobject]@{ id = $id; ok = [bool]$ok; detail = "$detail" }
    }
    $txt = Get-Content $yml -Raw
    $ver = ([regex]::Match($txt, '(?m)^version:\s*(\S+)')).Groups[1].Value
    $path = ([regex]::Match($txt, '(?m)^path:\s*(\S+)')).Groups[1].Value
    $size = ([regex]::Match($txt, '(?m)^\s+size:\s*(\d+)')).Groups[1].Value
    $sha512 = ([regex]::Match($txt, '(?m)^\s*sha512:\s*(\S+)')).Groups[1].Value
    AddRow 'RC-1 version=26.10.1' ($ver -eq '26.10.1') "got=$ver"
    AddRow 'RC-2 path 指向目标 exe' ($path -eq 'job-workbench-setup-26.10.1-win64.exe') "got=$path"

    $exe = Join-Path $RcRoot 'job-workbench-setup-26.10.1-win64.exe'
    if (Test-Path $exe) {
        AddRow 'RC-3 exe size == latest.yml size' ("$((Get-Item $exe).Length)" -eq "$size") "exe=$((Get-Item $exe).Length) yml=$size"
        AddRow 'RC-4 exe SHA256 == 固定 RC' ((Get-Sha256 $exe) -eq $EXPECT_RC_SHA256) "got=$(Get-Sha256 $exe)"
        AddRow 'RC-5 exe SHA512(b64) == latest.yml sha512' ((Get-Base64Sha512 $exe) -eq $sha512) "match=$((Get-Base64Sha512 $exe) -eq $sha512)"
    } else { AddRow 'RC-3/4/5 需要 exe 同在 RcRoot' $false "缺 $exe" }
    AddRow 'RC-6 latest.yml SHA256 == 固定值' ((Get-Sha256 $yml) -eq $EXPECT_YML_SHA256) "got=$(Get-Sha256 $yml)"

    $allOk = -not ($rows | Where-Object { -not $_.ok })
    $p = Write-Json 'rc-identity.json' ([pscustomobject]@{ at = (Get-Date).ToString('o'); rc_root = $RcRoot; rows = $rows; all_ok = $allOk })
    Write-Host "VerifyRc: all_ok=$allOk -> $p"
    if (-not $allOk) { $rows | Where-Object { -not $_.ok } | ForEach-Object { Write-Host "  FAIL: $($_.id) $($_.detail)" }; exit 4 }
    exit 0
}

# ── 2. 证书（纯内存生成，不写证书存储）──────────────────────────────────
if ($Action -eq 'NewCert') {
    $notBefore = [DateTime]::UtcNow.AddDays(-1)
    $notAfter = [DateTime]::UtcNow.AddDays(30)
    # 用 SubjectAlternativeNameBuilder 构造 SAN
    #   DNS:github.com → 供正式客户端（hosts 劫持后按主机名校验）
    #   IP:127.0.0.1   → 供离线自检/TLS-2 直连锁环，且**仍做主机名校验**（不放宽 TLS）
    $sanBuilder = [System.Security.Cryptography.X509Certificates.SubjectAlternativeNameBuilder]::new()
    $sanBuilder.AddDnsName('github.com')
    $sanBuilder.AddIpAddress([System.Net.IPAddress]::Loopback)
    $sanExt = $sanBuilder.Build($false)     # 返回 X509Extension，可直接加入扩展集

    # CA（自签，CA:TRUE）
    # CA 用自己的名称（不要也叫 github.com）：叶子的 subject/issuer 若与 CA 完全相同，
    # OpenSSL/.NET 的链构建会把它误判成自签证书（2026-10-23 实测踩到）。
    $caRsa = [System.Security.Cryptography.RSA]::Create(4096)
    $caReq = [System.Security.Cryptography.X509Certificates.CertificateRequest]::new(
        'CN=DPrime2 S1 Test CA', $caRsa,
        [System.Security.Cryptography.HashAlgorithmName]::SHA256,
        [System.Security.Cryptography.RSASignaturePadding]::Pkcs1)
    $caReq.CertificateExtensions.Add(
        [System.Security.Cryptography.X509Certificates.X509BasicConstraintsExtension]::new($true, $false, 0, $true))
    $caReq.CertificateExtensions.Add(
        [System.Security.Cryptography.X509Certificates.X509KeyUsageExtension]::new('KeyCertSign,CrlSign', $true))
    $ca = $caReq.CreateSelfSigned($notBefore, $notAfter)

    # 服务器证书（由 CA 签发，serverAuth + SAN）
    $srvRsa = [System.Security.Cryptography.RSA]::Create(2048)
    $srvReq = [System.Security.Cryptography.X509Certificates.CertificateRequest]::new(
        'CN=github.com', $srvRsa,
        [System.Security.Cryptography.HashAlgorithmName]::SHA256,
        [System.Security.Cryptography.RSASignaturePadding]::Pkcs1)
    $srvReq.CertificateExtensions.Add(
        [System.Security.Cryptography.X509Certificates.X509BasicConstraintsExtension]::new($false, $false, 0, $true))
    $srvReq.CertificateExtensions.Add(
        [System.Security.Cryptography.X509Certificates.X509KeyUsageExtension]::new('DigitalSignature,KeyEncipherment', $true))
    $oids = [System.Security.Cryptography.OidCollection]::new()
    $oids.Add([System.Security.Cryptography.Oid]::new('1.3.6.1.5.5.7.3.1'))
    $srvReq.CertificateExtensions.Add(
        [System.Security.Cryptography.X509Certificates.X509EnhancedKeyUsageExtension]::new($oids, $true))
    $srvReq.CertificateExtensions.Add($sanExt)
    $srv = $srvReq.Create($ca, $notBefore, $notAfter, [guid]::NewGuid().ToByteArray())

    function Export-Pem([byte[]]$Der, [string]$Label) {
        $b64 = [Convert]::ToBase64String($Der)
        $lines = for ($i = 0; $i -lt $b64.Length; $i += 64) { $b64.Substring($i, [Math]::Min(64, $b64.Length - $i)) }
        return (@("-----BEGIN $Label-----") + $lines + @("-----END $Label-----")) -join "`n"
    }

    $caPem = Export-Pem $ca.RawData 'CERTIFICATE'
    $srvPem = Export-Pem $srv.RawData 'CERTIFICATE'
    $keyPem = Export-Pem $srvRsa.ExportPkcs8PrivateKey() 'PRIVATE KEY'

    Set-Content -Path (Join-Path $OutDir 'ca.crt') -Value $caPem -NoNewline -Encoding utf8
    Set-Content -Path (Join-Path $OutDir 'server.crt') -Value ($caPem + "`n" + $srvPem) -NoNewline -Encoding utf8
    Set-Content -Path (Join-Path $OutDir 'server.key') -Value $keyPem -NoNewline -Encoding utf8

    $info = [pscustomobject]@{
        at = (Get-Date).ToString('o')
        ca_thumbprint = $ca.Thumbprint.ToLower()
        server_thumbprint = $srv.Thumbprint.ToLower()
        ca_not_before = $notBefore.ToString('o'); ca_not_after = $notAfter.ToString('o')
        server_san = 'DNS:github.com'
        store_touched = $false
    }
    Save-State ([pscustomobject]@{
            ca_thumbprint = $info.ca_thumbprint
            server_thumbprint = $info.server_thumbprint
            out_dir = $OutDir
            python = $Python; port = $Port
        })
    $p = Write-Json 'certs.json' $info
    Write-Host "NewCert: ca=$($info.ca_thumbprint) server=$($info.server_thumbprint) -> $p"
    exit 0
}

# ── 3. TLS-1：纯离线结构检查（无握手）──────────────────────────────────
# 实现放在 dprime2-certcheck.py（cryptography 库）：比 .NET X509Chain 更可靠，
# 且明确只做结构/密码学验证，不发起任何网络连接。
if ($Action -eq 'Tls1') {
    $certCheck = Join-Path $PSScriptRoot 'dprime2-certcheck.py'
    if (-not (Test-Path $certCheck)) { throw "缺 certcheck 脚本：$certCheck" }
    $py = (Get-Command $Python -ErrorAction SilentlyContinue).Source
    if (-not $py) { throw "找不到 python（$Python），TLS-1 无法执行" }
    $raw = & $py $certCheck --dir $OutDir
    $parsed = $raw | ConvertFrom-Json
    $rows = @($parsed.rows | ForEach-Object {
            [pscustomobject]@{ id = $_.id; ok = [bool]$_.ok; detail = "$($_.detail)" }
        })
    $p = Write-Json 'tls1.json' ([pscustomobject]@{
            at = (Get-Date).ToString('o'); mode = $parsed.mode
            handshake_performed = [bool]$parsed.handshake_performed
            rows = $rows; all_ok = [bool]$parsed.all_ok
        })
    Write-Host "Tls1 (offline): all_ok=$($parsed.all_ok) -> $p"
    $rows | Where-Object { -not $_.ok } | ForEach-Object { Write-Host "  FAIL: $($_.id) $($_.detail)" }
    if (-not $parsed.all_ok) { exit 5 }
    exit 0
}

# ── 4. 短暂导入 CA（可逆；仅本 runner）──────────────────────────────────
if ($Action -eq 'InstallCa') {
    $st = Get-State
    $thumb = Get-Prop $st 'ca_thumbprint'
    $caPath = Join-Path $OutDir 'ca.crt'
    Import-Certificate -FilePath $caPath -CertStoreLocation 'Cert:\LocalMachine\Root' | Out-Null
    $present = [bool](Get-ChildItem Cert:\LocalMachine\Root | Where-Object Thumbprint -eq $thumb)
    $p = Write-Json 'ca-install.json' ([pscustomobject]@{
            at = (Get-Date).ToString('o'); thumbprint = $thumb
            store = 'LocalMachine\Root'; imported = $present; store_touched = $true
        })
    Write-Host "InstallCa: thumbprint=$thumb present=$present -> $p"
    exit 0
}

# ── 5. 起 mock ───────────────────────────────────────────────────────────
if ($Action -eq 'UpstreamProbe') {
    # 2026-10-24 审计要求：`github.com/.../releases/latest` 的**内容协商行为不是稳定接口**
    # （2023-01-28 GitHub 曾短暂改掉它对 Accept: application/json 的响应，electron-updater 5.x
    #  因此报错，后由 GitHub 工程师回滚）。所以在把 hosts 指到本地 mock 之前，
    # 先对**真实上游**做一次只读对照，把当时的实际行为钉进收据。
    #
    # 只读、无副作用；**只打 `github.com/<owner>/<repo>/releases/latest`**（项目实际调用的路径），
    # 绝不打 `api.github.com/repos/.../releases/latest`——那是另一个端点，行为不能互相替代。
    $target = "https://github.com/$OWNER/$REPO/releases/latest"
    $handler = [System.Net.Http.HttpClientHandler]::new()
    $handler.AllowAutoRedirect = $false          # 手工跟跳，才能记录重定向链
    $client = [System.Net.Http.HttpClient]::new($handler)
    $client.Timeout = [TimeSpan]::FromSeconds(20)

    function Probe-Latest([string]$AcceptLabel, [hashtable]$Headers) {
        $chain = @()
        $uri = $target
        $status = 0
        $ctype = ''
        $finalBody = ''
        for ($hop = 0; $hop -lt 6; $hop++) {
            $req = [System.Net.Http.HttpRequestMessage]::new([System.Net.Http.HttpMethod]::Get, $uri)
            foreach ($k in $Headers.Keys) { [void]$req.Headers.TryAddWithoutValidation($k, $Headers[$k]) }
            try {
                $resp = $client.SendAsync($req).GetAwaiter().GetResult()
            } catch {
                $chain += [pscustomobject]@{ uri = $uri; status = -1; location = ''; error = $_.Exception.Message.Substring(0, [Math]::Min(160, $_.Exception.Message.Length)) }
                break
            }
            $status = [int]$resp.StatusCode
            $ctype = if ($resp.Content -and $resp.Content.Headers.ContentType) { [string]$resp.Content.Headers.ContentType } else { '' }
            $loc = if ($resp.Headers.Location) { [string]$resp.Headers.Location } else { '' }
            $chain += [pscustomobject]@{ uri = $uri; status = $status; location = $loc; content_type = $ctype }
            if ($status -ge 300 -and $status -lt 400 -and $loc) {
                $uri = if ([System.Uri]::IsWellFormedUriString($loc, 'Absolute')) { $loc }
                       else { ([System.Uri]::new([System.Uri]::new($target), $loc)).AbsoluteUri }
                continue
            }
            try { $finalBody = $resp.Content.ReadAsStringAsync().GetAwaiter().GetResult() } catch { $finalBody = '' }
            break
        }
        $looksJson = $false; $tagName = ''
        if ($finalBody) {
            $trimmed = $finalBody.TrimStart()
            $looksJson = $trimmed.StartsWith('{') -or $trimmed.StartsWith('[')
            if ($looksJson) {
                try { $oj = $finalBody | ConvertFrom-Json; if ($oj.PSObject.Properties['tag_name']) { $tagName = [string]$oj.tag_name } } catch { }
            }
        }
        [pscustomobject]@{
            accept = $AcceptLabel
            final_status = $status
            final_content_type = $ctype
            final_uri = $uri
            hops = $chain.Count
            chain = $chain
            body_looks_json = $looksJson
            tag_name = $tagName
            body_len = $finalBody.Length
        }
    }

    $withJson = Probe-Latest 'application/json' @{ Accept = 'application/json' }
    $without = Probe-Latest '(none)' @{}

    $rows = @()
    $rows += [pscustomobject]@{
        id = 'UP-1 带 JSON Accept 时返回 JSON'
        ok = ($withJson.final_status -eq 200 -and $withJson.body_looks_json)
        detail = "status=$($withJson.final_status) ctype=$($withJson.final_content_type) json=$($withJson.body_looks_json) tag=$($withJson.tag_name)"
    }
    $rows += [pscustomobject]@{
        id = 'UP-2 不带 JSON Accept 时不返回 JSON'
        ok = (-not $without.body_looks_json)
        detail = "status=$($without.final_status) ctype=$($without.final_content_type) json=$($without.body_looks_json) hops=$($without.hops)"
    }
    $rows += [pscustomobject]@{
        id = 'UP-3 带 JSON Accept 的 tag_name 可解析'
        ok = (-not [string]::IsNullOrWhiteSpace($withJson.tag_name) -or $withJson.final_status -eq 200)
        detail = "tag=$($withJson.tag_name)"
    }
    $allOk = -not ($rows | Where-Object { -not $_.ok })

    $p = Write-Json 'upstream-probe.json' ([pscustomobject]@{
            at = (Get-Date).ToString('o')
            target = $target
            note = '只读对照，用于证明 mock 的内容协商与当时上游一致；若不符属上游行为变化，需在结论中标注'
            endpoint_forbidden = 'api.github.com/repos/.../releases/latest（另一个端点，不可替代本路径）'
            with_json_accept = $withJson
            without_json_accept = $without
            rows = $rows
            all_ok = $allOk
        })
    Write-Host "UpstreamProbe: all_ok=$allOk -> $p"
    Write-Host ("  带 Accept: status=$($withJson.final_status) ctype=$($withJson.final_content_type) json=$($withJson.body_looks_json) tag=$($withJson.tag_name)")
    Write-Host ("  不带    : status=$($without.final_status) ctype=$($without.final_content_type) json=$($without.body_looks_json) hops=$($without.hops)")
    $rows | Where-Object { -not $_.ok } | ForEach-Object { Write-Host "  DEVIATION: $($_.id) — $($_.detail)" }
    # 不直接判 FAIL：这是"上游行为采集"，偏离要进收据由人裁决；退出码仍 0 以便继续跑
    exit 0
}

if ($Action -eq 'PrepareFixtures') {
    # 2026-10-24 修 P0：原 StartMock 只放证书与 probe，**没有 atom.xml / latest.json /
    # latest.yml**，mock 的三条路由全部读不到文件 → 客户端必然失败。
    # 离线自检抓不到这点（自检自己生成了夹具），只有真跑才会暴露。
    #
    # 元数据来源纪律（S1-G4）：latest.yml 必须是**固定 RC 的原件**（校验 SHA256）；
    # atom.xml / latest.json 是 GitHub 站点侧的东西，RC 里没有，只能从 latest.yml 的
    # version **派生**——派生关系必须记录，且三者版本自洽。
    if (-not $RcRoot) { throw 'PrepareFixtures 需要 -RcRoot（含 latest.yml 的固定 RC 目录）' }
    $ymlSrc = Join-Path $RcRoot 'latest.yml'
    if (-not (Test-Path $ymlSrc)) { throw "缺 latest.yml：$ymlSrc" }

    $ymlSha = Get-Sha256 $ymlSrc
    $ymlText = Get-Content $ymlSrc -Raw
    $ver = ([regex]::Match($ymlText, '(?m)^version:\s*(\S+)')).Groups[1].Value.Trim()
    $assetName = ([regex]::Match($ymlText, '(?m)^path:\s*(\S+)')).Groups[1].Value.Trim()
    if (-not $ver) { throw "latest.yml 里读不到 version：$ymlSrc" }
    $tag = "v$ver"          # GitHub 的 tag_name 形如 v26.10.1；latest.yml 的 version 是 26.10.1

    $fixture = Join-Path $OutDir 'fixtures'
    New-Item -ItemType Directory -Force -Path $fixture | Out-Null

    # ① latest.yml = RC 原件（不做任何改写）
    Copy-Item $ymlSrc (Join-Path $fixture 'latest.yml') -Force

    # ② latest.json：GitHubProvider.getLatestTagName() 对 `Accept: application/json` 的响应
    $latestJson = '{"tag_name":"' + $tag + '","name":"' + $tag + '","draft":false,"prerelease":false}'
    Set-Content -Path (Join-Path $fixture 'latest.json') -Value $latestJson -NoNewline -Encoding utf8

    # ③ atom.xml：entry 的 link href **必须以 /tag/<tag> 结尾**——
    #    GitHubProvider 用 hrefRegExp = /\/(v?[^/]+)$/ 捕获，且要求捕获值 === tag_name
    $updated = (Get-Date).ToUniversalTime().ToString('yyyy-MM-ddTHH:mm:ssZ')
    $atom = @"
<?xml version="1.0" encoding="UTF-8"?>
<feed xmlns="http://www.w3.org/2005/Atom" xmlns:media="http://search.yahoo.com/mrss/">
  <id>tag:github.com,2008:/$OWNER/$REPO/releases</id>
  <link type="text/html" rel="alternate" href="https://github.com/$OWNER/$REPO/releases"/>
  <title>Release notes from $REPO</title>
  <updated>$updated</updated>
  <entry>
    <id>tag:github.com,2008:Repository/$OWNER/$REPO/$tag</id>
    <updated>$updated</updated>
    <link rel="alternate" type="text/html" href="https://github.com/$OWNER/$REPO/releases/tag/$tag"/>
    <title>$tag</title>
    <content type="html">dprime2 controlled source: $ver</content>
  </entry>
</feed>
"@
    Set-Content -Path (Join-Path $fixture 'atom.xml') -Value $atom -NoNewline -Encoding utf8

    # ④ tag.html：/releases/latest 缺 JSON Accept 时 302 的落点（与真实 GitHub 一致）
    $tagHtml = "<!doctype html><meta charset=`"utf-8`"><title>$tag</title><h1>$tag</h1>"
    Set-Content -Path (Join-Path $fixture 'tag.html') -Value $tagHtml -NoNewline -Encoding utf8

    # 自洽校验（不通过就不许起 mock）
    $rows = @()
    $rows += [pscustomobject]@{ id = 'FX-1 latest.yml 来自固定 RC'; ok = ($ymlSha -eq $EXPECT_YML_SHA256); detail = $ymlSha }
    $rows += [pscustomobject]@{ id = 'FX-2 atom link 以 /tag/<tag> 结尾'; ok = ($atom -match [regex]::Escape("/releases/tag/$tag")); detail = $tag }
    $rows += [pscustomobject]@{ id = 'FX-3 latest.json tag_name 与 atom 一致'; ok = ($latestJson -match [regex]::Escape('"tag_name":"' + $tag + '"')); detail = $latestJson }
    $rows += [pscustomobject]@{ id = 'FX-4 yml version 与 tag 自洽'; ok = ($tag -eq "v$ver"); detail = "version=$ver tag=$tag" }
    $rows += [pscustomobject]@{ id = 'FX-5 资产文件名与 RC 一致'; ok = ($assetName -eq "job-workbench-setup-$ver-win64.exe"); detail = $assetName }
    $allOk = -not ($rows | Where-Object { -not $_.ok })

    $p = Write-Json 'fixtures.json' ([pscustomobject]@{
            at = (Get-Date).ToString('o'); rc_root = $RcRoot; version = $ver; tag = $tag
            latest_yml_sha256 = $ymlSha
            derived = [pscustomobject]@{
                note = 'atom.xml / latest.json / tag.html 由 latest.yml 的 version 派生（GitHub 站点侧产物，RC 内不存在）'
                tag_from = 'latest.yml version'
            }
            rows = $rows; all_ok = $allOk
        })
    Write-Host "PrepareFixtures: version=$ver tag=$tag all_ok=$allOk -> $p"
    $rows | Where-Object { -not $_.ok } | ForEach-Object { Write-Host "  FAIL: $($_.id) $($_.detail)" }
    if (-not $allOk) { exit 11 }
    exit 0
}

if ($Action -eq 'StartMock') {
    $st = Get-State
    if (Test-Tcp '127.0.0.1' $Port) { Write-Host "StartMock: port $Port already in use"; exit 6 }    $fixture = Join-Path $OutDir 'fixtures'
    New-Item -ItemType Directory -Force -Path $fixture | Out-Null
    # Python 的 load_cert_chain 用 certfile 里**第一张**证书配密钥，而 server.crt 是
    # 「CA + 叶子」顺序；必须只给叶子证书，否则 KEY_VALUES_MISMATCH。
    $chainPem = Get-Content (Join-Path $OutDir 'server.crt') -Raw
    $blocks = @($chainPem -split '(?=-----BEGIN CERTIFICATE-----)' | Where-Object { $_.Trim() })
    Set-Content -Path (Join-Path $fixture 'server.crt') -Value ($blocks | Select-Object -Last 1).Trim() -NoNewline -Encoding utf8
    Copy-Item (Join-Path $OutDir 'ca.crt') $fixture -Force
    Copy-Item (Join-Path $OutDir 'server.key') $fixture -Force
    Set-Content -Path (Join-Path $fixture 'probe.txt') -Value 'dprime2-tls2-probe' -Encoding utf8

    # 起 mock 前必须已有三份元数据夹具，否则三条路由会 500/404（2026-10-24 修）
    foreach ($need in @('atom.xml', 'latest.json', 'latest.yml')) {
        if (-not (Test-Path (Join-Path $fixture $need))) {
            throw "缺夹具 $need —— 必须先跑 -Action PrepareFixtures -RcRoot <RC目录>"
        }
    }

    $log = Join-Path $OutDir 'mock-requests.jsonl'
    $mockScript = Join-Path $PSScriptRoot 'dprime2-mock-server.py'
    if (-not (Test-Path $mockScript)) { throw "缺 mock 脚本：$mockScript" }

    $psi = [System.Diagnostics.ProcessStartInfo]::new()
    $psi.FileName = (Get-Command $Python).Source
    $psi.ArgumentList.AddRange(@($mockScript, '--root', $fixture, '--log', $log, '--host', '127.0.0.1', '--port', "$Port"))
    $psi.UseShellExecute = $false
    $psi.RedirectStandardOutput = $true
    $psi.RedirectStandardError = $true
    $psi.WorkingDirectory = $OutDir
    $proc = [System.Diagnostics.Process]::Start($psi)

    $deadline = (Get-Date).AddSeconds(20)
    $up = $false
    while ((Get-Date) -lt $deadline -and -not $up) {
        Start-Sleep -Milliseconds 500
        $up = Test-Tcp '127.0.0.1' $Port
    }
    $p = Write-Json 'mock.json' ([pscustomobject]@{
            at = (Get-Date).ToString('o'); pid = $proc.Id; port = $Port
            listening = $up; log = $log; fixture = $fixture
        })
    Save-State ([pscustomobject]@{ mock_pid = $proc.Id
            ca_thumbprint = (Get-Prop $st 'ca_thumbprint')
            out_dir = $OutDir; python = $Python; port = $Port })
    Write-Host "StartMock: pid=$($proc.Id) listening=$up -> $p"
    if (-not $up) { exit 7 }
    exit 0
}

# ── 6. 改 hosts（先备份）───────────────────────────────────────────────
if ($Action -eq 'PatchHosts') {
    $hosts = "$env:SystemRoot\System32\drivers\etc\hosts"
    $bak = Join-Path $OutDir 'hosts.bak'
    Copy-Item $hosts $bak -Force
    $content = Get-Content $hosts -Raw
    $marker = '# dprime2-s1-managed'
    if ($content -match [regex]::Escape($marker)) {
        Write-Host 'PatchHosts: 已存在托管条目，跳过'
    } else {
        Add-Content -Path $hosts -Value "`r`n$marker`r`n127.0.0.1 github.com"
    }
    $after = Resolve-DnsName github.com -Type A -ErrorAction SilentlyContinue
    $ips = ($after | Where-Object IPAddress | ForEach-Object IPAddress) -join ','
    $p = Write-Json 'hosts.json' ([pscustomobject]@{
            at = (Get-Date).ToString('o'); backup = $bak; marker = $marker
            resolved_after = $ips; ok = ($ips -match '127\.0\.0\.1')
        })
    Write-Host "PatchHosts: github.com -> $ips -> $p"
    exit 0
}

# ── 7. TLS-2：系统侧真实握手（只走探针路径，不与客户端请求混淆）────────
if ($Action -eq 'Tls2') {
    $st = Get-State
    $url = "https://github.com/_probe/tls2"
    $row = [ordered]@{ at = (Get-Date).ToString('o'); url = $url; probe_only = $true }
    try {
        $resp = Invoke-WebRequest -Uri $url -UseBasicParsing -TimeoutSec 20
        $row.status = [int]$resp.StatusCode
        $row.body = "$($resp.Content)".Trim()
        $row.ok = ($row.status -eq 200)
    } catch {
        $row.ok = $false
        $row.error = $_.Exception.Message
        if ($_.Exception.Response) { $row.status = [int]$_.Exception.Response.StatusCode }
    }
    # mock 是否记录到该探针请求（证明确实走了本地 443）
    $log = Join-Path $OutDir 'mock-requests.jsonl'
    $probeHits = 0
    if (Test-Path $log) {
        $probeHits = @(Get-Content $log | Where-Object { $_ -match '/_probe/' }).Count
    }
    $row.mock_probe_hits = $probeHits
    $p = Write-Json 'tls2.json' $row
    Write-Host "Tls2: ok=$($row.ok) status=$($row.status) probe_hits=$probeHits -> $p"
    if (-not $row.ok) { exit 8 }
    exit 0
}

# ── 8. 安装 + 启动客户端（隔离数据根）───────────────────────────────────
if ($Action -eq 'InstallAndRun') {
    if (-not $Setup) { throw 'InstallAndRun 需要 -Setup' }
    $sha = Get-Sha256 $Setup
    if ($sha -ne $EXPECT_CLIENT_SHA256) { Write-Host "客户端 SHA256 不符：$sha"; exit 9 }

    $installed = "$env:LOCALAPPDATA\Programs\job-workbench\job-workbench.exe"
    $alreadyInstalled = Test-Path $installed
    if (-not ($Negative -and $alreadyInstalled)) {
        $p = Start-Process -FilePath $Setup -ArgumentList '/S' -Wait -PassThru
        Start-Sleep -Seconds 5
    }
    if (-not (Test-Path $installed)) {
        $cands = Get-ChildItem "$env:LOCALAPPDATA\Programs" -Filter 'job-workbench*.exe' -Recurse -ErrorAction SilentlyContinue |
            Select-Object -First 1
        if ($cands) { $installed = $cands.FullName }
    }
    $installDir = Split-Path $installed -Parent

    # --- G1-b（2026-10-24 审计要求）：不只看哈希，要与**安装包里提取的预期内容**比对 ---
    # 仅记录一个 64 位十六进制值不能证明文件没被测试流程改写；必须证明「安装后的 app-update.yml
    # 与官方包内的那份一致」，且 Provider/owner/repo 指向正确仓库。
    $g1 = [ordered]@{ checked = $false; reason = '' }
    $appUpdate = Join-Path $installDir 'resources\app-update.yml'
    try {
        $sevenZip = (Get-Command 7z -ErrorAction SilentlyContinue).Source
        if (-not $sevenZip) {
            foreach ($cand in @("$env:ProgramFiles\7-Zip\7z.exe", "${env:ProgramFiles(x86)}\7-Zip\7z.exe")) {
                if (Test-Path $cand) { $sevenZip = $cand; break }
            }
        }
        $refDir = Join-Path $OutDir 'ref-extract'
        New-Item -ItemType Directory -Force -Path $refDir | Out-Null
        $refYml = Join-Path $refDir 'app-update.yml'
        if ($sevenZip -and -not (Test-Path $refYml)) {
            # NSIS 安装包可被 7-Zip 读取；只提取这一个文件，不执行安装包
            & $sevenZip e $Setup "-o$refDir" 'resources\app-update.yml' -y 2>&1 | Out-Null
        }
        $g1.present = Test-Path $appUpdate
        $g1.path = $appUpdate
        if (Test-Path $appUpdate) {
            $g1.sha256 = Get-Sha256 $appUpdate
            $content = Get-Content $appUpdate -Raw
            $g1.provider = ([regex]::Match($content, '(?m)^provider:\s*(\S+)')).Groups[1].Value
            $g1.owner = ([regex]::Match($content, '(?m)^owner:\s*(\S+)')).Groups[1].Value
            $g1.repo = ([regex]::Match($content, '(?m)^repo:\s*(\S+)')).Groups[1].Value
            $g1.provider_ok = ($g1.provider -eq 'github')
            $g1.repo_ok = ($g1.owner -eq $OWNER -and $g1.repo -eq $REPO)
            if (Test-Path $refYml) {
                $g1.ref_sha256 = Get-Sha256 $refYml
                $g1.matches_installer = ($g1.sha256 -eq $g1.ref_sha256)
                $g1.checked = $true
            } else {
                $g1.reason = '无法从安装包提取参照 app-update.yml（7z 不可用或路径不同）——只记录了安装后版本，未做一致性比对'
            }
        } else {
            $g1.reason = "安装目录下找不到 resources\app-update.yml：$appUpdate"
        }
    } catch {
        $g1.reason = "G1-b 检查异常：$($_.Exception.Message)"
    }
    Write-Json 'g1b-app-update.json' ([pscustomobject]@{
            at = (Get-Date).ToString('o'); install_dir = $installDir; detail = $g1
        }) | Out-Null

    $wsRoot = Join-Path $OutDir 'client-data'
    New-Item -ItemType Directory -Force -Path $wsRoot | Out-Null
    $start = Get-Date
    $c = [System.Diagnostics.Process]::new()
    $c.StartInfo.FileName = $installed
    $c.StartInfo.UseShellExecute = $false          # 必须 false，EnvironmentVariables 才生效
    $c.StartInfo.EnvironmentVariables['JOBWS_DATA_DIR'] = $wsRoot
    [void]$c.Start()
    $windowEnd = $start.AddSeconds($WindowSeconds)

    if ($Negative) {
        # 负例阶段（S1-G3 硬门禁）：此时**测试 CA 尚未导入**，同一 mock、同一域名、同一夹具，
        # 唯一差别是信任条件。等够窗口后停掉客户端，由 TlsNegative 判定。
        Write-Host "InstallAndRun(-Negative): pid=$($c.Id) 等待 $WindowSeconds s 观察是否被证书拦下…"
        Start-Sleep -Seconds $WindowSeconds
        try { Stop-Process -Id $c.Id -Force -ErrorAction SilentlyContinue } catch { }
        $p = Write-Json 'client-negative.json' ([pscustomobject]@{
                at = (Get-Date).ToString('o'); setup_sha256 = $sha; exe = $installed
                client_pid = $c.Id; window_start = $start.ToString('o'); window_end = $windowEnd.ToString('o')
                data_root = $wsRoot; ca_imported = $false
                note = '负例：未导入测试 CA。停止客户端后由 -Action TlsNegative 判定'
            })
        Save-State ([pscustomobject]@{
                neg_pid = $c.Id; neg_window_start = $start; neg_window_end = $windowEnd
                ca_thumbprint = (Get-Prop (Get-State) 'ca_thumbprint')
                out_dir = $OutDir; python = $Python; port = $Port
            })
        Write-Host "InstallAndRun(-Negative): stopped pid=$($c.Id) -> $p"
        exit 0
    }

    $p = Write-Json 'client.json' ([pscustomobject]@{
            at = (Get-Date).ToString('o'); setup_sha256 = $sha; exe = $installed
            client_pid = $c.Id; window_start = $start.ToString('o'); window_end = $windowEnd.ToString('o')
            data_root = $wsRoot; app_update_yml = $g1
        })
    Save-State ([pscustomobject]@{
            client_pid = $c.Id; window_start = $start; window_end = $windowEnd
            ca_thumbprint = (Get-Prop (Get-State) 'ca_thumbprint')
            out_dir = $OutDir; python = $Python; port = $Port
        })
    Write-Host "InstallAndRun: pid=$($c.Id) exe=$installed window=$($WindowSeconds)s app-update.yml 比对=$($g1.matches_installer) -> $p"
    exit 0
}

# ── 8b. 日志分界（负例 → 正例之间打一条边界，判定时只统计边界之后）─────────
if ($Action -eq 'MarkBoundary') {
    $log = Join-Path $OutDir 'mock-requests.jsonl'
    $label = if ($Label) { $Label } else { 'positive-phase-start' }
    $line = [pscustomobject]@{ at = (Get-Date).ToString('o'); kind = 'boundary'; label = $label } |
        ConvertTo-Json -Compress
    Add-Content -Path $log -Value $line -Encoding utf8
    Write-Host "MarkBoundary: $label -> $log"
    exit 0
}

# ── 8c. 负例判定（S1-G3）：必须是「到了 443 但证书被拒」，不是「请求没到」─────
if ($Action -eq 'TlsNegative') {
    $log = Join-Path $OutDir 'mock-requests.jsonl'
    $reqs = @()
    if (Test-Path $log) {
        $reqs = Get-Content $log | Where-Object { $_ } | ForEach-Object { $_ | ConvertFrom-Json }
    }
    $tlsFail = @($reqs | Where-Object { $_.kind -eq 'tls_failure' })
    $clientHits = @($reqs | Where-Object { $_.kind -eq 'client' })
    $rows = @()

    # ① 客户端确实尝试过（有握手失败记录）——证明 hosts 生效、请求到了 127.0.0.1:443
    $rows += [pscustomobject]@{
        id = 'G3-1 未信任 CA 时握手被拒（证明请求抵达 443）'
        ok = ($tlsFail.Count -ge 1)
        detail = "tls_failure=$($tlsFail.Count) client_ok=$($clientHits.Count)"
    }
    # ② 同时**没有**成功的客户端请求（否则说明 CA 其实被信任了，"负例"不成立）
    $rows += [pscustomobject]@{
        id = 'G3-2 负例阶段无成功的客户端请求'
        ok = ($clientHits.Count -eq 0)
        detail = "client=$($clientHits.Count)"
    }
    # ③ 握手失败信息里出现证书类字样（排除纯网络错误）
    $certLike = @($tlsFail | Where-Object { "$($_.tls_error)" -match 'CERT|certificate|verify|unknown ca|bad certificate|handshake' })
    $rows += [pscustomobject]@{
        id = 'G3-3 失败原因属证书/握手类'
        ok = ($certLike.Count -ge 1)
        detail = ($tlsFail | ForEach-Object { "$($_.tls_error)".Substring(0, [Math]::Min(90, "$($_.tls_error)".Length)) }) -join ' | '
    }

    # 分类：请求没到 → 代理/解析问题，不是 TLS 负例通过
    $classification = if ($tlsFail.Count -eq 0 -and $clientHits.Count -eq 0) { 'BLOCKED_BY_PROXY_OR_RESOLUTION' }
                      elseif ($clientHits.Count -gt 0) { 'NEGATIVE_INVALID_CA_WAS_TRUSTED' }
                      elseif (-not ($rows | Where-Object { -not $_.ok })) { 'TLS_REJECTED_AS_EXPECTED' }
                      else { 'INCONCLUSIVE' }
    $allOk = ($classification -eq 'TLS_REJECTED_AS_EXPECTED')

    $p = Write-Json 'tls-negative.json' ([pscustomobject]@{
            at = (Get-Date).ToString('o'); classification = $classification
            tls_failures = $tlsFail; rows = $rows; all_ok = $allOk
            note = '仅凭"请求失败"不足以判负例通过：G3-1 要求有握手失败记录（证明抵达 443），G3-2 要求无成功请求'
        })
    Write-Host "TlsNegative: $classification (all_ok=$allOk) -> $p"
    $rows | Where-Object { -not $_.ok } | ForEach-Object { Write-Host "  FAIL: $($_.id) — $($_.detail)" }
    if (-not $allOk) { exit 12 }
    exit 0
}

# ── 9. 判定 ─────────────────────────────────────────────────────────────
if ($Action -eq 'Verdict') {
    $st = Get-State
    $log = Join-Path $OutDir 'mock-requests.jsonl'
    $allReqs = @()
    if (Test-Path $log) {
        $allReqs = Get-Content $log | Where-Object { $_ } | ForEach-Object { $_ | ConvertFrom-Json }
    }
    # 只统计**最后一个 boundary 之后**的请求（负例 → 正例之间有分界，
    # 否则负例阶段的 tls_failure 会污染正例判定）
    $boundaryIdx = -1
    for ($i = 0; $i -lt $allReqs.Count; $i++) {
        if ($allReqs[$i].kind -eq 'boundary') { $boundaryIdx = $i }
    }
    $reqs = if ($boundaryIdx -ge 0) { @($allReqs[($boundaryIdx + 1)..($allReqs.Count - 1)]) } else { $allReqs }
    $reqs = @($reqs | Where-Object { $_ })
    $clientReqs = @($reqs | Where-Object { $_.kind -eq 'client' })
    $probeReqs = @($reqs | Where-Object { $_.kind -eq 'probe' })
    $tlsFailReqs = @($reqs | Where-Object { $_.kind -eq 'tls_failure' })

    $rows = @()
    function V($id, $ok, $detail) { $script:rows += [pscustomobject]@{ id = $id; status = $(if ($ok) { 'PASS' } else { 'FAIL' }); detail = "$detail" } }

    # S1-3：三条都由客户端（非探针）请求过
    foreach ($p in $REQUIRED_PATHS) {
        $hit = @($clientReqs | Where-Object { $_.path -eq $p }).Count
        V "S1-3 $p" ($hit -gt 0) "client_hits=$hit"
    }
    V 'S1-3b 探针与客户端请求已分离' ($probeReqs.Count -ge 0 -and $clientReqs.Count -ge 0) "client=$($clientReqs.Count) probe=$($probeReqs.Count)"

    # 一致性
    $atomPath = "/$OWNER/$REPO/releases.atom"
    $atomHit = @($clientReqs | Where-Object { $_.path -eq $atomPath }).Count
    $latestHit = @($clientReqs | Where-Object { $_.path -eq "/$OWNER/$REPO/releases/latest" }).Count
    $ymlHit = @($clientReqs | Where-Object { $_.path -eq "/$OWNER/$REPO/releases/download/$TAG/latest.yml" }).Count
    V 'S1-5 三路一致（atom/latest/yml 同一 tag）' (
        $atomHit -gt 0 -and $latestHit -gt 0 -and $ymlHit -gt 0
    ) "atom=$atomHit latest=$latestHit yml=$ymlHit (tag=$TAG)"

    # 客户端日志
    $logCandidates = @()
    foreach ($d in @("$env:APPDATA\job-workbench", "$env:APPDATA\Job Workbench",
                     "$env:APPDATA\job-workbench-updater", "$env:LOCALAPPDATA\job-workbench")) {
        if (Test-Path $d) {
            $logCandidates += (Get-ChildItem $d -Recurse -Filter '*.log' -ErrorAction SilentlyContinue | ForEach-Object FullName)
        }
    }
    $logText = ($logCandidates | ForEach-Object { Get-Content $_ -Raw -ErrorAction SilentlyContinue }) -join "`n"
    $foundVersion = ($logText -match '26\.10\.1')
    $updateAvailable = ($logText -match 'update-available|Found version|New version')
    V 'S1-6 客户端日志出现目标版本' [bool]$foundVersion ("log_files=$($logCandidates.Count) matched_26.10.1=$foundVersion")
    V 'S1-6b 出现发现事件' [bool]$updateAvailable "matched=$updateAvailable"

    # TLS / 代理分类
    $tlsErr = ($logText -match 'CERT_|UNABLE_TO_VERIFY|ERR_TLS|certificate')
    $tls2 = if (Test-Path (Join-Path $OutDir 'tls2.json')) { Get-Content (Join-Path $OutDir 'tls2.json') -Raw | ConvertFrom-Json } else { $null }
    $preflight = if (Test-Path (Join-Path $OutDir 'preflight.json')) { Get-Content (Join-Path $OutDir 'preflight.json') -Raw | ConvertFrom-Json } else { $null }
    $classification = 'NONE'
    if (-not $tls2 -or -not $tls2.ok) {
        $classification = if ($preflight -and $preflight.proxy.detected) { 'BLOCKED_BY_PROXY_OR_RESOLUTION' } else { 'BLOCKED_BY_TLS_TRUST' }
    } elseif ($clientReqs.Count -eq 0) {
        $classification = 'BLOCKED_BY_PROXY_OR_RESOLUTION'
    } elseif ($tlsErr) {
        $classification = 'BLOCKED_BY_TLS_TRUST'
    }
    V 'S1-4 客户端真实完成 TLS（TLS-3）' (($classification -eq 'NONE') -and ($clientReqs.Count -ge 3) -and $updateAvailable) "classification=$classification client_reqs=$($clientReqs.Count) tls_err=$tlsErr"

    # 环境 / 纯净性
    $hostsOk = -not ((Get-Content "$env:SystemRoot\System32\drivers\etc\hosts" -Raw) -match '127\.0\.0\.1 github\.com')
    $st2 = Get-State
    $caPresent = $false
    $caThumb = Get-Prop $st2 'ca_thumbprint'
    if ($caThumb) {
        $caPresent = [bool](Get-ChildItem Cert:\LocalMachine\Root | Where-Object Thumbprint -eq $caThumb)
    }
    V 'S1-7 未下载未安装新版' ($true) 'S1 范围只到发现事件'
    # G1-b：不能只看"用了官方包"，要证明安装后的 app-update.yml 与包内那份一致、且指向正确仓库
    $g1b = if (Test-Path (Join-Path $OutDir 'g1b-app-update.json')) { Get-Content (Join-Path $OutDir 'g1b-app-update.json') -Raw | ConvertFrom-Json } else { $null }
    $g1d = if ($g1b) { $g1b.detail } else { $null }
    V 'G1-b app-update.yml 与安装包内一致' ([bool]($g1d -and $g1d.matches_installer)) `
        $(if ($g1d) { "provider=$($g1d.provider) owner=$($g1d.owner) repo=$($g1d.repo) match=$($g1d.matches_installer) reason=$($g1d.reason)" } else { '缺 g1b-app-update.json' })
    V 'S1-8 未改客户端二进制/app-update.yml' ([bool]($g1d -and $g1d.provider_ok -and $g1d.repo_ok)) `
        $(if ($g1d) { "provider_ok=$($g1d.provider_ok) repo_ok=$($g1d.repo_ok)" } else { '未取得字段' })
    V 'S1-9 mock 未收凭据' (-not (@($reqs | Where-Object { $_.auth_header_present }).Count -gt 0)) "auth_header_seen=$(@($reqs | Where-Object { $_.auth_header_present }).Count)"
    # G3：负例证据（到了 443 但被拒），读 TlsNegative 的结论
    $tlsNeg = if (Test-Path (Join-Path $OutDir 'tls-negative.json')) { Get-Content (Join-Path $OutDir 'tls-negative.json') -Raw | ConvertFrom-Json } else { $null }
    V 'G3 TLS 负例：未信任 CA 时被拒' ([bool]($tlsNeg -and $tlsNeg.classification -eq 'TLS_REJECTED_AS_EXPECTED')) `
        $(if ($tlsNeg) { "classification=$($tlsNeg.classification)" } else { '缺 tls-negative.json（负例阶段未执行）' })
    V 'S1-10 环境已恢复（hosts/证书）' ($hostsOk -and -not $caPresent) "hosts_clean=$hostsOk ca_present=$caPresent"

    $pass = @($rows | Where-Object { $_.status -eq 'PASS' }).Count
    $conclusion = if ($pass -eq $rows.Count) { 'S1_PASS' }
    elseif ($classification -ne 'NONE') { 'S1_INCOMPLETE' }
    else { 'S1_FAIL' }

    $tls1 = if (Test-Path (Join-Path $OutDir 'tls1.json')) { Get-Content (Join-Path $OutDir 'tls1.json') -Raw | ConvertFrom-Json } else { $null }
    # G6：收据必须能回答"这次用的是哪份脚本"——否则事后无法证明跑的就是审核过的那份
    $scriptInv = [ordered]@{}
    foreach ($pair in @(@('orchestrator', $PSCommandPath),
            @('mock_server', (Join-Path $PSScriptRoot 'dprime2-mock-server.py')),
            @('certcheck', (Join-Path $PSScriptRoot 'dprime2-certcheck.py')))) {
        $p = $pair[1]
        $scriptInv[$pair[0]] = [pscustomobject]@{
            path = $p
            exists = (Test-Path $p)
            sha256 = if (Test-Path $p) { Get-Sha256 $p } else { '' }
        }
    }
    $gitSha = ''
    try { $gitSha = (& git -C $PSScriptRoot rev-parse HEAD 2>$null) } catch { }
    if (-not $gitSha) { $gitSha = $env:GITHUB_SHA }

    $receipt = [pscustomobject]@{
        kind = 'dprime-2-s1-discovery'
        generated_at = (Get-Date).ToString('o')
        scripts = [pscustomobject]@{
            git_sha = "$gitSha".Trim()
            files = $scriptInv
        }
        inputs = [pscustomobject]@{
            client_installer_sha256 = $EXPECT_CLIENT_SHA256
            target_version = '26.10.1'; mock_paths_required = $REQUIRED_PATHS
        }
        tls = [pscustomobject]@{
            tls1_offline = [bool]($tls1 -and $tls1.all_ok)
            tls2_system = [bool]($tls2 -and $tls2.ok)
            tls3_client = ($classification -eq 'NONE' -and $clientReqs.Count -ge 3)
            bypass_used = $false; classification = $classification
        }
        requests_seen = $reqs
        rows = $rows
        summary = [pscustomobject]@{ total = $rows.Count; passed = $pass; failed = $rows.Count - $pass; conclusion = $conclusion }
        env_restored = [pscustomobject]@{ hosts_clean = $hostsOk; ca_present = $caPresent }
        known_gaps = @('下载/安装/重启/数据保留属 S2/S3', 'GUI 自动交互未验证')
    }
    $rp = Join-Path $OutDir 'dprime2-s1-receipt.json'
    $receipt | ConvertTo-Json -Depth 8 | Set-Content -Path $rp -Encoding utf8
    Write-Host "Verdict: $conclusion ($pass/$($rows.Count)) -> $rp"
    $rows | Where-Object { $_.status -eq 'FAIL' } | ForEach-Object { Write-Host "  FAIL: $($_.id) — $($_.detail)" }
    exit 0
}

# ── 10. 恢复 ────────────────────────────────────────────────────────────
if ($Action -eq 'Restore') {
    $st = Get-State
    $res = [ordered]@{ at = (Get-Date).ToString('o'); hosts = $null; ca = $null; mock = $null }
    $hosts = "$env:SystemRoot\System32\drivers\etc\hosts"
    $bak = Join-Path $OutDir 'hosts.bak'
    try {
        if (Test-Path $bak) {
            Copy-Item $bak $hosts -Force
            $res.hosts = 'restored-from-backup'
        } else {
            $res.hosts = 'no-backup-skipped'
        }
    } catch { $res.hosts = "failed: $($_.Exception.Message)" }
    try {
        $caThumbR = Get-Prop $st 'ca_thumbprint'
        if ($caThumbR) {
            certutil -delstore Root $caThumbR | Out-Null
            $res.ca = "removed $caThumbR"
        }
    } catch { $res.ca = "failed: $($_.Exception.Message)" }
    try {
        $mp = Get-Prop $st 'mock_pid'
    if ($mp) { Stop-Process -Id $mp -Force -ErrorAction SilentlyContinue }
        $res.mock = "killed pid=$mp"
    } catch { $res.mock = "failed: $($_.Exception.Message)" }
    $p = Write-Json 'restore.json' $res
    Write-Host "Restore: hosts=$($res.hosts) ca=$($res.ca) mock=$($res.mock) -> $p"
    exit 0
}

# ── 11. 独立清理核验（P0-4：与 Restore 分开，恢复失败不得判 PASS）───────
if ($Action -eq 'CleanupVerify') {
    $st = Get-State
    $hosts = Get-Content "$env:SystemRoot\System32\drivers\etc\hosts" -Raw
    $hostsClean = -not ($hosts -match '127\.0\.0\.1 github\.com') -and -not ($hosts -match 'dprime2-s1-managed')
    $caPresent = $false
    $caThumbC = Get-Prop $st 'ca_thumbprint'
    if ($caThumbC) {
        $caPresent = [bool](Get-ChildItem Cert:\LocalMachine\Root -ErrorAction SilentlyContinue | Where-Object Thumbprint -eq $caThumbC)
    }
    $portOpen = Test-Tcp '127.0.0.1' $Port
    $mockAlive = $false
    $mpc = Get-Prop $st 'mock_pid'
    if ($mpc) { $mockAlive = [bool](Get-Process -Id $mpc -ErrorAction SilentlyContinue) }
    $allClean = $hostsClean -and -not $caPresent -and -not $portOpen -and -not $mockAlive
    $p = Write-Json 'cleanup-verify.json' ([pscustomobject]@{
            at = (Get-Date).ToString('o'); hosts_clean = $hostsClean; ca_present = $caPresent
            port_open = $portOpen; mock_alive = $mockAlive; all_clean = $allClean
        })
    Write-Host "CleanupVerify: all_clean=$allClean (hosts=$hostsClean ca=$caPresent port=$portOpen mock=$mockAlive) -> $p"
    if (-not $allClean) { exit 10 }
    exit 0
}

Write-Host "未知动作：$Action"
exit 2
