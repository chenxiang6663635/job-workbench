// 打包白名单守卫：main.js 里每个相对 require 的模块都必须在 build.files 里。
//
// 为什么需要这条检查：源码形态（`electron .` / `npm start`）用相对路径解析，文件
// 在不在都能跑；打包形态（asar）只带 `build.files` 列出的文件——漏一个模块，安装版
// 一启动就崩，而本地开发怎么试都是好的。2026-09-13 抽出 zoom.js 时白名单没跟上，
// 正是这条检查拦下的（`require("./zoom")` 对源码形态为真、对安装版为假）。
//
// 零依赖，`node web/electron/check_packaging.js` 直接跑（CI 里与 zoom.test.js 同一步）。
const fs = require("fs");
const path = require("path");

const dir = __dirname;
const mainSrc = fs.readFileSync(path.join(dir, "main.js"), "utf-8");
const pkg = JSON.parse(fs.readFileSync(path.join(dir, "package.json"), "utf-8"));
const files = (pkg.build && pkg.build.files) || [];

const problems = [];
const required = new Set();
for (const m of mainSrc.matchAll(/require\("\.\/([^"]+)"\)/g)) {
  required.add(m[1].endsWith(".js") ? m[1] : `${m[1]}.js`);
}

for (const name of required) {
  if (!files.includes(name)) {
    problems.push(
      `main.js 依赖 ${name}，但它不在 build.files 里——打包后 require 解析失败，启动即崩`);
  }
  if (!fs.existsSync(path.join(dir, name))) {
    problems.push(`${name} 在 web/electron/ 下不存在（改名或删除后忘了同步？）`);
  }
}

// 反向检查：白名单里写了不存在的文件，说明名单已经与实际脱节
for (const f of files) {
  if (f.includes("*")) continue;
  if (!fs.existsSync(path.join(dir, f))) {
    problems.push(`build.files 列了不存在的 ${f}`);
  }
}

if (problems.length) {
  console.error("check_packaging: FAIL");
  for (const p of problems) console.error(`  - ${p}`);
  process.exit(1);
}
console.log(`check_packaging: OK（${required.size} 个相对依赖都在 build.files 里）`);
