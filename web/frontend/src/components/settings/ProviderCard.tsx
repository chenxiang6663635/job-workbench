import { useEffect, useState } from "react";
import { useTranslation } from "react-i18next";
import { ExternalLink, KeyRound, PlugZap, Save } from "lucide-react";

import { PROVIDER_REFERRAL } from "../../lib/partner";
import {
  getProviderSettings,
  saveProvider,
  testProvider,
  type ProviderModels,
  type ProviderSettings,
} from "../../lib/providerApi";
import {
  PROVIDER_PRESETS,
  normalizeBaseUrl,
  presetIdForBaseUrl,
  validateBaseUrl,
} from "../../lib/providerPresets";
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

/**
 * 「模型服务（BYOK）」卡（2026-09-24 从 pages/Settings.tsx 拆出）。
 *
 * 拆出来是因为 `Settings.tsx` 登记过水位（只许变小），而本笔要给这张卡加
 * 「服务商预设 / 默认模型 / 模型可点选」三样东西。
 *
 * 一条纪律：**测试连接失败不阻塞保存**（Open WebUI 的经验：很多网关没实现
 * `/models`，但 chat 照样能用）。所以这里是"取清单 + 给人话"，不是"能不能用"的判据。
 */
interface ProviderCardProps {
  /** 设置页的搜索/分组过滤：隐藏时保留挂载（状态不丢） */
  hidden?: boolean;
}

export default function ProviderCard({ hidden = false }: ProviderCardProps) {
  const { t } = useTranslation();
  const [settings, setSettings] = useState<ProviderSettings | null>(null);
  const [presetId, setPresetId] = useState("custom");
  const [baseUrl, setBaseUrl] = useState("");
  const [apiKey, setApiKey] = useState("");
  const [model, setModel] = useState("");
  const [saving, setSaving] = useState(false);
  const [testing, setTesting] = useState(false);
  const [err, setErr] = useState<string | null>(null);
  const [info, setInfo] = useState<string | null>(null);
  const [models, setModels] = useState<ProviderModels | null>(null);

  // 推广入口先摊平成三个非空值：TS 在回调闭包里不做窄化，逐个判空只会更吵
  const refName = PROVIDER_REFERRAL?.name ?? "";
  const refUrl = PROVIDER_REFERRAL?.url ?? "";
  const refPreset = PROVIDER_REFERRAL?.presetBaseUrl ?? "";

  useEffect(() => {
    getProviderSettings()
      .then((r) => {
        setSettings(r);
        setBaseUrl(r.base_url);
        setModel(r.model);
        setPresetId(presetIdForBaseUrl(r.base_url));
      })
      .catch((e: Error) => setErr(e.message));
  }, []);

  // 本地即时提示优先（用户正在打字），其次才是后端对已保存值算出的提示
  const hintKey = validateBaseUrl(baseUrl) ?? settings?.baseUrlHint ?? null;

  const choosePreset = (value: string) => {
    setPresetId(value);
    const preset = PROVIDER_PRESETS.find((item) => item.id === value);
    if (!preset || !preset.baseUrl) return; // 「自定义」不动字段
    setBaseUrl(preset.baseUrl);
  };

  const save = () => {
    setErr(null);
    setInfo(null);
    setSaving(true);
    saveProvider({
      base_url: normalizeBaseUrl(baseUrl),
      api_key: apiKey,
      model: model.trim(),
    })
      .then((r) => {
        setSettings(r);
        setBaseUrl(r.base_url);
        setPresetId(presetIdForBaseUrl(r.base_url));
        setApiKey("");
      })
      .catch((e: Error) => setErr(e.message))
      .finally(() => setSaving(false));
  };

  const test = () => {
    setErr(null);
    setInfo(null);
    setModels(null);
    setTesting(true);
    testProvider()
      .then((r) => setModels(r))
      .catch((e: Error) => setErr(e.message))
      .finally(() => setTesting(false));
  };

  const shownPreset = PROVIDER_PRESETS.find((item) => item.id === presetId) ?? null;

  return (
    <Card className={cn("space-y-4 p-5", hidden && "hidden")}>
      <CardHeader className="p-0">
        <CardTitle className="flex items-center gap-2 text-sm">
          <KeyRound size={16} className="text-primary" /> {t("settings.providerTitle")}
        </CardTitle>
      </CardHeader>

      <FormField label={t("settings.providerPreset")}>
        <Select value={presetId} onValueChange={choosePreset}>
          <SelectTrigger aria-label={t("settings.providerPreset")}>
            <SelectValue />
          </SelectTrigger>
          <SelectContent>
            {PROVIDER_PRESETS.map((preset) => (
              <SelectItem key={preset.id} value={preset.id}>
                {t(preset.labelKey)}
              </SelectItem>
            ))}
          </SelectContent>
        </Select>
        {shownPreset?.noteKey && (
          <p className="text-[11px] leading-relaxed text-muted-foreground">
            {t(shownPreset.noteKey)}
          </p>
        )}
      </FormField>

      <div className="space-y-3">
        <FormField label={t("settings.baseUrl")}>
          <Input
            placeholder="https://api.xxx.ai/v1"
            value={baseUrl}
            onChange={(e) => setBaseUrl(e.target.value)}
          />
          {hintKey && (
            <p className="text-[11px] leading-relaxed text-muted-foreground">{t(hintKey)}</p>
          )}
        </FormField>

        <FormField label={t("settings.apiKey")}>
          <Input
            className="font-mono"
            type="password"
            placeholder={
              settings?.hasKey
                ? t("settings.apiKeySaved", { key: settings.api_key })
                : t("settings.apiKeyPlaceholder")
            }
            value={apiKey}
            onChange={(e) => setApiKey(e.target.value)}
          />
        </FormField>

        {/* 默认模型：三处使用点（导入 / 改写 / 邮件 AI）共用，仍可就地临时改 */}
        <FormField label={t("settings.providerModel")}>
          <Input
            className="font-mono"
            placeholder="deepseek-chat"
            value={model}
            onChange={(e) => setModel(e.target.value)}
          />
          {!model.trim() && (
            <p className="text-[11px] leading-relaxed text-muted-foreground">
              {t("settings.providerModelHint")}
            </p>
          )}
        </FormField>
      </div>

      {models && (
        <div className="space-y-2 rounded-lg border border-border bg-background/40 p-3">
          {/* 连上了才看得到这一块：status 与总数是"这次到底连上了什么"的凭据 */}
          <div className="flex flex-wrap items-center gap-2 text-xs font-semibold text-success">
            <PlugZap size={14} /> {t("settings.testOk", { status: models.status })}
            <span className="font-normal text-muted-foreground">
              {t("settings.modelCount", { count: models.modelCount })}
            </span>
          </div>
          {models.models.length > 0 ? (
            <>
              <div className="flex flex-wrap items-center justify-between gap-2">
                <span className="text-[11px] text-muted-foreground">
                  {t("settings.providerModelsTitle")}
                </span>
                {models.truncated && (
                  <span className="text-[11px] text-muted-foreground">
                    {t("settings.providerModelsTruncated", {
                      shown: models.models.length,
                      total: models.modelCount,
                    })}
                  </span>
                )}
              </div>
              <div className="flex flex-wrap gap-1.5">
                {models.models.map((name) => (
                  <button
                    key={name}
                    type="button"
                    className="rounded-full border border-border px-2.5 py-0.5 font-mono text-[11px] text-muted-foreground transition-colors hover:border-primary/40 hover:text-foreground"
                    onClick={() => setModel(name)}
                  >
                    {name}
                  </button>
                ))}
              </div>
            </>
          ) : (
            <p className="text-[11px] leading-relaxed text-muted-foreground">
              {t("settings.providerModelsEmpty")}
            </p>
          )}
        </div>
      )}

      {/* 推广入口：放在「正好要填 key」的位置，且必须写明它是推广链接。
          藏在一个像官网链接的按钮后面就是欺骗，与本项目的诚实红线冲突。 */}
      {/* 只在「还没存过 key」时出现：已经配好的人不需要这个入口，
          顺带也免掉 cfg 加载完成前的闪一下（cfg 为 null 时不渲染）。 */}
      {settings && !settings.hasKey && refUrl && (
        <div className="space-y-1.5 rounded-lg border border-border bg-background/40 p-3">
          <div className="flex flex-wrap items-center justify-between gap-2">
            <span className="text-xs text-muted-foreground">{t("settings.referralNoKey")}</span>
            <div className="flex flex-wrap items-center gap-2">
              {/* 端点一键填入：合作方的 Base URL 是固定的 OpenAI 兼容地址，
                  手抄容易错，且错了只会在「测试连接」时才暴露 */}
              {refPreset && refPreset !== baseUrl && (
                <Button
                  variant="ghost"
                  className="h-7 px-2.5 text-xs"
                  onClick={() => {
                    setBaseUrl(refPreset);
                    setPresetId(presetIdForBaseUrl(refPreset));
                    setInfo(t("settings.referralFilled", { name: refName }));
                  }}
                >
                  {t("settings.referralFill", { name: refName })}
                </Button>
              )}
              <Button asChild variant="outline" className="h-7 px-2.5 text-xs">
                <a href={refUrl} target="_blank" rel="noopener noreferrer">
                  <ExternalLink size={12} /> {t("settings.referralSignup", { name: refName })}
                </a>
              </Button>
            </div>
          </div>
          <p className="text-[11px] leading-relaxed text-muted-foreground">
            {t("settings.referralDisclosure")}
            {t("settings.referralNoData")}
          </p>
        </div>
      )}

      <div className="flex flex-wrap items-center gap-2 border-t border-border pt-4">
        <Button onClick={save} disabled={saving}>
          <Save size={15} /> {saving ? t("common.saving") : t("settings.save")}
        </Button>
        <Button
          variant="outline"
          onClick={test}
          disabled={testing}
          aria-label={t("settings.providerTestAction")}
        >
          <PlugZap size={15} /> {testing ? t("settings.testing") : t("settings.test")}
        </Button>
        {info && <span className="text-xs text-success">{info}</span>}
      </div>

      {err && <ErrorBanner message={err} onClose={() => setErr(null)} />}
    </Card>
  );
}
