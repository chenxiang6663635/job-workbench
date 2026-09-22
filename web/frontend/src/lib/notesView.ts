// 笔记的**阅读位置**与**视图态**记忆（sessionStorage，2026-09-21）。
//
// 解决两件具体的事：
// 1. 勾选写回后要重拉正文，此前 `setContent(null)` 让正文先塌成骨架 → 被打回顶部；
// 2. 外部编辑会触发 App 级指纹刷新（整页 reload），重新挂载后位置同样丢失。
//
// 为什么是 sessionStorage：这是"这一个会话里我读到哪"，不是跨会话的偏好——
// 与 lib/drill.ts 的 `jobws_drill_round` 同族。文件记忆（上次打开哪一篇）仍走
// localStorage（lib/notes.ts 的 jobws_notes_last），两件事不混。
//
// 位置坐标刻意复用渲染侧的 `data-line`（块级行号，与大纲锚点同源）：行号在
// 写回前后一致（写回只改标记字符，不改行数），比"滚了多少像素"稳。

const POS_KEY = "jobws_notes_pos";
const UI_KEY = "jobws_notes_ui";
const FLOW_KEY = "jobws_notes_flow";
// 批量待提交集合（C-1）：按「工作区 + 文件」各自一份，切文件是换键不是清空
const PENDING_KEY = "jobws_notes_pending";

export interface NotesViewPos {
  /** 工作区（换了就别把别的工作区的阅读位置搬过来） */
  ws: string;
  section: string;
  rel: string;
  /** 视口顶部所在的块级行号；没有可定位的块时为 null */
  line: number | null;
  /** 该块顶部相对视口顶部的位置（px，通常为负 = 已经滚过它一点） */
  offset: number;
}

/** 纯解析（可单测）：存的东西可能是旧版或被手改过，一律当"没存过"处理。 */
export function parseNotesPos(raw: string | null): NotesViewPos | null {
  if (!raw) return null;
  try {
    const parsed = JSON.parse(raw) as Partial<NotesViewPos>;
    if (typeof parsed?.rel !== "string" || typeof parsed?.section !== "string") return null;
    return {
      ws: typeof parsed.ws === "string" ? parsed.ws : "",
      section: parsed.section,
      rel: parsed.rel,
      line: typeof parsed.line === "number" ? parsed.line : null,
      offset: typeof parsed.offset === "number" ? parsed.offset : 0,
    };
  } catch {
    return null;
  }
}

export function readNotesPos(ws: string): NotesViewPos | null {
  try {
    const pos = parseNotesPos(sessionStorage.getItem(POS_KEY));
    return pos && pos.ws === ws ? pos : null;
  } catch {
    // 隐私模式 / 配额满：位置记忆失效无妨（不影响阅读）
    return null;
  }
}

export function writeNotesPos(pos: NotesViewPos): void {
  try {
    sessionStorage.setItem(POS_KEY, JSON.stringify(pos));
  } catch {
    /* 同上 */
  }
}

/**
 * 记下"我现在读到哪"：取视口顶部所在的那个块。
 *
 * 全在视口上方时记**最后一个**（它正是覆盖视口顶部的那块）；一个可定位块都没有
 * 时记 `{line: null}`——那样至少还有"在哪篇"这件事，恢复时不动滚动条。
 */
export function captureNotesPos(ws: string, section: string, rel: string): NotesViewPos | null {
  let best: { line: number; offset: number } | null = null;
  for (const el of Array.from(document.querySelectorAll<HTMLElement>("[data-line]"))) {
    const line = Number(el.getAttribute("data-line"));
    if (!Number.isFinite(line)) continue;
    const top = el.getBoundingClientRect().top;
    best = { line, offset: top };
    if (top > 1) break; // 第一个还在视口下方（或正好贴顶）的块就是"视口顶部所在"
  }
  const pos: NotesViewPos = {
    ws,
    section,
    rel,
    line: best?.line ?? null,
    offset: best?.offset ?? 0,
  };
  writeNotesPos(pos);
  return pos;
}

/**
 * 回到记录的位置：**直接算目标 scrollY**，不用 `scrollIntoView`——后者会带上
 * scroll-margin（标题有 `scroll-mt-24`），落点与记录时的几何对不上。
 */
export function restoreNotesPos(pos: NotesViewPos): boolean {
  if (pos.line == null) return false;
  const el = document.querySelector<HTMLElement>(`[data-line="${pos.line}"]`);
  if (!el) return false;
  // 目标：让该块的 rect.top 回到 pos.offset —— rect.top = 文档内绝对位置 - scrollY
  const absoluteTop = el.getBoundingClientRect().top + window.scrollY;
  window.scrollTo({ top: absoluteTop - pos.offset });
  return true;
}

// --- 视图态：关键词 / 过滤词 / 定位行（切页签不丢）----------------------------
//
// 页签切换会**卸载**组件（Radix Tabs 不 forceMount），三个输入框都是组件内 state，
// 于是"去宣讲会看一眼再回来"就把搜索结果全清空了。

export interface NotesUiState {
  ws: string;
  /** 全文搜索关键词 */
  keyword: string;
  /** 目录树过滤词 */
  query: string;
  /** 搜索命中的行号（1-based） */
  focusLine: number | null;
}

export function readNotesUi(ws: string): NotesUiState {
  const empty: NotesUiState = { ws, keyword: "", query: "", focusLine: null };
  try {
    const raw = sessionStorage.getItem(UI_KEY);
    if (!raw) return empty;
    const parsed = JSON.parse(raw) as Partial<NotesUiState>;
    if (parsed?.ws !== ws) return empty;
    return {
      ws,
      keyword: typeof parsed.keyword === "string" ? parsed.keyword : "",
      query: typeof parsed.query === "string" ? parsed.query : "",
      focusLine: typeof parsed.focusLine === "number" ? parsed.focusLine : null,
    };
  } catch {
    return empty;
  }
}

export function writeNotesUi(state: NotesUiState): void {
  try {
    sessionStorage.setItem(UI_KEY, JSON.stringify(state));
  } catch {
    /* 存储不可用：回到"切走即清空"的旧行为，不值得为此报错 */
  }
}

// --- 待确认的勾选写回（切页签 / 刷新后仍在）------------------------------------
//
// 只存 **confirm** 这一态：previewing 的请求与 applying 的落盘都是组件内的 promise，
// 组件一卸载就作废；把它们恢复出来只会得到一个永远不落地的确认框（且整篇勾选框
// 被 locked 卡死）。令牌十分钟过期——过期了服务端会拒绝，错误横幅照常显示。

export interface NotesToggleSnapshot {
  ws: string;
  section: string;
  rel: string;
  lines: number[];
  token: string;
  summary: string;
  diff: string[];
}

export function readToggleSnapshot(ws: string): NotesToggleSnapshot | null {
  try {
    const raw = sessionStorage.getItem(FLOW_KEY);
    if (!raw) return null;
    const parsed = JSON.parse(raw) as Partial<NotesToggleSnapshot> & { line?: number };
    if (parsed?.ws !== ws) return null;
    if (typeof parsed.rel !== "string" || typeof parsed.section !== "string") return null;
    if (typeof parsed.token !== "string") return null;
    // 兼容：C-1 之前的快照是 `line` 单数字段——升级瞬间在途的那一个确认框要
    // 读得回来（读不回来的话用户会以为"刚点的确认丢了"）
    const lines = Array.isArray(parsed.lines)
      ? parsed.lines.filter((item): item is number => typeof item === "number" && item >= 1)
      : typeof parsed.line === "number" && parsed.line >= 1
        ? [parsed.line]
        : null;
    if (!lines || !lines.length) return null;
    return {
      ws,
      section: parsed.section,
      rel: parsed.rel,
      lines: [...lines].sort((a, b) => a - b),
      token: parsed.token,
      summary: typeof parsed.summary === "string" ? parsed.summary : "",
      diff: Array.isArray(parsed.diff) ? parsed.diff.map(String) : [],
    };
  } catch {
    return null;
  }
}

export function writeToggleSnapshot(snapshot: NotesToggleSnapshot): void {
  try {
    sessionStorage.setItem(FLOW_KEY, JSON.stringify(snapshot));
  } catch {
    /* 存不上就退回"刷新即丢"，不影响写通道 */
  }
}

export function clearToggleSnapshot(): void {
  try {
    sessionStorage.removeItem(FLOW_KEY);
  } catch {
    /* 同上 */
  }
}

// --- 批量待提交集合（C-1）----------------------------------------------------
//
// 为什么落 sessionStorage：App 级的外部改动检测（10s 指纹）会整页 reload，
// 切页签也会卸载组件——集合只放 useState 的话"勾到一半"会全丢（drill 轮次
// 的先例同因）。按「工作区 + 文件」分键：切文件是换键，各自记住各自的。

function pendingKey(ws: string, section: string, rel: string): string {
  // NUL 分隔：文件名里不可能出现（`::` 会被含 `:` 的路径串键——POSIX 下合法）；
  // 与 hook 里的 SEP 同源，两处要一起改
  return `${ws}\u0000${section}\u0000${rel}`;
}

function readPendingMap(): Record<string, number[]> {
  try {
    const raw = sessionStorage.getItem(PENDING_KEY);
    if (!raw) return {};
    const parsed = JSON.parse(raw) as Record<string, unknown>;
    const out: Record<string, number[]> = {};
    for (const [key, value] of Object.entries(parsed ?? {})) {
      if (Array.isArray(value)) {
        out[key] = value.filter(
          (item): item is number => typeof item === "number" && item >= 1
        );
      }
    }
    return out;
  } catch {
    return {};
  }
}

function writePendingMap(map: Record<string, number[]>): void {
  try {
    sessionStorage.setItem(PENDING_KEY, JSON.stringify(map));
  } catch {
    /* 存不上就退回"切走即丢"，不值得为此报错 */
  }
}

export function readPendingLines(ws: string, section: string, rel: string): number[] {
  return readPendingMap()[pendingKey(ws, section, rel)] ?? [];
}

export function writePendingLines(
  ws: string,
  section: string,
  rel: string,
  lines: number[]
): void {
  const map = readPendingMap();
  const key = pendingKey(ws, section, rel);
  if (lines.length) map[key] = [...lines].sort((a, b) => a - b);
  else delete map[key];
  writePendingMap(map);
}

export function clearPendingLines(ws: string, section: string, rel: string): void {
  const map = readPendingMap();
  delete map[pendingKey(ws, section, rel)];
  writePendingMap(map);
}

/** 点选是切换（再点一次移出集合）；结果始终升序——与差异表里的行号顺序一致。 */
export function togglePendingLine(lines: number[], line: number): number[] {
  return lines.includes(line)
    ? lines.filter((item) => item !== line)
    : [...lines, line].sort((a, b) => a - b);
}
