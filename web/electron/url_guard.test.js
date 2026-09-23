// URL 守卫纯逻辑的无依赖单测：`node web/electron/url_guard.test.js`（CI 也跑这一步）。
// 与 zoom.test.js 同款形态：断言消息用英文（electron 树的字符串口径是英文，
// check_i18n_hardcode.py 会把中文串当界面文案拦下）；注释按仓库惯例用中文。
const assert = require("assert");
const { isAllowedNavigation, isSafeExternalUrl } = require("./url_guard");

const ORIGIN = "http://127.0.0.1:8765";

// --- 导航守卫：origin 严格比对（不做前缀匹配） ----------------------------------
assert.strictEqual(isAllowedNavigation("http://127.0.0.1:8765/#dashboard", ORIGIN), true);
assert.strictEqual(isAllowedNavigation("http://127.0.0.1:8765", ORIGIN), true);
assert.strictEqual(
  isAllowedNavigation("http://127.0.0.1:8765.evil.com/x", ORIGIN), false,
  "prefix lookalike host must not pass (audit P0-2)");
assert.strictEqual(
  isAllowedNavigation("http://127.0.0.1:8765.evil.com", ORIGIN), false);
assert.strictEqual(
  isAllowedNavigation("http://127.0.0.1:8765@evil.com/", ORIGIN), false,
  "userinfo tricks must not pass");
assert.strictEqual(
  isAllowedNavigation("https://127.0.0.1:8765/", ORIGIN), false,
  "same host, different scheme: still denied");
assert.strictEqual(isAllowedNavigation("file:///C:/Windows/System32", ORIGIN), false);
assert.strictEqual(isAllowedNavigation("not a url", ORIGIN), false, "unparseable is denied");
assert.strictEqual(isAllowedNavigation("", ORIGIN), false);

// --- 外链守卫：只放行 https ----------------------------------------------------
assert.strictEqual(isSafeExternalUrl("https://mail.google.com/u/0/#search/xyz"), true);
assert.strictEqual(isSafeExternalUrl("http://example.com/"), false, "http is denied");
assert.strictEqual(isSafeExternalUrl("file:///C:/Users/x/evil.exe"), false);
assert.strictEqual(isSafeExternalUrl("javascript:alert(1)"), false);
assert.strictEqual(isSafeExternalUrl("vbscript:msgbox"), false);
assert.strictEqual(isSafeExternalUrl("not a url"), false);

console.log("url_guard: all assertions passed");
