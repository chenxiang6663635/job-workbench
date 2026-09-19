import type { Components } from "react-markdown";
import ReactMarkdown from "react-markdown";
import remarkGfm from "remark-gfm";

import { cn } from "../lib/utils";

// 笔记正文的 Markdown 渲染（react-markdown + remark-gfm）。
//
// 三条纪律：
// 1. 样式全部走 token 类（check_ui_tokens 拦写死色）；裸文本样式只在本文件定义。
// 2. **不启用 rehype-raw**：md 里的 HTML 源（03 模板里的 `<!-- 填写说明 -->`）
//    默认不渲染——正好满足"注释忽略"，也是 XSS 面的收敛（不注入 HTML，只出元素树）。
// 3. 标题锚点 id 用 `node.position.start.line`（源码行号）——与 lib/notes.ts 的
//    extractOutline 同源，两处不会漂移。
//
// 注意：每个映射都要把 `node` 从 props 里解构掉（它是 remark 的 AST 节点，
// 展开给 DOM 会触发 React 未知属性告警）。

type NodeLike = { position?: { start?: { line?: number } } } | null | undefined;

const anchorId = (node: NodeLike) => {
  const line = node?.position?.start?.line;
  return typeof line === "number" ? `h-${line}` : undefined;
};

const components: Components = {
  h1: ({ node, ...props }) => (
    <h1 id={anchorId(node)} className="mb-2 mt-0 text-[21px] font-semibold tracking-tight" {...props} />
  ),
  h2: ({ node, ...props }) => (
    <h2
      id={anchorId(node)}
      className="mb-2.5 mt-8 border-t border-border pt-6 text-[16px] font-semibold first-of-type:border-t-0 first-of-type:pt-0"
      {...props}
    />
  ),
  h3: ({ node, ...props }) => (
    <h3 id={anchorId(node)} className="mb-1.5 mt-5 text-[15px] font-semibold" {...props} />
  ),
  p: ({ node, ...props }) => <p className="my-2.5" {...props} />,
  ul: ({ node, ...props }) => <ul className="my-2.5 list-disc pl-5" {...props} />,
  ol: ({ node, ...props }) => <ol className="my-2.5 list-decimal pl-5" {...props} />,
  li: ({ node, className, ...props }) => (
    <li
      className={cn("my-1", className?.includes("task-list-item") && "list-none", className)}
      {...props}
    />
  ),
  blockquote: ({ node, ...props }) => (
    <blockquote
      className="my-3 rounded-r-md border-l-2 border-primary/60 bg-secondary/40 py-1.5 pl-4 pr-3 text-muted-foreground"
      {...props}
    />
  ),
  pre: ({ node, ...props }) => (
    <pre
      className="my-3 overflow-auto rounded-md border border-border bg-background/80 p-4 font-mono text-xs leading-relaxed"
      {...props}
    />
  ),
  code: ({ node, className, children, ...props }) => {
    // 围栏代码块：带 language- 标注，或（无标注时）内容是整段含换行文本
    const block =
      (className ?? "").startsWith("language-") || String(children).includes("\n");
    if (block) {
      return (
        <code className={cn("font-mono text-xs", className)} {...props}>
          {children}
        </code>
      );
    }
    return (
      <code className="rounded bg-secondary px-1 py-0.5 font-mono text-[12.5px]" {...props}>
        {children}
      </code>
    );
  },
  table: ({ node, ...props }) => (
    <table className="my-3 w-full border-collapse text-[13.5px]" {...props} />
  ),
  th: ({ node, ...props }) => (
    <th className="border border-border bg-secondary px-2.5 py-1.5 text-left font-semibold" {...props} />
  ),
  td: ({ node, ...props }) => <td className="border border-border px-2.5 py-1.5" {...props} />,
  hr: ({ node, ...props }) => <hr className="my-6 border-t border-border" {...props} />,
  a: ({ node, href, children, ...props }) => {
    if (href?.startsWith("#")) {
      return (
        <a href={href} className="text-primary hover:underline" {...props}>
          {children}
        </a>
      );
    }
    if (/^https?:/i.test(href ?? "")) {
      return (
        <a href={href} target="_blank" rel="noreferrer" className="text-primary hover:underline" {...props}>
          {children}
        </a>
      );
    }
    // 相对链接（工作区内互链，如 ../04_知识库/）：SPA 里没有对应路由——
    // 显示为弱化的文本（点了不会 404，最保守的退化；将来做路由跳转时再升级）。
    return (
      <span className="text-muted-foreground underline decoration-dotted" title={href}>
        {children}
      </span>
    );
  },
  // GFM 勾选框：**只读展示**（写回是后续批次；本批不提供任何写路径）
  input: ({ node, checked, ...props }) => (
    <input
      type="checkbox"
      checked={checked}
      readOnly
      disabled
      className="mr-2 h-4 w-4 accent-primary align-middle"
      {...props}
    />
  ),
};

export default function NotesMarkdown({ content }: { content: string }) {
  return (
    <div className="text-[15px] leading-[1.85] text-foreground">
      <ReactMarkdown remarkPlugins={[remarkGfm]} components={components}>
        {content}
      </ReactMarkdown>
    </div>
  );
}
