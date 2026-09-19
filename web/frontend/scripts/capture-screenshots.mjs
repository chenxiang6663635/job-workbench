#!/usr/bin/env node
/**
 * 拍 README / 文档用的界面截图：8 页 × 中英两套 → docs/screenshots[/zh-CN]/
 *
 * **为什么要有这个脚本**：此前 14 张是手工拍的——重拍一次要开 8 页、切一次语言、
 * 挪窗口对齐分辨率，而每次新增页面或板块都要重拍一遍（2026-09-18 新增「准备」板块
 * 就是最近一次）。手工路径已经出过三类事故：漏拍一张、拍到 personal 真实工作区
 * （localStorage 里残留的 `jobws_selected_workspace` 会盖掉后端默认值）、忘了切语言
 * 导致中文目录里躺着英文界面。这些都不该靠记性。
 *
 * **放在这里的原因**：脚本要 `import` 前端的 `@playwright/test`，而依赖装在
 * `web/frontend/node_modules`——放仓库根的 `scripts/` 之下 Node 解析不到。
 *
 * **复用什么**：环境约定与 `e2e/fixtures.ts` **同源**（demo-shots 工作区 + 显式写
 * localStorage 再进页面）；那三个常量（页面顺序 / 视口 / 环境脚本）改动时要与
 * fixtures.ts 同步，别只改一边。
 *
 * **用法**（都在 web/frontend 下，`--help` 有同一份说明）：
 *   npm.cmd run build          # 先产出最新 dist（后端同源托管它；脚本会检查新旧）
 *   npm.cmd run capture        # 重建 demo-shots → 起后端 → 拍 16 张 → 关后端
 *   npm.cmd run capture -- --only prepare,settings      # 只重拍某几页（**不会**清其余图）
 *   npm.cmd run capture -- --base-url http://127.0.0.1:8765   # 连已在跑的服务（不重建、不清图）
 *
 * 镜像规范：`docs/screenshots/`（英文）与 `docs/screenshots/zh-CN/`（中文），
 * 文件名为 `NN-<page>.png`，编号 = App.tsx 的 TABS 顺序（**新增页面要整体重排，
 * 这正是脚本存在的第二个理由**）。1440×900、deviceScaleFactor 1——与既有 14 张一致。
 */

import { spawn } from "node:child_process";
import { existsSync } from "node:fs";
import { mkdir, readdir, rm, stat } from "node:fs/promises";
import os from "node:os";
import path from "node:path";
import process from "node:process";
import { fileURLToPath } from "node:url";

import { chromium } from "@playwright/test";

// 本文件在 web/frontend/scripts/ 下 → 上溯三级是仓库根
const REPO = path.resolve(path.dirname(fileURLToPath(import.meta.url)), "..", "..", "..");

/** 与 App.tsx 的 TABS 一一对应；数组下标 +1 就是文件名编号（改了要重排全部截图）。 */
const PAGES = [
  "dashboard",
  "applications",
  "jobs",
  "resume",
  "prepare",
  "progress",
  "library",
  "settings",
];

/** 三个视口里取 wide-1440：既有截图的规格（1440×900，一像素比）。 */
const VIEWPORT = { width: 1440, height: 900 };

const USAGE = `用法：node scripts/capture-screenshots.mjs [选项]

  --base-url <url>    连到已在跑的服务（不重建工作区、不清旧图）
  --port <n>          自起后端时的端口（默认 8769）
  --workspace <name>  拍哪个工作区（默认 demo-shots，须在仓库内）
  --out <dir>         图片输出根目录（默认 docs/screenshots，须在仓库内）
  --only a,b          只拍这几页（可选：${PAGES.join(", ")}；不会清其余图）
  --no-rebuild        跳过 demo-shots 重建（复用现有数据）
  -h, --help          显示本说明`;

function die(message, code = 2) {
  console.error(message);
  process.exit(code);
}

/**
 * 把相对路径解析到仓库内，越界即拒。
 *
 * 为什么要有这道闸：`--workspace` 的值会交给 `rm -rf` 用（重建演示数据），
 * 而它来自命令行——`--workspace ..` 会删掉仓库的父目录、`--workspace .`
 * 会删掉整个仓库（含未提交的工作）。这类参数没有「善意误用」的余地。
 */
function withinRepo(rel, label) {
  const resolved = path.resolve(REPO, rel);
  if (resolved === REPO) die(`${label} 不能是仓库根：${rel}`);
  if (!resolved.startsWith(REPO + path.sep)) die(`${label} 越出仓库范围：${rel}`);
  return resolved;
}

function parseArgs(argv) {
  const args = { port: 8769, workspace: "demo-shots", out: "docs/screenshots" };
  const takesValue = new Set(["--base-url", "--port", "--workspace", "--out", "--only"]);
  for (let i = 0; i < argv.length; i += 1) {
    const key = argv[i];
    if (key === "--help" || key === "-h") { console.log(USAGE); process.exit(0); }
    if (key === "--no-rebuild") { args.noRebuild = true; continue; }
    if (!takesValue.has(key)) die(`未知参数：${key}\n\n${USAGE}`);
    const value = argv[i + 1];
    if (value === undefined || value.startsWith("--")) die(`参数 ${key} 缺少值\n\n${USAGE}`);
    i += 1;
    if (key === "--base-url") {
      args.baseUrl = value;
    } else if (key === "--port") {
      const port = Number(value);
      if (!Number.isInteger(port) || port <= 0 || port > 65535) die(`--port 不是合法端口：${value}`);
      args.port = port;
    } else if (key === "--workspace") {
      args.workspace = value;
    } else if (key === "--out") {
      args.out = value;
    } else if (key === "--only") {
      args.only = value.split(",").map((s) => s.trim()).filter(Boolean);
    }
  }
  if (args.only) {
    const unknown = args.only.filter((name) => !PAGES.includes(name));
    if (unknown.length) {
      die(`--only 里有不是页面的名字：${unknown.join(", ")}\n可选：${PAGES.join(", ")}`);
    }
  }
  return args;
}

function pythonBin() {
  return process.env.JOBWS_PYTHON || "python";
}

function run(command, argv, cwd) {
  return new Promise((resolve, reject) => {
    const child = spawn(command, argv, { cwd, stdio: ["ignore", "pipe", "pipe"] });
    let stderr = "";
    child.stderr.on("data", (chunk) => { stderr += String(chunk); });
    child.on("error", reject);
    child.on("close", (code) => {
      if (code === 0) resolve();
      else reject(new Error(`${command} ${argv.join(" ")} 退出码 ${code}\n${stderr.trim()}`));
    });
  });
}

/** 目录里最新的 mtime（用于判断 dist 是否落后于源码）。 */
async function newestMtime(dir) {
  let newest = 0;
  for (const entry of await readdir(dir, { withFileTypes: true })) {
    const full = path.join(dir, entry.name);
    if (entry.isDirectory()) newest = Math.max(newest, await newestMtime(full));
    else newest = Math.max(newest, (await stat(full)).mtimeMs);
  }
  return newest;
}

/**
 * dist 必须比 src 新。
 *
 * 不检查的话，忘了 `npm run build` 就会对着旧产物拍一整批图、而且**不会报错**——
 * README 上「页面改了就重跑 capture」这句号召也就落空了。
 */
async function assertDistFresh() {
  const distIndex = path.join(REPO, "web", "frontend", "dist", "index.html");
  if (!existsSync(distIndex)) die("找不到 web/frontend/dist/index.html——先跑 npm.cmd run build");
  const srcNewest = await newestMtime(path.join(REPO, "web", "frontend", "src"));
  if (srcNewest > (await stat(distIndex)).mtimeMs) {
    die("dist 比 src 旧——先跑 npm.cmd run build（否则拍到的是旧界面）");
  }
}

/** 重建演示工作区：.gitignore 的约定是「跑命令重建，不要手工维护 demo 数据」。 */
async function rebuildWorkspace(name) {
  const target = withinRepo(name, "--workspace");
  if (existsSync(target)) await rm(target, { recursive: true, force: true });
  // 走统一入口 `jobws init`：tools/*.py 直跑自 2026-09 起只给迁移提示并 exit 2
  await run(pythonBin(), ["tools/jobws.py", "init", "--target", name, "--demo"], REPO);
  console.log(`已重建工作区 ${name}（jobws init --demo）`);
}

/**
 * 清掉自己命名空间里的旧图（`NN-*.png`）。
 *
 * 为什么要清：新增页面会让编号整体后移（2026-09-18 的「准备」插在第 5 位，
 * 旧 `05-progress` 就变成了孤儿——既不被覆盖、也不再被任何文档引用，但会一直
 * 躺在仓库里骗人）。只删两位数字开头的 PNG，别的文件一律不碰。
 * **`--only` 与 `--base-url` 模式下跳过**：用户是要补拍，不是要清仓。
 */
async function cleanOutDir(dir) {
  if (!existsSync(dir)) return;
  const stale = (await readdir(dir)).filter((name) => /^\d{2}-.*\.png$/.test(name));
  await Promise.all(stale.map((name) => rm(path.join(dir, name), { force: true })));
  if (stale.length) console.log(`清理 ${path.relative(REPO, dir)} 下 ${stale.length} 张旧图`);
}

async function waitForHealth(baseUrl, timeoutMs = 60_000) {
  const deadline = Date.now() + timeoutMs;
  while (Date.now() < deadline) {
    try {
      const res = await fetch(`${baseUrl}/api/health`, { signal: AbortSignal.timeout(2000) });
      if (res.ok && (await res.text()).includes("ok")) return;
    } catch (err) { /* 还没起来，继续等 */ }
    await new Promise((resolve) => setTimeout(resolve, 400));
  }
  throw new Error(`后端在 ${timeoutMs / 1000}s 内没有就绪：${baseUrl}/api/health`);
}

/**
 * 断言导航栏显示的就是目标工作区。
 *
 * 两条静默路径都靠这一步兜住：① 端口被占时后端会**复用**已有实例（`main.py` 的
 * 行为，退出码还是 0）；② localStorage 里的工作区无效时前端会回落到默认工作区。
 * 两条都不报错，却会拍到另一份数据——极端情况是 personal。
 */
async function assertWorkspace(page, expected) {
  const text = (await page.locator("nav").getByRole("combobox").first().innerText()).trim();
  if (!text.startsWith(expected)) {
    throw new Error(
      `连到的服务不是目标工作区：期望 ${expected}，导航栏显示 ${text}\n` +
      "（端口被占时后端会复用已有实例——换 --port，或先关掉那个服务）",
    );
  }
}

/**
 * 进页面之前写死三个偏好（工作区 / 语言 / 主题）。
 *
 * - 工作区：不写就会拍到 personal 真实数据（localStorage 的残留会盖掉后端默认值）；
 * - 语言：不写就会拍到系统语言那一套，中文目录里可能躺着英文界面；
 * - 主题：**既有 14 张全部是暗色**，而主题的默认值是「跟随系统」（`lib/theme.ts`
 *   的 `SYSTEM_ID` 排在第一位）——全新 context 没有 localStorage，会在浅色系统的
 *   机器上拍出另一套风格。这正是必须显式钉住而不是靠默认值的原因。
 *
 * 语言取值见 `src/i18n/index.ts`（`en` / `zh-CN`，不是 `zh`）；
 * 主题取值见 `src/lib/theme.ts`（键名带点：`jobws.theme`）。
 */
function envScript(workspace, lang) {
  return `
    try {
      localStorage.setItem("jobws_selected_workspace", ${JSON.stringify(workspace)});
      localStorage.setItem("jobws_lang", ${JSON.stringify(lang)});
      localStorage.setItem("jobws.theme", "dark");
    } catch (e) { /* 隐私模式下不可用：assertWorkspace 会把后果暴露出来 */ }
  `;
}

const LANGS = [
  { code: "en", dir: "." },
  { code: "zh-CN", dir: "zh-CN" },
];

/**
 * 把真实用户名换成 `<用户名>`，并**断言页面上已无残留**。
 *
 * 「设置」页会显示数据目录（`C:\Users\<真名>\…`），那是这些图唯一会泄露本机身份的
 * 地方——既有 14 张也是这么处理的（CHANGELOG 有记录）。文本节点之外还要扫一遍
 * `title` / `aria-label` / `placeholder` 与输入框的 value：只替换文本节点会漏掉
 * 属性里带路径的写法，而漏了**不会报错**、只会把用户名带进仓库。
 * React 会在数据刷新时重渲染覆盖，所以这一步紧贴 screenshot 之前做，并当场复验。
 */
async function maskLocalUsername(page) {
  const user = os.userInfo().username;
  if (!user) return;
  await page.evaluate((real) => {
    const swap = (text) => text.split(real).join("<用户名>");
    const walker = document.createTreeWalker(document.body, NodeFilter.SHOW_TEXT);
    const hits = [];
    while (walker.nextNode()) {
      const node = walker.currentNode;
      if (node.nodeValue && node.nodeValue.includes(real)) hits.push(node);
    }
    hits.forEach((node) => { node.nodeValue = swap(node.nodeValue); });
    document.querySelectorAll("[title], [aria-label], [placeholder]").forEach((el) => {
      ["title", "aria-label", "placeholder"].forEach((attr) => {
        const value = el.getAttribute(attr);
        if (value && value.includes(real)) el.setAttribute(attr, swap(value));
      });
    });
    document.querySelectorAll("input, textarea").forEach((el) => {
      if (el.value && el.value.includes(real)) el.value = swap(el.value);
    });
  }, user);
  const leftover = await page.evaluate((real) => document.body.innerText.includes(real), user);
  if (leftover) {
    throw new Error(`用户名 ${user} 仍出现在页面上——遮挡失败，拒绝出图`);
  }
}

async function main() {
  const args = parseArgs(process.argv.slice(2));
  const outRoot = withinRepo(args.out, "--out");
  if (!args.baseUrl) withinRepo(args.workspace, "--workspace");

  await assertDistFresh();

  const only = args.only && args.only.length ? new Set(args.only) : null;
  const pages = only ? PAGES.filter((p) => only.has(p)) : PAGES;

  if (!args.noRebuild && !args.baseUrl) await rebuildWorkspace(args.workspace);

  let server = null;
  let stopping = false;
  let baseUrl = args.baseUrl;
  if (!baseUrl) {
    baseUrl = `http://127.0.0.1:${args.port}`;
    console.log(`启动后端：${pythonBin()} web/backend/main.py --workspace ${args.workspace} --port ${args.port}`);
    server = spawn(
      pythonBin(),
      ["web/backend/main.py", "--workspace", args.workspace, "--port", String(args.port)],
      {
        cwd: REPO,
        env: { ...process.env, JOBWS_NO_BROWSER: "1" },
        stdio: ["ignore", "ignore", "inherit"],
      },
    );
    server.on("error", (err) => {
      die(`启动后端失败：${err.message}\n（解释器可用 JOBWS_PYTHON 指定）`);
    });
    server.on("exit", (code) => {
      if (!stopping && code !== null && code !== 0) {
        die(`后端提前退出（码 ${code}）——端口 ${args.port} 可能被占用，换 --port 或先关掉那个服务`);
      }
    });
  } else {
    console.log(`连到已在跑的服务：${baseUrl}（未重建工作区、未清旧图）`);
  }

  const written = [];
  try {
    await waitForHealth(baseUrl);

    const browser = await chromium.launch();
    for (const lang of LANGS) {
      // 补拍模式（--only / --base-url）下不清图：否则会先删掉整批再只写回几张
      if (!only && !args.baseUrl) await cleanOutDir(path.join(outRoot, lang.dir));
      const context = await browser.newContext({
        viewport: VIEWPORT,
        locale: lang.code,
        deviceScaleFactor: 1,
      });
      await context.addInitScript(envScript(args.workspace, lang.code));

      for (const key of pages) {
        // **每页新开一个 page**，不要复用同一个：同一页面内的 hash 导航
        // （`#jobs` → `#resume`）不触发真正的导航，复用时「等 nav 选择器可见」
        // 与 `networkidle` 都会在**上一页**立刻满足——于是拍下的是上一页，
        // 而且时对时错（实测踩到：`03-jobs.png` 里是追踪表）。
        // 新 page 的首次 goto 是真导航，两个等待信号才真的有效。
        const page = await context.newPage();
        page.setDefaultTimeout(20_000);
        try {
          const index = PAGES.indexOf(key) + 1;
          const file = path.join(outRoot, lang.dir, `${String(index).padStart(2, "0")}-${key}.png`);
          await mkdir(path.dirname(file), { recursive: true });
          // 就绪信号用导航栏的工作区选择器：它只在 listWorkspaces 返回后渲染，
          // 比等某个业务文案稳定（与 e2e/fixtures.ts 的 openPage 同款理由）。
          await page.goto(`${baseUrl}/#${key}`);
          await page.locator("nav").getByRole("combobox").first().waitFor({ state: "visible" });
          await page.waitForLoadState("networkidle");
          await assertWorkspace(page, args.workspace);
          await maskLocalUsername(page);
          await page.screenshot({ path: file });
          const size = (await stat(file)).size;
          written.push({ file: path.relative(REPO, file), kb: Math.round(size / 1024) });
        } finally {
          await page.close();
        }
      }
      await context.close();
    }
    await browser.close();
  } finally {
    if (server) {
      stopping = true;
      server.kill();
    }
  }

  console.log(`\n已拍 ${written.length} 张：`);
  for (const item of written) console.log(`  ${item.file}  ${item.kb} KB`);
  console.log("\n接着做：确认成图无误 → 更新 README / README.zh-CN 的引用与编号 → 记 CHANGELOG。");
}

main().catch((err) => {
  console.error(`\n截图失败：${err.message}`);
  process.exit(1);
});
