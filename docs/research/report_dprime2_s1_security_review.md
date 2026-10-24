# D′-2 S1 逐项安全审查记录（v3，2026-10-23）

> 对象：`D:\g2g3-build\dprime2\` 下的 5 个交付物 + `D:\g2g3-build\dprime-2-s1-contract.md` v3
> + `D:\g2g3-build\dprime-2-s1-workflow-design.md` v3。
> 性质：**静态审查 + 离线自检**（40/40）。**未**在真实 runner 执行、**未** push/merge/dispatch/tag。

---

## 一、红线逐条对照（合同 §八 R-1…R-8）

| # | 红线 | 实现如何满足 | 证据 |
|---|---|---|---|
| R-1 | 不在日常 Windows 做任何操作 | 所有环境变更（hosts/CA/mock）都由**工作流在 runner 内**执行；本机只做了写文件与高位端口 TLS 自检 | 自检 A4「mock 只绑回环」；自检未调用 PatchHosts/InstallCa |
| R-2 | 不使用真实 GitHub Token 给 mock | mock 无任何鉴权逻辑；`Authorization` 头只记录**是否存在**，绝不使用或外传 | `dprime2-mock-server.py` 的 `auth_header_present`；判据 S1-9 |
| R-3 | 不关 TLS 校验 / 不用 ignore-certificate-errors | 脚本内**零**绕过开关；TLS-2 用普通 `Invoke-WebRequest`（不传 `-SkipCertificateCheck`） | 自检 A1（剥注释后禁项扫描，hits=[]） |
| R-4 | 不修改被测客户端 | 只下载官方 `v26.10.0` 安装包并校验 SHA256；不解包、不改 `app-update.yml` | 判据 S1-8；`InstallAndRun` 先验 SHA256 再装 |
| R-5 | 不触碰正式 Release / Draft / tag / 官网 | mock 只回环；hosts 劫持后不再访问 github.com；工作流无任何 release/tag 动作 | 工作流 `on: workflow_dispatch`，无 `gh release`/`git tag` |
| R-6 | 不使用真实用户数据 | 客户端启动时注入**虚构** `JOBWS_DATA_DIR`；RC 元数据只读 | `InstallAndRun` 的 `client-data` 目录 |
| R-7 | 不调用模型 / 外部 API | 全链路无模型调用；mock 不转发任何外部请求 | 源码审查 |
| R-8 | 任一红线触发 → 停止并登记，失败路径也恢复 | `Restore` 与 `CleanupVerify` 都是 `if: always()`，且**互相独立** | 工作流步骤 14/15；自检 F2 |

---

## 二、逐文件审查

### 1. `dprime2-s1.ps1`（编排，12 动作）

| 动作 | 读 | 写 | 系统变更 | 风险点 / 处置 |
|---|---|---|---|---|
| Preflight | 代理注册表、`netsh`、DNS、端口、安装目录 | `preflight.json` | 无 | 只读探测；代理检出即记录并 `ABORT` 要求处置 |
| VerifyRc | RC 目录 | `rc-identity.json` | 无 | 任一项不符 `exit 4` 中止 |
| NewCert | — | `ca.crt`/`server.crt`/`server.key`/`certs.json` | **无**（纯内存 + 落盘到 OutDir） | CA 名独立、SAN 含 DNS+回环 IP |
| Tls1 | 上述证书 | `tls1.json` | 无 | 调用 Python certcheck；**不发起网络** |
| InstallCa | `ca.crt` | `ca-install.json` | **导入 LocalMachine\Root**（可逆） | 仅 runner；指纹记入收据；Restore 删除 |
| StartMock | 夹具 | `mock.json`/`mock-requests.jsonl` | 监听 `127.0.0.1:443` | 夹具只放**叶子**证书；无凭据逻辑 |
| PatchHosts | hosts | `hosts.bak`/`hosts.json` | **改 hosts**（有备份、有标记） | 幂等；恢复用备份覆盖并校验 |
| Tls2 | — | `tls2.json` | 无（只发一次 HTTPS 探针） | 只打 `/_probe/tls2`；**不**加 `-SkipCertificateCheck` |
| InstallAndRun | 安装包 | `client.json` | 安装客户端 + 启动进程 | 先验 SHA256；数据根隔离；`UseShellExecute=$false` 保证 env 生效 |
| Verdict | mock 日志 / 客户端日志 / tls*.json | 收据 JSON | 无 | 失败分类三态；不把"没到"一律算 TLS |
| Restore | hosts.bak / state | `restore.json` | 还原 hosts / 删 CA / 杀 mock | 幂等；缺备份则跳过并如实记录 |
| CleanupVerify | hosts / Root / 端口 / PID | `cleanup-verify.json` | 无 | **独立**于 Restore；不干净 `exit 10` |

**残留风险**：`InstallAndRun` 用 `Start-Process` 启动 GUI 应用，runner 无交互会话时可能起不来
→ 收据里 `client.json` 缺失即 `S1_INCOMPLETE`，不会误判 PASS。

### 2. `dprime2-mock-server.py`

- 只绑 `127.0.0.1`（默认 443，自检用高位端口），**不接受凭据**；
- 三条路由 + `/_probe/tls2`；未知路径 404，**从不重定向**到真实 GitHub；
- 每条请求写 JSONL，含 `kind`（client/probe）、`method`、`path`、`ua`、`remote`、
  `tls_version`、`cipher`、`auth_header_present`、`had_query`；
- 不打印请求细节到 stdout（避免污染工作流日志）；
- TLS 最低版本 TLSv1_2，**不提供关闭校验的开关**。

### 3. `dprime2-certcheck.py`

- 纯离线：只读 `ca.crt` / `server.crt` / `server.key`，**无任何网络调用**；
- 7 项检查，其中 T1-6 是**用 CA 公钥验叶子签名**（关键项）；
- 依赖系统 Python 的 `cryptography`（runner 预装；Preflight 已校验 `python` 存在）。

### 4. `s1-workflow.yml`

- `on: workflow_dispatch` 唯一触发，**无 pull_request / schedule**；
- `permissions: contents: read, actions: read`（后者仅用于跨 run 取 RC artifact）；
- 步骤 4 的 `run-id` 是**输入**且有默认值 `39748850478`，避免误取其他 run 的资产；
- 4 个关键步骤 `if: always()`；上传用 `if-no-files-found: warn`（失败也要留下已有证据）；
- 超时 25 分钟 + `concurrency` 防重入。

### 5. `selftest-offline.py`

- **不**装证书、**不**改 hosts、**不**绑 443、**不**起客户端；
- 唯一网络行为是到 `127.0.0.1:<高位端口>` 的本地 TLS 握手，且**只信任自建 CA**；
- 含禁项扫描（剥注释后），防止绕过开关被无意引入。

---

## 三、离线自检结论（40/40）

| 组 | 覆盖 | 结果 |
|---|---|---|
| A | 禁项扫描 / hosts 只经 PatchHosts / Restore+CleanupVerify 分立 / mock 只绑回环 | 4/4 |
| B | VerifyRc 实跑 + RC 身份逐项 | 2/2 |
| C | NewCert / 产物 / Tls1 全过 / Tls1 未握手 | 4/4 |
| D | mock 监听 / 三条路由内容逐字节一致 / 探针路径 / 未知 404 / 请求分类 / 归属字段 | 6/6 |
| E | Verdict 三态分类（NONE / 代理 / TLS） | 3/3 |
| F | 工作流 12 步骤齐全 / 4×always() / actions:read / 无 PR 触发 / 固定 run-id | 5/5 |

---

## 四、只能在 runner 上验证的（**不得**据自检结果宣称通过）

1. `InstallCa` 导入后，**真实 Electron Chromium 会话**是否信任该 CA（= TLS-3，唯一有效判据）；
2. hosts 劫持后三条请求是否真的抵达 mock（可能被系统代理/PAC/IPv6 绕过）；
3. 客户端能否无头启动并产生 `update-available`；
4. `Restore` / `CleanupVerify` 在真实系统上的还原效果。

---

## 五、明确未授权 / 未做

未 push、未 merge、未 dispatch、未打 tag、未建 Release、未改 `ce789f4`、
未在本机安装证书或软件、未改本机 hosts、未起 443 mock、未调用模型、
未使用真实 GitHub Token、未触碰正式 Release。

**下一步**：待维护者审核本记录与合同 v3 后，单独申请一次 S1 云端执行授权。

---

## 六、2026-10-24 修订（本轮两处实现变更 + 三个真缺陷）

### 6.1 新增 `-Action PrepareFixtures`

| 项 | 内容 |
|---|---|
| 读 | `-RcRoot` 下的 `latest.yml` |
| 写 | `$OutDir/fixtures/` 下 `latest.yml`(原件复制) / `latest.json` / `atom.xml` / `tag.html` |
| 系统变更 | **无**（纯文件操作） |
| 元数据纪律 | `latest.yml` 必须是 RC **原件**（校验 SHA256 = 固定值）；`atom.xml`/`latest.json` 是 GitHub 站点侧产物、RC 内不存在，只能从 `version` **派生**，派生关系写入 `fixtures.json` |
| 失败即停 | 5 项自洽校验任一不过 → `exit 11`，不许起 mock |

### 6.2 mock 的 `Accept` 契约（等价性，不是功能）

- `/releases/latest` 缺 `Accept: application/json` → **302 → `/releases/tag/<tag>`**（与真实 GitHub 一致）；
- 新增 `/releases/tag/<tag>` 路由返回 HTML（302 落点，使重定向链闭合）；
- 请求日志新增 `accept` 字段——它同时是**判据**（证明客户端发了正确的头）。

**为什么这不是"放宽"而是"收紧"**：原实现无条件回 JSON，客户端漏发头也会判成功；
现在漏发头会走 302 → HTML → 客户端 `JSON.parse` 失败 → 正确地失败。**更严格，不是更宽松。**

### 6.3 三个真缺陷（详见 `s1-review-package.md` 第一节）

| # | 缺陷 | 性质 |
|---|---|---|
| 1 | `StartMock` 不生成 `atom.xml`/`latest.json`/`latest.yml` | **P0，dispatch 必失败**；自检自己造夹具掩盖了它 |
| 2 | mock 不校验 `Accept` | P1，假阳性风险 |
| 3 | RT-9 异常分支（D′-1，已在 main 修复） | 同类教训：静态自检抓不到异常分支 |

### 6.4 红线复核（本轮未破任何一条）

- 未 push、未 dispatch、未装软件、未改本机网络或证书；
- 新增代码中仍**零** `-SkipCertificateCheck` / `ignore-certificate-errors` / `setCertificateVerifyProc`；
- mock 仍只绑 `127.0.0.1`、仍无凭据逻辑、仍不重定向到真实 GitHub。
