import { createContext, memo, useContext, useMemo, type InputHTMLAttributes } from "react";
import type { Components } from "react-markdown";
import ReactMarkdown from "react-markdown";
import { useTranslation } from "react-i18next";
import { ImageOff } from "lucide-react";
import remarkGfm from "remark-gfm";

import i18n from "../i18n";
import { cn } from "../lib/utils";

// 笔记正文的 Markdown 渲染（react-markdown + remark-gfm）。
//
// 纪律（只读批建立，2026-09-18 勾选写回批扩充）：
// 1. 样式全部走 token 类（check_ui_tokens 拦写死色）；裸文本样式只在本文件定义。
// 2. **不启用 rehype-raw**：md 里的 HTML 源（03 模板里的 `<!-- 填写说明 -->`）
//    默认不渲染——XSS 面收敛（不注入 HTML，只出元素树）；注释文本另由
//    lib/notes.ts 的 stripHtmlComments 在渲染前剥除（默认行为会输出它的文本）。
// 3. 标题锚点 id 与勾选框行号都用 `node.position.start.line`（源码行号）——
//    与 lib/notes.ts 的 extractOutline 同源（两侧都消费 strip 后的同一份文本），
//    不会漂移。
// 4. 每个映射都要把 `node` 从 props 里解构掉（它是 remark 的 AST 节点，
//    展开给 DOM 会触发 React 未知属性告警）；eslint 侧由 ignoreRestSiblings
//    放行「为剔除而解构」的写法。
// 5. 勾选框**可点击**（写回编排在 NotesBrowser：预览 → 确认 → apply → 重拉）：
//    GFM 的 input 由 hast 直接构造、**没有 position**，行号只能从包着它的
//    li（有 position）经 TaskLineContext 传下来——这是全链路里唯一的一跳。

type NodeLike = { position?: { start?: { line?: number } } } | null | undefined;

const anchorId = (node: NodeLike) => {
  const line = node?.position?.start?.line;
  return typeof line === "number" ? `h-${line}` : undefined;
};

// 块级元素的源码行号（与标题锚点同源）：搜索命中后据此定位到块、并给命中块
// 加视觉标记。挂在**块**上而不挂在单元格/行内元素上——那些的 position 指的不是
// "这一块从哪行开始"，挂上去会让定位指错地方。
const lineAttr = (node: NodeLike) => {
  const line = node?.position?.start?.line;
  return typeof line === "number" ? { "data-line": line } : {};
};

// 任务项行号（1-based 源码行）：li 写入、input 读取——同一次渲染、同一棵树。
const TaskLineContext = createContext<number | null>(null);

function TaskCheckbox({
  checked,
  onToggle,
  pendingLine,
  locked,
  ...props
}: {
  checked?: boolean;
  onToggle?: (line: number) => void;
  /** 正在预览的行号——该项呈 pending 禁用态 */
  pendingLine: number | null;
  /** 有写回流程在进行中：整篇勾选框都禁用（避免连点时"点 A 弹出 B 的确认框"） */
  locked?: boolean;
} & InputHTMLAttributes<HTMLInputElement>) {
  const { t } = useTranslation();
  const line = useContext(TaskLineContext);
  // 有回调且行号可定位才可点击；否则退回只读展示（缺任一条件都不写）。
  // aria-label 走 t()——它是 form 元素，axe 的 label 规则要求可访问名称
  // （disabled 也不例外），且文案要能翻译。
  const interactive = onToggle != null && line != null;
  const pending = interactive && pendingLine === line;
  return (
    <input
      type="checkbox"
      checked={checked}
      {...props}
      readOnly={!interactive}
      // 展开之后再写 disabled / onChange：GFM 生成的 props 里带 disabled:true，
      // 放前面会被它覆盖（那是只读批的形态，写回批要能点）。
      disabled={!interactive || pending || locked}
      onChange={interactive ? () => onToggle?.(line) : undefined}
      aria-label={t("notes.checkboxLabel")}
      className={cn(
        "mr-2 h-4 w-4 accent-primary align-middle",
        interactive && !pending && "cursor-pointer"
      )}
    />
  );
}

const baseComponents: Components = {
  h1: ({ node, ...props }) => (
    <h1
      id={anchorId(node)}
      {...lineAttr(node)}
      className="mb-2 mt-0 text-[21px] font-semibold tracking-tight"
      {...props}
    />
  ),
  h2: ({ node, ...props }) => (
    <h2
      id={anchorId(node)}
      {...lineAttr(node)}
      className="mb-2.5 mt-8 scroll-mt-24 border-t border-border pt-6 text-[16px] font-semibold first-of-type:border-t-0 first-of-type:pt-0"
      {...props}
    />
  ),
  h3: ({ node, ...props }) => (
    <h3
      id={anchorId(node)}
      {...lineAttr(node)}
      className="mb-1.5 mt-5 scroll-mt-24 text-[15px] font-semibold"
      {...props}
    />
  ),
  // h4–h6 也挂行号：命中落在小标题上时能定位到它本身，而不是退回到前一个块
  h4: ({ node, ...props }) => (
    <h4
      {...lineAttr(node)}
      className="mb-1.5 mt-4 scroll-mt-24 text-[14px] font-semibold"
      {...props}
    />
  ),
  h5: ({ node, ...props }) => (
    <h5
      {...lineAttr(node)}
      className="mb-1 mt-3.5 scroll-mt-24 text-[13.5px] font-semibold"
      {...props}
    />
  ),
  h6: ({ node, ...props }) => (
    <h6
      {...lineAttr(node)}
      className="mb-1 mt-3 scroll-mt-24 text-[13px] font-semibold text-muted-foreground"
      {...props}
    />
  ),
  p: ({ node, ...props }) => <p {...lineAttr(node)} className="my-2.5" {...props} />,
  // className 先解构再合并：remark-gfm 会给含任务项的列表挂 `contains-task-list`，
  // 展开顺序若在 className 之后会把它那一份整体顶掉——utility 类（缩进 / 标记）随之
  // 丢失，任务列表表现为没有左缩进（2026-09-20 独立审查发现，与 li 的 children 同源）。
  ul: ({ node, className, ...props }) => (
    <ul {...lineAttr(node)} className={cn("my-2.5 list-disc pl-5", className)} {...props} />
  ),
  ol: ({ node, className, ...props }) => (
    <ol {...lineAttr(node)} className={cn("my-2.5 list-decimal pl-5", className)} {...props} />
  ),
  li: ({ node, className, children, ...props }) => {
    if (className?.includes("task-list-item")) {
      const line = node?.position?.start?.line;
      return (
        <li {...lineAttr(node)} className={cn("my-1 list-none", className)} {...props}>
          <TaskLineContext.Provider value={typeof line === "number" ? line : null}>
            {children}
          </TaskLineContext.Provider>
        </li>
      );
    }
    // 普通列表项也要渲染 children——2026-09-20 修复：此前该分支漏渲染
    // children，导致所有非任务项（无序 / 有序）只剩标记符号、正文全部丢失。
    return (
      <li {...lineAttr(node)} className={cn("my-1", className)} {...props}>
        {children}
      </li>
    );
  },
  blockquote: ({ node, ...props }) => (
    <blockquote
      {...lineAttr(node)}
      className="my-3 rounded-r-md border-l-2 border-primary/60 bg-secondary/40 py-1.5 pl-4 pr-3 text-muted-foreground"
      {...props}
    />
  ),
  pre: ({ node, ...props }) => (
    <pre
      {...lineAttr(node)}
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
  // 表格只在 table 上挂行号：单元格（th/td）的 position 是单元格自身的位置，
  // 挂上去会让"定位到某一行"指到单元格而非表格起点。
  table: ({ node, ...props }) => (
    <table {...lineAttr(node)} className="my-3 w-full border-collapse text-[13.5px]" {...props} />
  ),
  th: ({ node, ...props }) => (
    <th className="border border-border bg-secondary px-2.5 py-1.5 text-left font-semibold" {...props} />
  ),
  td: ({ node, ...props }) => <td className="border border-border px-2.5 py-1.5" {...props} />,
  hr: ({ node, ...props }) => (
    <hr {...lineAttr(node)} className="my-6 border-t border-border" {...props} />
  ),
  a: ({ node, href, children, ...props }) => {
    if (href?.startsWith("#")) {
      // 站内锚点（手写目录链接 / GFM 脚注）：**必须 preventDefault**——
      // App 是 hash 路由，原生跳转会触发 hashchange、未知 hash 被判无效并
      // 直接踢回看板（独立审查 MINOR-3；大纲按钮已是同款处理）。
      const id = href.slice(1);
      return (
        <a
          href={href}
          onClick={(e) => {
            e.preventDefault();
            document.getElementById(id)?.scrollIntoView({ behavior: "smooth", block: "start" });
          }}
          className="text-primary hover:underline"
          {...props}
        >
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
  // 图片一律渲染成明确占位（2026-09-21 批次 C-4）：相对路径在 SPA 里必然 404、
  // 外链要联网（与本应用"本地优先"相抵）——统一兜底，不做"加载一半失败"
  // （比不加载更困惑）。真支持需新增笔记侧只读文件端点（复用 ro_files 的
  // realpath 二次确认写法）。这里用 i18n.t 而非 hook：baseComponents 是模块级常量
  // （与 lib/bank.ts 的错误本地化同款）。
  img: ({ node, src, alt, ...props }) => (
    <span
      className="my-1 inline-flex max-w-full items-center gap-1.5 rounded-md border border-dashed border-border px-2 py-1 align-middle text-[11px] text-muted-foreground"
      title={i18n.t("notes.imageSkippedHint")}
      {...props}
    >
      <ImageOff size={12} className="shrink-0" />
      <span className="shrink-0">{i18n.t("notes.imageSkipped")}</span>
      <span className="truncate font-mono" title={src}>
        {alt || src}
      </span>
    </span>
  ),
};

function NotesMarkdown({
  content,
  onToggleTask,
  pendingLine = null,
  locked = false,
}: {
  content: string;
  onToggleTask?: (line: number) => void;
  pendingLine?: number | null;
  locked?: boolean;
}) {
  const components = useMemo<Components>(
    () => ({
      ...baseComponents,
      input: ({ node, checked, ...props }) => (
        <TaskCheckbox
          checked={checked}
          onToggle={onToggleTask}
          pendingLine={pendingLine}
          locked={locked}
          {...props}
        />
      ),
    }),
    [onToggleTask, pendingLine, locked]
  );

  return (
    <div className="text-[15px] leading-[1.85] text-foreground">
      <ReactMarkdown remarkPlugins={[remarkGfm]} components={components}>
        {content}
      </ReactMarkdown>
    </div>
  );
}

// memo（A-3）：正文解析是整篇级别的开销，父组件因为**别的**状态重渲染时（例如
// 展开大纲、切换页签）不该把整篇再解析一遍。props 不变就跳过——`onToggleTask` 在
// 编排侧已经是 useCallback，pendingLine / locked 只在写回流程里变。
export default memo(NotesMarkdown);
