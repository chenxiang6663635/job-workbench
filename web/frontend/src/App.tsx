import { useEffect, useState } from "react";
import { Briefcase, FolderOpen, LayoutDashboard, Library as LibraryIcon, Settings as SettingsIcon } from "lucide-react";
import Dashboard from "./pages/Dashboard";
import Applications from "./pages/Applications";
import Jobs from "./pages/Jobs";
import Library from "./pages/Library";
import Settings from "./pages/Settings";
import { api, setWorkspace, type WorkspaceItem } from "./api";

type Tab = "dashboard" | "applications" | "jobs" | "library" | "settings";

const TABS: { key: Tab; label: string; icon: React.ReactNode }[] = [
  { key: "dashboard", label: "看板", icon: <LayoutDashboard size={16} /> },
  { key: "applications", label: "追踪表", icon: <Briefcase size={16} /> },
  { key: "jobs", label: "岗位池", icon: <FolderOpen size={16} /> },
  { key: "library", label: "素材库", icon: <LibraryIcon size={16} /> },
  { key: "settings", label: "设置", icon: <SettingsIcon size={16} /> },
];

function tabFromHash(): Tab {
  const h = window.location.hash.replace("#", "");
  return TABS.some((t) => t.key === h) ? (h as Tab) : "dashboard";
}

export default function App() {
  // hash 路由：刷新保持当前 Tab，且可直接用 #library 等定位页面
  // （此前用纯 state，刷新总回看板，也无头验证工具无法直达内页）
  const [tab, setTab] = useState<Tab>(tabFromHash);
  const [online, setOnline] = useState<boolean | null>(null);
  const [workspaces, setWorkspaces] = useState<WorkspaceItem[]>([]);
  const [currentWs, setCurrentWs] = useState<string>(() => {
    // 初始值：从后端默认工作区推断。真正值在加载列表后回填。
    return "";
  });

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

  // 加载可用工作区，并把默认工作区设为当前选中
  useEffect(() => {
    api
      .listWorkspaces()
      .then((r) => {
        setWorkspaces(r.items);
        const def = r.items.find((w) => w.isDefault);
        if (def) {
          setCurrentWs(def.name);
          setWorkspace(def.name);
        }
      })
      .catch(() => {});
  }, []);

  // 切换工作区：更新全局并刷新页面（各页面在 mount 时按 currentWorkspace 拉数据）
  const switchWorkspace = (name: string) => {
    if (name === currentWs) return;
    setWorkspace(name);
    setCurrentWs(name);
    window.location.reload();
  };

  return (
    <div className="min-h-screen bg-ink-950 text-slate-200">
      <div className="pointer-events-none fixed inset-x-0 top-0 h-64 bg-gradient-to-b from-accent/10 to-transparent" />

      <nav className="fixed inset-x-0 top-0 z-50 border-b border-white/10 bg-ink-950/80 backdrop-blur-xl">
        <div className="mx-auto flex h-16 max-w-7xl items-center gap-6 px-6">
          <div className="flex items-center gap-2">
            <div className="h-7 w-7 rounded-lg bg-gradient-to-br from-accent to-accent-dim" />
            <span className="text-sm font-semibold tracking-wide text-white">
              秋招工作台
            </span>
          </div>

          <div className="flex items-center gap-1">
            {TABS.map((t) => (
              <button
                key={t.key}
                onClick={() => switchTab(t.key)}
                className={`flex cursor-pointer items-center gap-1.5 rounded-lg px-3 py-2 text-sm transition-all duration-200 ${
                  tab === t.key
                    ? "bg-accent/15 text-accent"
                    : "text-slate-400 hover:bg-white/5 hover:text-slate-200"
                }`}
              >
                {t.icon}
                {t.label}
              </button>
            ))}
          </div>

          <div className="ml-auto flex items-center gap-3 text-xs">
            {workspaces.length > 0 && (
              <select
                value={currentWs}
                onChange={(e) => switchWorkspace(e.target.value)}
                className="cursor-pointer rounded-lg border border-white/10 bg-ink-900 px-2 py-1.5 text-xs text-slate-200 outline-none focus:border-accent/50"
                title="切换工作区"
              >
                {workspaces.map((w) => (
                  <option key={w.name} value={w.name}>
                    {w.name}
                    {w.isDefault ? "（默认）" : ""}
                  </option>
                ))}
              </select>
            )}

            <span
              className={`h-2 w-2 rounded-full ${
                online === null
                  ? "bg-slate-500"
                  : online
                  ? "bg-good"
                  : "bg-bad"
              }`}
            />
            <span className="text-slate-500">
              {online === null
                ? "连接中"
                : online
                ? "已连接本地数据"
                : "后端未启动"}
            </span>
          </div>
        </div>
      </nav>

      <main className="relative mx-auto max-w-7xl px-6 pb-16 pt-24">
        {online === false ? (
          <div className="rounded-2xl border border-bad/30 bg-bad/10 p-6">
            <p className="text-sm font-medium text-bad">
              无法连接到后端（localhost:8765）
            </p>
            <p className="mt-2 text-xs leading-relaxed text-slate-400">
              请在仓库根目录运行：
              <code className="mx-1 rounded bg-ink-950 px-1.5 py-0.5 text-slate-300">
                cd web/backend &amp;&amp; python -m uvicorn main:app --port 8765
              </code>
            </p>
          </div>
        ) : tab === "dashboard" ? (
          <Dashboard />
        ) : tab === "applications" ? (
          <Applications />
        ) : tab === "jobs" ? (
          <Jobs />
        ) : tab === "library" ? (
          <Library />
        ) : (
          <Settings />
        )}
      </main>
    </div>
  );
}
