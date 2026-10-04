// 导航守卫与内容安全策略（CSP）的接线层（#204 拆分 D）。
// 安全边界收敛在这里：窗口内只允许停在本机后端（严格同源比对），外链交给系统浏览器
// 且只放行 https，CSP 只给本机后端一个源加。判定本身在 url_guard.js（纯函数）；
// 本模块只负责把判定接到 webContents / session 上——接线用假对象可测，
// 见 navigation.test.js。
//
// 不 require("electron")：session 与 shell 全部注入——纯 node 下也能安全加载。

// 内容安全策略（2026-09-23 二轮审计的纵深防御项）：界面会内联预览**工作区里手写的
// 简历模板 HTML**，没有 CSP 时它一旦被 popup / 重定向绕过窗口守卫，就能以同源身份
// 调本机 API 读写整个工作区（本地 API 无鉴权）。这里只给本机后端这一个源加，
// 且保留 `'unsafe-inline'`：index.html 有一段防闪白用的内联主题引导脚本，
// 去掉它首帧会闪一次默认色（取舍写在 CONTRIBUTING 的「刻意不做」里）。
const CONTENT_SECURITY_POLICY = [
  "default-src 'self'",
  "script-src 'self' 'unsafe-inline'",
  "style-src 'self' 'unsafe-inline'",
  "img-src 'self' data: blob:",
  "font-src 'self' data:",
  "connect-src 'self'",
  "frame-src 'self' blob: data:",
  "object-src 'none'",
  "base-uri 'none'",
].join("; ");

function createNavigation({ session, shell, log, backendPort, urlGuard = require("./url_guard") }) {
  // 窗口允许停留的唯一源（与建窗 loadURL 同一口径）
  const allowedOrigin = `http://127.0.0.1:${backendPort}`;

  /** 给本机后端源的响应加 CSP；安装失败只记日志（加固不该挡住启动）。 */
  function installCsp() {
    try {
      session.defaultSession.webRequest.onHeadersReceived((details, callback) => {
        const headers = Object.assign({}, details.responseHeaders);
        if (details.url.startsWith(`http://127.0.0.1:${backendPort}`)) {
          headers["Content-Security-Policy"] = [CONTENT_SECURITY_POLICY];
        }
        callback({ responseHeaders: headers });
      });
    } catch (e) {
      // 加固失败不该挡住启动：日志里留一条，界面照常
      log(`CSP install failed: ${e.message}`);
    }
  }

  /** 三处接线：窗口内导航（will-navigate / will-redirect）与外链出口（setWindowOpenHandler）。 */
  function wireWindow(win) {
    // 只允许留在本机界面：页面一旦被导航到外部站点，preload 注入的偏好通道也会跟着
    // 暴露给那个文档（contextBridge 是按文档注入的）。窗口内的外链交给系统浏览器。
    // 判断收敛到 url_guard.js（审计 P0-2）：前缀匹配会被 `127.0.0.1:8765.evil.com`
    // 绕过，外链必须有 scheme 白名单（只放行 https）。
    win.webContents.on("will-navigate", (event, url) => {
      if (!urlGuard.isAllowedNavigation(url, allowedOrigin)) {
        event.preventDefault();
        log(`Blocked navigation to ${url}`);
      }
    });
    // 服务端 302 不走 will-navigate，走的是独立的可取消事件（批末审查发现漏挂）。
    // 本机后端是唯一可能发重定向的一方，但守卫的语义就是"所有导航出口都要判"。
    win.webContents.on("will-redirect", (event, url) => {
      if (!urlGuard.isAllowedNavigation(url, allowedOrigin)) {
        event.preventDefault();
        log(`Blocked redirect to ${url}`);
      }
    });
    win.webContents.setWindowOpenHandler(({ url }) => {
      if (!urlGuard.isSafeExternalUrl(url)) {
        log(`Blocked external open of ${url}`);
        return { action: "deny" };
      }
      shell.openExternal(url).catch((e) => log(`Failed to open external URL: ${e.message}`));
      // 恒 deny：外链一律走系统浏览器，绝不在应用内开新窗口
      return { action: "deny" };
    });
  }

  return { installCsp, wireWindow };
}

module.exports = { createNavigation };
