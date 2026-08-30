# 简历 PDF 生成脚本（Windows PowerShell）
# 用途：将同目录下 resume_*.html 打印为 A4 一页 PDF，并校验页数。
# 运行：右键"使用 PowerShell 运行"，或 PowerShell 中执行 .\build_resume_pdf.ps1
#
# 依赖：Google Chrome（自动探测）；校验页数需要 Python + pypdf（可选）。
#
# 照片：同目录 photo.jpg 会被嵌入两份简历头部右侧（24mm × 33.6mm，一寸照比例）。
#   更换照片：直接覆盖 photo.jpg 即可；不需要照片时，删除 HTML 中的 <img class="photo" ...> 一行。
# 版面：若 PDF 超过一页，优先微调照片尺寸与行距，不要删减核心事实（见文末提示）。

$ErrorActionPreference = "Stop"
$pdfDir = Split-Path -Parent $MyInvocation.MyCommand.Path

# 1. 探测 Chrome
$chromePaths = @(
    "C:\Program Files\Google\Chrome\Application\chrome.exe",
    "C:\Program Files (x86)\Google\Chrome\Application\chrome.exe",
    "C:\Program Files (x86)\Microsoft\Edge\Application\msedge.exe",
    "C:\Program Files\Microsoft\Edge\Application\msedge.exe"
)
$chrome = $chromePaths | Where-Object { Test-Path $_ } | Select-Object -First 1
if (-not $chrome) {
    Write-Host "未找到 Chrome / Edge，无法生成 PDF。" -ForegroundColor Red
    exit 1
}
Write-Host "使用浏览器: $chrome" -ForegroundColor Gray

# 2. HTML -> PDF 映射
$jobs = @(
    @{ Html = "resume_hvac.html";       Pdf = "某用户_简历_空调制冷HVAC_v1.1.pdf" },
    @{ Html = "resume_datacenter.html"; Pdf = "某用户_简历_数据中心冷却_v1.1.pdf" }
)

foreach ($job in $jobs) {
    $html = Join-Path $pdfDir $job.Html
    $pdf  = Join-Path $pdfDir $job.Pdf
    if (-not (Test-Path $html)) {
        Write-Host "跳过（HTML 不存在）: $($job.Html)" -ForegroundColor Yellow
        continue
    }
    Write-Host "生成: $($job.Pdf)" -ForegroundColor Cyan
    $prevEap = $ErrorActionPreference
    $ErrorActionPreference = "Continue"   # Chrome 会向 stderr 输出无关注噪，避免中断
    & $chrome --headless --disable-gpu --no-pdf-header-footer --virtual-time-budget=4000 --print-to-pdf="$pdf" "$html" 2>&1 | Out-Null
    $ErrorActionPreference = $prevEap
    if (Test-Path $pdf) {
        $size = [math]::Round((Get-Item $pdf).Length / 1KB, 1)
        Write-Host "  完成 ($size KB)" -ForegroundColor Green
    } else {
        Write-Host "  生成失败" -ForegroundColor Red
    }
}

# 3. 页数校验（需要 pypdf；缺失则跳过）
Write-Host ""
Write-Host "页数校验（应为 1 页）:" -ForegroundColor Cyan
$pyCheck = @"
from pypdf import PdfReader
import glob, os, sys
d = r'$pdfDir'
for f in sorted(glob.glob(os.path.join(d, '*.pdf'))):
    n = len(PdfReader(f).pages)
    flag = 'OK' if n == 1 else 'WARNING'
    print(os.path.basename(f), '页数:', n, flag)
"@
$tmpPy = Join-Path $env:TEMP "check_resume_pages.py"
Set-Content -Path $tmpPy -Value $pyCheck -Encoding UTF8
try {
    python $tmpPy 2>&1 | ForEach-Object { Write-Host "  $_" }
} catch {
    Write-Host "  （未检测到 pypdf，跳过页数校验；请手动打开 PDF 确认为一页）" -ForegroundColor Yellow
}
Remove-Item $tmpPy -Force -ErrorAction SilentlyContinue

Write-Host ""
Write-Host "提示：若 PDF 超过一页，按既定顺序删减：驾驶证 -> 本科 GPA/部分课程 -> Profile 压一行 -> 项目1方法细节 -> 标准栏。" -ForegroundColor Gray
Write-Host "绝不先删：X% 结果、控制贡献、SCI、硕士课程成绩、工程实践。" -ForegroundColor Gray
