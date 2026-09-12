import i18n from "i18next";
import { initReactI18next } from "react-i18next";
import zhCN from "./locales/zh-CN";
import en from "./locales/en";

/** 语言持久化的 localStorage 键（与 jobws_selected_workspace 同一前缀） */
export const LANG_STORAGE_KEY = "jobws_lang";

/** 支持的界面语言；zh-CN 是源语言（其余翻译以它的 key 为准） */
export const LANGS = [
  { value: "zh-CN", label: "中文" },
  { value: "en", label: "English" },
] as const;

export type Lang = (typeof LANGS)[number]["value"];

function isSupported(value: string | null): value is Lang {
  return value === "zh-CN" || value === "en";
}

/** 首次语言：localStorage > 系统语言（zh* → zh-CN，其余 → en）。

    为什么不用 Electron 主进程的 `app.getLocale()`：渲染进程（Electron 与浏览器
    同环境）里 `navigator.language` 已经是系统语言，为这一个字符串多开一条 IPC
    不划算；若将来实测发现 zh-TW 等变体需要区别对待，再经 preload 注入也不迟。
*/
function detectLang(): Lang {
  try {
    const saved = localStorage.getItem(LANG_STORAGE_KEY);
    if (isSupported(saved)) return saved;
  } catch {
    // localStorage 不可用（隐私模式等）时退化为系统语言
  }
  return navigator.language?.toLowerCase().startsWith("zh") ? "zh-CN" : "en";
}

i18n.use(initReactI18next).init({
  resources: {
    "zh-CN": { translation: zhCN },
    en: { translation: en },
  },
  lng: detectLang(),
  // 缺 key 时回落到源语言，而不是把 key 名显示给用户
  fallbackLng: "zh-CN",
  // React 自身已做转义，再转义一次会把 & < > 显示成乱码
  interpolation: { escapeValue: false },
});

// 语言包走静态 import 打进 bundle：既满足 Electron asar 下不依赖文件路径，
// 也让初始化同步完成（无 Suspense、无首屏文案闪一下 key 名的问题）。

// 切换语言：持久化 + 同步 <html lang>（无障碍与浏览器翻译器都用得到）
i18n.on("languageChanged", (lng) => {
  try {
    localStorage.setItem(LANG_STORAGE_KEY, lng);
  } catch {
    // 持久化失败只影响下次启动的默认语言，不影响本次会话
  }
  document.documentElement.lang = lng;
});

export default i18n;
