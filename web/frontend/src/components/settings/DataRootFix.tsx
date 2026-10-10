import { useState } from "react";
import { useTranslation } from "react-i18next";
import { Check, Eraser } from "lucide-react";

import { clearDataRoot, setDataRoot } from "../../lib/dataRootApi";
import { Button } from "../ui/button";
import { Input } from "../ui/input";

/**
 * 失效 / 歧义态下的「重选 / 清除数据根」入口（A2 文案承诺的落点）。
 *
 * 数据不是坏在迁移上，而是**当前选择本身不可用**（路径被删 / 不可写 / 遗留多份
 * 候选）——这时迁移流程起点就没有源根，必须先修选择。两条动作与后端三态一一
 * 对应：POST 记住一个绝对路径、DELETE 清除已保存的选择（回到默认位置）。
 * 成功后就地给结果并请上层刷新系统路径（`onReload`）；失败进跨卡错误通道。
 */
interface DataRootFixProps {
  onError: (message: string) => void;
  onReload?: () => void;
}

export default function DataRootFix({ onError, onReload }: DataRootFixProps) {
  const { t } = useTranslation();
  const [path, setPath] = useState("");
  const [busy, setBusy] = useState(false);
  const [done, setDone] = useState<string | null>(null);

  const run = (action: () => Promise<{ path: string }>) => {
    setBusy(true);
    setDone(null);
    action()
      .then((diag) => {
        setDone(t("settings.dataRootFixDone", { path: diag.path }));
        setPath("");
        onReload?.();
      })
      .catch((e: Error) => onError(e.message))
      .finally(() => setBusy(false));
  };

  return (
    <div className="space-y-2 rounded-md border border-dashed border-border p-3">
      <p className="text-[0.6875rem] leading-relaxed text-muted-foreground">
        {t("settings.dataRootFixHint")}
      </p>
      <div className="flex flex-wrap items-center gap-2">
        <Input
          value={path}
          onChange={(e) => setPath(e.target.value)}
          placeholder={t("settings.dataRootFixPlaceholder")}
          aria-label={t("settings.dataRootFixHint")}
          className="h-8 w-64 font-mono text-xs"
        />
        <Button
          variant="outline"
          size="sm"
          disabled={busy || !path.trim()}
          onClick={() => run(() => setDataRoot(path.trim()))}
        >
          <Check size={14} /> {t("settings.dataRootFixApply")}
        </Button>
        <Button
          variant="ghost"
          size="sm"
          disabled={busy}
          onClick={() => run(clearDataRoot)}
        >
          <Eraser size={14} /> {t("settings.dataRootFixClear")}
        </Button>
      </div>
      {done && (
        <p className="break-all text-[0.6875rem] text-muted-foreground">{done}</p>
      )}
    </div>
  );
}
