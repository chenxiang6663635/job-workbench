import { AlertTriangle, X } from "lucide-react";
import { cn } from "../lib/utils";

/**
 * 统一错误/警示条。此前五个页面各写一份（Jobs:345 / Library:97 / Settings:103 /
 * Resume:237 / ResumeTemplates:178,234），写法与色板都不一致——按 rule of three 收敛。
 */
export function ErrorBanner({
  message,
  onClose,
  tone = "error",
  className,
}: {
  message: string;
  onClose?: () => void;
  tone?: "error" | "warning";
  className?: string;
}) {
  const isError = tone === "error";
  return (
    <div
      role={isError ? "alert" : "status"}
      className={cn(
        "flex items-start gap-2 rounded-lg border px-4 py-2 text-sm",
        isError
          ? "border-destructive/30 bg-destructive/10 text-destructive"
          : "border-warning/30 bg-warning/10 text-warning",
        className
      )}
    >
      <AlertTriangle size={16} className="mt-0.5 shrink-0" />
      <span className="flex-1 leading-relaxed">{message}</span>
      {onClose && (
        <button
          type="button"
          onClick={onClose}
          aria-label="关闭提示"
          className="cursor-pointer text-current opacity-70 transition-opacity hover:opacity-100"
        >
          <X size={14} />
        </button>
      )}
    </div>
  );
}
