import { useTranslation } from "react-i18next";

/**
 * 凭据存放形态提示（#203）：后端 `storage` 字段如实报告「凭据保存在哪」——
 * credman = Windows 凭据管理器（桌面版默认，工作区配置文件只留引用），
 * plaintext = 工作区配置文件明文（源码 / CLI 形态的回退）。
 *
 * 旧响应缺该字段、或将来出现未知形态时都不渲染：宁可少一句话，
 * 也不要在界面上闪一坨对不上号的文案。plaintext 用警告语气（与
 * ErrorBanner 的 warning 同口径，带 role="status"），credman 是常态、
 * 只作次要说明。
 */
interface CredentialStorageNoticeProps {
  /** 后端响应里的 `storage`；非 "credman" / "plaintext"（含 undefined）时不渲染 */
  storage?: string;
  /** 是否**真的存过**凭据（`hasPassword` / `hasKey`）：没存过就别报"存在哪" */
  hasCredential?: boolean;
}

export default function CredentialStorageNotice({ storage, hasCredential }: CredentialStorageNoticeProps) {
  const { t } = useTranslation();

  // 从没保存过凭据时，后端照样报当前形态（默认桌面版是 credman）——照显会变成
  // "已存入凭据管理器"的假陈述，用户找不到对应的条目。没有凭据就没有"存哪"可说。
  if (!hasCredential) return null;

  if (storage === "credman") {
    return (
      <p className="text-[0.6875rem] leading-relaxed text-muted-foreground">
        {t("settings.credStorageCredman")}
      </p>
    );
  }

  if (storage === "plaintext") {
    return (
      <p
        role="status"
        className="rounded-lg border border-warning/30 bg-warning/10 px-3 py-2 text-[0.6875rem] leading-relaxed text-foreground"
      >
        {t("settings.credStoragePlaintext")}
      </p>
    );
  }

  return null;
}
