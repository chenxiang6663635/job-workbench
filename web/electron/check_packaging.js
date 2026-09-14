// 打包白名单守卫：main.js 里每个相对 require 的模块都必须在 build.files 里。
//
// 为什么需要这条检查：源码形态（`electron .` / `npm start`）用相对路径解析，文件
// 在不在都能跑；打包形态（asar）只带 `build.files` 列出的文件——漏一个模块，安装版
// 一启动就崩，而本地开发怎么试都是好的。2026-09-13 抽出 zoom.js 时白名单没跟上，
// 正是这条检查拦下的（`require("./zoom")` 对源码形态为真、对安装版为假）。
//
// 零依赖，`node web/electron/check_packaging.js` 直接跑（CI 里与 zoom.test.js 同一步）。
//
// 消息一律英文：electron 树的**字符串**口径是英文——check_i18n_hardcode.py 把这里
// 的字符串按界面文案判（electron 日志用户会在 bug 报告里贴出来），中文串会被 CI 拦；
// 注释仍按仓库惯例用中文。
const fs = require("fs");
const path = require("path");

const dir = __dirname;
const mainSrc = fs.readFileSync(path.join(dir, "main.js"), "utf-8");
const pkg = JSON.parse(fs.readFileSync(path.join(dir, "package.json"), "utf-8"));
const files = (pkg.build && pkg.build.files) || [];

const problems = [];
const required = new Set();
// 单引号与双引号都认：只认双引号时，把 require 改成单引号就能让守卫静默失效
for (const m of mainSrc.matchAll(/require\(\s*['"](\.[^'"]+)['"]\s*\)/g)) {
  const spec = m[1];
  const base = path.resolve(dir, spec);
  // 归一化三种等价写法：显式扩展名、省略扩展名、目录（→ index.js）
  const resolved = [base, `${base}.js`, path.join(base, "index.js")]
    .find((p) => fs.existsSync(p));
  if (!resolved) {
    problems.push(`main.js requires ${spec}, but no such file exists under web/electron/`);
    continue;
  }
  const rel = path.relative(dir, resolved).split(path.sep).join("/");
  required.add(rel);
  if (!files.includes(rel)) {
    problems.push(
      `main.js requires ${rel}, but it is not listed in build.files — the packaged app would fail to start`);
  }
}

// 反向检查：白名单里写了不存在的文件，说明名单已经与实际脱节
for (const f of files) {
  if (f.includes("*")) continue;
  if (!fs.existsSync(path.join(dir, f))) {
    problems.push(`build.files lists ${f}, which does not exist`);
  }
}

// preload 走的是字符串路径（不是 require），上面那个相对依赖扫描看不到它：
// 漏登记时源码形态照跑（路径能解析）、安装版一启动就崩——与 zoom.js 那次同类。
// 只认 path.join(__dirname, "x.js") 这一种写法；将来写法变了，正则匹配不到就
// 静默跳过，宁可漏报也不误报（误报会把守卫变成噪音，然后被绕过）。
for (const m of mainSrc.matchAll(/preload:\s*path\.join\(\s*__dirname\s*,\s*['"]([^'"]+)['"]\s*\)/g)) {
  const rel = m[1].split(path.sep).join("/");
  if (!fs.existsSync(path.join(dir, rel))) {
    problems.push(`webPreferences.preload points at ${rel}, but no such file exists under web/electron/`);
    continue;
  }
  if (!files.includes(rel)) {
    problems.push(
      `webPreferences.preload points at ${rel}, but it is not listed in build.files — the packaged app's preference channel would be missing`);
  }
}

if (problems.length) {
  console.error("check_packaging: FAIL");
  for (const p of problems) console.error(`  - ${p}`);
  process.exit(1);
}
console.log(`check_packaging: OK (${required.size} relative dependency/ies listed in build.files)`);
