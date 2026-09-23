// 工作区同步（批 8）：GUI 端（桌面版 / 浏览器 dev 同一套前端）感知「外部写过数据」并请调用方刷新。
//
// 为什么不用文件监听：Windows 上 ReadDirectoryChangesW 缓冲溢出会**静默丢事件**，
// 原子保存（temp + rename）也会绕过「监听具体文件路径」的实现；而本项目是
// 「多个短命进程写 + 单一长命 GUI 读」——聚焦重拉 + 轻量指纹轮询才是稳的组合。
// 详见批 8 计划与 .codebuddy/memory 的调研记录。
//
// **关键约束（独立审查 B1）**：GUI 自己也会写同一批文件（如简历页 400ms 防抖
// 自动保存），指纹端点分不清写入者。若"变了就 reload"，就会形成
// 「打字 → 自动保存 → 重载 → 防抖保存被卸载取消 → 丢字」的循环。
// 因此：**有输入活动时先推迟**（并在推迟时推进基线，把本端写出的变化吃掉），
// 无输入活动时指纹变化只可能来自外部 → 才刷新。
//
// 为什么不走 api.ts：本 hook 只有一个端点的窄需求（no-store 轮询），直接 fetch
// 比给统一封装加一整个转发面更小——api.ts 是"水位"文件（只许变小），不撑它。
//
// 行为：
// - 每 10s 拉一次工作区指纹（cache: no-store）；窗口隐藏时暂停、可见时补一次；
// - 窗口聚焦 / 可见性变化时也查一次（"从 CLI / MCP 切回 GUI"的主场景）；
// - **仅在"指纹变化 且 近 10s 无输入活动"时回调**；
// - 网络错误不吞：首次失败给一条 console.warn（禁静默吞错是本仓纪律），之后静默重试。
import { useEffect, useRef } from "react";

const POLL_MS = 10_000;
const ACTIVITY_GRACE_MS = 10_000;
const WS_STORAGE_KEY = "jobws_selected_workspace";

function currentWorkspaceQuery(): string {
  try {
    const name = localStorage.getItem(WS_STORAGE_KEY) ?? "";
    return name ? `?ws=${encodeURIComponent(name)}` : "";
  } catch {
    return "";
  }
}

async function fetchFingerprint(): Promise<string> {
  const res = await fetch(`/api/system/workspace-version${currentWorkspaceQuery()}`, {
    cache: "no-store",
  });
  if (!res.ok) throw new Error(`workspace-version ${res.status}`);
  const data = (await res.json()) as { fingerprint?: string };
  return data.fingerprint ?? "";
}

export function useWorkspaceSync(
  onExternalChange: () => void,
  enabled = true
): void {
  const lastRef = useRef<string | null>(null);
  const callbackRef = useRef(onExternalChange);
  callbackRef.current = onExternalChange;

  useEffect(() => {
    if (!enabled) return () => undefined;
    let stopped = false;
    let timer: number | undefined;
    let warned = false;
    // 最近一次用户活动：本端可能正在防抖保存，早于阈值的刷新要先让路。
    // `input`/`keydown` 之外**必须**也认指针事件（2026-09-23 二轮审计）：界面上
    // 大量写入是纯鼠标完成的（Radix 下拉选项、"标记已联系"这类按钮）——它们不产生
    // input 事件，于是"刚在界面里改完一行、页面自己 reload 一次"，未提交的草稿
    // （新增投递表单、填了一半的联系人）随之清空。
    let lastActivityAt = 0;
    const markActivity = () => {
      lastActivityAt = Date.now();
    };

    const check = async () => {
      try {
        const fingerprint = await fetchFingerprint();
        if (stopped) return;
        if (lastRef.current !== null && fingerprint !== lastRef.current) {
          const idleFor = Date.now() - lastActivityAt;
          if (idleFor >= ACTIVITY_GRACE_MS) {
            callbackRef.current();
          }
          // 无论是否回调都推进基线：正在输入时的变化（多半是自己写的）不反复触发
        }
        lastRef.current = fingerprint;
      } catch (err) {
        if (!warned) {
          warned = true;
          console.warn("[jobws] workspace sync poll failed (will retry)", err);
        }
      }
    };

    const schedule = () => {
      if (stopped) return;
      timer = window.setTimeout(async () => {
        if (document.visibilityState === "visible") await check();
        schedule();
      }, POLL_MS);
    };

    const onFocus = () => {
      if (document.visibilityState === "visible") void check();
    };

    void check(); // 首次只建立基线（不触发回调）
    schedule();
    window.addEventListener("keydown", markActivity, true);
    window.addEventListener("input", markActivity, true);
    window.addEventListener("pointerdown", markActivity, true);
    window.addEventListener("click", markActivity, true);
    window.addEventListener("focus", onFocus);
    document.addEventListener("visibilitychange", onFocus);
    return () => {
      stopped = true;
      if (timer !== undefined) window.clearTimeout(timer);
      window.removeEventListener("keydown", markActivity, true);
      window.removeEventListener("input", markActivity, true);
      window.removeEventListener("pointerdown", markActivity, true);
      window.removeEventListener("click", markActivity, true);
      window.removeEventListener("focus", onFocus);
      document.removeEventListener("visibilitychange", onFocus);
    };
  }, [enabled]);
}
