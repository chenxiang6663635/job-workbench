import { useTranslation } from "react-i18next";
import { AlertTriangle, CheckCircle2, Info, X } from "lucide-react";
import { cn } from "../lib/utils";

/** 三种语气的样式与图标。成功态必须用对勾——此前固定用警告三角，语义反了。
    文字用前景色、**图标保状态色**（独立审查 MAJOR：状态色当正文色只有 3.2–4.0:1；
    图标是小图形元素，3:1 门限即可，且语义提示由它承担）。 */
const TONES = {
  error: {
    cls: "border-destructive/30 bg-destructive/10 text-foreground",
    iconCls: "text-destructive",
    Icon: AlertTriangle,
    role: "alert",
  },
  warning: {
    cls: "border-warning/30 bg-warning/10 text-foreground",
    iconCls: "text-warning",
    Icon: Info,
    role: "status",
  },
  success: {
    cls: "border-success/30 bg-success/10 text-foreground",
    iconCls: "text-success",
    Icon: CheckCircle2,
    role: "status",
  },
} as const;

/**
 * 统一错误/警示/成功提示条。此前五个页面各写一份（Jobs:345 / Library:97 /
 * Settings:103 / Resume:237 / ResumeTemplates:178,234），写法与色板都不一致
 * ——按 rule of three 收敛。
 */
export function ErrorBanner({
  message,
  onClose,
  onRetry,
  tone = "error",
  className,
}: {
  message: string;
  onClose?: () => void;
  /** UX-1：失败态附带「重试」——把自救入口收进提示条本身，调用方不再各摆一个按钮 */
  onRetry?: () => void;
  tone?: "error" | "warning" | "success";
  className?: string;
}) {
  const { t } = useTranslation();
  const { cls, iconCls, Icon, role } = TONES[tone];
  return (
    <div
      role={role}
      className={cn("flex items-start gap-2 rounded-lg border px-4 py-2 text-sm", cls, className)}
    >
      <Icon size={16} className={cn("mt-0.5 shrink-0", iconCls)} />
      <span className="flex-1 leading-relaxed">{message}</span>
      {onRetry && (
        <button
          type="button"
          onClick={onRetry}
          className="shrink-0 cursor-pointer self-center text-xs font-medium underline underline-offset-2 opacity-80 transition-opacity hover:opacity-100"
        >
          {t("common.retry")}
        </button>
      )}
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
