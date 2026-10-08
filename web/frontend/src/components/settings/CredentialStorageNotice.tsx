import { useState } from "react";
import { useTranslation } from "react-i18next";
import { Trash2 } from "lucide-react";

import type { TranslationKey } from "../../i18n/locales/zh-CN";

/**
 * 凭据存放形态提示（#203）：后端 `storage` 字段如实报告「凭据保存在哪」——
 * credman = Windows 凭据管理器（桌面版默认，工作区配置文件只留引用），
 * plaintext = 工作区配置文件明文（源码 / CLI 形态的回退）。
 *
 * 「清除即删」入口（#203 遗留，2026-10-07）：传入 onClear 时，在「真的存过凭据」
 * 的前提下就近提供两段式清除（点击 → 就地确认 → 调接口）。清除会同时删除系统
 * 存储里的条目——确认行必须把「之后要重新输入」说出来，而不是一个孤零零的
 * 危险按钮。成功由调用方刷新卡片并给出结果文案；失败也走卡片既有的错误条
 * （本组件不为错误再长一套展示）。
 *
 * 旧响应缺 storage、或将来出现未知形态时都不渲染：宁可少一句话，
 * 也不要在界面上闪一坨对不上号的文案。plaintext 用警告语气（与
 * ErrorBanner 的 warning 同口径，带 role="status"），credman 是常态、
 * 只作次要说明。
 */
interface CredentialStorageNoticeProps {
  /** 后端响应里的 `storage`；非 "credman" / "plaintext"（含 undefined）时不渲染 */
  storage?: string;
  /** 是否**真的存过**凭据（`hasPassword` / `hasKey`）：没存过就别报"存在哪" */
  hasCredential?: boolean;
  /** 提供清除入口（调用方接各自的 DELETE 端点、刷新卡片；成败都由调用方展示） */
  onClear?: () => Promise<void>;
  /** 文案变体：设置页两张卡（邮箱 / 模型服务）共用本组件 */
  surface?: "imap" | "provider";
}

export default function CredentialStorageNotice({
  storage,
  hasCredential,
  onClear,
  surface = "imap",
}: CredentialStorageNoticeProps) {
  const { t } = useTranslation();
  const [confirming, setConfirming] = useState(false);
  const [busy, setBusy] = useState(false);

  // 从没保存过凭据时，后端照样报当前形态（默认桌面版是 credman）——照显会变成
  // "已存入凭据管理器"的假陈述，用户找不到对应的条目。没有凭据就没有"存哪"可说。
  if (!hasCredential) return null;

  const notice =
    storage === "credman" ? (
      <p className="text-[0.6875rem] leading-relaxed text-muted-foreground">
        {t("settings.credStorageCredman")}
      </p>
    ) : storage === "plaintext" ? (
      <p
        role="status"
        className="rounded-lg border border-warning/30 bg-warning/10 px-3 py-2 text-[0.6875rem] leading-relaxed text-foreground"
      >
        {t("settings.credStoragePlaintext")}
      </p>
    ) : null;

  if (!notice) return null;

  const buttonKey: TranslationKey =
    surface === "imap" ? "settings.imapCredClear" : "settings.providerCredClear";

  const runClear = async () => {
    setBusy(true);
    try {
      await onClear?.();
    } finally {
      // 成败都收起确认态：失败由调用方经卡片错误条展示，入口仍在（可重试）。
      setBusy(false);
      setConfirming(false);
    }
  };

  return (
    <div className="space-y-1.5">
      {notice}
      {onClear &&
        (confirming ? (
          <div className="flex flex-wrap items-center gap-2 text-[0.6875rem]" role="status">
            <span className="text-muted-foreground">{t("settings.credClearConfirm")}</span>
            <button
              type="button"
              disabled={busy}
              onClick={() => void runClear()}
              className="cursor-pointer font-medium text-primary underline-offset-2 hover:underline disabled:cursor-default disabled:opacity-60"
            >
              {t("settings.credClearAction")}
            </button>
            <button
              type="button"
              onClick={() => setConfirming(false)}
              className="cursor-pointer text-muted-foreground hover:underline"
            >
              {t("common.cancel")}
            </button>
          </div>
        ) : (
          <button
            type="button"
            onClick={() => setConfirming(true)}
            className="flex cursor-pointer items-center gap-1 text-[0.6875rem] text-muted-foreground transition-colors hover:text-primary"
          >
            <Trash2 size={12} /> {t(buttonKey)}
          </button>
        ))}
    </div>
  );
}
