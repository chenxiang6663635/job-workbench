import { defineConfig, type Plugin } from "vite";
import react from "@vitejs/plugin-react";

// vite.config 运行在 Node 里；本仓库前端刻意不装 @types/node（控制依赖面），
// 这里只声明实际用到的 surface，避免为一个环境变量引入整个 node 类型包。
declare const process: { env: Record<string, string | undefined> };

// https://vite.dev/config/
//
// 绑定地址默认只对本机开放（127.0.0.1）：dev server 的 /api 代理会把请求转给
// 本机后端（127.0.0.1:8765，无鉴权的本地数据 API）——绑 0.0.0.0 等于让同一
// 网络里的任何设备都能经这条代理读写你的数据，同时关掉 Host 校验还会放大
// DNS rebinding 面（SECURITY.md 的立场：任何让 API 从网络可达的路径都是 bug）。
// 需要手机 / 平板预览时显式开放：
//
//   PowerShell:  $env:VITE_HOST="0.0.0.0"; npm run dev
//
// ——只有这一种情况才绑全网卡并放宽 allowedHosts；关掉终端即恢复默认。
const openToLan = process.env.VITE_HOST === "0.0.0.0";

/** P-2（体检 P-5）：@fontsource 的**静态**字体包在 @font-face 里带 woff 回退，
 * 构建产物因此带双份字体（woff + woff2，约 200 个文件）。运行时只有 Chromium
 * （桌面端与开发浏览器）——woff2 是必然支持面，网页版目前不存在；这里在 CSS
 * 进打包管线前剥掉 woff 那一项，只留 woff2（字体栈与 unicode-range 一字不动）。
 * 只动 node_modules 里的 @fontsource CSS，业务样式不碰。 */
function stripFontsourceWoff(): Plugin {
  return {
    name: "jobws:strip-fontsource-woff",
    enforce: "pre",
    transform(code, id) {
      const clean = id.replace(/\\/g, "/");
      if (!clean.includes("node_modules/@fontsource") || !/\.css(\?|$)/.test(clean)) {
        return null;
      }
      const next = code.replace(
        /,\s*url\([^)]*\.woff\)\s*format\(\s*['"]woff['"]\s*\)/g,
        ""
      );
      return next === code ? null : next;
    },
  };
}

export default defineConfig({
  plugins: [react(), stripFontsourceWoff()],
  build: {
    // P-2（体检 P-5）：单 JS chunk 1.21MB → 按「更新频率低的大依赖」分包。
    // 业务代码改动时用户只重下业务 chunk；下面几组各自吃长期缓存。只收 JS 模块
    // （CSS 交给 Vite 默认管线），未单列的依赖归入 vendor。
    rollupOptions: {
      output: {
        manualChunks(id) {
          // 先剥掉 `?commonjs-proxy` 之类的查询串：带查询的 CJS 包装模块同样是 JS
          // 模块，漏给默认分块会把 React 的包装模块塞进任意 chunk，运行期报
          // "Cannot read properties of undefined (reading 'forwardRef')"（实测踩过）。
          const path = id.replace(/\\/g, "/").split("?")[0];
          const marker = path.lastIndexOf("node_modules/");
          if (marker === -1) return undefined;
          if (!/\.(mjs|cjs|js|jsx|ts|tsx)$/.test(path)) return undefined;
          const pkg = path.slice(marker + "node_modules/".length);
          if (/^(react|react-dom|scheduler)\//.test(pkg)) return "vendor-react";
          if (pkg.startsWith("@radix-ui/")) return "vendor-radix";
          if (/^(i18next|react-i18next)\//.test(pkg)) return "vendor-i18n";
          if (pkg.startsWith("lucide-react/")) return "vendor-icons";
          if (/^(recharts|victory-vendor|d3-[a-z-]+|internmap)\//.test(pkg)) {
            return "vendor-charts";
          }
          // 其余全部并入 vendor。曾把 markdown 系（react-markdown / remark /
          // micromark…）单列一组，结果与 vendor 形成跨 chunk 循环、运行期 TDZ
          // （Cannot access 'T' before initialization）。依赖图里有环时宁可并入
          // 同一 chunk——Rollup 对 chunk 内的循环有定序保证，跨 chunk 没有。
          return "vendor";
        },
      },
    },
  },
  server: {
    host: openToLan ? "0.0.0.0" : "127.0.0.1",
    ...(openToLan ? { allowedHosts: true } : {}),
    port: 5173,
    proxy: {
      "/api": {
        target: "http://127.0.0.1:8765",
        changeOrigin: true,
      },
    },
  },
});
