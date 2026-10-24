# upgrade-smoke 的纯判据函数（无副作用、不碰注册表/文件/网络）。
#
# 为什么单独成文件（2026-10-24）：这些判据原先内联在 upgrade-smoke.ps1 的主流程里，
# 只能靠 grep 关键词做静态自检——而静态检查抓不到"elseif 少一个前置条件""变量在某些
# 路径未初始化"这类异常分支缺陷（RT-9 正是这样漏过去的）。抽成纯函数后，
# upgrade-smoke.selftest.ps1 可以 dot-source 本文件并**实际调用**它们跑组合用例。

# RT-9：PDF 导入返回值的三态判定。
#
# 背景（resume.py 实测）：
#   提取失败          → 422 resume.extractFailed
#   提取成功、停模型   → 502 之一：modelHttpError / modelUnreachable / modelCallFailed / modelNotJson
# 所以：
#   弱结论 RT-9-1 = status == 502（任一分支）→ 已越过本地提取；
#   强结论 RT-9-2 = status == 502 且 error_code == modelUnreachable。
#
# 返回 @{ Rt91Ok; Detail; Rt92Kind = 'PASS'|'GAP'|'FAIL'; Rt92Detail }
#   PASS → 命中强结论
#   GAP  → 判据无法落地（502 到了但 error_code 读不出 / RT-9-1 未通过故前提不成立）
#   FAIL → 判据明确不符（502 且解析出了别的错误码）
function Get-Rt9Verdict {
    param(
        [int] $Status,
        [string] $ErrorCode = '',
        [string] $Body = ''
    )

    $passedExtract = ($Status -eq 502)
    $detail = "http=$Status error_code=" + $(if ($ErrorCode) { $ErrorCode } else { '<unparsed>' })

    $result = @{
        Rt91Ok     = $passedExtract
        Detail     = $detail
        Rt92Kind   = 'GAP'
        Rt92Detail = ''
    }

    if (-not $passedExtract) {
        # 200 / 422 / 0（无响应）——强结论的前提不成立。不能说"命中别的 502 分支"，
        # 也不能记通过；记缺口并写明前置未满足。
        $result.Rt92Detail = "前置未满足：RT-9-1 未通过，无从判定强结论；$detail"
        return $result
    }

    if ($ErrorCode -eq 'resume.modelUnreachable') {
        $result.Rt92Kind = 'PASS'
        $result.Rt92Detail = $detail
        return $result
    }

    if (-not $ErrorCode) {
        # 502 到了但错误码读不出来（解析器差异）→ 判据无法落地，不放宽成 PASS。
        $rawSnippet = if ($Body) { ($Body -replace '\s+', ' ') } else { '<empty body>' }
        $result.Rt92Kind = 'GAP'
        $result.Rt92Detail = "证据缺口：502 已到但 error_code 未解析；raw=" + $rawSnippet.Substring(0, [Math]::Min(140, $rawSnippet.Length))
        return $result
    }

    # 502 且解析出了别的错误码 → 真实的判据不符。
    $result.Rt92Kind = 'FAIL'
    $result.Rt92Detail = $detail
    return $result
}
