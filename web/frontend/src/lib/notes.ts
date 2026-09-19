// 笔记（03_面试准备 / 04_知识库）的纯逻辑：平铺列表 → 树、过滤、大纲提取。
//
// 为什么单独成文件而不是写在组件里：这些是纯函数（数组/字符串进、结构出），
// 正好落在 vitest 的 node 环境单测里；组件只负责渲染与交互（与 lib/domainLabels.ts、
// lib/fonts.ts 同款分层）。
//
// 排序口径：服务端已按 rel 字典序返回（唯一真源），这里只做展示所需的重组——
// README 置顶、目录先于文件、组内按名称比较（确定性，不依赖输入顺序的巧合）。

import type { PrepFile } from "../api";

// 两个 section 的真实目录名（工作区约定，不翻译；与后端 deps.DIR_PREP / DIR_KB 同源）
export const NOTES_SECTIONS = [
  { key: "interview", dir: "03_面试准备" },
  { key: "knowledge", dir: "04_知识库" },
] as const;

export type NotesSectionKey = (typeof NOTES_SECTIONS)[number]["key"];

// 文件角色：README 是目录说明、_模板_/_示例_ 是脚手架，其余是用户正文。
// 前缀约定来自工作区 README（"_模板_ 开头是待复制样板；_示例_ 是只读参考数据"）。
export type NotesFileKind = "readme" | "template" | "example" | "doc";

export interface NotesNode {
  name: string; // 显示名：文件已去 .md 后缀；目录为目录名
  rel: string; // 文件为完整 rel；目录为 rel 前缀
  kind: "dir" | "file";
  fileKind?: NotesFileKind;
  size?: number;
  children?: NotesNode[];
}

export function classifyNotesFile(name: string): NotesFileKind {
  if (name.toLowerCase() === "readme.md") return "readme";
  if (name.startsWith("_模板_")) return "template";
  if (name.startsWith("_示例_")) return "example";
  return "doc";
}

// 展示排序：README 置顶 > 目录 > 普通文件；组内按名称比较（稳定、确定性）
const rank = (node: NotesNode) =>
  node.kind === "file" && node.fileKind === "readme" ? 0 : node.kind === "dir" ? 1 : 2;

function sortNodes(nodes: NotesNode[]): void {
  nodes.sort(
    (a, b) => rank(a) - rank(b) || (a.name < b.name ? -1 : a.name > b.name ? 1 : 0)
  );
  for (const node of nodes) {
    if (node.children) sortNodes(node.children);
  }
}

/** 平铺 rel 列表 → 分组树。空目录天然不出现（树从文件构建）；0 字节文件照常保留。 */
export function buildNotesTree(
  groups: { key: NotesSectionKey; items: PrepFile[] }[]
): Record<NotesSectionKey, NotesNode[]> {
  const out = {} as Record<NotesSectionKey, NotesNode[]>;
  for (const group of groups) {
    const roots: NotesNode[] = [];
    const dirs = new Map<string, NotesNode>();
    for (const item of group.items) {
      const parts = item.rel.split("/");
      const fileName = parts.pop() ?? item.rel;
      let siblings = roots;
      let prefix = "";
      for (const part of parts) {
        prefix = prefix ? `${prefix}/${part}` : part;
        let node = dirs.get(prefix);
        if (!node) {
          node = { name: part, rel: prefix, kind: "dir", children: [] };
          dirs.set(prefix, node);
          siblings.push(node);
        }
        siblings = node.children ?? [];
      }
      siblings.push({
        name: fileName.replace(/\.md$/i, ""),
        rel: item.rel,
        kind: "file",
        fileKind: classifyNotesFile(fileName),
        size: item.size,
      });
    }
    sortNodes(roots);
    out[group.key] = roots;
  }
  return out;
}

/** 按名称/路径过滤（大小写不敏感）；目录只要有命中子项就保留，无命中的组消失。 */
export function filterNotes(nodes: NotesNode[], query: string): NotesNode[] {
  const q = query.trim().toLowerCase();
  if (!q) return nodes;
  const walk = (list: NotesNode[]): NotesNode[] => {
    const out: NotesNode[] = [];
    for (const node of list) {
      if (node.kind === "dir") {
        const kids = walk(node.children ?? []);
        if (kids.length > 0) out.push({ ...node, children: kids });
      } else if (
        node.name.toLowerCase().includes(q) ||
        node.rel.toLowerCase().includes(q)
      ) {
        out.push(node);
      }
    }
    return out;
  };
  return walk(nodes);
}

export interface NotesOutlineItem {
  level: 2 | 3;
  text: string;
  id: string; // `h-<源码行号>`：与渲染侧（heading 的 node.position.start.line）同源
}

/**
 * 提取 h2/h3 大纲。**跳过围栏代码块**（代码块里的 `# 注释` 不是标题）；
 * id 用源码行号（1-based）而不是文本 slug——渲染侧用同一种行号，两处天然一致，
 * 不会出现"锚点对不上"的文本归一化分歧（CRLF 也算一行）。
 */
export function extractOutline(markdown: string): NotesOutlineItem[] {
  const lines = markdown.split(/\r?\n/);
  const out: NotesOutlineItem[] = [];
  let fence: string | null = null;
  lines.forEach((line, index) => {
    const open = line.match(/^\s{0,3}(`{3,}|~{3,})/);
    if (open) {
      const marker = open[1][0];
      if (fence === null) fence = marker;
      else if (fence === marker) fence = null;
      return;
    }
    if (fence !== null) return;
    const heading = line.match(/^(#{2,3})\s+(.+?)\s*$/);
    if (heading) {
      out.push({
        level: heading[1].length as 2 | 3,
        text: heading[2].replace(/\s*#+\s*$/, ""),
        id: `h-${index + 1}`,
      });
    }
  });
  return out;
}

/**
 * 去掉 md 里的 HTML 注释（`<!-- … -->`，含跨行与行内）。
 *
 * 03 的模板里注释是写给用户的**填写说明**（"勾选这个故事能回答的维度…"），
 * 阅读视图不该看见它；react-markdown 不启用 rehype-raw 时注释会以文本形式
 * 渲染出来（2026-09-18 实机截图确认），所以要在渲染前剥掉。
 *
 * **行数必须保持不变**（注释按空串留在原行）：大纲锚点用源码行号
 * （`h-<line>`），删行会让渲染侧（react-markdown 的 position.start.line）与
 * extractOutline 的行号对不上。围栏代码块内的注释不动——那是示例内容。
 */
export function stripHtmlComments(markdown: string): string {
  let inFence: string | null = null;
  let inComment = false;
  const out: string[] = [];
  for (const line of markdown.split(/\r?\n/)) {
    const fence = line.match(/^\s{0,3}(`{3,}|~{3,})/);
    if (fence) {
      const marker = fence[1][0];
      if (inFence === null) inFence = marker;
      else if (inFence === marker) inFence = null;
      out.push(line);
      continue;
    }
    if (inFence !== null) {
      out.push(line);
      continue;
    }
    let rest = line;
    let cleaned = "";
    while (rest !== "") {
      if (inComment) {
        const end = rest.indexOf("-->");
        if (end === -1) {
          rest = "";
          break;
        }
        rest = rest.slice(end + 3);
        inComment = false;
      } else {
        const start = rest.indexOf("<!--");
        if (start === -1) {
          cleaned += rest;
          rest = "";
          break;
        }
        cleaned += rest.slice(0, start);
        rest = rest.slice(start + 4);
        inComment = true;
      }
    }
    out.push(cleaned);
  }
  // 换行统一为 \n：CRLF 与 LF 混排时行号仍按逻辑行计，两侧消费方一致
  return out.join("\n");
}
