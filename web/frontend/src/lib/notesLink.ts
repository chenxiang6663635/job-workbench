// 笔记正文里「相对路径 → 树内位置」的纯解析（一期：03_面试准备 / 04_知识库 两棵树）。
//
// 为什么单独成文件：notes.ts 已盯 300 行规模闸门（logic 型），解析器是独立职责，
// 拆在这里；与 notes.ts 的树/过滤/大纲逻辑单向依赖（只取常量与类型，不反向）。
//
// 解析规则（对齐 VS Code 的双基准约定）：
// - 默认以**当前文件所在目录**为基准归一化 `..` / `.`（手写与互链生成都是这种形态）；
// - 也接受直接以 section 目录名开头（`04_知识库/…`，工作区根基准）；已知歧义：
//   首段命中 section 名时**总是**按工作区根解析，不会退化为"当前目录下的同名子目录"
//   （概率极低；与 VS Code 的 `/` 前缀语义对齐，二期若遇到真实案例再收）；
// - 结果必须落在 NOTES_SECTIONS 的某一棵树内，扩展名判断由两个出口各自做：
//   `resolveNoteLink` 只认 `.md`，`resolveNoteImage` 只认位图白名单——否则返回
//   null，渲染侧据此保持降级（外链 / 越界 / 扩展名不符一律不进）。
// 这里只做纯字符串归一化；真正的读取仍由后端 prep 端点做三层防护（白名单 + realpath
// 二次确认），前端结果不以任何方式放宽服务端校验。

import { NOTES_SECTIONS, type NotesActive, type NotesSectionKey } from "./notes";

const SECTION_BY_DIR = new Map<string, NotesSectionKey>(
  NOTES_SECTIONS.map((s) => [s.dir as string, s.key])
);

/** 位图白名单：与 `web/backend/routers/prep.py` 的 `IMAGE_EXT` 同名同集——
 *  前端只决定「是否升级成 <img>」，真正的校验仍在服务端（三层防护）。
 *  刻意**不含 SVG**：它是可执行脚本载体。 */
export const IMAGE_EXTS = new Set([".png", ".jpg", ".jpeg", ".gif", ".webp", ".bmp"]);

/** 归一化 + 越界判定（链接与图片共用的**唯一**一份；不做扩展名判断）。 */
function resolveWithinNotes(
  src: string | undefined,
  current: NotesActive
): NotesActive | null {
  if (!src) return null;
  // 带 scheme（http: / mailto: / file: / C:）或协议相对（//）的一律不是树内路径
  if (/^[a-z][a-z0-9+.-]*:/i.test(src) || src.startsWith("//")) return null;
  // 跨文件锚点（`x.md#小节`）一期不支持：fragment 剥离后只打开文件本身
  // （二期可把 fragment 接到 NotesReader 的定位机制上）。
  const hash = src.indexOf("#");
  const raw = hash === -1 ? src : src.slice(0, hash);
  if (!raw) return null;
  let decoded: string;
  try {
    decoded = decodeURIComponent(raw);
  } catch {
    return null; // 非法百分号编码：按不可解析处理，不抛错
  }
  const segments = decoded
    .replace(/\\/g, "/")
    .split("/")
    .filter((seg) => seg !== "" && seg !== ".");
  const first = segments[0];
  const sectionDir = NOTES_SECTIONS.find((s) => s.key === current.section)?.dir;
  if (!sectionDir) return null;
  // 第一段就是某个 section 目录名 → 按工作区根解析；否则按当前文件目录解析
  const stack: string[] =
    first !== undefined && SECTION_BY_DIR.has(first)
      ? []
      : [sectionDir, ...current.rel.split("/").slice(0, -1)];
  for (const seg of segments) {
    if (seg === "..") {
      if (stack.length === 0) return null; // 已到工作区根，再上跳即越界
      stack.pop();
      continue;
    }
    stack.push(seg);
  }
  const section = stack.length >= 2 ? SECTION_BY_DIR.get(stack[0]) : undefined;
  if (!section) return null;
  return { section, rel: stack.slice(1).join("/") };
}

export function resolveNoteLink(
  href: string | undefined,
  current: NotesActive
): NotesActive | null {
  const hit = resolveWithinNotes(href, current);
  return hit && /\.md$/i.test(hit.rel) ? hit : null;
}

/** 正文里的相对图片 → 树内位置（可直出字节）；外链 / 越界 / 非白名单一律 null。 */
export function resolveNoteImage(
  src: string | undefined,
  current: NotesActive
): NotesActive | null {
  const hit = resolveWithinNotes(src, current);
  if (!hit) return null;
  const dot = hit.rel.lastIndexOf(".");
  return dot >= 0 && IMAGE_EXTS.has(hit.rel.slice(dot).toLowerCase()) ? hit : null;
}
