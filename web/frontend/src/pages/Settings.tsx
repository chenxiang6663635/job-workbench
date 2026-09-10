import { useEffect, useState } from "react";
import {
  Archive,
  Download,
  FolderOpen,
  KeyRound,
  PlugZap,
  Save,
  ShieldCheck,
} from "lucide-react";
import {
  api,
  type ProviderConfig,
  type ProviderTestResult,
  type SystemPaths,
} from "../api";
import { Button } from "../components/ui/button";
import { Card, CardHeader, CardTitle } from "../components/ui/card";
import { Badge } from "../components/ui/badge";
import { Input } from "../components/ui/input";
import { Skeleton } from "../components/ui/skeleton";
import { ErrorBanner } from "../components/ErrorBanner";
import { FormField } from "../components/FormField";

export default function Settings() {
  const [cfg, setCfg] = useState<ProviderConfig | null>(null);
  const [baseUrl, setBaseUrl] = useState("");
  const [apiKey, setApiKey] = useState("");
  const [error, setError] = useState<string | null>(null);
  const [info, setInfo] = useState<string | null>(null);
  const [saving, setSaving] = useState(false);
  const [testing, setTesting] = useState(false);
  const [testResult, setTestResult] = useState<ProviderTestResult | null>(null);
  const [paths, setPaths] = useState<SystemPaths | null>(null);
  const [pathsError, setPathsError] = useState<string | null>(null);
  const [backing, setBacking] = useState(false);
  const [backupInfo, setBackupInfo] = useState<string | null>(null);

  const load = () => {
    api
      .getProvider()
      .then((r) => {
        setCfg(r);
        setBaseUrl(r.base_url);
      })
      .catch((e: Error) => setError(e.message));
  };

  useEffect(load, []);

  // 路径加载：成功要清掉上一次的错误，否则一次失败会永久盖住后来成功加载的数据
  const loadPaths = () =>
    api
      .systemPaths()
      .then((r) => {
        setPaths(r);
        setPathsError(null);
      })
      .catch((e: Error) => {
        console.error("读取系统路径失败", e);
        setPathsError(e.message);
      });

  useEffect(() => {
    // 之前是空 catch：失败后页面永远停在骨架上，且错误被静默吞掉（违反「禁静默吞错」）
    loadPaths();
  }, []);

  const backup = () => {
    setError(null);
    setBackupInfo(null);
    setBacking(true);
    api
      .backupWorkspace()
      .then((r) => {
        setBackupInfo(
          `已备份 ${r.files} 个文件（${(r.size / 1024).toFixed(0)} KB），保留 ${r.kept} 份、淘汰 ${r.removed} 份`
        );
        return loadPaths();
      })
      .catch((e: Error) => setError(e.message))
      .finally(() => setBacking(false));
  };

  const save = () => {
    setError(null);
    setInfo(null);
    setSaving(true);
    api
      .saveProvider({ base_url: baseUrl, api_key: apiKey })
      .then((r) => {
        setCfg(r);
        setApiKey("");
        setInfo("配置已保存");
      })
      .catch((e: Error) => setError(e.message))
      .finally(() => setSaving(false));
  };

  const test = () => {
    setError(null);
    setInfo(null);
    setTestResult(null);
    setTesting(true);
    api
      .testProvider()
      .then((r) => setTestResult(r))
      .catch((e: Error) => setError(e.message))
      .finally(() => setTesting(false));
  };

  return (
    <div className="mx-auto max-w-2xl space-y-4">
      <div>
        <h2 className="text-lg font-semibold text-foreground">设置</h2>
        <p className="mt-1 text-xs text-muted-foreground">
          LLM Provider 配置（BYOK）。配置后可用于 JD 解析 / 评分等 AI 增强，判断由你或 AI 完成。
        </p>
      </div>

      {error && <ErrorBanner message={error} onClose={() => setError(null)} />}
      {info && <ErrorBanner tone="success" message={info} onClose={() => setInfo(null)} />}

      <Card className="space-y-4 p-5">
        <CardHeader className="p-0">
          <CardTitle className="flex items-center gap-2 text-sm">
            <KeyRound size={16} className="text-primary" /> Provider
          </CardTitle>
        </CardHeader>

        <div className="space-y-3">
          <FormField label="Base URL（OpenAI 兼容，含 /v1，如 https://api.orcarouter.ai/v1）">
            <Input
              placeholder="https://api.xxx.ai/v1"
              value={baseUrl}
              onChange={(e) => setBaseUrl(e.target.value)}
            />
          </FormField>

          <FormField label="API Key（留空则保留已保存的 key）">
            <Input
              className="font-mono"
              type="password"
              placeholder={cfg?.hasKey ? `已保存（${cfg.api_key}）` : "sk-..."}
              value={apiKey}
              onChange={(e) => setApiKey(e.target.value)}
            />
          </FormField>
        </div>

        <div className="flex flex-wrap items-center gap-2 border-t border-border pt-4">
          <Button onClick={save} disabled={saving}>
            <Save size={15} /> {saving ? "保存中..." : "保存配置"}
          </Button>
          <Button variant="outline" onClick={test} disabled={testing}>
            <PlugZap size={15} /> {testing ? "测试中..." : "测试连接"}
          </Button>
        </div>
      </Card>

      <Card className="space-y-4 p-5">
        <CardHeader className="p-0">
          <CardTitle className="flex items-center gap-2 text-sm">
            <ShieldCheck size={16} className="text-success" /> 数据与隐私
          </CardTitle>
        </CardHeader>

        <p className="text-xs leading-relaxed text-muted-foreground">
          全部数据只存在你这台机器，无遥测、无上传。文件就是数据库——
          你可以随时用编辑器直接打开，也可以整包导出后彻底离开本应用。
        </p>

        <div className="flex flex-wrap items-center gap-2">
          <Button asChild>
            <a
              href={api.exportUrl()}
              onClick={() =>
                setBackupInfo("导出包含你的真实简历与个人信息，请妥善保管导出的 zip。")
              }
            >
              <Download size={15} /> 导出整包 zip
            </a>
          </Button>
          <Button variant="outline" onClick={backup} disabled={backing}>
            <Archive size={15} /> {backing ? "备份中..." : "立即备份"}
          </Button>
          <Button
            variant="outline"
            onClick={() => api.openFolder("workspace").catch((e: Error) => setError(e.message))}
          >
            <FolderOpen size={15} /> 打开数据目录
          </Button>
        </div>

        {backupInfo && (
          <p className="rounded-lg border border-border bg-background/60 px-3 py-2 text-xs text-muted-foreground">
            {backupInfo}
          </p>
        )}

        <div className="space-y-1 border-t border-border pt-3 text-[11px] text-muted-foreground">
          {/* 三态齐全：加载中骨架 / 读取失败可定位 / 就绪显示真实路径 */}
          {pathsError ? (
            <p className="text-destructive">路径信息读取失败：{pathsError}</p>
          ) : !paths ? (
            <Skeleton className="h-14 w-full" />
          ) : (
            <>
              <p>
                上次备份：{paths.lastBackup ?? "从未备份"}（共 {paths.snapshotCount} 份快照）
              </p>
              <p className="break-all">快照位置：{paths.snapshotDir}</p>
              <p className="break-all">工作区：{paths.workspace}</p>
            </>
          )}
          <p className="pt-1 text-muted-foreground/70">
            快照刻意存放在工作区之外——与源数据同盘同目录的备份会被误删、被
            git、被同步工具一并波及。导出包含简历与个人信息，不含应用外的快照。
          </p>
        </div>
      </Card>

      {testResult && (
        <Card className="space-y-2 border-success/30 bg-success/10 p-5">
          <div className="flex items-center gap-2 text-sm font-semibold text-success">
            <PlugZap size={15} /> 连接成功（HTTP {testResult.status}）
          </div>
          <p className="text-xs text-muted-foreground">
            可用模型 {testResult.modelCount} 个
          </p>
          {testResult.models.length > 0 && (
            <div className="flex flex-wrap gap-1.5 pt-1">
              {testResult.models.map((m) => (
                <Badge key={m} variant="outline" className="font-mono text-[11px]">
                  {m}
                </Badge>
              ))}
            </div>
          )}
        </Card>
      )}
    </div>
  );
}
