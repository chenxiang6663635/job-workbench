import { useEffect, useState } from "react";
import { AlertTriangle } from "lucide-react";
import { useTranslation } from "react-i18next";

import { isGateOpen, isMismatch, requiresTyping, type DangerLevel } from "../lib/dangerGate";
import { Button } from "./ui/button";
import {
  Dialog,
  DialogContent,
  DialogDescription,
  DialogFooter,
  DialogHeader,
  DialogTitle,
} from "./ui/dialog";
import { Input } from "./ui/input";

/**
 * 确认强度三档：与「撤销窗口」二选一，绝不同时给两种。
 *
 * - `confirm`：对话框点名对象 + 按钮复用动词（不用"确定"）就够了（如删除自定义主题）
 * - `phrase`：会连带丢数据的，要求照打一句确认词（如还原备份、重置设置）
 * - `name`：最高危、影响面最大，要求输入对象名（如工作区名）
 */
export type { DangerLevel };

interface ConfirmDangerDialogProps {
  open: boolean;
  level: DangerLevel;
  /** 标题与说明都已翻译——容器文案由调用方传（本仓 i18n 纪律） */
  title: string;
  description: string;
  /** 主按钮动词（如「删除主题」「还原到此刻」）：必须是动词，不许写「确定」 */
  confirmLabel: string;
  /** `phrase` / `name` 档要求输入的内容；这两档必给 */
  challenge?: string;
  /** 输入框上方的说明（如「请输入工作区名以确认」） */
  challengeLabel?: string;
  busy?: boolean;
  onConfirm: () => void;
  onCancel: () => void;
}

export default function ConfirmDangerDialog({
  open,
  level,
  title,
  description,
  confirmLabel,
  challenge,
  challengeLabel,
  busy = false,
  onConfirm,
  onCancel,
}: ConfirmDangerDialogProps) {
  const { t } = useTranslation();
  const [typed, setTyped] = useState("");

  // 每次打开都从空白开始：上一次输过的确认词不该被继承（否则第二次点开形同无门禁）
  useEffect(() => {
    if (open) setTyped("");
  }, [open]);

  const needsTyping = requiresTyping(level);
  const matched = isGateOpen(level, challenge, typed);
  const mismatch = isMismatch(level, challenge, typed);

  return (
    <Dialog
      open={open}
      onOpenChange={(next) => {
        if (!next) onCancel();
      }}
    >
      <DialogContent className="max-w-md">
        <DialogHeader>
          <DialogTitle className="flex items-center gap-2">
            <AlertTriangle size={16} className="text-destructive" aria-hidden="true" />
            {title}
          </DialogTitle>
          <DialogDescription>{description}</DialogDescription>
        </DialogHeader>

        {needsTyping ? (
          <div className="space-y-2">
            <label
              htmlFor="danger-challenge"
              className="block text-xs text-muted-foreground"
            >
              {challengeLabel}
            </label>
            {/* 焦点会落在这里（需要打字才放行）——这一档刻意不给"默认聚焦取消" */}
            <Input
              id="danger-challenge"
              value={typed}
              autoComplete="off"
              spellCheck={false}
              placeholder={challenge}
              onChange={(event) => setTyped(event.target.value)}
            />
            <p
              className="min-h-[1rem] text-[11px] text-muted-foreground"
              aria-live="polite"
            >
              {mismatch ? t("danger.challengeMismatch") : ""}
            </p>
          </div>
        ) : null}

        <DialogFooter>
          <Button variant="outline" size="sm" onClick={onCancel}>
            {t("common.cancel")}
          </Button>
          <Button
            variant="destructive"
            size="sm"
            disabled={!matched || busy}
            onClick={onConfirm}
          >
            {confirmLabel}
          </Button>
        </DialogFooter>
      </DialogContent>
    </Dialog>
  );
}
