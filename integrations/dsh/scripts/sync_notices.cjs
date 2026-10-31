#!/usr/bin/env node
// 把仓库根的 LICENSE 与 THIRD-PARTY-NOTICES.md 复制进 npm 包目录（2026-10-30 审计 §六）。
//
// 为什么必须复制：npm 只打包包目录内的文件，`files` 里写 `../../LICENSE` 无效。
// 而 `package.json` 声明了 `"license": "MIT"`——MIT 要求副本或实质部分随附版权与
// 许可声明，平台包还会分发 PyInstaller 打进去的第三方依赖（它们各自的 LICENSE 在
// `bin/_internal/*.dist-info/licenses/` 里，这一层由 PyInstaller 保证，不由本脚本管）。
//
// 用法：node scripts/sync_notices.js [目标目录，默认 .]
// 由各包 package.json 的 `prepack` 调用，所以 `npm pack` / `npm publish` 一定带上它们。
// 产出是**生成物**，已在 .gitignore 里，别提交。

const fs = require("fs");
const path = require("path");

const FILES = ["LICENSE", "THIRD-PARTY-NOTICES.md"];

function findRepoRoot(start) {
  let dir = path.resolve(start);
  for (;;) {
    if (FILES.every((name) => fs.existsSync(path.join(dir, name)))) return dir;
    const parent = path.dirname(dir);
    if (parent === dir) return null;
    dir = parent;
  }
}

function main() {
  const target = path.resolve(process.argv[2] || ".");
  const root = findRepoRoot(target);
  if (!root) {
    console.error(
      "sync_notices: 从 " + target + " 往上找不到同时含 " + FILES.join(" / ") + " 的目录"
    );
    process.exit(1);
  }
  for (const name of FILES) {
    const from = path.join(root, name);
    const to = path.join(target, name);
    if (path.resolve(from) === path.resolve(to)) continue;
    fs.copyFileSync(from, to);
    const bytes = fs.statSync(to).size;
    if (bytes === 0) {
      console.error("sync_notices: " + name + " 复制后是空文件");
      process.exit(1);
    }
    console.log("sync_notices: " + name + " -> " + path.relative(process.cwd(), to) + " (" + bytes + " B)");
  }
}

main();
