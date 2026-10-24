# D′-2 S1 受控更新源：评审交付包（2026-10-24）

> 状态：**可审查、可 dispatch、尚未执行**。未 push、未 dispatch、未装任何软件、未改本机网络/证书。
> 本次**未** dispatch，也**未**把 S1 与 D′-1 混在一起——D′-1 的实现已合入 main（`5f6ca06`）。

---

## 一、本轮最重要的产出：3 个真实缺陷（自检通过 ≠ 可 dispatch）

这是本轮的核心价值。**离线自检 40/40 曾让这套方案看起来就绪，但逐行核对上游源码后发现三处必失败/假阳性缺陷。**

### 缺陷 1（P0，dispatch 必失败）：`StartMock` 根本不生成元数据夹具

`dprime2-s1.ps1` 的 `StartMock` 只写 `server.crt` / `ca.crt` / `server.key` / `probe.txt`，
**没有 `atom.xml` / `latest.json` / `latest.yml`**。而 mock 的三条路由全部从 `--root` 读这三个文件。

| 后果 | 三条路由全 404/500 → 客户端 `Cannot parse releases feed` 或 `No published versions` |
|---|---|
| 为什么自检没抓到 | 自检**自己手写了**这三份夹具（`selftest-offline.py` 原 L113-116），把生产路径的缺口掩盖了 |
| 修法 | 新增 `-Action PrepareFixtures`，从固定 RC 派生三份夹具 + 自洽校验；`StartMock` 缺任一夹具即 `throw`；**自检改为走同一条路径** |

### 缺陷 2（P1，假阳性风险）：mock 不校验 `Accept`，比真实 GitHub 宽松

`GitHubProvider.getLatestTagName()`（6.8.9 `out/providers/GitHubProvider.js:158-175`）对 `github.com`：

```js
const url = newURL(`${this.basePath}/latest`);                    // .../releases/latest
const rawData = await this.httpRequest(url, { Accept: "application/json" });
const releaseInfo = JSON.parse(rawData);
return releaseInfo.tag_name;
```

真实站点**只有带 `Accept: application/json` 才回 JSON**，否则 302 到 `/releases/tag/<tag>` 的 HTML，
客户端 `JSON.parse(HTML)` 必然失败。原 mock 无条件回 JSON → 客户端漏发该头时我们仍判"成功"。

**修法**：mock 在缺 `Accept: application/json` 时返回 **302 → `/releases/tag/<tag>`**（并新增该落点路由）。
副作用是好的：收据里多一个 `accept` 字段，可**证明客户端确实发了正确的头**（支撑 S1-G2）。

### 缺陷 3（已在 D′-1 修，`main=5f6ca06`）：RT-9 异常分支三处

见 PR #389。与 S1 无关，但同一批「静态自检抓不到异常分支」的教训。

---

## 二、真实请求路径清单（逐行核对本地 `electron-updater@6.8.9` 安装版本）

核对对象：`web/electron/node_modules/electron-updater@6.8.9`（**实际锁定的版本**，不是上游 master）。

| # | 请求 | 触发位置 | 关键约束 |
|---|---|---|---|
| 1 | `GET https://github.com/<owner>/<repo>/releases.atom` | `GitHubProvider.js:43`，`accept: application/xml, application/atom+xml, text/xml, */*` | `parseXml` 后必须存在 `entry`（否则 `ERR_UPDATER_NO_PUBLISHED_VERSIONS`） |
| 2 | `GET https://github.com/<owner>/<repo>/releases/latest` | `GitHubProvider.js:93` → `getLatestTagName()` | **仅稳定版走这条**（`allowPrerelease=false`）；必须 `Accept: application/json`，响应 `JSON.parse().tag_name` |
| 3 | `GET https://github.com/<owner>/<repo>/releases/download/<tag>/latest.yml` | `GitHubProvider.js:116-121` | tag 来自请求 2；404 报 `Cannot find latest.yml in the latest release artifacts` |

**两条强约束（mock 必须满足，否则假阴性）**：

1. `hrefRegExp = /\/tag\/(v?[^/]+)$/`（`GitHubProvider.js:10`）——atom 的 `entry > link[href]` **必须以 `/releases/tag/v26.10.1` 结尾**；
2. `hrefMatch[1] === tag`（`:100`）——atom 里捕获的 tag 必须与请求 2 返回的 `tag_name` **完全一致**（`v26.10.1`，带 `v`）。

**⚠ 与早前材料的一处修正**：三个请求**是顺序且条件性的**，不是无条件三连——
请求 2 只在 `allowPrerelease=false`（默认）时发生；`allowPrerelease=true` 时 tag 直接从 atom 的 href 取。
本项目 `updater.js` 未开 prerelease，故稳定版三请求成立。但**判定时不能只看"三条都到过"**，
还要看 `kind=client` 且顺序合理（时间戳递增）。

**重定向**：`electronHttpExecutor.js:22` 是 `redirect: "manual"`，由 `addRedirectHandlers`（`:64-73`）手动跟随。
所以 mock 的 302 会被客户端自己跟一次——这条链必须在 mock 里闭合（已加 `tag.html`）。

---

## 三、TLS 证明方案（三层，只有 TLS-3 算数）

| 层 | 内容 | 在哪做 | 能证明什么 |
|---|---|---|---|
| **TLS-1** | 证书**离线**结构检查：CN/SAN（DNS:github.com + IP:127.0.0.1）、有效期、EKU serverAuth、CA 基本约束、**用 CA 公钥验叶子签名**、私钥与证书公钥模数一致 | mock 启动**之前**，纯本地 | 证书材料本身正确。**不做任何握手** |
| **TLS-2** | 系统侧真实 HTTPS 握手，**只打 `/_probe/tls2`** | 起 mock + 改 hosts 之后 | Windows 信任库能接受该 CA；但**不**代表 Electron 能 |
| **TLS-3** | **真实 26.10.0 客户端的 Electron 网络会话**完成含证书校验的 HTTPS | 客户端启动后 | **唯一的 S1 客户端 TLS 证据** |

**网络栈事实**（本轮据上游源码确认）：更新请求走 `ElectronHttpExecutor → electron.net.request()` →
**Chromium 网络栈** + `session.fromPartition("electron-updater", {cache:false})`，**不是** Node `https.request`。

因此：
- `NODE_EXTRA_CA_CERTS` **不是**首选/必要条件（它影响 Node 侧，不是 Chromium 会话）；
- 不能据此断言"Windows 根存储的 CA 一定会被接受"——**仍须 TLS-3 实测**；
- **禁止**用 `setCertificateVerifyProc` 或任何忽略证书错误的开关让它"通过"（那会改变要证明的默认信任行为）。

**Chromium 还会考虑系统代理/PAC/WPAD** → 若请求没到 mock，必须归为
`BLOCKED_BY_PROXY_OR_RESOLUTION`，**不得**混进 `BLOCKED_BY_TLS_TRUST`。

---

## 四、隔离与恢复合同

### 三处根必须分别核对（缺一不可）

| 根 | 变量/路径 | 隔离方式 | 谁验证 |
|---|---|---|---|
| 宿主配置根 | `DSH_HOME` | 本方案不涉及（S1 不启动 DSH） | — |
| Electron 用户目录 | `%APPDATA%\@deepseek-ai\...` / `%APPDATA%\<productName>` | runner 是一次性托管机，天然隔离 | 收据记录 `runner` 字段 |
| **业务数据根** | `JOBWS_DATA_DIR` | `InstallAndRun` 注入 `$OutDir\client-data` | 收据 + 独立清理核验 |

### 变更清单与可逆性

| 变更 | 备份 | 恢复 | 独立核验 |
|---|---|---|---|
| hosts 追加 `127.0.0.1 github.com` | `hosts.bak` 完整复制 | `Restore` 用备份覆盖 | `CleanupVerify` 检查**无**该行、**无**标记注释 |
| CA 导入 `Cert:\LocalMachine\Root` | 记录指纹 | `certutil -delstore Root <thumb>` | `CleanupVerify` 检查 Root 下**不存在**该指纹 |
| mock 进程监听 443 | 记录 PID | `Stop-Process` | `CleanupVerify` 检查端口**已关闭**且 PID **不存在** |

**恢复独立于主流程**：`Restore` 与 `CleanupVerify` 都是 `if: always()` 的**独立 workflow 步骤**，
不依赖脚本内部 `finally`（脚本被 kill 时 `finally` 未必执行）。`CleanupVerify` 不干净 → `exit 10` → 结论不得为 `S1_PASS`。

---

## 五、测试矩阵

| 组 | 覆盖 | 数量 | 性质 |
|---|---|---|---|
| A | 禁项扫描（剥注释）/ hosts 只经 PatchHosts / Restore 与 CleanupVerify 分立 / mock 只绑回环 | 4 | 静态 |
| B | `VerifyRc` 实跑 + RC 身份逐项 | 2 | **实跑** |
| C | `NewCert` 实跑 / 三份证书产物 / `Tls1` 全过 / 未做握手 | 4 | **实跑** |
| **C2** | **`PrepareFixtures` 实跑 / 夹具自洽 5 项 / 派生关系标注 / 三份元数据在位** | **6** | **实跑（新增）** |
| D | mock 监听 / 三条路由内容逐字节一致 / **缺 Accept → 302** / 探针路径 / 未知 404 / 请求分类 / 归属字段 | 7 | **实跑** |
| E | `Verdict` 三态分类（NONE / 代理阻断 / TLS 阻断） | 3 | **实跑** |
| F | 工作流 12 步齐全 / 4×`always()` / `actions:read` / 无 PR 触发 / 固定 run-id | 5 | 静态 |
| **G** | **`PrepareFixtures` 存在 / `StartMock` 缺夹具拒绝启动 / 工作流含该步 / mock 校验 Accept / 302 落点 / 记录派生关系** | **6** | 静态（回归钉子） |

**合计 53/53 通过**（`selftest-result.txt`）。原为 40/40，本轮 +13。

---

## 六、六项硬门禁对照（S1-G1…G6）

| 门禁 | 要求 | 当前状态 | 说明 |
|---|---|---|---|
| **S1-G1** 客户端真实性 | 官方 26.10.0 包 SHA256、安装后版本、`app-update.yml` 原样、updater 精确版本 | **设计已覆盖 / 运行时未证** | 工作流第 3 步下载并校验 `197fe105…`；`InstallAndRun` 再验一次；`app-update.yml` 不改（只在 runner 上读，不做断言 → **建议补一条 `G1-b`：安装后读 `resources/app-update.yml` 并记录其 SHA256**） |
| **S1-G2** 网络接管完整性 | 真实 Electron 更新进程的请求日志 | **设计已覆盖 / 运行时未证** | mock 记录 `kind/path/at/tls_version/cipher/ua/accept/remote`；**只能 runner 证明**。⚠ 早前材料说"三请求必需"，本轮已修正为"稳定版顺序三请求" |
| **S1-G3** TLS 真实性 | 系统握手 + 真实 Electron 请求均验签；**错误证书负例必须失败** | **部分覆盖** | TLS-1/2/3 已设计；**负例（用错误 CA 起 mock 应失败）尚未实现** → 建议加 `-Action TlsNegative`（P1） |
| **S1-G4** 受控源一致性 | 元数据版本/文件名/SHA512/RC SHA256 相互对应，不用占位包冒充 | **已覆盖（本轮修补）** | `VerifyRc` 6 项 + `PrepareFixtures` 5 项自洽；`latest.yml` 是 RC **原件**，`atom/latest.json` 标注为**派生** |
| **S1-G5** 隔离和恢复 | 无 Token、无真实数据、变更前后快照、失败仍恢复 | **已覆盖** | 见第四节；`CleanupVerify` 独立步骤 |
| **S1-G6** 可审计收据 | 脚本 SHA、runner、请求轨迹、证书指纹、实际状态、独立清理结果 | **部分覆盖** | 收据有 runner/指纹/请求轨迹/清理结果；**脚本 SHA 尚未入库**（本方案未 push，见 §八） |

**结论：G4/G5 可判"设计已闭环"；G1/G2/G3/G6 仍有 4 个待补项**（G1-b、G3 负例、G6 脚本 SHA 入库）。

---

## 七、精确到输入 SHA 的 dispatch 操作单（**未执行**）

```powershell
# 前置：本目录 5 个文件已入仓库（当前未 push，见 §八）
gh workflow run dprime2-s1-discovery.yml `
  --repo chenxiang6663635/job-workbench `
  --ref main `
  -f old_sha256=197fe10593eb50b127c87aaa690ad575aee7dc38b001110de5421e4df52ca954 `
  -f rc_run_id=39748850478 `
  -f window_seconds=45
```

**固定输入表**：

| 项 | 值 | 校验点 |
|---|---|---|
| 旧客户端 | `job-workbench-setup-26.10.0-win64.exe` | SHA256 `197fe105…2ca954` |
| RC 来源 | run `39748850478`，artifact `installer` | 下载后 `VerifyRc` |
| RC 安装包 | `job-workbench-setup-26.10.1-win64.exe` | SHA256 `fbc6bbee…5615c7` |
| RC `latest.yml` | 同 artifact | SHA256 `aa4d8197…23dc7b` |
| 目标版本 | `26.10.1` | `latest.yml` version |
| 观察窗口 | 45s | 客户端延时触发（事实基线 5s） |

**运行后必查（不看绿标，看收据）**：

1. `head_sha` 是否等于审核过的提交（`gh run view <id> --json headSha`）；
2. `mock-requests.jsonl` 里 `kind=client` 的三条是否都在、时间递增、`accept` 含 `application/json`；
3. `tls2.json` 的 `mock_probe_hits ≥ 1`（证明确实走了本地 443）；
4. `cleanup-verify.json` 的 `all_clean = true`；
5. 客户端日志是否出现 `26.10.1` 与 `update-available`。

---

## 八、未做 / 需要你裁决的事项

### 我发现但**未擅自实施**的两项

1. **G1-b**：安装后读 `resources/app-update.yml` 并记录 SHA256（证明更新源配置未被改动）。**建议加**，改动很小。
2. **G3 负例**：用**错误 CA** 起 mock，断言客户端**失败**。这是"TLS 真的在验"的最强证据，但会增加一次 runner 时间与一次预期失败。**需要你决定是否纳入 S1**。

### 授权边界（严格遵守）

| 项 | 状态 |
|---|---|
| 本地设计/Mock/脚本/自检 | ✅ 已做（本轮 +13 条自检、修 2 个真缺陷） |
| push 到仓库 | ❌ 未做（5 个文件仍在 `D:\g2g3-build\dprime2\`） |
| workflow_dispatch | ❌ 未做 |
| 装正式候选做 E2 | ❌ 未做 |
| 改本机网络/证书 | ❌ 未做 |
| 改 hotfix `ce789f4` / tag / Release | ❌ 未做 |

**一个必须先解决的问题**：S1 要在 runner 上跑，脚本必须**在仓库里**（workflow 要 checkout）。
所以"入仓库"是 dispatch 的前置——但入仓库不等于授权执行。**请明确：是否允许把 5 个文件作为 PR 提交（不合并、不 dispatch）？**

### 与 26.10.1 的关系

- S1 使用的是**同一个** RC（`fbc6bbee…`），**不重建**；
- S1 若通过，回答的是"旧客户端能否被受控源发现"= E1；
- **E1 不等于 E2**，更不等于政策 §五 的"自动更新链实测"——后者需完整发现→下载→安装→重启（S2/S3），
  且 Draft Release 对 `electron-updater` **不可见**（该机制性冲突仍在，需单独裁决路线 ①/②）。
