// 打包白名单守卫：任一打包模块里的相对 require 与 `__dirname` 派生的 .js 路径，
// 都必须在 build.files 里。
//
// 为什么需要这条检查：源码形态（`electron .` / `npm start`）用相对路径解析，文件
// 在不在都能跑；打包形态（asar）只带 `build.files` 列出的文件——漏一个模块，安装版
// 一启动就崩，而本地开发怎么试都是好的。2026-09-13 抽出 zoom.js 时白名单没跟上，
// 正是这条检查拦下的（`require("./zoom")` 对源码形态为真、对安装版为假）。
//
// 2026-10-04（#204 拆分）把扫描范围从 main.js 扩到**全部打包模块**：拆分后新模块
// 自己的 require（以及 preload 这类 `path.join(__dirname, "x.js")` 路径）若漏登记，
// 同一次事故会再来一遍——旧版只看 main.js，根本看不见子模块里的依赖。
//
// 零依赖，`node web/electron/check_packaging.js` 直接跑（CI 里与各 *.test.js 同一步）。
//
// 消息一律英文：electron 树的**字符串**口径是英文——check_i18n_hardcode.py 把这里
// 的字符串按界面文案判（electron 日志用户会在 bug 报告里贴出来），中文串会被 CI 拦；
// 注释仍按仓库惯例用中文。
const fs = require("fs");
const path = require("path");

const dir = __dirname;
const pkg = JSON.parse(fs.readFileSync(path.join(dir, "package.json"), "utf-8"));
const files = (pkg.build && pkg.build.files) || [];

const problems = [];
const required = new Set();

// 扫描范围：build.files 里列出的真实 .js 文件（跳过通配条目与非 js 条目）。
// 测试文件不在 build.files 里，因此不会被扫——它们不进安装包，不需要守卫。
const scanned = files.filter((f) => f.endsWith(".js") && !f.includes("*"));

// 归一化三种等价写法：显式扩展名、省略扩展名、目录（→ index.js）
function resolveSpec(spec) {
  const base = path.resolve(dir, spec);
  return [base, `${base}.js`, path.join(base, "index.js")].find((p) => fs.existsSync(p));
}

function requireSpec(rel, spec) {
  const resolved = resolveSpec(spec);
  if (!resolved) {
    problems.push(`${rel} requires ${spec}, but no such file exists under web/electron/`);
    return;
  }
  const target = path.relative(dir, resolved).split(path.sep).join("/");
  required.add(target);
  if (!files.includes(target)) {
    problems.push(
      `${rel} requires ${target}, but it is not listed in build.files — the packaged app would fail to start`);
  }
}

for (const rel of scanned) {
  const src = fs.readFileSync(path.join(dir, rel), "utf-8");

  // ① 相对 require（单引号与双引号都认：只认双引号时，改成单引号就能让守卫静默失效）
  for (const m of src.matchAll(/require\(\s*['"](\.[^'"]+)['"]\s*\)/g)) {
    requireSpec(rel, m[1]);
  }

  // ② `path.join/resolve(__dirname, ..., "x.js")` 这类派生路径。
  // 现行覆盖：main.js 的 preload 路径（字符串形式，require 扫描看不到它；漏登记时
  // 源码形态照跑、安装版一启动就崩——与 zoom.js 那次同类）。
  // 只认含 __dirname 且最后一个字符串字面量以 .js 结尾的调用；写法变了匹配不到就
  // 静默跳过，宁可漏报也不误报（误报会把守卫变成噪音，然后被绕过）。
  for (const m of src.matchAll(/path\.(?:join|resolve)\(([^)\n]*)\)/g)) {
    const args = m[1];
    if (!args.includes("__dirname")) continue;
    const literals = [...args.matchAll(/['"`]([^'"`]+)['"`]/g)].map((x) => x[1]);
    const last = literals[literals.length - 1];
    if (!last || !last.endsWith(".js")) continue;
    requireSpec(rel, last);
  }
}

// 反向检查：白名单里写了不存在的文件，说明名单已经与实际脱节
for (const f of files) {
  if (f.includes("*")) continue;
  if (!fs.existsSync(path.join(dir, f))) {
    problems.push(`build.files lists ${f}, which does not exist`);
  }
}

if (problems.length) {
  console.error("check_packaging: FAIL");
  for (const p of problems) console.error(`  - ${p}`);
  process.exit(1);
}
console.log(`check_packaging: OK (${required.size} relative dependency/ies across ${scanned.length} packaged module(s))`);
