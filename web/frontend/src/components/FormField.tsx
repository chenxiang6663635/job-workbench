import { cloneElement, isValidElement, useId, type ReactElement, type ReactNode } from "react";
import { Label } from "./ui/label";

/**
 * 表单字段容器：Label + 控件。此前在四处各写一遍完全相同的三行结构
 * （ResumeForm 的 Row / InterviewForm / OfferForm / Settings 的内联 div），
 * 按 rule of three 收敛为一处，顺带统一 label 的排版（mb-1 + text-[11px]）。
 *
 * 把 id 注入控件并配 htmlFor：ResumeForm 原先用 `<label>` 包住 `<Textarea>`
 * 拿到的是隐式关联，改成分离结构后若不显式关联，点标签不再聚焦输入框、
 * 读屏也读不出标签——这类回归 build 与 CI 都抓不到（独立审查抓出的 MAJOR）。
 */
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
    ? cloneElement(children as ReactElement<{ id?: string }>, { id })
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
