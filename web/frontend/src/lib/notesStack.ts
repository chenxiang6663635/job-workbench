// 笔记的**会话内返回栈**（2026-10-16，issue #274 三期）。
//
// 缺口是具体的：笔记互链（一期，lib/notesLink.ts）让正文里的 `.md` 可点，但跳转是
// **覆盖式**的——`onOpenNote` 直接切 active、不记来源；而应用是自建 hash 路由 +
// 页签（Electron 里没有浏览器式历史可退），于是"文档 → 文档 → 文档"这条全应用唯一
// 的深度导航路径没有回头路（其余 4 处"返回"都是状态级：关详情 / 清筛选回列表）。
//
// 为什么是 sessionStorage：这是"**这一个会话里我走过哪几篇**"，与 lib/notesView.ts
// 的阅读位置 / 视图态同族；跨会话的"上次打开哪一篇"仍走 localStorage 的
// `jobws_notes_last`，两件事不混。按工作区隔离——换工作区不该把别处的路径搬过来。
//
// 上限 50 步：栈只在会话内用，"退回第 50 步"已是无意义的目标，但没有上限会在长会话
// 里把 sessionStorage 慢慢写满。读侧一律当"没存过"处理脏值（与 notesView 同款：
// 手改过的存储不该让界面炸，也不该把越界路径喂给接口）。

import { NOTES_SECTIONS, type NotesActive, type NotesSectionKey } from "./notes";

const STACK_KEY = "jobws_notes_stack";

/** 栈深上限：超出丢最旧的一条（防会话内无限增长，见文件头） */
export const NOTES_STACK_LIMIT = 50;

interface StoredStack {
  ws: string;
  entries: NotesActive[];
}

const SECTION_KEYS = new Set<string>(NOTES_SECTIONS.map((s) => s.key));

/**
 * 单项校验：section 必须是已知的树，rel 必须是不越界的工作区相对路径。
 * 栈里的项只会来自我们自己的代码（树 / 互链解析 / 搜索命中），这道校验只为
 * 挡住手改过的存储——越界路径喂给 `prepContent` 会被后端拒绝、白弹一条错误横幅。
 */
function parseEntry(raw: unknown): NotesActive | null {
  if (!raw || typeof raw !== "object") return null;
  const { section, rel } = raw as Partial<NotesActive>;
  if (typeof section !== "string" || !SECTION_KEYS.has(section)) return null;
  if (typeof rel !== "string" || !rel) return null;
  if (rel.startsWith("/") || rel.includes("\\")) return null;
  if (rel.split("/").some((seg) => seg === "" || seg === "." || seg === "..")) return null;
  return { section: section as NotesSectionKey, rel };
}

/** 纯解析：脏值一律当"没存过"；单项坏了只丢那一项，好项照常读回来。 */
export function parseNotesStack(raw: string | null, ws: string): NotesActive[] {
  if (!raw) return [];
  try {
    const parsed = JSON.parse(raw) as Partial<StoredStack>;
    if (parsed?.ws !== ws) return [];
    if (!Array.isArray(parsed.entries)) return [];
    const out: NotesActive[] = [];
    for (const item of parsed.entries) {
      const entry = parseEntry(item);
      if (entry) out.push(entry);
    }
    return out;
  } catch {
    return [];
  }
}

export function readNotesStack(ws: string): NotesActive[] {
  try {
    return parseNotesStack(sessionStorage.getItem(STACK_KEY), ws);
  } catch {
    // 隐私模式 / 存储不可用：没有返回栈无妨（不影响阅读本身）
    return [];
  }
}

export function writeNotesStack(ws: string, entries: NotesActive[]): void {
  try {
    const stored: StoredStack = { ws, entries };
    sessionStorage.setItem(STACK_KEY, JSON.stringify(stored));
  } catch {
    /* 同上：存不上就退回"切页签即丢"，不值得为此报错 */
  }
}

/** 同一篇的判定只看 section + rel（显示名 / 大小都不参与） */
function sameNote(a: NotesActive, b: NotesActive): boolean {
  return a.section === b.section && a.rel === b.rel;
}

/**
 * 为落点 `next` 记一步来处时，**该记的是哪一篇**：就是当前这一篇；两种情形返回 null——
 * 还没有当前篇（首次挂载），或落点与当前同一篇（树里又点了一次已高亮的那一项、
 * 正文里指向自己的链接）：没有"上一篇"可退，不该凭空多出一步（返回会点一次无反应的）。
 */
export function rememberFrom(
  current: NotesActive | null,
  next: NotesActive
): NotesActive | null {
  if (!current || sameNote(current, next)) return null;
  return current;
}

/**
 * 入栈（纯函数）：追加一条，超上限丢最旧。
 *
 * 与栈顶同一篇时**不动**——这是"栈"这个结构自持的不变式（不出现连续重复项）。
 * 实际接线里几乎不会走到：入栈值恒为"离开前那一篇"，而 `rememberFrom` 已经保证落点 ≠
 * 当前篇，故相邻两次入栈必然不同（真正挡住"点同一条互链两次"的是 `rememberFrom`，
 * 不是这里，2026-10-16 独立审查 n1 订正措辞）。保留这层是因为不变式本身该被单测钉住。
 */
export function pushStack(entries: NotesActive[], entry: NotesActive): NotesActive[] {
  const top = entries[entries.length - 1];
  if (top && sameNote(top, entry)) return entries;
  const next = [...entries, entry];
  return next.length > NOTES_STACK_LIMIT ? next.slice(next.length - NOTES_STACK_LIMIT) : next;
}

/** 出栈（纯函数）：空栈给出 `previous: null`，调用方据此不渲染入口 / 不做跳转。 */
export function popStack(entries: NotesActive[]): {
  previous: NotesActive | null;
  rest: NotesActive[];
} {
  if (!entries.length) return { previous: null, rest: [] };
  return { previous: entries[entries.length - 1], rest: entries.slice(0, -1) };
}
