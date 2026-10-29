// 启动阶段的用户可见文案：端口冲突 / 启动超时附带的「另一个实例占着端口」提示。
//
// 为什么有这份测试（2026-10-28 审计 §七 第 2 条）：这两处此前是**硬编码英文**，
// 中文用户看到英文；而 `check_i18n_hardcode` 只查中文，抓不到「英文没进语言表」。
// 断言直接打真实语言表（`i18n.js` 的 TABLES + tFor），不 mock 文案。
const test = require("node:test");
const assert = require("node:assert");

const { TABLES, tFor } = require("./i18n");
const { conflictText, timeoutHint } = require("./startup_messages");

const ZH = tFor("zh-CN");
const EN = tFor("en");
const NEW_KEYS = [
  "portConflictTitle",
  "portConflictReuseDetail",
  "portConflictOtherDetail",
  "backendTimeoutHintIdentity",
];

test("startup messages: the four new keys exist in both language tables", () => {
  for (const key of NEW_KEYS) {
    for (const lang of ["en", "zh-CN"]) {
      const value = TABLES[lang][key];
      assert.equal(typeof value, "string", `${lang}.${key} must be a string`);
      assert.ok(value.trim().length > 0, `${lang}.${key} must not be empty`);
    }
  }
});

test("conflictText: reuse-disallowed explains the address, the env switch and no leftover placeholders", () => {
  const { title, detail } = conflictText("reuse-disallowed", ZH);
  assert.equal(title, ZH("portConflictTitle"));
  assert.ok(detail.includes("127.0.0.1:8765"), detail);
  assert.ok(detail.includes("JOBWS_ALLOW_REUSE=1"), detail);
  assert.ok(!detail.includes("{"), "placeholders must be substituted: " + detail);
});

test("conflictText: every non-reuse kind names the reason and never suggests attaching", () => {
  for (const kind of ["identity", "status", "timeout", "error"]) {
    const { detail } = conflictText(kind, ZH);
    assert.ok(detail.includes(kind), kind + " must be named: " + detail);
    assert.ok(!detail.includes("JOBWS_ALLOW_REUSE"),
      kind + " must not suggest attaching to a port with an unknown identity");
    assert.ok(!detail.includes("{"), "placeholders must be substituted: " + detail);
  }
});

test("startup messages: plain text only — native dialogs do not render markdown", () => {
  // 2026-10-28 评审 MAJOR：这四条文案会进 dialog.showMessageBox（原生弹窗，不解析
  // Markdown），写成 `**不是**` 用户会看到字面星号。这条是它的回归网。
  for (const t of [ZH, EN]) {
    for (const text of [t("portConflictReuseDetail"), t("portConflictOtherDetail"),
      t("backendTimeoutHintIdentity")]) {
      assert.ok(!text.includes("**"), "no markdown bold allowed: " + text);
      assert.ok(!/\]\(/.test(text), "no markdown link allowed: " + text);
    }
  }
});

test("conflictText: English stays English for both branches", () => {
  assert.ok(conflictText("reuse-disallowed", EN).detail.includes("Another Job Workbench"));
  assert.ok(conflictText("reuse-disallowed", EN).title.includes("port is in use"));
  assert.ok(conflictText("timeout", EN).detail.includes("not a healthy Job Workbench"));
});

test("timeoutHint: only an identity-mismatch gets the extra paragraph, and it is localized", () => {
  const zh = timeoutHint("identity", ZH);
  assert.ok(zh.includes("JOBWS_ALLOW_REUSE=1"), zh);
  assert.ok(/[\u4e00-\u9fa5]/.test(zh), "zh-CN hint must be Chinese: " + zh);
  const en = timeoutHint("identity", EN);
  assert.ok(en.includes("another Job Workbench instance"), en);
  for (const reason of ["refused", "status", "error", "timeout", "ok"]) {
    assert.equal(timeoutHint(reason, ZH), "", reason + " must not carry the identity hint");
  }
});
