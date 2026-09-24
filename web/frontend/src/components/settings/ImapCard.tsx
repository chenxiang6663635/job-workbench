import { useEffect, useMemo, useState } from "react";
import { useTranslation } from "react-i18next";
import { Inbox, PlugZap, Save } from "lucide-react";

import { api, type ImapConfig, type ImapTestResult } from "../../api";
import { listMailFolders, listMailProviders } from "../../lib/mailSetupApi";
import {
  MANUAL_PROVIDER_ID,
  matchProvider,
  presetDraft,
  type MailProvider,
} from "../../lib/mailProviders";
import { cn } from "../../lib/utils";
import { Button } from "../ui/button";
import { Card, CardHeader, CardTitle } from "../ui/card";
import { Input } from "../ui/input";
import {
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from "../ui/select";
import { ErrorBanner } from "../ErrorBanner";
import { FormField } from "../FormField";
import FolderCandidates from "./FolderCandidates";
import MailAuthHint from "./MailAuthHint";

/**
 * 「邮箱只读拉取」卡（2026-09-24 从 pages/Settings.tsx 拆出，为守住水位）。
 * 三条承诺别弄丢：只读连接（`SELECT(readonly)` + `BODY.PEEK`）、凭证只存本机
 * `config/imap.json`、**没有后台轮询**（文件夹候选也是"点一次连一次"）。
 */
interface ImapCardProps {
  /** 设置页的搜索/分组过滤：隐藏时保留挂载（状态不丢） */
  hidden?: boolean;
}

export default function ImapCard({ hidden = false }: ImapCardProps) {
  const { t } = useTranslation();
  const [cfg, setCfg] = useState<ImapConfig | null>(null);
  const [providers, setProviders] = useState<MailProvider[]>([]);
  const [providerId, setProviderId] = useState<string>(MANUAL_PROVIDER_ID);
  const [host, setHost] = useState("");
  const [port, setPort] = useState("993");
  const [user, setUser] = useState("");
  const [password, setPassword] = useState("");
  const [folder, setFolder] = useState("INBOX");
  /** 用户手改过服务器/端口：改过就不再被预设覆写（判定在 lib/mailProviders） */
  const [dirty, setDirty] = useState(false);
  const [saving, setSaving] = useState(false);
  const [testing, setTesting] = useState(false);
  const [err, setErr] = useState<string | null>(null);
  const [message, setMessage] = useState<string | null>(null);
  const [testResult, setTestResult] = useState<ImapTestResult | null>(null);
  const [folders, setFolders] = useState<string[]>([]);
  const [foldersLoading, setFoldersLoading] = useState(false);

  const selected = useMemo(
    () => providers.find((item) => item.id === providerId) ?? null,
    [providers, providerId]
  );
  const recognised = useMemo(() => matchProvider(user, providers), [user, providers]);
  const providerName = (item: MailProvider) => t(item.labelKey);

  useEffect(() => {
    api
      .getImap()
      .then((r) => {
        setCfg(r);
        setHost(r.host);
        setPort(String(r.port));
        setUser(r.user);
        setFolder(r.folder || "INBOX");
      })
      .catch((e: Error) => setErr(e.message));
    // 预设清单拉不到只是少一个下拉（还能手填），不该打断整张卡：日志留痕、界面静默
    listMailProviders()
      .then(setProviders)
      .catch((e: Error) => console.error("listMailProviders failed", e));
  }, []);

  /** 选服务商 → 带出服务器/端口（用户改过就不动他的输入）。 */
  const chooseProvider = (value: string) => {
    setProviderId(value);
    const provider = providers.find((item) => item.id === value) ?? null;
    if (!provider) return; // 「其它（手工填写）」：什么都不动
    const next = presetDraft(provider, { host, port }, dirty);
    setHost(next.host);
    setPort(next.port);
    setDirty(false); // 这次是自动带出，之后再选可以继续覆写
  };

  /** 显式点「套用」：用户明确要求，所以强制覆写。 */
  const applyRecognised = () => {
    if (!recognised) return;
    const next = presetDraft(recognised, { host, port }, false);
    setHost(next.host);
    setPort(next.port);
    setProviderId(recognised.id);
    setDirty(false);
  };

  const loadFolders = () => {
    setFoldersLoading(true);
    listMailFolders()
      .then((r) => setFolders(r.folders))
      .catch((e: Error) => setErr(e.message))
      .finally(() => setFoldersLoading(false));
  };

  const save = () => {
    setErr(null);
    setMessage(null);
    if (!user.trim()) {
      setErr(t("settings.imapEmailRequired"));
      return;
    }
    const portNumber = Number(port);
    if (!Number.isInteger(portNumber) || portNumber < 1 || portNumber > 65535) {
      setErr(t("settings.imapPortRange"));
      return;
    }
    setSaving(true);
    api
      .saveImap({ host, port: portNumber, user, password, folder })
      .then((r) => {
        setCfg(r);
        setPassword("");
        setMessage(t("settings.imapSaved"));
      })
      .catch((e: Error) => setErr(e.message))
      .finally(() => setSaving(false));
  };

  const test = () => {
    setErr(null);
    setMessage(null);
    setTestResult(null);
    setTesting(true);
    api
      .testImap()
      .then((r) => {
        setTestResult(r);
        loadFolders(); // 连上了才谈得上候选；这一下仍由用户点击触发
      })
      .catch((e: Error) => setErr(e.message))
      .finally(() => setTesting(false));
  };

  return (
    <Card className={cn("space-y-4 p-5", hidden && "hidden")}>
      <CardHeader className="p-0">
        <CardTitle className="flex items-center gap-2 text-sm">
          <Inbox size={16} className="text-primary" /> {t("settings.imapTitle")}
        </CardTitle>
      </CardHeader>

      <p className="text-xs leading-relaxed text-muted-foreground">
        {t("settings.imapDesc1")}
        {t("settings.imapDesc2")}
        {/* 句号与它后面的空格都在 key 里：写死在 JSX 里会同时出现两个问题——
            英文界面里冒出中文句号，且句末少一个空格（冒烟时抓到） */}
        <span className="text-foreground">{t("settings.imapDesc3")}</span>
        {t("settings.imapDesc4")}
      </p>

      <FormField label={t("settings.imapProvider")}>
        <Select value={providerId} onValueChange={chooseProvider}>
          <SelectTrigger aria-label={t("settings.imapProvider")}>
            <SelectValue />
          </SelectTrigger>
          <SelectContent>
            {providers.map((item) => (
              <SelectItem key={item.id} value={item.id}>
                {providerName(item)}
                <span className="ml-2 text-[11px] text-muted-foreground">{item.host}</span>
              </SelectItem>
            ))}
            <SelectItem value={MANUAL_PROVIDER_ID}>
              {t("settings.imapProviderManual")}
            </SelectItem>
          </SelectContent>
        </Select>
      </FormField>

      {/* 就地引导：文案按服务商换，连不上的直接说原因；key 用 id 以便换服务商即重展开 */}
      {selected && (
        <MailAuthHint
          key={selected.id}
          provider={selected}
          messageKey={
            selected.unsupported && selected.unsupportedReasonKey
              ? selected.unsupportedReasonKey
              : selected.authHintKey
          }
        />
      )}

      <div className="grid grid-cols-1 gap-3 sm:grid-cols-2">
        <FormField label={t("settings.imapEmail")}>
          <div className="space-y-1">
            <Input
              placeholder="your-email@example.com"
              value={user}
              onChange={(e) => setUser(e.target.value)}
            />
            {recognised && recognised.id !== providerId && (
              <button
                type="button"
                className="text-[11px] text-primary underline-offset-2 hover:underline"
                onClick={applyRecognised}
              >
                {t("settings.imapProviderAuto", { name: providerName(recognised) })}
                {" · "}
                {t("settings.imapProviderApply")}
              </button>
            )}
          </div>
        </FormField>
        <FormField label={t("settings.imapPassword")}>
          <Input
            className="font-mono"
            type="password"
            placeholder={
              cfg?.hasPassword
                ? t("settings.imapPasswordSaved", { key: cfg.password })
                : t("settings.imapPasswordHint")
            }
            value={password}
            onChange={(e) => setPassword(e.target.value)}
          />
        </FormField>
        <FormField label={t("settings.imapHost")}>
          <Input
            className="font-mono"
            placeholder={cfg?.serverHint || "imap.example.com"}
            value={host}
            onChange={(e) => {
              setHost(e.target.value);
              setDirty(true);
            }}
          />
        </FormField>
        <FormField label={t("settings.imapPort")}>
          <Input
            type="number"
            value={port}
            onChange={(e) => {
              setPort(e.target.value);
              setDirty(true);
            }}
          />
        </FormField>
        <FormField label={t("settings.imapFolder")}>
          <Input
            className="font-mono"
            placeholder="INBOX"
            value={folder}
            onChange={(e) => setFolder(e.target.value)}
          />
        </FormField>
      </div>

      <FolderCandidates
        folders={folders}
        loading={foldersLoading}
        onLoad={loadFolders}
        onPick={setFolder}
      />

      <div className="flex flex-wrap items-center gap-2 border-t border-border pt-4">
        <Button onClick={save} disabled={saving}>
          <Save size={15} /> {saving ? t("common.saving") : t("common.save")}
        </Button>
        <Button
          variant="outline"
          onClick={test}
          disabled={testing}
          aria-label={t("settings.imapTestAction")}
        >
          <PlugZap size={15} /> {testing ? t("settings.testing") : t("settings.test")}
        </Button>
        {message && <span className="text-xs text-success">{message}</span>}
      </div>

      {err && <ErrorBanner message={err} onClose={() => setErr(null)} />}

      {testResult && (
        <p className="rounded-lg border border-success/30 bg-success/10 px-3 py-2 text-xs text-muted-foreground">
          {t("settings.imapTestResult", {
            server: testResult.server,
            folder: testResult.folder,
            count: testResult.messageCount,
          })}
        </p>
      )}
    </Card>
  );
}
