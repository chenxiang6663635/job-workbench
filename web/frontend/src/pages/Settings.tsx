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

  useEffect(() => {
    api.systemPaths().then(setPaths).catch(() => {});
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
        return api.systemPaths();
      })
      .then(setPaths)
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

  const inputCls =
    "w-full rounded-lg border border-white/10 bg-ink-950 px-3 py-2 text-sm text-slate-100 outline-none transition-colors placeholder:text-slate-600 focus:border-accent/60 focus:ring-1 focus:ring-accent/30";

  return (
    <div className="mx-auto max-w-2xl space-y-4">
      <div>
        <h2 className="text-lg font-semibold text-white">设置</h2>
        <p className="mt-1 text-xs text-slate-500">
          LLM Provider 配置（BYOK）。配置后可用于 JD 解析 / 评分等 AI 增强，判断由你或 AI 完成。
        </p>
      </div>

      {error && (
        <div className="rounded-xl border border-bad/30 bg-bad/10 px-4 py-2 text-sm text-bad">
          {error}
        </div>
      )}
      {info && (
        <div className="rounded-xl border border-good/30 bg-good/10 px-4 py-2 text-sm text-good">
          {info}
        </div>
      )}

      <div className="space-y-4 rounded-2xl border border-white/10 bg-ink-900/60 p-5">
        <div className="flex items-center gap-2 text-sm font-semibold text-slate-200">
          <KeyRound size={16} className="text-accent" /> Provider
        </div>

        <div className="space-y-3">
          <div>
            <label className="mb-1 block text-xs text-slate-400">
              Base URL（OpenAI 兼容，含 /v1，如 https://api.orcarouter.ai/v1）
            </label>
            <input
              className={inputCls}
              placeholder="https://api.xxx.ai/v1"
              value={baseUrl}
              onChange={(e) => setBaseUrl(e.target.value)}
            />
          </div>

          <div>
            <label className="mb-1 block text-xs text-slate-400">
              API Key（留空则保留已保存的 key）
            </label>
            <input
              className={`${inputCls} font-mono`}
              type="password"
              placeholder={cfg?.hasKey ? `已保存（${cfg.api_key}）` : "sk-..."}
              value={apiKey}
              onChange={(e) => setApiKey(e.target.value)}
            />
          </div>
        </div>

        <div className="flex flex-wrap items-center gap-2 border-t border-white/10 pt-4">
          <button
            onClick={save}
            disabled={saving}
            className="flex cursor-pointer items-center gap-1.5 rounded-lg bg-accent px-3 py-2 text-sm font-medium text-ink-950 transition-all hover:bg-accent-soft active:scale-95 disabled:cursor-not-allowed disabled:opacity-40"
          >
            <Save size={15} /> {saving ? "保存中..." : "保存配置"}
          </button>
          <button
            onClick={test}
            disabled={testing}
            className="flex cursor-pointer items-center gap-1.5 rounded-lg border border-white/10 px-3 py-2 text-sm text-slate-300 transition-colors hover:bg-white/5 disabled:cursor-not-allowed disabled:opacity-40"
          >
            <PlugZap size={15} /> {testing ? "测试中..." : "测试连接"}
          </button>
        </div>
      </div>

      <div className="space-y-4 rounded-2xl border border-white/10 bg-ink-900/60 p-5">
        <div className="flex items-center gap-2 text-sm font-semibold text-slate-200">
          <ShieldCheck size={16} className="text-good" /> 数据与隐私
        </div>

        <p className="text-xs leading-relaxed text-slate-400">
          全部数据只存在你这台机器，无遥测、无上传。文件就是数据库——
          你可以随时用编辑器直接打开，也可以整包导出后彻底离开本应用。
        </p>

        <div className="flex flex-wrap items-center gap-2">
          <a
            href={api.exportUrl()}
            onClick={() =>
              setBackupInfo("导出包含你的真实简历与个人信息，请妥善保管导出的 zip。")
            }
            className="flex cursor-pointer items-center gap-1.5 rounded-lg bg-accent px-3 py-2 text-sm font-medium text-ink-950 transition-all hover:bg-accent-soft active:scale-95"
          >
            <Download size={15} /> 导出整包 zip
          </a>
          <button
            onClick={backup}
            disabled={backing}
            className="flex cursor-pointer items-center gap-1.5 rounded-lg border border-white/10 px-3 py-2 text-sm text-slate-300 transition-colors hover:bg-white/5 disabled:cursor-not-allowed disabled:opacity-40"
          >
            <Archive size={15} /> {backing ? "备份中..." : "立即备份"}
          </button>
          <button
            onClick={() => api.openFolder("workspace").catch((e: Error) => setError(e.message))}
            className="flex cursor-pointer items-center gap-1.5 rounded-lg border border-white/10 px-3 py-2 text-sm text-slate-300 transition-colors hover:bg-white/5"
          >
            <FolderOpen size={15} /> 打开数据目录
          </button>
        </div>

        {backupInfo && (
          <p className="rounded-lg border border-white/10 bg-ink-950/60 px-3 py-2 text-xs text-slate-300">
            {backupInfo}
          </p>
        )}

        <div className="space-y-1 border-t border-white/10 pt-3 text-[11px] text-slate-500">
          <p>
            上次备份：{paths?.lastBackup ?? "从未备份"}
            {paths ? `（共 ${paths.snapshotCount} 份快照）` : ""}
          </p>
          <p className="break-all">快照位置：{paths?.snapshotDir ?? "—"}</p>
          <p className="break-all">工作区：{paths?.workspace ?? "—"}</p>
          <p className="pt-1 text-slate-600">
            快照刻意存放在工作区之外——与源数据同盘同目录的备份会被误删、被
            git、被同步工具一并波及。导出包含简历与个人信息，不含应用外的快照。
          </p>
        </div>
      </div>

      {testResult && (
        <div className="space-y-2 rounded-2xl border border-good/30 bg-good/10 p-5">
          <div className="flex items-center gap-2 text-sm font-semibold text-good">
            <PlugZap size={15} /> 连接成功（HTTP {testResult.status}）
          </div>
          <p className="text-xs text-slate-400">
            可用模型 {testResult.modelCount} 个
          </p>
          {testResult.models.length > 0 && (
            <div className="flex flex-wrap gap-1.5 pt-1">
              {testResult.models.map((m) => (
                <span
                  key={m}
                  className="rounded-md border border-white/10 bg-ink-950/60 px-2 py-0.5 text-[11px] font-mono text-slate-300"
                >
                  {m}
                </span>
              ))}
            </div>
          )}
        </div>
      )}
    </div>
  );
}
