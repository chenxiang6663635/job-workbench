import { StrictMode } from 'react'
import { createRoot } from 'react-dom/client'
// 本地打包字体（批 4，4g）：离线可用、不依赖网络字体。
// Inter Variable 覆盖拉丁 UI；Maple Mono 提供等宽数字（中英混排等宽）。
// 中文仍走系统栈（体积 10–30MB 级，不内置——见批 4 施工单）。
import '@fontsource-variable/inter'
import '@fontsource/maple-mono/400.css'
import '@fontsource/maple-mono/500.css'
import '@fontsource/maple-mono/600.css'
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
import { applyStoredFont, applyStoredTheme } from './lib/theme'

// 首帧之前由 index.html 的内联脚本按偏好写过一次；这里在 React 挂载前再同步一次，
// 保证内存状态与 DOM 属性一致（含「跟随系统」的解析与监听注册）。
applyStoredTheme()
applyStoredFont()

createRoot(document.getElementById('root')!).render(
  <StrictMode>
    <ErrorBoundary>
      <App />
    </ErrorBoundary>
  </StrictMode>,
)
