# Roadmap

A living document. Current work is in **Now** (below the shipped log); finished
items move to the [changelog](CHANGELOG.md), and items link to a tracking issue
when one exists. Historical implementation records stay in
[`docs/specs/`](docs/specs/) — they are engineering provenance, not the plan.

## Shipped — recent batches (details in the changelog)

- [x] **v0.3.0 "agent-ready workbench" batch (2026-09-14)** — the CLI is one entry point now (`jobws`, PR #95 — **breaking**: the old script names no longer run features, they print a migration hint and exit 2, full mapping table in the changelog); an MCP server (`jobws-mcp`, three read-only tools at v0.3.0, PR #94; the three two-phase write tools landed after) puts the tracker / job pool / dashboard in front of an agent host; **writes became two-phase everywhere** (preview → one-shot token → apply, for `track add` / `import` / `update` / `init`, PR #98 / #99) and the MCP side ships the same flow as three tools sharing one implementation; **outbound TLS got a third, safe option** (fall back to a bundled CA list when the system trust store cannot be loaded — verification stays on by default, PR #96); first-run guidance for an empty workspace (PR #100) and a data-location card in settings (PR #101); skill bodies now use command names and a check keeps repo paths out of them (PR #97); the CodeBuddy plugin shell and cross-host review assets landed (PR #102); the domain contract is written down with `jobws lint domains` + `jobws release check` (PR #103, closing B13/B14); all 14 screenshots were re-shot in both languages (PR #104). **Released 2026-09-14 as `v0.3.0`** (tag → workflow built the installer and attached it) — read the changelog before upgrading, the CLI rename is breaking. Post-release: the IMAP edge case from [#50](https://github.com/chenxiang6663635/job-workbench/issues/50) was verified against a real mailbox and closed — the extra probe connection stays, its removal is tied to the Python 3.12 baseline registered below.
- [x] [#2](https://github.com/chenxiang6663635/job-workbench/issues/2) — Shared UI primitive migration (batch B + batch C), empty / loading / error states on every page. Shipped in PR #15 / #16; the legacy palette still left in `Applications` / `Dashboard` / shell / `ErrorBoundary` is tracked separately as [#17](https://github.com/chenxiang6663635/job-workbench/issues/17) (2026-09-11: scheduled into the v0.2.0 batch)
- [x] Collect early external-user feedback on the install / run experience — **done, and it immediately found something worth acting on**: [#19](https://github.com/chenxiang6663635/job-workbench/issues/19) (an English-speaking user installed it and could not use the interface). See the *English readiness* item below, which exists because of this report
- [x] **English readiness** — **closed 2026-09-13**: the interface itself is bilingual now (full i18n, PR #52/#54/#55/#56/#57/#58 → [#19](https://github.com/chenxiang6663635/job-workbench/issues/19) closed), so every part below is resolved. README / CONTRIBUTING / issue templates were already English. **Same-day follow-up (v0.2.2)**: the *reverse* leak was cleaned too — English strings still hard-coded in the Chinese UI (settings card title, Electron window title and update dialogs) — and `tools/jobws.py lint i18n` grew a hard-coded-**English** check so the class stays closed; its scope and known limits are tracked as [#77](https://github.com/chenxiang6663635/job-workbench/issues/77).
    - [x] `docs/usage-guide.md` translated to English as the primary version, 简体中文 kept as `usage-guide.zh-CN.md`
    - [x] English trigger phrases in the 5 `SKILL.md` `description` fields — the model matches requests against those descriptions, and they are Chinese-only today, so the "just drive it from your AI CLI" path is *also* closed to an English user ([#19](https://github.com/chenxiang6663635/job-workbench/issues/19)). **2026-09-10: 随技能改名同批加上（PR #25），五个技能的描述均已含 `English triggers:`**
    - [x] Make the Chinese-first caveat land **before** the download step instead of inside a blockquote under *UI Preview* — documenting a limitation is not the same as it being acceptable ([#19](https://github.com/chenxiang6663635/job-workbench/issues/19)). **2026-09-10 进展：提示已前移到 Download 标题下；但按本项自己的标准（"记录一个限制 ≠ 这个限制可以接受"）；**2026-09-13 起界面双语，这条限制本身已被解除——提示随删除（比把提示挪位置更彻底），[#19](https://github.com/chenxiang6663635/job-workbench/issues/19) 关闭**
- [x] **v0.2.2 bilingual + hardening batch (2026-09-13)** — the interface ships bilingual (English + 简体中文, header switch, system language on first run, choice remembered); outbound TLS now follows one policy (`tools/tls_policy.py`: verify by default, refuse when the trust store can't be loaded, opt-in downgrade only — issue [#59](https://github.com/chenxiang6663635/job-workbench/issues/59)); the IMAP edges got their audit follow-ups (issue [#50](https://github.com/chenxiang6663635/job-workbench/issues/50)); accessibility pass **B15** (native radio groups replace tabs-as-segmented-controls, axe exemptions emptied, keyboard walkthrough, **all seven pages share one content width**); docs screenshots became two sets (English in `docs/screenshots/`, 简体中文 in `docs/screenshots/zh-CN/`). **Shipped: PR #75 / #76 / #78 / #79 / #80 / #81 / #85, released 2026-09-13** — see the changelog for the outbound-TLS behaviour change. (Tag `v0.2.2` was cut only after #85, which fixed a release-blocking packaging defect: the PyInstaller dependency graph missed the `tools/` modules, so the packaged backend crashed on startup — now guarded by a packaged-backend smoke step in the release workflow.)
- [x] **v0.2.0 closeout batch (2026-09-11)** — job pool ↔ tracker linking (directory-name match + one-click apply), job pool four sorts + status filter, dashboard "high-score not applied" + score-tier × status distribution; legacy palette migration ([#17](https://github.com/chenxiang6663635/job-workbench/issues/17)); regression expansion ([#4](https://github.com/chenxiang6663635/job-workbench/issues/4)); then a single-pass re-shoot of all 7 screenshots and release **v0.2.0** — which carries the breaking `jwb-` skill rename (migration steps go into the Release notes). **Shipped: PR #29 / #30 / #31 / #32 / #33 / #34, released 2026-09-12**

### Earlier batches (details in the changelog)

- [x] Reproducible desktop packaging (PyInstaller backend exe → Electron NSIS) — shipped as `job-workbench-setup-0.1.1-win64.exe` on the v0.1.1 release; one-command rebuild via `scripts/build_desktop.ps1`
- [x] [#3](https://github.com/chenxiang6663635/job-workbench/issues/3) — One-command demo workspace (`init_workspace.py --demo`) so a fresh clone shows a fully populated workbench in 30 seconds — shipped in PR #20
- [x] [#4](https://github.com/chenxiang6663635/job-workbench/issues/4) — Expand privacy & anti-fabrication regression coverage as the Web surface grows — **shipped in PR #32**: portability resolution, CSV-import privacy & atomicity, and doc relative-link reachability (three previously untested surfaces)
- [x] **Release automation** — shipped in PR #23: tag (`v*`) triggers the Windows build and attaches the installer to the Release, so the v0.1.1 asset drift is now structurally impossible; the v0.2.0 release will be its first real run

## Now — 不发布积累期：三桶推进（2026-10-09 登记）

> 上一段「DSH 接入件第二阶段：自包含发行物」已全部完结（P2-1…P2-5 + 文档收口，
> PR #281–#286；逐项见 [CHANGELOG](CHANGELOG.md)），`v26.10.0` 已于 2026-10-06 发布。
> 用户拍板**暂不发布**：发布节点维持 `26.11.0`（十一月换月）。候选清单来自
> 2026-10-08 积累期审计（四路并行侦察 + 外部对照），报告归档
> [`docs/research/2026-10-08-accumulate-backlog-audit.md`](docs/research/2026-10-08-accumulate-backlog-audit.md)。

**三桶推进**（桶一 → 桶二 → 桶三；桶三只登记、不主动开工）：

- [x] **桶一：取号前小修批**（一个 PR，2026-10-09）— 正确性六项（评分档位小数缝隙、
  插件解析字母序兜底、CLI 默认工作区零校验、令牌簿记三连、渲染临时文件前缀、
  `history.csv` 双保险）+ `jd_score` 纯函数测试群 + 登记漂移回填 + 站点口径收口 +
  治理四项（远端已合并分支清理、#204/#259 核对、审计报告归档）。
- [ ] **桶二：积累期主线**（按周推进，十一月初取号前收口）— 测试盲区（JD↔简历差距
  链路 / MCP 只读工具 / `mail_dates` / 硬门槛判定）、读放大优化（先 `--durations`
  观测再上 xdist）、重复实现收编（越界判定三处 / ISO 解析两份 / CSV 读取两份，收编后
  `cross_end_audit` 复核）、贴线文件拆 1~2、前端体验（路由懒加载 / 长表虚拟化 /
  数据根设置页入口 / 笔记图片端点）、双语与 a11y、CodeQL 评估、**DSH `jobws://`
  只读资源真机核验**（三个技能把它当 JD 正文唯一读法，结构性盲区）。
- [ ] **桶三：触发条件驱动**（不主动开工）— 390 整站、托盘、ICS RRULE、Outlook
  OAuth2、Electron 主版本升级、代码签名、winget、国内直链、macOS、marketplace 收录
  （**必须在 npm 首发之后**）。凡涉发布物形态与元数据者：取号前落定或顺延。

**发布节点**：`26.11.0`（十一月发车，单一发布节点）；`26.10.1` 只留给四类阻断
hotfix（安全 / 数据损坏 / 安装·启动阻断 / 更新链失效）。

**Graduation (the first timestamped release is the 1.0-equivalent)**: it ships when the workbench
is stable for daily use and the workspace format promises **backward compatibility** — new columns
and tables are read as empty when missing and written with unified headers, so no user-side
conversion is ever required. **判据已成文（2026-09-22）**：四条可核的条件、支持策略与数据兼容条款见
[`docs/support-and-compatibility.md`](docs/support-and-compatibility.md)。

**毕业判定（2026-10-09）**：四条判据全部满足——① 连续 14 天自用无阻断（dev 栈，9-26 起）；
② 主流程冒烟全绿（八页 + CLI + CI 全 job，`v26.10.0` 上）；③ 无未决 P0/MAJOR（开放
issue 仅 minor/跟踪类）；④ 兼容条款经 `v26.10.0` 升级真机复装验证（旧工作区直接打开）。
判定证据见 [`docs/releases/26.10.0-verification.md`](docs/releases/26.10.0-verification.md)。

## Later

- [x] Third-party domain profiles — **shipped in v0.3.0** (PR #103): [`docs/domain-contract.md`](docs/domain-contract.md) is the contribution contract and `jobws lint domains` validates a third-party profile (structure + dictionaries parse), so a new industry plugs in without touching core code
- [x] **English UI (i18n)** — **shipped 2026-09-13** (details in the [changelog](CHANGELOG.md)): bilingual 简体中文 / English with a header switch, first run follows the system language, choice remembered; the domain enum *values* stay Chinese on purpose (shared contract with the CLI and your data). Closed [#19](https://github.com/chenxiang6663635/job-workbench/issues/19)
- [x] Richer maintainer automation — **partly shipped in v0.3.0** (PR #103): `jobws release check --tag v26.9.0` validates the tag/version match (since 2026-09-24: exact equality under the month-granularity CalVer scheme) and the changelog section, and prints the release notes CI will publish (the workflow assembles the Release body from the changelog). Anything beyond that still has to pay for itself
- Accessibility and localization beyond zh-CN / en
- [x] Desktop auto-update (electron-updater) — **shipped in v0.2.1** (asks twice: download, then restart; the first updater-enabled version still needed one manual install)
- [x] **Real-time application status** — **shipped in v0.3.0**: the research (2026-09-11) found that no recruiting platform exposes a candidate-facing status API, so the answer is local — *paste the email* → parse (which record, what to change, and the sentence it came from) → confirm row by row → write, with a read-only IMAP pull as the optional sync on top (verified against a real mailbox, 2026-09-14). 时间与会议链接的抽取已在 `Now` 段的 **Mail structuring** 条目交付（PR #176）；宣讲会一侧的扩展登记在下方候选池

## 候选池（暂缓，逐条写明触发条件）

**这一节是什么**：暂缓事项的集中登记处。与上面 `Later` 的区别是——这些**没有承诺**，只是「想过、决定现在不做」。每条都写明**什么条件下才值得做**，将来不必重新论证一遍；已经定了「怎么做」的决策在 [`docs/README.md`](docs/README.md) 的「决策记录」一节（ADR），这里只回答「要不要做」。

**纪律**：往这里加条目只需一行「一句话 + 触发条件」；真正要开工时，先从 `Now` 走一遍四道门（`CONTRIBUTING.md` 的「新需求四道门」），再把它从这里移出去（`Now` 段只保留一行状态指针，不重复描述）。

| 候选 | 一句话 | 触发条件 |
|---|---|---|
| 考公赛道（原批 7，2026-09-22 暂缓） | 阶段名做成赛道配置（默认值与今天一致，现有工作区零改动）、题库加考公主科预设 | 确定要考公，且日常使用已稳定（先看 [`docs/support-and-compatibility.md`](docs/support-and-compatibility.md) 的毕业条件） |
| 整站 390px 适配 | 顶栏与看板网格在窄屏本就横向溢出；e2e 基线钉的只是「不再变坏」 | 手机成为主要使用场景，或基线再次被真实回归触发 |
| 宿主内渲染工作台界面 | 在 AI 宿主里开面板，而不是切到浏览器或桌面壳 | 宿主开放稳定的渲染 API，且界面成为主要使用方式 |
| 长任务扩展（面试周 / 备考周） | 一次性把一段时间的任务排开、按周复盘 | 出现连续两周以上的高强度面试或备考 |
| 浏览器表单预填 | 只预填、不提交（自动投递永不考虑，见 ADR） | 平台页面结构稳定，且用户明确要求 |
| ICS 重复会议（RRULE） | 现在只取首个实例并在卡片注明；需要时评估 `icalendar`（BSD-2） | 真实收到重复会议邀请，且因此误判过一次时间 |
| 用户级 / 插件缓存副本的一致性 | 检查器只看仓库内的项目级副本（范围说明见 [`CONTRIBUTING.md`](CONTRIBUTING.md) 的「资产分发到各宿主」），用户级 `~/.agents/skills/` 与插件缓存在视野之外 | 出现「装到用户级却长期用旧版」的真实事件 |
| 依赖主版本升级（Electron 等） | 调研已做（[`docs/research/report_electron_33_to_44.md`](docs/research/report_electron_33_to_44.md)）；升级要人工批次、单独冒烟 | 安全修复需要，或宿主 / 打包链要求 |
| 文档英文润色（超出 i18n 范围） | README 与文档的英文由人过一遍（术语一致但语感生硬） | 有英文母语使用者开始用时 |
| 托盘常驻 + 开机自启 | 关窗后退到托盘、继续发到点提醒（带总开关）。现在**关窗即停**——刻意的轻量取舍（工具类惯例：VS Code / Obsidian 也是关窗即退；驻留托盘属"持续通知职责"类应用） | 提醒成为日常依赖（真实发生过"关着窗口错过截止"），或用户明确要求后台常驻 |
| 区域可拖拽组合布局（桌面端） | 面板 / 分栏可拖放重组（候选库：dockview / flexlayout-react）；需要新的布局容器模型、持久化与每页迁移，8 页响应式基线要重写 | 多屏 / 宽屏成为主要使用方式，或面板重排成为日常诉求（先看 UI 线 A / B 落地后的真实使用） |
| offer / 薪酬差比较（2026-10-08 外部对照） | 多 offer 条款与薪酬差本地分析——敏感数据恰是「本地优先」的优势场景 | 同时持有两个以上真实 offer，且比较需要表格化 |
| 按 JD 定向模拟面试出题 | 题库→按 JD 生成定向题组 + 复盘链路（已有 `bank drill` 与复盘卡，增量小；中英信息源近一年共同热点） | 真实面试邀约给出 JD 后想练定向题 |
| 简历「AI 味」自检 | 面向反 AI 筛查的生成度 / 个性化检查，输出改写建议而非代写（与本仓诚实红线天然契合） | 出现因「AI 味」被筛的真实反馈 |
| 浏览器扩展一键收职位 | 招聘页一键书签进看板（Teal 式形态） | 技术债「本地 API token」先行，且手动录入成为日常负担 |
