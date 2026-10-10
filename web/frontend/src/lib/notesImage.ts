// 笔记内嵌图片的**只读字节** URL（与后端 prep `/{section}/file` 配对）。
//
// 与 `api.resumeTemplateFileUrl` 同款：工作区名挂在查询串上（当前工作区从
// lib/http 的活绑定取，不在模块加载时固化——切换工作区走整页 reload，取到的
// 一定是当次的值）。前端只负责拼 URL；归属与扩展名校验在服务端做。
import { currentWorkspace } from "./http";
import type { NotesSectionKey } from "./notes";
import { resolveNoteImage } from "./notesLink";

export function noteImageUrl(section: NotesSectionKey, rel: string): string {
  const base = `/api/prep/${section}/file?rel=${encodeURIComponent(rel)}`;
  return currentWorkspace ? `${base}&ws=${encodeURIComponent(currentWorkspace)}` : base;
}

/** 组装「正文 src → 可直出 URL」的解析器；无当前文件（rel 为空）时返回 undefined
 *  （渲染侧据此整块不升级）。返回函数身份必须稳定——会被 NotesMarkdown 的
 *  components memo 收进依赖，每次新身份都会让它重建。 */
export function makeNoteImageResolver(section: NotesSectionKey, rel: string | null) {
  if (!rel) return undefined;
  return (src: string): string | null => {
    const hit = resolveNoteImage(src, { section, rel });
    return hit ? noteImageUrl(hit.section, hit.rel) : null;
  };
}
