import { FolderOpen } from "lucide-react";
import { useTranslation } from "react-i18next";

import { Button } from "../ui/button";

/**
 * 可选文件夹候选（2026-09-24 从 ImapCard 拆出，为守住 300 行水位）。
 *
 * 候选来自一次**只读 `LIST`**：用户点「读取可用文件夹」才连，连完即登出（没有后台预取）。
 * 点一下填入输入框，但输入框本身仍可手填——有些服务器 `LIST` 不出来（权限或实现差异），
 * 不该因此把用户卡住。
 */
interface FolderCandidatesProps {
  folders: string[];
  loading: boolean;
  onLoad: () => void;
  onPick: (name: string) => void;
}

export default function FolderCandidates({
  folders,
  loading,
  onLoad,
  onPick,
}: FolderCandidatesProps) {
  const { t } = useTranslation();

  return (
    <div className="space-y-2">
      <div className="flex flex-wrap items-center gap-2">
        <Button
          variant="outline"
          className="h-8 px-3 text-xs"
          onClick={onLoad}
          disabled={loading}
        >
          <FolderOpen size={14} />
          {loading ? t("settings.imapFolderLoading") : t("settings.imapFolderLoad")}
        </Button>
        {folders.length > 0 && (
          <span className="text-[11px] text-muted-foreground">
            {t("settings.imapFolderCandidates")}
          </span>
        )}
      </div>
      {folders.length > 0 && (
        <div className="flex flex-wrap gap-1.5">
          {folders.map((name) => (
            <button
              key={name}
              type="button"
              className="rounded-full border border-border px-2.5 py-0.5 font-mono text-[11px] text-muted-foreground transition-colors hover:border-primary/40 hover:text-foreground"
              onClick={() => onPick(name)}
            >
              {name}
            </button>
          ))}
        </div>
      )}
    </div>
  );
}
