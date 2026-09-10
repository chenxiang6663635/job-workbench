import type { ReactNode } from "react";
import { Label } from "./ui/label";

/**
 * 表单字段容器：Label + 控件。此前在四处各写一遍完全相同的三行结构
 * （ResumeForm 的 Row / InterviewForm / OfferForm / Settings 的内联 div），
 * 按 rule of three 收敛为一处，顺带统一 label 的排版（mb-1 + text-[11px]）。
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
  return (
    <div className={className}>
      <Label className="mb-1 block text-[11px] text-muted-foreground">{label}</Label>
      {children}
      {hint && <p className="mt-1 text-[11px] leading-relaxed text-muted-foreground">{hint}</p>}
    </div>
  );
}
