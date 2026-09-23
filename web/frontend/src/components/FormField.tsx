import {
  Children,
  cloneElement,
  isValidElement,
  useId,
  type ReactElement,
  type ReactNode,
} from "react";
import { Label } from "./ui/label";
import { Select, SelectTrigger } from "./ui/select";

/**
 * 表单字段容器：Label + 控件。此前在四处各写一遍完全相同的三行结构
 * （ResumeForm 的 Row / InterviewForm / OfferForm / Settings 的内联 div），
 * 按 rule of three 收敛为一处，顺带统一 label 的排版（mb-1 + text-[11px]）。
 *
 * `id` 必须真的落在**能聚焦的那个元素**上，配 `htmlFor` 才是有效关联：
 * - 原生控件：直接把 id 传给控件本身；
 * - Radix `Select`：`Select.Root` **不渲染 DOM**（只是 context 容器），把 id 给它等于
 *   丢掉——必须落到它内部的 `SelectTrigger` 上，否则点标签没反应、读屏读不出字段名
 *   （2026-09-23 二轮审计的发现：这条修复对 7 处下拉静默失效）；
 * - `ApplicationSelect` 这类自定义组件：由它自己接收并透传 id。
 */
function isSelectRoot(el: ReactElement<{ children?: ReactNode }>): boolean {
  return el.type === Select;
}

/** 把 id 注入到 Radix Select 的触发器上（根节点不渲染 DOM，注给它是无效的）。 */
function injectIntoTrigger(el: ReactElement<{ children?: ReactNode }>, id: string): ReactElement {
  const children = Children.map(el.props.children, (child) =>
    isValidElement(child) && child.type === SelectTrigger
      ? cloneElement(child as ReactElement<{ id?: string }>, { id })
      : child,
  );
  return cloneElement(el, { children });
}

export function FormField({
  label,
  hint,
  className,
  children,
}: {
  label: string;
  /** 控件下方的补充说明（可选） */
  hint?: string;
  className?: string;
  children: ReactNode;
}) {
  const id = useId();
  const control = isValidElement(children)
    ? isSelectRoot(children as ReactElement<{ children?: ReactNode }>)
      ? injectIntoTrigger(children as ReactElement<{ children?: ReactNode }>, id)
      : cloneElement(children as ReactElement<{ id?: string }>, { id })
    : children;

  return (
    <div className={className}>
      <Label htmlFor={id} className="mb-1 block text-[11px] text-muted-foreground">
        {label}
      </Label>
      {control}
      {hint && <p className="mt-1 text-[11px] leading-relaxed text-muted-foreground">{hint}</p>}
    </div>
  );
}
