import { defineConfig } from "vite";
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

export default defineConfig({
  plugins: [react()],
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
