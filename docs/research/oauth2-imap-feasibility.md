# OAuth2 连 IMAP 的可行性（调研）

> 日期：2026-09-24｜**本文件只做决策依据，不含任何实现改动**（邮箱配置批只到"调研"这一步）。
>
> 结论先行：**技术上可做，且零第三方依赖可达；真正的门槛不在代码**——Google 那边是发布侧的验证成本，Microsoft 那边是"个人账号到底能不能连上"这个**尚未解开的前提**。

## 0. 一句话建议（六条）

1. **MVP 只做 Gmail 的 OAuth**（Desktop app + PKCE + `127.0.0.1` 回环），**并保留**现有"用户名 + 应用专用密码"路径，两者并存、用户自选。
2. **Microsoft 先做 1–2 小时协议探针**（注册应用 → 拿 token → `imaplib` 试连 `outlook.office365.com`）；**不过就不做**，直接维持"暂不支持 Outlook 个人邮箱"并给替代指引。
3. **跳转方式**：Loopback 主路径，Device Code 作降级；**不做**自定义协议（Google 已砍、Windows 注册易碎）。
4. **零依赖可行**：`urllib` / `http.server` / `hashlib` / `secrets` / `base64` 足够，**不引入** OAuth 客户端库、JWT 库、requests、keyring。
5. **安全存储定为可选增强**：默认沿用"本地存储 + 明确告知"，可选接 Electron `safeStorage` + Python `ctypes`+DPAPI。
6. **把"令牌过期 / 续期失败"当一等公民**做 UX：不要做任何"永不失效"的假设。

## 1. Google（Gmail）

**事实**

- 登录串：`base64("user=" + 邮箱 + "\x01auth=Bearer " + access_token + "\x01\x01")`，IMAP 用 `AUTHENTICATE XOAUTH2`；出错时服务端返回 base64 的 JSON，客户端需回一个空响应。
- scope：IMAP/POP/SMTP 需要 `https://mail.google.com/`，属 **Restricted（限制级）**。
- 客户端类型选 **Desktop app**；**PKCE 官方标注为 Recommended（非强制）**，推荐 `S256`。
- 回环重定向：官方明确支持 `http://127.0.0.1:<随机端口>`；**自定义 URI scheme 已不再支持**，OOB（手工复制粘贴）已弃用。
- 端点：授权 `https://accounts.google.com/o/oauth2/v2/auth`；换/刷令牌 `https://oauth2.googleapis.com/token`；撤销 `https://oauth2.googleapis.com/revoke`。
- refresh token：内置应用**总会返回**；但有三种"隐形过期"——**7 天规则**（同意屏幕 External + 发布状态 Testing + 请求了超出 `openid/email/profile` 的 scope）、**6 个月未使用**、**每 Client ID × 每账号上限 100 个，超出会静默失效最旧的**；改密码也会失效。
- **限制级 scope 的强制安全措施包含 CASA**，且政策**没有**"仅本地存储可豁免"的条款（唯一豁免是"仅供自己组织内部用户使用"）。

**归纳**：代码成本很低——与现在 `imaplib` 的登录只差一个 base64 拼装与 `authenticate('XOAUTH2', …)`；**成本在发布侧**（验证 + CASA，周级日历时间）。

**注**：Gmail 的"应用专用密码"**目前仍可用**（需先开两步验证），但**工作/学校账号看不到这个选项**。

## 2. Microsoft

**事实**

- delegated scope：IMAP = `https://outlook.office.com/IMAP.AccessAsUser.All`（建议加 `offline_access` 换长期 refresh token）。
- **必须做 Entra（Azure AD）应用注册**；tenant 取值：`common`（个人 + 工作/学校）/ `organizations` / `consumers`。
- 回环：`localhost` 支持且**匹配时端口被忽略**；**不要**注册多个只差端口的 URI；**IPv6 `[::1]` 不支持**；`http://127.0.0.1` 在门户文本框里加不了，需要改应用清单。
- 个人账号的 IMAP 服务器是 **`outlook.office365.com`**（993 / SSL / Modern Auth）。
- **Device Code flow 可用**（不占端口、不需注册回调）；个人账户会**二次登录 + 同意**；官方警告 MSA 的令牌**可能不是 JWT、不要依赖其内部结构**。
- **公开的未解案例**：有人把权限、管理员同意、公共客户端流、IMAP 开关、令牌有效期全部配对之后，用 `imaplib` + XOAUTH2 连 `@outlook.com` **仍然稳定 `AUTHENTICATE failed`**（拿到的还是 opaque token）；该帖无采纳答案，另有数人报同样问题。

**归纳**：文档层面"支持"，现实层面**高度存疑**。这条不做 POC 就投入，很可能白做。

## 3. 令牌安全存放（Windows）

**事实**

- **Electron `safeStorage`** 是主进程内置模块（Windows 下走 DPAPI），**无需第三方库**；官方边界写得很清楚：只防"同机其他用户"，**不防同一用户空间下的其它进程**；推荐异步 API。
- Python 侧：`keyring` 是**第三方包**；标准库 `ctypes` 可直接调 DPAPI（`CryptProtectData`）或 Credential Manager（`CredWriteW`）。

**归纳**：两侧都能做到零第三方依赖。**取舍**——DPAPI 相对"本地明文"的真实收益是"跨用户/跨机器不可解密 + 不落明文"（以及合规叙事），对"同一用户下的恶意软件"几乎**没有增量防护**。所以值得做，但别把它宣传成"安全多了"；如实告知用户即可。

## 4. 授权跳转的三种实现

| 方案 | Windows 可移植性 | 要管理员权限？ | 零依赖友好度 | 关键坑 |
|---|---|---|---|---|
| **Loopback HTTP 回调** | 好（纯 TCP 回环） | 否 | 高（`http.server` 够用） | 回环端口可能被防火墙/杀软拦；随机端口需动态处理（Google 明确接受、Microsoft 端口匹配被忽略） |
| **自定义协议 `myapp://`** | 要写注册表 | 安装期可能需要 | 中 | **Google 已不支持**；未签名/未注册时静默失败 |
| **Device Code flow** | 最好（纯 HTTPS 轮询） | 否 | 高（`urllib` 轮询） | 体验偏"命令行"；**Google 是否对普通桌面开放未核实**；Microsoft 个人账户会二次登录 |

**结论**：主路径 Loopback，降级 Device Code，**不做**自定义协议。

## 5. 零依赖可行性（Python 标准库）

可完整实现，逐段对应：PKCE → `secrets` + `hashlib.sha256` + `base64.urlsafe_b64encode`；回环回调 → `http.server`；换/刷令牌 → `urllib.request` + `urllib.parse.urlencode`；XOAUTH2 → `base64` + `imaplib.IMAP4_SSL.authenticate`；安全存放 → `ctypes`。

**不需要**：JWT 解析（access token 通常是不透明的，解析也无意义）、加密库、requests、任何 OAuth 客户端库。微软文档"优先用 MSAL"是**安全建议而非协议强制**。

**待验证的工程细节**：`http.server` 单线程监听的**超时与取消**要自己写（标准库够用，但没有现成组件）。

## 6. 工作量（三档，开发+自测，不含对方审核等待）

| 档 | 范围 | 人日 | 复杂度 |
|---|---|---|---|
| **A** | 只做 Gmail：后端 `oauth_google.py`（PKCE + 回环 + 换/刷令牌 + XOAUTH2）约 150–250 行；设置页加"用 Google 登录"；`config/` 增字段 | **3–6** | 中 |
| **B** | 再加 Microsoft（或直接走 Device Code，更简单） | **+3–6** | 中偏高 |
| **C** | 再加系统凭据存储（Python `ctypes`+DPAPI；Electron `safeStorage`；迁移既有明文） | **+2–4** | 中 |
| 合计 | A+B+C | **8–16** | — |

**最容易翻车的三处**：① Google 限制级 scope 的验证/CASA（不是代码问题，是发布门槛与日历时间）；② Microsoft 个人账号 IMAP OAuth2 **可能根本不工作**；③ 令牌生命周期（7 天规则 / 6 个月 / 100 个上限静默踢旧）+ 回环端口被拦——都会表现为"用户偶尔莫名要重新登录"。

## 7. 替代方案（不做 OAuth 时，Outlook 用户怎么办）

| 路径 | 现实可行性 | 说明 |
|---|---|---|
| 企业邮箱申请"应用专用密码" | **低** | Exchange Online 基本认证已全停且**不可重开**，是否有应用密码取决于管理员策略 |
| Outlook 个人账号的应用密码 | **未核实** | 个人账号基本认证已于 2024-09 停用；是否仍可用需实测 |
| 本机 IMAP 代理/网关 | **中，但不推荐** | 代理本身仍要 OAuth2（难题只是前移），且多半引入第三方 |
| **明确不支持 + 给替代指引** | **高（最省事）** | 零开发、零审核风险；当前实现已走这条路 |
| Gmail + 应用专用密码 | **高** | 对已开 2FA 的 Gmail 个人账号可用 |
| 改为"邮件导出/导入"（.eml/.mbox） | **高** | 彻底绕开 IMAP，代价是放弃实时同步 |

## 8. 未核实项（要落地必须先确认）

1. Google "Desktop app" 客户端现在是否仍随附 `client_secret`（官方文档称 native app 的 secret 为可选，未逐字说明现行行为）。
2. **Google 是否对普通 Windows 桌面应用开放 Device Code flow**（该机制历史上面向 TV/输入受限设备）。
3. **Outlook.com 个人账号的"应用专用密码"是否仍可用于 IMAP**。
4. **Microsoft 个人账号 IMAP OAuth2 失败案例的根因与官方立场**——只有 POC 能定。

## 9. 对本项目的落点

- 现状：只有"用户名 + 授权码/应用专用密码"，无 OAuth；设置页对 Outlook 已明确标注 **暂不支持并说明原因**（见 `jobws_core/mail_providers.py` 的 `unsupported` / `unsupportedReasonKey`）。
- **本批不改这个判断**：先有本文件，再决定是否投 A 档。
- 若要动手，按第 0 节六条执行；**第 8 节的四项确认**没做完之前，不要对外承诺"支持 Outlook"。

## 来源

- Gmail XOAUTH2 协议：https://developers.google.com/workspace/gmail/imap/xoauth2-protocol
- Google 原生应用 OAuth（Desktop app / PKCE / 回环）：https://developers.google.com/identity/protocols/oauth2/native-app
- Google refresh token 过期规则：https://developers.google.com/identity/protocols/oauth2#expiration
- Gmail scope 分级：https://developers.google.com/gmail/api/auth/scopes
- Google Workspace 用户数据政策（CASA / 静态加密）：https://developers.google.com/workspace/workspace-api-user-data-developer-policy
- Google 应用专用密码：https://support.google.com/accounts/answer/185833
- Microsoft：用 OAuth 认证 IMAP/POP/SMTP：https://learn.microsoft.com/en-us/exchange/client-developer/legacy-protocols/how-to-authenticate-an-imap-pop-smtp-application-by-using-oauth
- Microsoft 身份平台协议与 tenant 取值：https://learn.microsoft.com/en-us/entra/identity-platform/v2-protocols
- Microsoft Device Code flow：https://learn.microsoft.com/en-us/entra/identity-platform/v2-oauth2-device-code
- Microsoft 回环重定向限制：https://learn.microsoft.com/en-us/entra/identity-platform/reply-url
- Exchange Online 基本认证弃用：https://learn.microsoft.com/en-us/exchange/clients-and-mobile-in-exchange-online/deprecation-of-basic-authentication-exchange-online
- Outlook.com 的 POP/IMAP/SMTP 设置：https://support.microsoft.com/zh-cn/office/outlook-com-%E7%9A%84-pop%E3%80%81imap%E5%92%8C-smtp-%E8%AE%BE%E7%BD%AE-d088b986-291d-42b8-9564-9c414e2aa040
- 个人账号 IMAP OAuth2 失败案例（无采纳答案）：https://learn.microsoft.com/en-us/answers/questions/2121624/need-help-imap-oauth2-authentication-issue-for-out
- Electron safeStorage：https://www.electronjs.org/docs/latest/api/safe-storage
- Python ctypes：https://docs.python.org/3/library/ctypes.html
- RFC 8252（原生应用 OAuth 最佳实践）：https://www.rfc-editor.org/info/rfc8252
- RFC 8628（Device Code Grant）：https://oauth.net/2/grant-types/device-code/
