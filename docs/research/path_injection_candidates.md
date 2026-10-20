# `py/path-injection` 逐条候选清单（2026-10-19，机械映射）

> **本文回答什么**：每个 open 告警的**编号 → 位置 → 所在函数 → 该函数内是否出现自研校验器**。
> **本文不回答什么**：某条数据流是否**已经被证明安全**。审计已指出——「所在函数引用了校验器」不等于「这条流已受控」；而且**校验常在调用方**，core 层普遍如此，所以函数内为空 ≠ 没防。
>
> 本文的用途只有一个：**把"37 条还是 25 条"这种口径争议变成可逐条勾选的编号清单**，让 dismissal 决策能按编号走，而不是按段落口号走。

## 一、方法（可复现）

```powershell
# ① 拉全量 open 告警（3 页，任何一页失败即中止——避免把不完整读数据当结论）
1..3 | ForEach-Object { gh api "repos/chenxiang6663635/job-workbench/code-scanning/alerts?state=open&per_page=100&page=$_" }
# ② 取 most_recent_instance.location.start_line，从该行往上找最近的 def，取函数体
# ③ 函数体内是否出现：escape_reason / segment_reason / safe_join / within_any /
#    strictly_within_any / read_in_workspace / is_within_or_equal / inside( / is_in_workspace
```

## 二、与我上一份分诊文档的口径对账（**更正**）

| 项 | 上一份（`report_path_injection_triage.md`） | 本文（机械口径） |
|---|---|---|
| 有依据的条数 | 37（jobs 14 + jd_gap 13 + resume 8 + open_folder 2） | **函数内可见校验器 25 条**（jobs 14 + jd_gap 8 + resume 3） |
| `jd_gap.py` | **13 条全部上游已防** | **8/13**（4 条 `segment_reason` + 4 条 `is_in_workspace`）；其余 5 条函数内无校验器 |

**差在哪**：旧的「13 条全部上游已防」只对 **Web** 路径成立（`jobs.py:461` 先 `safe_join`）。审计指出 CLI / MCP 是另外的入口，这条批评是对的——`#339` 补掉了 `domain`/`direction` 那 4 条（`segment_reason`），但 `parse_lexicon` / `_read_text` / `_resume_text` 里还有 **5 条**函数内看不到校验器。

旧的「resume 8 / open_folder 2」是**人工判断**，不是机械判据——本文把它们从「有依据」里移出，单列待核（open_folder 的证据是「预设键白名单 + 字面量可执行文件」，属**另一类**判据，见 §四）。

## routers/jobs.py（协议层）（14 条，其中函数内可见校验器 14 条）

| 告警 | 行 | 所在函数 | 函数内校验器 | 处置（待你勾） |
|---:|---:|---|---|---|
| #91 | 175 | `_summary` | `safe_join`、`read_in_workspace`、`inside(` | ☐ |
| #92 | 182 | `_summary` | `safe_join`、`read_in_workspace`、`inside(` | ☐ |
| #93 | 236 | `list_jobs` | `safe_join` | ☐ |
| #94 | 241 | `list_jobs` | `safe_join` | ☐ |
| #95 | 243 | `list_jobs` | `safe_join` | ☐ |
| #96 | 267 | `create_job` | `safe_join` | ☐ |
| #97 | 273 | `create_job` | `safe_join` | ☐ |
| #98 | 275 | `create_job` | `safe_join` | ☐ |
| #99 | 396 | `fetch_jd` | `safe_join` | ☐ |
| #100 | 397 | `fetch_jd` | `safe_join` | ☐ |
| #101 | 438 | `job_detail` | `safe_join`、`read_in_workspace` | ☐ |
| #102 | 461 | `job_gap` | `safe_join` | ☐ |
| #104 | 472 | `job_gap` | `safe_join` | ☐ |
| #103 | 474 | `job_gap` | `safe_join` | ☐ |

## core/jd_gap.py（领域层）（13 条，其中函数内可见校验器 8 条）

| 告警 | 行 | 所在函数 | 函数内校验器 | 处置（待你勾） |
|---:|---:|---|---|---|
| #198 | 63 | `resolve_profile` | `segment_reason` | ☐ |
| #199 | 96 | `resolve_profile` | `segment_reason` | ☐ |
| #201 | 100 | `resolve_profile` | `segment_reason` | ☐ |
| #200 | 101 | `resolve_profile` | `segment_reason` | ☐ |
| #202 | 114 | `parse_lexicon` | **—** | ☐ |
| #203 | 116 | `parse_lexicon` | **—** | ☐ |
| #204 | 147 | `_read_text` | **—** | ☐ |
| #205 | 149 | `_read_text` | **—** | ☐ |
| #206 | 167 | `_input_anchor_errors` | `is_in_workspace` | ☐ |
| #207 | 174 | `_input_anchor_errors` | `is_in_workspace` | ☐ |
| #208 | 199 | `_collect_master_text` | `is_in_workspace` | ☐ |
| #209 | 200 | `_collect_master_text` | `is_in_workspace` | ☐ |
| #210 | 219 | `_resume_text` | **—** | ☐ |

## routers/resume.py（协议层）（32 条，其中函数内可见校验器 3 条）

| 告警 | 行 | 所在函数 | 函数内校验器 | 处置（待你勾） |
|---:|---:|---|---|---|
| #112 | 85 | `list_versions` | **—** | ☐ |
| #113 | 88 | `list_versions` | **—** | ☐ |
| #114 | 95 | `list_versions` | **—** | ☐ |
| #115 | 96 | `list_versions` | **—** | ☐ |
| #116 | 97 | `list_versions` | **—** | ☐ |
| #117 | 115 | `_list_template_files` | **—** | ☐ |
| #118 | 118 | `_list_template_files` | **—** | ☐ |
| #119 | 131 | `_list_template_files` | **—** | ☐ |
| #120 | 132 | `_list_template_files` | **—** | ☐ |
| #123 | 264 | `template_content` | `safe_join`、`inside(` | ☐ |
| #124 | 271 | `template_content` | `safe_join`、`inside(` | ☐ |
| #125 | 283 | `template_file` | `safe_join`、`inside(` | ☐ |
| #126 | 313 | `build_template` | **—** | ☐ |
| #127 | 330 | `build_template` | **—** | ☐ |
| #128 | 341 | `get_resume` | **—** | ☐ |
| #129 | 345 | `get_resume` | **—** | ☐ |
| #130 | 359 | `save_resume` | **—** | ☐ |
| #131 | 360 | `save_resume` | **—** | ☐ |
| #132 | 377 | `preview_html` | **—** | ☐ |
| #133 | 381 | `preview_html` | **—** | ☐ |
| #134 | 406 | `export_doc` | **—** | ☐ |
| #135 | 410 | `export_doc` | **—** | ☐ |
| #136 | 457 | `build_resume` | **—** | ☐ |
| #137 | 463 | `build_resume` | **—** | ☐ |
| #138 | 470 | `build_resume` | **—** | ☐ |
| #139 | 471 | `build_resume` | **—** | ☐ |
| #140 | 476 | `build_resume` | **—** | ☐ |
| #141 | 485 | `build_resume` | **—** | ☐ |
| #142 | 487 | `build_resume` | **—** | ☐ |
| #143 | 502 | `build_resume` | **—** | ☐ |
| #147 | 583 | `suggest_rewrite` | **—** | ☐ |
| #148 | 587 | `suggest_rewrite` | **—** | ☐ |

## routers/system.py（协议层）（17 条，其中函数内可见校验器 0 条）

| 告警 | 行 | 所在函数 | 函数内校验器 | 处置（待你勾） |
|---:|---:|---|---|---|
| #156 | 92 | `_iter_files` | **—** | ☐ |
| #157 | 135 | `_apply_retention` | **—** | ☐ |
| #158 | 138 | `_apply_retention` | **—** | ☐ |
| #159 | 142 | `_apply_retention` | **—** | ☐ |
| #160 | 151 | `_apply_retention` | **—** | ☐ |
| #162 | 173 | `system_paths` | **—** | ☐ |
| #163 | 174 | `system_paths` | **—** | ☐ |
| #161 | 177 | `system_paths` | **—** | ☐ |
| #164 | 193 | `system_paths` | **—** | ☐ |
| #165 | 193 | `system_paths` | **—** | ☐ |
| #166 | 255 | `backup_workspace` | **—** | ☐ |
| #167 | 256 | `backup_workspace` | **—** | ☐ |
| #168 | 273 | `backup_workspace` | **—** | ☐ |
| #169 | 273 | `backup_workspace` | **—** | ☐ |
| #170 | 280 | `backup_workspace` | **—** | ☐ |
| #171 | 318 | `open_folder` | **—** | ☐ |
| #172 | 320 | `open_folder` | **—** | ☐ |

## 三、可用于逐条批准的集合（机械证据最硬的部分）

> **姿态（2026-10-19 审计纠正）**：本文的 22 条是"具备进一步复核价值"的集合，**不是**已证明
> 安全的误报；属既有安全债务。**不阻塞** G2/G3 发行验收，**不批量 dismiss**——先补足
> source→sink 证据，人工批准发生在有证据之后。

| 组 | 条数 | 机械判据 | 建议 |
|---|---:|---|---|
| `routers/jobs.py` | **14** | 所在函数内**全部**可见 `safe_join` / `read_in_workspace` / `inside(` | 逐条核 source→sink 后可 `false positive` |
| `core/jd_gap.py` 的 8 条 | **8** | 4 条 `segment_reason`（`#339` 新增）+ 4 条 `is_in_workspace` | 同上 |
| 合计 | **22** | —— | **这是唯一建议进入首批 dismissal 的集合** |

其余 **51 条**（`jd_gap` 5 + `resume` 29 + `system` 17）保持 open：函数内看不到校验器，需要人工沿调用链核，不能靠本文的机械列下结论。

## 四、两类**不适用机械判据**的条目（单列，别混进上面的表）

| 条目 | 为什么机械判据不适用 | 应怎么核 |
|---|---|---|
| `system.py:open_folder`（#171/#172） | 路径不来自用户拼接，而是**预设键白名单**取出的固定目录 + 字面量可执行文件 | 核白名单是否穷举、有无「键未命中则回落用户输入」的分支（S2 矩阵已核实过一次） |
| `resume.py` 的 `build_template` / `export_doc` 等 | 路径来自 `_pdf_dir(ws)` 等已有归属校验的助手，校验在**调用方**而非本函数 | 逐条沿 `ws → _pdf_dir → 本函数` 走一遍，而不是看本函数体 |

## 五、下一步（需要你）

1. 在 §二 的表格里对 **22 条**逐条勾「认可 / 驳回」；
2. 认可的逐条填 dismissal 理由（`false positive` 优先——这些是「CodeQL 未识别已实施的校验」；`mitigated` 只在确有补偿控制时用；**不要一律 `won't fix`**）；
3. 勾完我把结果落成 `dismissals.md` 并执行——**在你勾之前我不会动任何 dismissal**。
