# P1-C · Electron 运行时专项扫描（2026-10-16）

> 交接包 §二 审计对账里 `P1-C ⏳（Electron 运行时专项扫描）` 的闭环交付。
> 范围：桌面壳（`web/electron/`）的**运行时攻击面**——窗口偏好、渲染隔离、preload
> 暴露、导航与外链、CSP、后端进程拉起、IPC 通道。方法：读 + 定点检索安全旋钮
> （不跑动态测试；动态项归 G2/G3 真机验收）。

## 一、现状（#204 拆分后）

`main.js` 128 行，已拆成 `navigation / url_guard / preload / prefs / window / zoom /
notifications / reminders / backend_process / diagnostics_bridge / i18n / updater /
single_instance / window_state / logger` 等模块；`navigation.test.js`（230 行）、
`url_guard.test.js`、`prefs.test.js` 等有对应单测（CI 一并跑）。

## 二、逐项扫描结果

| 面 | 旋钮 / 位置 | 状态 | 判定 |
|---|---|---|---|
| 渲染隔离 | `window.js:130` `contextIsolation: true` | ✅ 显式开启 | 通过 |
| Node 暴露 | `window.js:131` `nodeIntegration: false` | ✅ 显式关闭 | 通过 |
| preload 暴露面 | `preload.js`：单命名空间 `jobwsPrefs` + 8 个方法，**全是纯数据进出**，明确不做任意 channel 转发（注释钉住理由） | ✅ 最小化 | 通过 |
| 窗口内导航 | `navigation.js:52` `will-navigate` + `will-redirect`：只允许与后端源**同源**且 scheme 在白名单 | ✅ | 通过（前缀匹配绕过已修，`url_guard.js:2-4` 留证） |
| 外链出口 | `navigation.js:66` `setWindowOpenHandler` → `shell.openExternal`，只放行 **https** | ✅ | 通过（`file:` / 自定义协议拒绝） |
| CSP | `navigation.js:31-36`：给本机后端源响应加 CSP；安装失败只记日志不挡启动 | ✅ | 通过（取舍见下） |
| IPC 通道 | `prefs:*`（缩放/语言/工作区/提醒）、`app:open-log-folder` | ✅ | 通过：处理器**均不吃用户路径**（`openLogFolder` 用 `app.getPath("userData")` 硬编码） |
| 后端进程拉起 | `backend_process.js:79` `execFileSync(cand, ["-c", …])`：**数组参数、无 shell** | ✅ | 通过（无命令注入面） |
| `webSecurity` / `webviewTag` / `plugins` | 未显式设置 | 默认值（开 / 关 / 关） | 通过 |

## 三、两条加固候选（不阻断，记录在案）

1. **preload 未开 `sandbox: true`**：当前 preload 直接 `require("electron")` 取
   `contextBridge` / `ipcRenderer`。开 sandbox 需评估 polyfill 与 Electron 版本
   兼容（会动发行冻结前的主链路）。**关键隔离项 `contextIsolation` 已开**，sandbox
   是纵深防御的下一步，不是当前缺口。
2. **`JOBWS_PYTHON` 环境变量可指定解释器**（`backend_process.js:66-67`）：本地优先
   工具的可接受逃逸阀——能设该用户环境变量者已具备同级执行能力。记录为**已知设计**，
   不建议改（改了会打断开发态用虚拟环境的常规用法）。

## 四、已知取舍（如实记录）

- **CSP 安装失败只记日志、不阻断启动**（`navigation.js:38-42`）：取舍是"加固不该
  挡住用户打开应用"。若 CSP 缺失，简历模板 HTML 的防护退化到导航守卫一层
  （`navigation.js:10` 记了这条推理）。
- 本扫描是**静态面**；动态项（真实窗口行为、协议注册、更新通道）归 G2/G3 真机验收。

## 五、结论

**P1-C 关闭：未发现高危发现。** 九项检查全部通过；两条加固候选各附不做的理由。
审计对账里 `P1-C ⏳` 可改为 `P1-C ✅`。
