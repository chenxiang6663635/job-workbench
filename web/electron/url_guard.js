// URL 守卫（纯函数、零依赖）：导航同源比对 + 外链 scheme 白名单。
// 为什么单独一层：main.js 原先用 `url.startsWith(allowedOrigin)` 判导航，
// `http://127.0.0.1:8765.evil.com` 能绕过（前缀匹配 ≠ 同源）；外链打开则没有
// scheme 白名单，`file://` 与自定义协议都会被 shell.openExternal 拉起。
// 两处判断收敛到这一对纯函数——electron 树里能测的判断都放这层
// （`node web/electron/url_guard.test.js`，CI 一并跑）。

// 外链只放行 https：界面里出现的可点外链（邮件深链、岗位来源页）都是 https；
// http / file / 自定义协议一律拒绝（审计 P0-2）。
const EXTERNAL_SCHEMES = ["https:"];

/** 导航守卫：只允许与 allowedOrigin **同源**的 URL（比较 origin，不做前缀匹配）。 */
function isAllowedNavigation(url, allowedOrigin) {
  try {
    return new URL(url).origin === new URL(allowedOrigin).origin;
  } catch (e) {
    return false; // 解析不了的一律不放行
  }
}

/** 外链守卫：只放行 https（交给系统浏览器打开；其余 scheme 一律拒绝）。 */
function isSafeExternalUrl(url) {
  try {
    return EXTERNAL_SCHEMES.includes(new URL(url).protocol);
  } catch (e) {
    return false;
  }
}

module.exports = { isAllowedNavigation, isSafeExternalUrl };
