# 桶二收口记录（2026-10-16，main = `ff25c08`）

> 用途：G0 退出时证明「积累期主线八站全部闭环」，每站给证据而非断言。
> 八站 = 测试盲区 → 读放大/耗时 → 重复实现收编 → 贴线拆分 → 前端体验 →
> 双语与 a11y → CodeQL → DSH `jobws://` 真机核验。

## 一、八站逐站证据

| 站 | 交付 | 证据（合并 PR / 实测） |
|---|---|---|
| 1 测试盲区 | gap 链路、MCP 只读工具、`mail_dates`、硬门槛判定的直测 | #296 / #307 批；全量从 1848 → 1948 passed |
| 2 读放大与耗时 | `--durations` 观测先行，再上 xdist（`-n 4`）与解析卡/看板读放大 | #288 / #289；`-n 4` 全量 19–21s |
| 3 重复实现收编 | 越界判据三处 → `containment.escape_reason`；CSV 读取八处 → `csv_cells.read_rows`；ISO 日期删私有副本 | #290（四端复核零 MAJOR）；`test_dedup_parity.py` 钉同源 |
| 4 贴线拆分 | `tools_readonly` 429→363（`dashboard_sections.py`）、`deps` 239→293（`request_guard.py`）、`_core`→`_workspace.py`、`prep.py`→`prep_files.py`、`MailList`→`MailRows` | 每次拆分均「只搬不改行为」+ 登记水位随实测下调；`lint size` OK |
| 5 前端体验 | 路由懒加载（八页各自成 chunk）、长表窗口化（`useRowWindow`）、数据根重选/清除入口（`DataRootFix`）、笔记插图只读字节端点（`prep_files.py` + `NoteImage`） | #291；生产构建八 chunk 实证、单测 210、eslint 0 error |
| 6 双语与 a11y | 见 §二 | 本轮补齐核查，全绿 |
| 7 CodeQL | 工作流评估 + 告警基线 + **合并保护** | #294 / #295；S4 建 ruleset `codeql-merge-protection`（#316/#317） |
| 8 DSH `jobws://` | 真机核验：宿主**不桥接**资源与提示模板 | 2026-10-12 核验；结论已入记忆（技能与提示改走 `read_job_text` 工具） |

## 二、双语与 a11y 的逐项核查（本轮补证，原为待验项）

**双语**：
- 题库徽章 `bank.badgeDue` / `bank.badgeWrong` 中英对称（zh-CN L119-120 / en L116-117）；
- `docs/glossary.md` 有英文对照版 `glossary.en-US.md`（L5 互相链接）；
- 用户可见模板双语：`template/AGENTS.example.en-US.md`、`template/workspace/README.en-US.md`
  （中文版 L5 各指向对照版）；
- `tools/check_i18n_keys.py`：**死键 0、中英对称**。

**a11y（按审计建议的「最小键盘可达性」范围，不含全站 WCAG 专项）**：

| 项 | 状态 | 证据 |
|---|---|---|
| 跳到主内容 | ✅ 已实现 + **已测** | `App.tsx` L97-103（skip link）+ L233（`<main id="main-content" tabIndex={-1}>`）；`e2e/a11y.spec.ts:118`「Tab 首站可见，Enter 后焦点落到主内容」——正是审计给的验收判据 |
| 主内容语义区域 | ✅ | 同上（`<main>` landmark + 跳转目标有效） |
| 图标按钮可访问名 | ✅ **20/20** | 静态扫描（`.codebuddy/tmp/a11y_scan.py`）：20 个 `size="icon"` 按钮全部带 `aria-label` 或 `title={t(...)}` |
| 列表键盘导航 | ✅ | `NotesSearch.tsx` L131-142：↑↓ 在结果间移动焦点，焦点不在列表内时不抢输入框方向键 |
| 弹窗焦点管理 | ✅ 委托 Radix | 对话组件均为 Radix Dialog（焦点圈禁 + 退出还原为原生能力）；`e2e/dialogs-a11y.spec.ts` 对关键对话框跑 axe |
| 全站对比度 / WCAG AA 专项 | ⏭️ **明确延后** | 不作为本轮范围（审计建议：避免「a11y 收口」无限扩张）；axe 八页扫描仅对 serious/critical 失败，豁免走带节点数的 allowlist |

## 三、审计对账表更新（相对交接包 §二）

| 原登记 | 现状态 |
|---|---|
| `P1-C ⏳（Electron 运行时专项扫描）` | **✅ 已闭环**（#321，九项检查全过、无高危发现） |
| `P1-D ⏳（门禁升级，需仓库权限）` | **✅ 已闭环**（S4：Required 4→6 条 + CodeQL ruleset，负向阻断实证 #315） |
| `P2-B/C 按裁决缓办` | **P2 双根已修**（#311/#312 合并，契约回归网 12 条钉住）；B/C 其余项维持缓办登记 |
| `S2 边界矩阵 待做` | **✅ 已闭环**（#320：五类边界全覆盖，UNC 零覆盖已补，TOCTOU 如实说明成文） |
| `E：筛选校准 等用户确认` | ⏳ **ADR 提案已就绪**（#318），等用户确认三点后进实现批 |

## 四、结论

**桶二八站全部闭环**，积累期主线的事实面工作已清空。G0 剩余退出条件只有
**E 三项确认**（用户裁决）；G1 前的实现面只剩 **E 实现批**与 **D（MCP exe 重打包，
必须排在 E 之后）**；G2/G3 的 `v26.10.0` 隔离安装探针按纪律须用户在场。
