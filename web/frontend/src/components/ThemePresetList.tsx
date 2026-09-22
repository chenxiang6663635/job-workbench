import { useState } from "react";
import { useTranslation } from "react-i18next";
import { Pencil, Trash2 } from "lucide-react";
import { Button } from "./ui/button";
import { Input } from "./ui/input";
import {
  Dialog,
  DialogContent,
  DialogDescription,
  DialogFooter,
  DialogHeader,
  DialogTitle,
} from "./ui/dialog";

// 已存自定义主题列表（2026-09-22 从 ThemeEditor 拆出，配合规模闸门：
// ThemeEditor 主体留给「调色 → 保存 / 导入导出」，列表与删除确认迁到此处）。
//
// UX-5（体检）：删除自定义主题不可逆，此前却是点一下即落盘——这里补一层轻量确认。
// 全仓刻意不用 window.confirm（太糙），也不新增依赖：复用既有 Radix Dialog。
// （全仓扫过：ResumeForm 的 Trash2 删的是未保存草稿的行，不落盘，无需缓冲；
// 其余落盘删除都已在批 D 的「预览 → 令牌」两段式流程里。）
interface ThemePresetListProps {
  items: { id: string; label: string }[];
  onRename: (id: string, draft: string, fallback: string) => void;
  onDelete: (id: string) => void;
}

export default function ThemePresetList({
  items,
  onRename,
  onDelete,
}: ThemePresetListProps) {
  const { t } = useTranslation();
  // 非空 = 该行处于行内编辑态
  const [renamingId, setRenamingId] = useState<string | null>(null);
  const [renameDraft, setRenameDraft] = useState("");
  const [deleteTarget, setDeleteTarget] = useState<{ id: string; label: string } | null>(
    null
  );

  if (items.length === 0) return null;

  return (
    <div className="space-y-1 border-t border-border pt-3">
      {items.map((theme) => (
        <div key={theme.id} className="flex items-center justify-between gap-2">
          {renamingId === theme.id ? (
            <>
              <Input
                value={renameDraft}
                onChange={(event) => setRenameDraft(event.target.value)}
                aria-label={t("settings.themeRename")}
                className="h-7 flex-1 text-xs"
              />
              <Button
                size="sm"
                className="h-7 shrink-0 px-2 text-[11px]"
                onClick={() => {
                  onRename(theme.id, renameDraft, theme.label);
                  setRenamingId(null);
                }}
              >
                {t("common.save")}
              </Button>
            </>
          ) : (
            <>
              <span className="truncate text-xs text-foreground">{theme.label}</span>
              <div className="flex shrink-0 items-center gap-2">
                <button
                  type="button"
                  onClick={() => {
                    setRenamingId(theme.id);
                    setRenameDraft(theme.label);
                  }}
                  className="flex cursor-pointer items-center gap-1 text-[11px] text-muted-foreground transition-colors duration-150 hover:text-primary"
                >
                  <Pencil size={11} aria-hidden="true" />
                  {t("settings.themeRename")}
                </button>
                <button
                  type="button"
                  onClick={() => setDeleteTarget({ id: theme.id, label: theme.label })}
                  className="flex cursor-pointer items-center gap-1 text-[11px] text-muted-foreground transition-colors duration-150 hover:text-destructive"
                >
                  <Trash2 size={11} aria-hidden="true" />
                  {t("settings.themeDelete")}
                </button>
              </div>
            </>
          )}
        </div>
      ))}

      <Dialog
        open={deleteTarget !== null}
        onOpenChange={(open) => {
          if (!open) setDeleteTarget(null);
        }}
      >
        <DialogContent className="max-w-sm">
          <DialogHeader>
            <DialogTitle>{t("settings.themeDeleteConfirmTitle")}</DialogTitle>
            <DialogDescription>
              {t("settings.themeDeleteConfirmDesc", { name: deleteTarget?.label ?? "" })}
            </DialogDescription>
          </DialogHeader>
          <DialogFooter>
            <Button variant="outline" size="sm" onClick={() => setDeleteTarget(null)}>
              {t("common.cancel")}
            </Button>
            <Button
              variant="destructive"
              size="sm"
              onClick={() => {
                if (deleteTarget) onDelete(deleteTarget.id);
                setDeleteTarget(null);
              }}
            >
              {t("settings.themeDelete")}
            </Button>
          </DialogFooter>
        </DialogContent>
      </Dialog>
    </div>
  );
}
