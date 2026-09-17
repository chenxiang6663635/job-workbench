import { StrictMode } from 'react'
import { createRoot } from 'react-dom/client'
// 本地打包字体（批 4 4g → 2026-09-17 扩到 12 款界面 + 6 款等宽；全部 OFL-1.1、
// 离线可用）。统一引用 wght 入口（避开 Inter / DM Sans / IBM Plex 的 opsz 大
// 文件）；各款只含拉丁子集——CJK 不在其 unicode-range 内，中文自动回退系统栈
// （见 index.css 的 --font-cjk）。切字体只改 html[data-font] / [data-mono] /
// [data-numeric]。
import '@fontsource-variable/inter/wght.css'
import '@fontsource-variable/geist/wght.css'
import '@fontsource-variable/ibm-plex-sans/wght.css'
import '@fontsource-variable/manrope/wght.css'
import '@fontsource-variable/plus-jakarta-sans/wght.css'
import '@fontsource-variable/dm-sans/wght.css'
import '@fontsource-variable/figtree/wght.css'
import '@fontsource-variable/outfit/wght.css'
import '@fontsource-variable/public-sans/wght.css'
import '@fontsource-variable/source-sans-3/wght.css'
import '@fontsource-variable/work-sans/wght.css'
import '@fontsource-variable/atkinson-hyperlegible-next/wght.css'
import '@fontsource/maple-mono/400.css'
import '@fontsource/maple-mono/600.css'
import '@fontsource-variable/jetbrains-mono/wght.css'
import '@fontsource-variable/fira-code/wght.css'
import '@fontsource-variable/geist-mono/wght.css'
import '@fontsource/ibm-plex-mono/400.css'
// 数字槽（批 4.6）里 Plex Mono 是静态字重包（非 variable）：数字阶梯用到
// 500（列表）与 600（KPI），只导 400 会让这两档落到浏览器合成粗体
import '@fontsource/ibm-plex-mono/500.css'
import '@fontsource/ibm-plex-mono/600.css'
import '@fontsource-variable/source-code-pro/wght.css'
import './index.css'
// 主题变量（批 4）：每套一个文件；:root 为默认暗，首帧属性由 index.html 内联脚本先行写入
import './themes/light.css'
import './themes/catppuccin-mocha.css'
import './themes/catppuccin-latte.css'
import './themes/nord.css'
import './themes/tokyo-night.css'
import './themes/rose-pine.css'
import './themes/rose-pine-dawn.css'
import './themes/gruvbox.css'
import './themes/everforest.css'
import './i18n'
import App from './App.tsx'
import ErrorBoundary from './ErrorBoundary.tsx'
import {
  applyStoredFont,
  applyStoredFontSize,
  applyStoredMono,
  applyStoredNumeric,
  applyStoredTheme,
} from './lib/theme'

// 首帧之前由 index.html 的内联脚本按偏好写过一次；这里在 React 挂载前再同步一次，
// 保证内存状态与 DOM 属性一致（含「跟随系统」的解析与监听注册）。
// applyStoredMono 是 2026-09-17 双槽落地时漏掉的对称项（首帧脚本兜住了绝大部分
// 场景），批 4.6 与 applyStoredNumeric 一并补齐。
applyStoredTheme()
applyStoredFont()
applyStoredMono()
applyStoredFontSize()
applyStoredNumeric()

createRoot(document.getElementById('root')!).render(
  <StrictMode>
    <ErrorBoundary>
      <App />
    </ErrorBoundary>
  </StrictMode>,
)
