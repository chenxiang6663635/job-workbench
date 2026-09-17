import { useEffect, useMemo, useState } from "react";
import { useTranslation } from "react-i18next";
import { Check, Copy, Download, Pencil, Trash2, Upload } from "lucide-react";
import { Button } from "./ui/button";
import { Input } from "./ui/input";
import { cn } from "../lib/utils";
import {
  THEME_VAR_KEYS,
  applyTheme,
  exportThemeVars,
  exportThemeVarsAsCss,
  getCustomThemes,
  getThemeChoice,
  injectCustomCss,
  parseThemeImport,
  removeCustomTheme,
  renameCustomTheme,
  saveCustomTheme,
} from "../lib/theme";
import { contrastRatio, hexToTriple, tripleToHex, wcagLevel } from "../lib/contrast";

// 主题编辑器 MVP（批 4）：
// - 起点 = **当前生效主题**的全部 45 个变量（getComputedStyle 读），只暴露 10 个关键色；
//   其余 35 键原样继承——「微调」比「从零造」符合真实需求，也避免用户掉进完整变量表。
// - 实时预览：编辑即注入临时 <style>（不写存储）；对比度提示与 check_themes 同口径。
// - 保存后进入主题列表（自定义主题与内置主题共用同一应用路径）。
// - 2026-09-17 收尾批：导出补「复制 CSS」（与导入的 CSS 分支成往返闭环）、
//   已存主题支持重命名（只改显示名，不切主题、不动变量）。

interface Editable {
  key: string;
  labelKey: string;
  /** 对比度检查的基准面（多数色对 background，主要文字对 card） */
  against: "background" | "card";
  large?: boolean;
}

const EDITABLE: Editable[] = [
  { key: "background", labelKey: "settings.themeColorBg", against: "background" },
  { key: "foreground", labelKey: "settings.themeColorFg", against: "background" },
  { key: "card", labelKey: "settings.themeColorCard", against: "background" },
  { key: "primary", labelKey: "settings.themeColorPrimary", against: "background" },
  { key: "secondary", labelKey: "settings.themeColorSecondary", against: "background" },
  { key: "muted", labelKey: "settings.themeColorMuted", against: "background" },
  { key: "border", labelKey: "settings.themeColorBorder", against: "background" },
  { key: "success", labelKey: "settings.themeColorSuccess", against: "background", large: true },
  { key: "warning", labelKey: "settings.themeColorWarning", against: "background", large: true },
  { key: "destructive", labelKey: "settings.themeColorDanger", against: "background" },
];

function readCurrentVars(): Record<string, string> {
  const styles = getComputedStyle(document.documentElement);
  const vars: Record<string, string> = {};
  for (const key of THEME_VAR_KEYS) {
    const value = styles.getPropertyValue(`--${key}`).trim();
    if (value) vars[key] = value;
  }
  return vars;
}

interface ThemeEditorProps {
  /** 保存/删除后通知外层刷新主题列表（ThemePicker 的网格要立刻出现新主题）。 */
  onSaved?: () => void;
}

export default function ThemeEditor({ onSaved }: ThemeEditorProps) {
  const { t } = useTranslation();
  const [vars, setVars] = useState<Record<string, string>>({});
  const [name, setName] = useState("");
  const [importText, setImportText] = useState("");
  const [note, setNote] = useState<string | null>(null);
  const [applied, setApplied] = useState(false);
  const [previewOn, setPreviewOn] = useState(true);
  // 重命名（2026-09-17）：非空 = 该行处于行内编辑态
  const [renamingId, setRenamingId] = useState<string | null>(null);
  const [renameDraft, setRenameDraft] = useState("");

  useEffect(() => {
    setVars(readCurrentVars());
  }, []);

  // 编辑预览：注入临时主题并应用；卸载时把根属性**还原为已存选择**——
  // 只清 style 块会让 data-theme 停在预览 id 上（已无规则命中），全站回落默认
  // 暗而设置页仍勾着原主题（独立审查 MAJOR）。保存后关掉预览（previewOn），
  // 让属性跟随「刚保存的主题」而不是预览 id。
  useEffect(() => {
    if (!previewOn || !Object.keys(vars).length) return;
    injectCustomCss([{ id: "jobws-preview", label: "preview", vars }]);
    document.documentElement.setAttribute("data-theme", "jobws-preview");
    return () => {
      injectCustomCss(); // 清掉临时块（保留存储里的自定义主题）
      applyTheme(getThemeChoice()); // 还原为已存选择
    };
  }, [vars, previewOn]);

  const currentVars = useMemo(() => readCurrentVars(), []);
  const customThemes = getCustomThemes();

  const setColor = (key: string, hex: string) => {
    const triple = hexToTriple(hex);
    if (!triple) return;
    setVars((prev) => ({ ...prev, [key]: triple }));
    setApplied(false);
  };

  const onSave = () => {
    const label = name.trim() || t("settings.themeUntitled");
    const id = `custom-${Date.now()}`;
    saveCustomTheme({ id, label, vars });
    setNote(t("settings.themeSaved"));
    setApplied(true);
    setPreviewOn(false); // 属性跟随刚保存的主题，不再被预览 effect 拉回预览 id
    setVars(readCurrentVars());
    onSaved?.();
  };

  const onExport = async () => {
    const text = exportThemeVars(vars);
    try {
      await navigator.clipboard.writeText(text);
      setNote(t("settings.themeCopied"));
    } catch {
      setImportText(text);
      setNote(t("settings.themeCopyFailed"));
    }
  };

  // 导出 CSS（2026-09-17）：`--key: value;` 逐行——与下方导入的 CSS 分支闭环
  const onExportCss = async () => {
    const text = exportThemeVarsAsCss(vars);
    try {
      await navigator.clipboard.writeText(text);
      setNote(t("settings.themeCopied"));
    } catch {
      setImportText(text);
      setNote(t("settings.themeCopyFailed"));
    }
  };

  const onImport = () => {
    const parsed = parseThemeImport(importText);
    if (!parsed) {
      setNote(t("settings.themeImportFailed"));
      return;
    }
    setVars((prev) => ({ ...prev, ...parsed }));
    setNote(t("settings.themeImported"));
  };

  const onDelete = (id: string) => {
    removeCustomTheme(id);
    setNote(t("settings.themeDeleted"));
    setVars(readCurrentVars());
    onSaved?.();
  };

  const submitRename = (id: string, fallback: string) => {
    renameCustomTheme(id, renameDraft.trim() || fallback);
    setRenamingId(null);
    onSaved?.();
  };

  return (
    <div className="space-y-4 rounded-lg border border-border bg-surface-1 p-4">
      <p className="text-xs leading-relaxed text-muted-foreground">
        {t("settings.themeEditorDesc")}
      </p>

      <div className="space-y-2">
        {EDITABLE.map((item) => {
          const value = vars[item.key] || "";
          const ratio = contrastRatio(value, vars[item.against] || "");
          const level = ratio === null ? null : wcagLevel(ratio, item.large);
          return (
            <div key={item.key} className="flex items-center gap-3">
              <input
                type="color"
                value={tripleToHex(value)}
                onChange={(event) => setColor(item.key, event.target.value)}
                aria-label={t(item.labelKey)}
                className="h-7 w-9 shrink-0 cursor-pointer rounded-md border border-border bg-transparent"
              />
              <span className="w-28 shrink-0 truncate text-xs text-foreground">
                {t(item.labelKey)}
              </span>
              <span
                className={cn(
                  "flex items-center gap-1 text-[11px] tabular-nums",
                  level === "fail" ? "text-destructive" : "text-muted-foreground"
                )}
              >
                {ratio === null ? "—" : `${ratio.toFixed(2)}:1`}
                {level === "fail" && <span aria-hidden="true">!</span>}
                {level && level !== "fail" && (
                  <Check size={11} className="text-success" aria-hidden="true" />
                )}
              </span>
            </div>
          );
        })}
      </div>

      <div className="flex flex-wrap items-center gap-2">
        <Input
          value={name}
          onChange={(event) => setName(event.target.value)}
          placeholder={t("settings.themeName")}
          aria-label={t("settings.themeName")}
          className="h-8 w-44 text-xs"
        />
        <Button size="sm" onClick={onSave}>
          <Download size={13} className="mr-1" />
          {t("settings.themeSave")}
        </Button>
        <Button variant="outline" size="sm" onClick={onExport}>
          <Copy size={13} className="mr-1" />
          {t("settings.themeExport")}
        </Button>
        <Button variant="outline" size="sm" onClick={onExportCss}>
          <Copy size={13} className="mr-1" />
          {t("settings.themeExportCss")}
        </Button>
        {applied && <span className="text-[11px] text-success">{t("settings.themeApplied")}</span>}
      </div>

      <div className="space-y-2">
        <label htmlFor="theme-import" className="text-xs text-muted-foreground">
          {t("settings.themeImportHint")}
        </label>
        <textarea
          id="theme-import"
          value={importText}
          onChange={(event) => setImportText(event.target.value)}
          rows={2}
          className="w-full rounded-lg border border-border bg-surface-0 p-2 font-mono text-[11px] text-foreground outline-none focus:ring-2 focus:ring-primary/40"
        />
        <Button variant="outline" size="sm" onClick={onImport} disabled={!importText.trim()}>
          <Upload size={13} className="mr-1" />
          {t("settings.themeImport")}
        </Button>
      </div>

      {customThemes.length > 0 && (
        <div className="space-y-1 border-t border-border pt-3">
          {customThemes.map((theme) => (
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
                    onClick={() => submitRename(theme.id, theme.label)}
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
                      onClick={() => onDelete(theme.id)}
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
        </div>
      )}

      {note && <p className="text-[11px] text-muted-foreground">{note}</p>}
      {Object.keys(currentVars).length === 0 && (
        <p className="text-[11px] text-destructive">{t("settings.themeReadFailed")}</p>
      )}
      <button
        type="button"
        onClick={() => setVars(readCurrentVars())}
        className="cursor-pointer text-[11px] text-muted-foreground underline-offset-2 hover:underline"
      >
        {t("settings.themeResetFromCurrent")}
      </button>
    </div>
  );
}
