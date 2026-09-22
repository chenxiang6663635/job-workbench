import { useCallback, useEffect, useState } from "react";
import { api, setWorkspace, type WorkspaceItem } from "../api";

// 上次选中的工作区持久化到 localStorage。没有记录时用空串（= 后端默认）
const WS_STORAGE_KEY = "jobws_selected_workspace";

function readSavedWorkspace(): string {
  try {
    return localStorage.getItem(WS_STORAGE_KEY) ?? "";
  } catch {
    return "";
  }
}

/**
 * 首启序列：列工作区 → 激活 → 探活（三件事一个序列）。
 *
 * **探活为什么必须排在激活之后**（2026-09-13 实测发现）：探活请求原先不带工作区，
 * 服务端就按**它自己的默认**工作区作答；而工作区一致性守卫（见 lib/http.ts 的
 * workspaceMismatch）在 currentWorkspace 已激活后，会把这份"默认工作区的响应"
 * 判成错位 → 探活失败 → 整页显示"后端未启动"，而后端一切正常。
 * main.tsx 开着 StrictMode，effect 会跑两遍，第二遍必然踩到——只要 localStorage
 * 里存的是**非默认**工作区，首页就是一块错误面板（本地实测：ws=demo 时复现）。
 * 完成后置 workspaceReady=true 才渲染内容区，消除首屏用空 ws 拉默认数据的竞态。
 *
 * 2026-09-21（U-1/UX-1）：整段从 App.tsx 拆出，boot 同时供离线屏的「重试」按钮
 * 复用——重试不整页 reload，hash / 语言 / 主题状态都还在，只是重跑这条序列。
 */
export function useBackendBoot() {
  const [online, setOnline] = useState<boolean | null>(null);
  const [workspaces, setWorkspaces] = useState<WorkspaceItem[]>([]);
  const [workspaceReady, setWorkspaceReady] = useState(false);
  // 初始值：优先上次选中的工作区（localStorage），否则空串待列表加载后回填
  const [currentWs, setCurrentWs] = useState<string>(readSavedWorkspace);

  const boot = useCallback(() => {
    setOnline(null);
    setWorkspaceReady(false);
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
        // 探活带上刚激活的工作区：这次请求的成败才真的只反映"后端在不在"
        return api.dashboard();
      })
      .then(() => setOnline(true))
      .catch(() => {
        // 列工作区或探活任一失败，都说明后端不可用
        setOnline(false);
        setWorkspaceReady(true); // 同时放行内容区，避免永久卡在加载中
      });
  }, []);

  useEffect(() => {
    boot();
  }, [boot]);

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

  return { online, workspaces, workspaceReady, currentWs, boot, switchWorkspace };
}
