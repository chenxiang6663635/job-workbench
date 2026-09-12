import { useEffect, useState } from "react";
import { useTranslation } from "react-i18next";
import { Briefcase, FileText, FolderOpen, LayoutDashboard, Library as LibraryIcon, Settings as SettingsIcon, TrendingUp } from "lucide-react";
import Dashboard from "./pages/Dashboard";
import Applications from "./pages/Applications";
import Jobs from "./pages/Jobs";
import Library from "./pages/Library";
import Progress from "./pages/Progress";
import Resume from "./pages/Resume";
import Settings from "./pages/Settings";
import { api, setWorkspace, type WorkspaceItem } from "./api";
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from "./components/ui/select";
import { LANGS } from "./i18n";
import type { TranslationKey } from "./i18n/locales/zh-CN";

type Tab = "dashboard" | "applications" | "jobs" | "resume" | "progress" | "library" | "settings";

// label 改成 i18n key：文案不再写死在组件里（翻译缺失时回落 zh-CN，不会露出 key 名）。
// 页面与组件内部的文案不在本批范围，留给「批量抽取」批统一处理。
const TABS: { key: Tab; labelKey: TranslationKey; icon: React.ReactNode }[] = [
  { key: "dashboard", labelKey: "nav.dashboard", icon: <LayoutDashboard size={16} /> },
  { key: "applications", labelKey: "nav.applications", icon: <Briefcase size={16} /> },
  { key: "jobs", labelKey: "nav.jobs", icon: <FolderOpen size={16} /> },
  { key: "resume", labelKey: "nav.resume", icon: <FileText size={16} /> },
  { key: "progress", labelKey: "nav.progress", icon: <TrendingUp size={16} /> },
  { key: "library", labelKey: "nav.library", icon: <LibraryIcon size={16} /> },
  { key: "settings", labelKey: "nav.settings", icon: <SettingsIcon size={16} /> },
];

const WS_STORAGE_KEY = "jobws_selected_workspace";

// 上次选中的工作区持久化到 localStorage。没有记录时用空串（= 后端默认）
function readSavedWorkspace(): string {
  try {
    return localStorage.getItem(WS_STORAGE_KEY) ?? "";
  } catch {
    return "";
  }
}

function tabFromHash(): Tab {
  const h = window.location.hash.replace("#", "");
  return TABS.some((t) => t.key === h) ? (h as Tab) : "dashboard";
}

export default function App() {
  const { t, i18n } = useTranslation();
  // hash 路由：刷新保持当前 Tab，且可直接用 #library 等定位页面
  // （此前用纯 state，刷新总回看板，也无头验证工具无法直达内页）
  const [tab, setTab] = useState<Tab>(tabFromHash);
  const [online, setOnline] = useState<boolean | null>(null);
  const [workspaces, setWorkspaces] = useState<WorkspaceItem[]>([]);
  const [workspaceReady, setWorkspaceReady] = useState(false);
  // 初始值：优先上次选中的工作区（localStorage），否则空串待列表加载后回填
  const [currentWs, setCurrentWs] = useState<string>(readSavedWorkspace);

  const switchTab = (t: Tab) => {
    setTab(t);
    if (window.location.hash !== "#" + t) {
      window.location.hash = t;
    }
  };

  useEffect(() => {
    const onHash = () => setTab(tabFromHash());
    window.addEventListener("hashchange", onHash);
    return () => window.removeEventListener("hashchange", onHash);
  }, []);

  useEffect(() => {
    api
      .dashboard()
      .then(() => setOnline(true))
      .catch(() => setOnline(false));
  }, []);

  // 加载可用工作区，并把当前选中的工作区设为激活态（同步 api.ts 全局）。
  // 完成后置 workspaceReady=true 才渲染内容区，消除首屏用空 ws 拉默认数据的竞态。
  // 优先 localStorage 里上次的选择；无效或无记录时回退默认工作区。
  useEffect(() => {
    api
      .listWorkspaces()
      .then((r) => {
        setWorkspaces(r.items);
        const saved = readSavedWorkspace();
        const match = r.items.find((w) => w.name === saved);
        if (match) {
          setCurrentWs(match.name);
          setWorkspace(match.name);
        } else {
          const def = r.items.find((w) => w.isDefault);
          if (def) {
            setCurrentWs(def.name);
            setWorkspace(def.name);
          }
        }
        setWorkspaceReady(true);
      })
      .catch(() => {
        setWorkspaceReady(true); // 即便列工作区失败也放行，避免永久卡在加载中
      });
  }, []);

  // 切换工作区：持久化选择并刷新页面（各页面在 mount 时按 currentWorkspace 拉数据）。
  // reload 后从 localStorage 恢复，避免丢回默认工作区。
  const switchWorkspace = (name: string) => {
    if (name === currentWs) return;
    setWorkspace(name);
    setCurrentWs(name);
    try {
      localStorage.setItem(WS_STORAGE_KEY, name);
    } catch {
      // localStorage 不可用时退化为仅本次会话有效
    }
    window.location.reload();
  };

  return (
    <div className="min-h-screen bg-background text-foreground">
      <div className="pointer-events-none fixed inset-x-0 top-0 h-64 bg-hero-glow" />

      <nav className="fixed inset-x-0 top-0 z-50 border-b border-border bg-background/80 backdrop-blur-xl">
        <div className="mx-auto flex h-16 max-w-7xl items-center gap-6 px-6">
          <div className="flex items-center gap-2">
            <img src="/favicon.png" alt={t("app.title")} className="h-7 w-7 rounded-lg" />
            <span className="text-sm font-semibold tracking-wide text-foreground">
              {t("app.title")}
            </span>
          </div>

          <div className="flex items-center gap-1">
            {TABS.map((item) => (
              <button
                key={item.key}
                onClick={() => switchTab(item.key)}
                className={`flex cursor-pointer items-center gap-1.5 rounded-lg px-3 py-2 text-sm transition-all duration-200 ease-premium ${
                  tab === item.key
                    ? "bg-primary/15 text-primary shadow-glow-primary"
                    : "text-muted-foreground hover:bg-secondary/60 hover:text-foreground"
                }`}
              >
                {item.icon}
                {t(item.labelKey)}
              </button>
            ))}
          </div>

          <div className="ml-auto flex items-center gap-3 text-xs">
            {/* 语言切换：只有 zh-CN / en 两态，用分段按钮比下拉更省一次点击 */}
            <div
              className="flex items-center rounded-lg border border-border p-0.5"
              role="group"
              title={t("lang.switch")}
            >
              {LANGS.map((l) => (
                <button
                  key={l.value}
                  onClick={() => i18n.changeLanguage(l.value)}
                  className={`cursor-pointer rounded-md px-2 py-1 text-xs transition-colors ${
                    i18n.language === l.value
                      ? "bg-primary/15 text-primary"
                      : "text-muted-foreground hover:text-foreground"
                  }`}
                >
                  {l.label}
                </button>
              ))}
            </div>

            {workspaces.length > 0 && (
              <Select value={currentWs} onValueChange={switchWorkspace}>
                <SelectTrigger
                  className="h-7 w-36 px-2 py-1 text-xs"
                  title={t("nav.switchWorkspaceTitle")}
                >
                  <SelectValue placeholder={t("nav.workspacePlaceholder")} />
                </SelectTrigger>
                <SelectContent>
                  {workspaces.map((w) => (
                    <SelectItem key={w.name} value={w.name} className="text-xs">
                      {w.name}
                      {w.isDefault ? t("nav.workspaceDefaultSuffix") : ""}
                    </SelectItem>
                  ))}
                </SelectContent>
              </Select>
            )}

            <span
              className={`h-2 w-2 rounded-full ${
                online === null
                  ? "bg-muted-foreground/50"
                  : online
                  ? "bg-success ring-2 ring-success/30"
                  : "bg-destructive ring-2 ring-destructive/30"
              }`}
            />
            <span className="text-muted-foreground">
              {online === null
                ? t("status.connecting")
                : online
                ? t("status.online")
                : t("status.offline")}
            </span>
          </div>
        </div>
      </nav>

      <main className="relative mx-auto max-w-7xl px-6 pb-16 pt-24">
        {online === false ? (
          <div className="rounded-2xl border border-destructive/30 bg-destructive/10 p-6">
            <p className="text-sm font-medium text-destructive">
              {t("error.backend")}
            </p>
            <p className="mt-2 text-xs leading-relaxed text-muted-foreground">
              {t("error.backendHint")}
              {/* 命令行本身不翻译：它是可直接复制执行的命令，翻译了就没法粘贴运行 */}
              <code className="mx-1 rounded bg-background px-1.5 py-0.5 text-foreground">
                cd web/backend &amp;&amp; python -m uvicorn main:app --port 8765
              </code>
            </p>
          </div>
        ) : !workspaceReady ? (
          // 工作区尚未激活（listWorkspaces 返回前）：避免首屏用空 ws 拉默认数据，
          // 否则切到非默认工作区 reload 后会先渲染一次默认工作区数据，产生闪烁
          <div className="text-sm text-muted-foreground">{t("loading.workspace")}</div>
        ) : tab === "dashboard" ? (
          <Dashboard key={currentWs} />
        ) : tab === "applications" ? (
          <Applications key={currentWs} />
        ) : tab === "jobs" ? (
          <Jobs key={currentWs} />
        ) : tab === "resume" ? (
          <Resume key={currentWs} />
        ) : tab === "progress" ? (
          <Progress key={currentWs} />
        ) : tab === "library" ? (
          <Library key={currentWs} />
        ) : (
          <Settings key={currentWs} />
        )}
      </main>
    </div>
  );
}
