# 发布检查清单（Release Checklist）

> 每次打 tag 前过一遍。分两栏：**CI 自动**（release.yml 已固化，绿了就是过了）与
> **人工必做**（必须有人的判断或桌面会话，机器替代不了）。配套阅读：`docs/contributing.zh-CN.md`
> 的「发布流程」七步与「版本号体系」；版本号 = 月粒度 CalVer `YY.MM.N`（`26.9.0`
> 首发 / `26.9.1` hotfix / `26.10.0` 换月）。
>
> 出事了怎么办（RUNBOOK，见第三节）：**撤 latest 标记 → 发一个版本号更高的修复版**
> ——electron-updater 不会接受相同或更低的版本号覆盖，「删掉坏的 Release 重传」无效。
>
> **本轮（v26.10.0）的勾选状态：2026-10-06 记录**。CI 各项与「版本落章」三项已由
> 演练 `37434793050` 与 `release check --tag v26.10.0`（exit 0）验证并勾选；真机与发布
> 那几项已补勾——证据归档在 [`releases/26.10.0-verification.md`](releases/26.10.0-verification.md)
> （#275）。**下一个发布节点请把勾选重置**（清单是可复用的操作单，不是台账）。
> **本批新增**：Release 说明模板重构（`release_notes_format.py`：直链下载置顶 /
> 不重复版本号大标题 / English Highlights 折叠）——下一节点 dry_run 首用；
> 「发布后完整验证链」已由维护者完成并确认（2026-10-07 补记；证据见 [`releases/26.10.0-verification.md`](releases/26.10.0-verification.md)）。

## 〇、发布阻断清单（任一存在即不发布）

数据损坏 / 静默覆盖 · secret 泄漏 · 路径越界 · installer 装不上或起不来 · 更新链失效 · 主流程阻断 · privacy 文案与行为不一致 · backup–restore 不可靠。其中四类**不等功能批次**、可直接 `26.10.1` hotfix：安全 / 数据损坏 / 安装·启动阻断 / 更新链失效。完整定义与发布窗口纪律见 docs/contributing.zh-CN.md 的「发布治理」节。

**26.11.0 的已知阻断项**（2026-10-28 审计发现，落章前必须处置或如实登记）：

> 逐条验收（含「已自动化 / 需真机 / 无法构造」的三分标注）见
> [handover/2026-10-28-release-acceptance-matrix.md](handover/2026-10-28-release-acceptance-matrix.md)。

- [ ] **26.10.1 的公开自动升级链未端到端验证**：P-2（真实客户端能发现）/ P-3（能下载）/
      P-4（能安装并重启——`quitAndInstall(true,true)` 与 `elevate.exe` 分支从未执行）/
      P-5（自动升级路径的数据保持）全部为 `NOT_EXECUTED`。26.10.1 已按政策例外公开并
      以独立文件接受残余风险，但那份文件 §二.6 明确写着**「26.11.0 发行门禁必须重新审查
      完整更新路径，不得继承本次例外」**。
      → 落章前要么真做一次真实客户端自动升级，要么在 release notes 里如实写明「未验证」。
- [ ] **风险接受文件的签字状态未闭合**：`docs/releases/26.10.1-post-release-risk-acceptance.md`
      §五 仍为「☐ 待签」，签字人 / 日期 / 复核责任人三格空白。首次复核日 **2026-11-02**
      前须统一口径（补签凭据，或把 `26.10.1-verification.md` 的「处置已作出」改成
      「已裁决、待签」——**不得倒签**）。
- [ ] **Electron 与已公开的 TLS 证书公告（两条状态不同，别合并成一句）**：
      · **已发布的 `v26.10.1` 仍是 44.4.5** → 用户手里的版本**仍在受影响范围**；
        是否出 `26.10.2` 属独立的安全维护决策，本清单不替它做结论
      · **当前 `main` 已升到 44.10.0**（#439）→ 开发主线的依赖修补已完成
      上游建议 44 系列升到 44.9.1+。这条链与 Python `certifi` 的 PEM 基线**无关**
      （一个是 Electron 内置 Chromium/Node TLS，一个是 Python CA 包），
      现有构建门禁覆盖不到——`certifi` 的门禁通过**不能**用来回答本条。
      评估见 [`2026-10-28-electron-tls-advisory-review.md`](handover/2026-10-28-electron-tls-advisory-review.md)；
      落章前须先回答「打包制品的确切运行时」与「实际 TLS 请求路径」两问，再定 C-1 / C-2。
      目前**没有证据表明攻击已发生**，也未证实该路径在本项目配置下可被利用。

## 一、CI 自动（release.yml，绿了即过）

- [x] 闸 1：tag `v26.10.x` 与 `web/electron/package.json` 的 version **逐字一致** — v26.10.0：演练 `37434793050` 通过（package.json 读为 `26.10.0`）
- [x] 闸 2：CHANGELOG 有同名版本段（抽段即 Release 说明） — v26.10.0：`release check --tag v26.10.0` exit 0（段 77 行）
- [x] 闸 3：产物 exe + `latest.yml` 真实产出（缺 latest.yml 拒发——老用户收不到更新） — v26.10.0：exe 131.6 MB 级 + `latest.yml`（26.10.0 + sha512 + size）已在演练 artifact 内核过
- [x] 后端 exe 冒烟（`scripts/smoke_backend_exe.py`：起产物 → 健康检查） — v26.10.0：演练内步骤通过（起进程 + `/api/system/check` + 资源自检）
- [x] **安装/卸载冒烟**（NSIS `/S` 静默装 → 验证 → 静默卸载；2026-09-24 新增） — v26.10.0：演练内装→验→卸→等目录消失全通过
- [x] **SHA256SUMS.txt** 生成并挂 Release（**完整性**补偿：证明下载未损坏、与已发布文件一致；**不构成发布者身份认证**——未签名场景的身份信任根是 GitHub 账号与仓库保护；也**不能**用于「按 commit 重建校验」——electron-builder 产物非字节可复现，同一个 commit 重跑会得到不同哈希） — v26.10.0：清单已生成，真下载重算 exe 哈希与清单一致
- [x] **SBOM**（`sbom.spdx.json`，Python + npm 两条链）随 Release 挂出 — **v26.10.0 首次勾选**：`release.yml` 固化（生成器 `tools/gen_sbom.py`；零包即构建失败），532 packages 随 Release 与演练 artifact 双处核到；解读见下方「SBOM 怎么用」
- [x] **Release notes 自动附加**未签名 / SmartScreen 说明（微软官方口径：未签名拦截页更严重、每版本信誉归零） — v26.10.0：说明尾部含中英安装说明 + 校验和块；**2026-10-06 起说明模板重构**（直链下载置顶 / 不重复版本号大标题 / English Highlights 折叠，`release_notes_format.py`）
- [x] **发布证明链（全量 E2E）**：`publish` 依赖 `[package, e2e]`——E2E 红则 Release 不会创建（2026-09-25 起的并行结构） — v26.10.0：run `37452235789` 内通过
- [x] 发布后核验资产：exe + blockmap + latest.yml + SHA256SUMS.txt（**v26.10.0 起五样**，含 sbom.spdx.json）全在（**打 tag 后**才做） — v26.10.0：五样齐（见 `releases/26.10.0-verification.md`）

**SBOM 怎么用**（issue #206）：软件物料清单——两条链（`requirements.lock` /
`package-lock.json`）全部包名与版本的机器可读清单，SPDX 2.3 JSON 随 Release 挂出
（`sbom.spdx.json`）。用途：某依赖爆 CVE 时直接对照受影响版本区间，不必重建当时的
依赖树。导入：grype / Dependency-Track 等工具原生可读；临时查一个包用
`jq '.packages[] | select(.name=="fastapi")' sbom.spdx.json` 即可。注意
`licenseDeclared` 一律 `NOASSERTION`——锁文件里没有许可证事实，不猜。

## 二、人工必做（发布日，约 15 分钟 + 真机）

**版本落章**：

- [x] `python tools/jobws.py release version` 取号 → bump `web/electron/package.json`（同一号） — v26.10.0：#272 已落章（package.json / 技能 ×9 metadata / plugin.json 由 `assets_registry --write` 重生成 / CHANGELOG 段名，四处同步）
- [ ] **DSH 两包同号**：`integrations/dsh/package.json` 与 `integrations/dsh/platform/win32-x64/package.json` 一起改成同一个号（2026-10-19 补：原文只写「四处同步」，照单落章会漏掉这两处。闸是有的但分两段——`assets_registry --check` 只校验**主包** vs 应用版本，子包 vs 主包由 `scripts/build_mcp_exe.ps1` 校验（不一致即 exit 1），所以**先落章、再构建**才拿得到全链验证）
- [x] CHANGELOG `[Unreleased]` 改为 `[版本号] - ISO 日期` → `release check --tag v<号>` 绿 — v26.10.0：`## [26.10.0] - 2026-10-06`；`release check` exit 0
- [x] dry_run 演练：`gh workflow run release.yml -f dry_run=true -f tag=v<号>` → 下载 artifact 里的安装包 — v26.10.0：`37434793050` success（产物已下载并**四重核验**：artifact digest / 解压六件 / exe sha256 / exe sha512 对照 `latest.yml`）

### 落章执行单（逐条命令 + 校验点，2026-10-19 补）

> **时机硬约束**：号是**日期的函数**（同月 N 递增、换月重置）。2026-10-19 实测
> `release version` 输出 `26.10.1`——**要到 11 月才输出 `26.11.0`**。提前落章 =
> 发的是十月 hotfix 号，不是本版目标。

**0. 前置**：G1 已批准；`main` 干净；`gh pr list --state open` 为空。

**1. 取号**（确认输出就是目标号再往下）

```powershell
python tools\jobws.py release version
```

**2. 六处同号**（改完才算落章；**只有第 5 处是生成的，其余都手改**）

| # | 位置 | 怎么改 |
|---|---|---|
| 1 | `web/electron/package.json` | 手改 `version`（**唯一真值源**） |
| 2 | `integrations/dsh/package.json` | 手改（`assets_registry --check` 校验它 == 应用版本） |
| 3 | `integrations/dsh/platform/win32-x64/package.json` | 手改（`build_mcp_exe.ps1` 校验它 == 主包） |
| 4 | `skills/*/SKILL.md` ×9 的 `metadata.version` | **手改 9 处**——`assets_registry --write` **不碰技能**；`jobws skills check` 校验 == 应用版本 |
| 5 | `.codebuddy-plugin/plugin.json` + `marketplace.json` | `python tools\assets_registry.py --write` 生成（手改会被覆盖） |
| 6 | `CHANGELOG.md`：`## [Unreleased]` → `## [26.11.0] - 2026-11-XX` | 手改段名（内容不动） |

**3. 校验（三道闸，顺序不能反）**

```powershell
python tools\jobws.py skills check          # 技能 metadata 与插件壳/应用版本三向对齐（9 个）
python tools\assets_registry.py --check     # plugin.json / marketplace.json 与真源一致
pwsh -NoProfile -ExecutionPolicy Bypass -File scripts\build_mcp_exe.ps1
                                            # 子包版本 == 主包（不等 exit 1）；产出 bin/ 与 prebuilds.json
                                            # 需**非 editable 的构建 venv**（脚本默认探测
                                            # D:\tools\venvs\jobws-mcp-build；别用开发用的 jobws-mcp venv）
                                            # **必须用 pwsh 7**：脚本是 UTF-8 无 BOM，Windows PowerShell
                                            # 5.1 会按 ANSI 解码，中文注释被拆坏 → ParserError（2026-10-19 实测）
python scripts\smoke_mcp_exe.py             # 17 工具 + 数量/末位/真调两个后补工具
python tools\jobws.py release check --tag v26.11.0
                                            # 段名 + tag 与版本一致；不通过会给具体原因
```

**4. 产物预检（npm 两包）**

```powershell
cd integrations\dsh\platform\win32-x64; npm pack --dry-run    # 期望含 bin/jobws-mcp.exe + prebuilds.json
cd ..\..; npm pack --dry-run                                   # 期望含 cordis.patch.yml / skills / platform
```

**5. 之后**：dry_run 演练（`gh workflow run release.yml -f dry_run=true -f tag=v26.11.0`）
→ 下载产物核验 → tag（`git tag -a v26.11.0 -m "..."` 并推送，**有外部副作用**）
→ npm 首发（**子包先、主包后**）→ 收录 PR。

**中途的"预期红"（不要误判成坏）**：只改了第 1 处时，`jobws skills check` 会报
「skills/*/SKILL.md 的 metadata.version 与应用版本不一致」、`assets_registry --check`
会报 plugin.json/marketplace.json 漂移——都是正常中间态。**`--write` 只治后两者**，
技能那 9 处仍要手改，改完两道闸才一起绿。

**真机冒烟**（自己的 Windows 真机，CI 没有桌面会话）：

- [x] **通知实测**：造一条今天到期的待办 → 确认 toast 真的弹出（CI 测不了通知） — v26.10.0：真机通过（dry-run 产物）
- [x] **双开**：第二个实例应直接退出并聚焦已有窗口 — v26.10.0：真机通过（dry-run 产物）
- [x] **离线启动**：断网启动应安静（更新检查失败只进日志，不弹窗） — v26.10.0：真机通过（dry-run 产物）
- [x] 人眼验收四项：八个页面各操作一遍 / 深浅主题各看一遍 / 设置页搜索与单项还原 / 中英切换 — v26.10.0：真机通过（dry-run 产物）
- [ ] **截图新鲜度**：界面有可见改动时重拍（`npm.cmd run capture`，8 页 × 中英），并确认 `docs/screenshots/` 与当前 UI 一致 — v26.10.0：本版改动（笔记搜索状态行）不在截图页范围，未重拍；下一节点含 UI 改动时一并重拍
- [x] **DSH preset boot**（D4 遗留，v26.10.0 起纳入）：带 `preset.yml` 的真实 boot——`--dump-config` 零启动合成零警告 + headless 实跑 exit 0；已知边界：headless 无 `agentPresets` 服务，preset 停 pending 属宿主形态（详见 `integrations/dsh/README.md` 待补条）

**发布**：

- [x] `git tag -a v<号> <commit> && git push origin v<号>` → CI 走完 — v26.10.0：tag **annotated** 显式钉在 `0f9cfd8`（真机验证产物的构建提交——同源纪律），run `37452235789` success
- [x] `gh release view` 核资产 → **真下载一次** → 核对 SHA256 — v26.10.0：真下载核验通过（`197fe105…ca954` = `SHA256SUMS.txt`）
- [x] **发布后完整验证链**（人工至少一次——验的是"用户拿到的东西"，不是本地构建产物）：真下载 → 安装 → 首次启动 → 建工作区 → 打开旧工作区 → 退出 → 再启动 → 卸载（CI 已自动覆盖安装/卸载冒烟；这条是人眼版）——v26.10.0：**维护者确认已完成**（2026-10-07 补记：原「连续两版未做」表述不确）
- [x] 发布公告要素：定位一句话 / 隐私承诺（**按 `docs/data-flow-matrix.md` 表述**——不复述"不联网"类绝对句）/ SmartScreen 说明（已自动附）/ issue 反馈入口 — v26.10.0：要素文本已入 [`releases/26.10.0-verification.md`](releases/26.10.0-verification.md) 的「发布公告要素（草稿）」节（#277，2026-10-07）
- [x] **官网下载页核验**：确认站点「下载」页版本号 / 发布日期已随本次发版自动更新（`site.yml` 在 main push 后重建 `site-dist`，版本号不人工维护），并确认主下载与「Issues 留言获取备用链接」两条通道可达 — v26.10.0：首页与下载页均显示 26.10.0（2026-10-06 核验）；同批把下载页主通道改为**版本化直链**（`releases/download/v<版本>/…`，模板占位符随每版自动更新）
- [ ] **Hotfix 例外的官网同步（`26.10.1` 这类一次性发行线；机制已由 #372 落地）**：官网版本来自
  `site/published-release.json`（**不再是 main 的 `web/electron/package.json`**），生产构建对该文件
  fail-closed。分两阶段：
  **A. 发布前**：机制生效、站点展示真实已发布版本（现为 `v26.10.0`）、Hotfix 资产与哈希已审核、
  切换与失败处置方案就绪；**不要求 tag 前直链已指向 `26.10.1`**（Release 未公开时该链不存在）。
  **B. Release 公开后立即**：核对 26.10.1 资产 → 更新 `published-release.json`（填真实 SHA256）→
  触发 `site-dist` → 点击核验中英文下载页。失败时**不得**把 `v26.10.0` 重新设为主下载，应指向
  26.10.1 的 GitHub Release 直链或显示维护提示。
  验收：中英文页显示 `26.10.1`、直链可达、`latest.yml` 指向 26.10.1、首页区分「已发布版/开发中源码」。
  见 [`2026-10-21-26.10.1-policy-exception.md`](handover/2026-10-21-26.10.1-policy-exception.md) §四。
- [x] **归档发布验证记录**：复制骨架 → 新建 `docs/releases/<版本>-verification.md` 并填本次事实（tag / commit / workflow run / 资产哈希 / 真机项 / 发布后核验）——**清单是操作单、会被下一版重置；这份文件是不重写的历史** — v26.10.0：`releases/26.10.0-verification.md`（#275）

## 三、发布后 72 小时（RUNBOOK）

- [ ] 盯 GitHub Issues（无遥测，这是唯一反馈面）
- [ ] 盯 Release 下载量（Release 页侧栏 / API）
- [ ] 出问题：撤 latest 标记 → **发更高版本号的修复版** → README 置顶已知问题 → 公告说明

## 四、v1.x 待办（不阻塞本节点）

### 真机清单（下一发布节点并入）

- [ ] **桌面快捷方式生成确认**：`build.nsis.createDesktopShortcut` 已为 `true`（#218，配置层完成）——v26.10.0 真机未专项确认（用户装在自选目录）；并入下一节点真机冒烟。

### 长期

- [ ] winget 分发（`winget-create` 从 installer URL 生成 manifest，人工提 PR）
- [ ] 代码签名评估 —— **已决策：暂不采购（2026-10-02，#202）**；选项矩阵（Azure Trusted Signing 已排除：限美加 + 3 年实体）/ 触发条件 / 若触发的改造清单见 [`decisions/code-signing.md`](decisions/code-signing.md)
- [ ] 更多领域插件（`docs/domain-contract.md`；`jwb-domain-setup` 技能上线后引导用户自助生成）
