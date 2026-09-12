import { FileCode2, FileImage, FileText } from "lucide-react";
import { cn } from "../lib/utils";
import { fmtSize } from "../lib/format";

/** 文件类型图标。此前 Library.tsx:10-21 与 ResumeTemplates.tsx:22-33 各写一份 */
export function FileIcon({ kind, name }: { kind?: string; name?: string }) {
  if (kind === "text") return <FileCode2 size={16} className="text-primary" />;
  const ext = name?.split(".").pop()?.toLowerCase();
  if (ext === "pdf") return <FileText size={16} className="text-destructive" />;
  return <FileImage size={16} className="text-warning" />;
}

/**
 * 文件卡。素材库与简历模板页的卡片此前是各自一整块 <button>，
 * 图标/大小格式化重复两份——收敛为公共组件。
 */
export function FileCard({
  name,
  kind,
  size,
  meta,
  badge,
  onClick,
  className,
}: {
  /** 展示名（短名） */
  name: string;
  kind?: string;
  size?: number;
  /** 无 size 时的替代信息 */
  meta?: string;
  /** 右侧尾标（如「预览」） */
  badge?: React.ReactNode;
  onClick: () => void;
  className?: string;
}) {
  return (
    <button
      type="button"
      onClick={onClick}
      title={name}
      className={cn(
        "group flex cursor-pointer items-center gap-3 rounded-lg border border-border bg-card-gradient p-4 text-left shadow-card ring-1 ring-white/5 transition-all duration-200 ease-premium hover:-translate-y-0.5 hover:border-primary/40 hover:shadow-lg hover:shadow-primary/10",
        className
      )}
    >
      <FileIcon kind={kind} name={name} />
      <span className="min-w-0 flex-1">
        <span className="block truncate text-sm text-foreground">{name}</span>
        <span className="mt-0.5 block text-xs text-muted-foreground">
          {size !== undefined ? fmtSize(size) : meta}
        </span>
      </span>
      {badge}
    </button>
  );
}
