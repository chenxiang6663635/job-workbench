import { useTranslation } from "react-i18next";
import { AlertTriangle, CheckCircle2, Info, X } from "lucide-react";
import { cn } from "../lib/utils";

/** 三种语气的样式与图标。成功态必须用对勾——此前固定用警告三角，语义反了 */
const TONES = {
  error: { cls: "border-destructive/30 bg-destructive/10 text-destructive", Icon: AlertTriangle, role: "alert" },
  warning: { cls: "border-warning/30 bg-warning/10 text-warning", Icon: Info, role: "status" },
  success: { cls: "border-success/30 bg-success/10 text-success", Icon: CheckCircle2, role: "status" },
} as const;

/**
 * 统一错误/警示/成功提示条。此前五个页面各写一份（Jobs:345 / Library:97 /
 * Settings:103 / Resume:237 / ResumeTemplates:178,234），写法与色板都不一致
 * ——按 rule of three 收敛。
 */
export function ErrorBanner({
  message,
  onClose,
  tone = "error",
  className,
}: {
  message: string;
  onClose?: () => void;
  tone?: "error" | "warning" | "success";
  className?: string;
}) {
  const { t } = useTranslation();
  const { cls, Icon, role } = TONES[tone];
  return (
    <div
      role={role}
      className={cn("flex items-start gap-2 rounded-lg border px-4 py-2 text-sm", cls, className)}
    >
      <Icon size={16} className="mt-0.5 shrink-0" />
      <span className="flex-1 leading-relaxed">{message}</span>
      {onClose && (
        <button
          type="button"
          onClick={onClose}
          aria-label={t("common.close")}
          className="cursor-pointer text-current opacity-70 transition-opacity hover:opacity-100"
        >
          <X size={14} />
        </button>
      )}
    </div>
  );
}
