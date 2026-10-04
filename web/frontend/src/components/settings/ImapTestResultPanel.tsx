import { useTranslation } from "react-i18next";

import type { ImapTestResult } from "../../lib/domainTypes";

/**
 * 测试连接结果面板（2026-10-04 从 ImapCard 拆出，为守住 300 行水位）。
 *
 * 纯展示、无状态：连接成功后如实报告「连到哪台服务器、看的哪个文件夹、
 * 共几封」。行为、文案、条件渲染与拆分前一致——只在有结果时由调用方挂载。
 */
interface ImapTestResultPanelProps {
  result: ImapTestResult;
}

export default function ImapTestResultPanel({ result }: ImapTestResultPanelProps) {
  const { t } = useTranslation();

  return (
    <p className="rounded-lg border border-success/30 bg-success/10 px-3 py-2 text-xs text-muted-foreground">
      {t("settings.imapTestResult", {
        server: result.server,
        folder: result.folder,
        count: result.messageCount,
      })}
    </p>
  );
}
