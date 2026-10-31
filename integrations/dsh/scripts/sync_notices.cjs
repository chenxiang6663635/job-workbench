#!/usr/bin/env node
// 把仓库根的 LICENSE 与 THIRD-PARTY-NOTICES.md 复制进 npm 包目录（2026-10-30 审计 §六）。
//
// 为什么必须复制：npm 只打包包目录内的文件，`files: ["../../LICENSE"]` 无效。
// 而 `package.json` 声明了 `"license": "MIT"`——MIT 要求副本或实质部分随附版权与
// 许可声明，平台包还会分发 PyInstaller 打进去的第三方依赖（它们各自的 LICENSE 在
// `bin/_internal/*.dist-info/licenses/` 里，这一层由 PyInstaller 保证，不由本脚本管）。
//
// **源目录固定为仓库根**（2026-10-31 审计发现 3 修）：第一版是「从目标目录往上找
// 同时含两份材料的目录」，而第一次运行后**包目录自己**就满足该条件——第二次起
// `root === target`，`from === to` 直接跳过，根许可更新了也永远刷不过去。现在以脚本
// 自身位置为锚，向上找含 `.git` 的仓库根，然后**无条件覆盖**目标。
//
// 用法：node scripts/sync_notices.cjs [目标目录，默认 .]
// 后缀是 .cjs 而不是 .js：主包声明了 `"type": "module"`，`.js` 会被当 ESM 解析，
// 里面的 `require` 直接炸（实测过）。
// 由各包 package.json 的 `prepack` 调用，所以 `npm pack` / `npm publish` 一定带上它们。
// 产出是**生成物**，已在 .gitignore 里，别提交。
//
// 注意：主包的 tarball 里会出现**两份**许可（根级一份 + `platform/win32-x64/` 一份，
// 后者给平台子包自己用）。内容相同，这是有意的，不是重复打包 bug。

const fs = require("fs");
const path = require("path");

const FILES = ["LICENSE", "THIRD-PARTY-NOTICES.md"];

function findRepoRoot() {
  let dir = path.resolve(__dirname);
  for (;;) {
    if (fs.existsSync(path.join(dir, ".git"))) return dir;
    const parent = path.dirname(dir);
    if (parent === dir) return null;
    dir = parent;
  }
}

function main() {
  const target = path.resolve(process.argv[2] || ".");
  const root = findRepoRoot();
  if (!root) {
    // 从发布包内部运行（tarball 里没有 .git）：此时包目录里应当已经有副本，
    // 没有才是真的坏了。不能用「找不到仓库根」一票否决——否则 `npm rebuild`
    // 或用户侧二次打包会直接失败。
    const missing = FILES.filter((name) => !fs.existsSync(path.join(target, name)));
    if (missing.length) {
      console.error("sync_notices: 无仓库根，且目标目录缺 " + missing.join(" / ") + "（" + target + "）");
      process.exit(1);
    }
    console.log("sync_notices: 无仓库根（在发布包内运行），许可副本已存在，跳过同步");
    return;
  }

  for (const name of FILES) {
    const from = path.join(root, name);
    if (!fs.existsSync(from)) {
      console.error("sync_notices: 仓库根缺 " + name + "（" + root + "）");
      process.exit(1);
    }
    const to = path.join(target, name);
    if (path.resolve(from) === path.resolve(to)) {
      console.error("sync_notices: 目标目录就是仓库根，不该在这里打包（" + target + "）");
      process.exit(1);
    }
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
