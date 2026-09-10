import { useEffect, useMemo, useRef, useState } from "react";
import {
  ArrowLeft,
  FileCode2,
  FileText,
  FileImage,
  Loader2,
  Printer,
} from "lucide-react";
import {
  api,
  type ResumeBuildResult,
  type ResumeTemplateItem,
} from "../api";
import { Badge } from "./ui/badge";
import { Button } from "./ui/button";
import { Card } from "./ui/card";
import { Skeleton } from "./ui/skeleton";
import { ErrorBanner } from "./ErrorBanner";
import { A4Preview } from "./A4Preview";
import { FileCard, fmtSize } from "./FileCard";

// 从文件列表里挑出手写模板（resume_<版本>.html），供「生成 PDF」按钮使用
function templateVersion(rel: string): string | null {
  const m = /resume_([A-Za-z0-9_-]+)\.html$/.exec(rel);
  return m ? m[1] : null;
}

export default function ResumeTemplates() {
  const [items, setItems] = useState<ResumeTemplateItem[]>([]);
  const [error, setError] = useState<string | null>(null);
  const [selected, setSelected] = useState<ResumeTemplateItem | null>(null);
  const [textContent, setTextContent] = useState<string | null>(null);
  const [building, setBuilding] = useState(false);
  const [result, setResult] = useState<ResumeBuildResult | null>(null);
  const [loading, setLoading] = useState(true);

  useEffect(() => {
    api
      .listResumeTemplates()
      .then((r) => setItems(r.items))
      .catch((e: Error) => setError(e.message))
      .finally(() => setLoading(false));
  }, []);

  // 选中文件后：文本类拉内容，二进制直接用文件 URL
  useEffect(() => {
    if (!selected || selected.kind !== "text") {
      setTextContent(null);
      return;
    }
    api
      .resumeTemplateContent(selected.rel)
      .then((r) => setTextContent(r.type === "text" ? r.content : null))
      .catch((e: Error) => setError(e.message));
  }, [selected]);

  const buildable = useMemo(
    () => (selected ? templateVersion(selected.rel) : null),
    [selected]
  );

  const build = () => {
    if (!buildable) return;
    setBuilding(true);
    setResult(null);
    api
      .buildResumeTemplate(buildable)
      .then(setResult)
      .catch((e: Error) => setError(e.message))
      .finally(() => setBuilding(false));
  };

  if (selected) {
    const fileUrl = api.resumeTemplateFileUrl(selected.rel);
    const isHtml = selected.rel.toLowerCase().endsWith(".html");
    return (
      <div className="space-y-4">
        <div className="flex flex-wrap items-center gap-3">
          <Button
            variant="ghost"
            size="sm"
            onClick={() => {
              setSelected(null);
              setTextContent(null);
              setResult(null);
            }}
            className="-ml-2"
          >
            <ArrowLeft size={16} /> 返回列表
          </Button>
          <span className="text-sm font-medium text-foreground">{selected.rel}</span>
          <span className="text-xs text-muted-foreground">{fmtSize(selected.size)}</span>
          {buildable && (
            <Button onClick={build} disabled={building} className="ml-auto">
              {building ? <Loader2 size={15} className="animate-spin" /> : <Printer size={15} />}
              {building ? "生成中…" : `生成 ${buildable} 的 PDF`}
            </Button>
          )}
        </div>

        {error && (
          <ErrorBanner message={error} />
        )}

        {result && (
          <Card
            className={`p-4 ${
              result.passed ? "border-success/30 bg-success/10" : "border-destructive/30 bg-destructive/10"
            }`}
          >
            <div className="flex items-center justify-between">
              <span className="text-sm font-semibold text-foreground">
                {result.passed ? "生成成功，校验通过" : "生成完成，校验未通过"}
              </span>
              <span className="font-mono text-xs text-muted-foreground">
                {(result.size / 1024).toFixed(1)} KB · {result.a4.message}
              </span>
            </div>
            <ul className="mt-1 space-y-0.5 text-xs">
              {result.checks.map((c) => (
                <li key={c.label} className="flex items-center justify-between">
                  <span className="text-muted-foreground">{c.label}</span>
                  <span
                    className={
                      c.ok === null ? "text-muted-foreground" : c.ok ? "text-success" : "text-destructive"
                    }
                  >
                    {c.value}
                  </span>
                </li>
              ))}
            </ul>
          </Card>
        )}

        {isHtml ? (
          // 手写模板带相对资源（photo.jpg 等），用文件 URL 的 iframe 保真展示
          <A4Preview src={fileUrl} title={selected.rel} />
        ) : textContent !== null ? (
          <pre className="max-h-[75vh] overflow-auto whitespace-pre-wrap rounded-2xl border border-border bg-background p-5 font-mono text-xs leading-relaxed text-foreground">
            {textContent}
          </pre>
        ) : (
          <A4Preview src={fileUrl} title={selected.rel} />
        )}
      </div>
    );
  }

  return (
    <div className="space-y-4">
      <p className="text-sm text-muted-foreground">
        手写 HTML 的精排版（高级模板）。只读浏览与生成；编辑仍走手写 HTML，改动后回到这里刷新预览。
      </p>

      {error && (
        <ErrorBanner message={error} />
      )}

      {loading ? (
        <div className="grid gap-2 sm:grid-cols-2 lg:grid-cols-3">
          {[0, 1, 2, 3, 4, 5].map((i) => (
            <Skeleton key={i} className="h-16 w-full" />
          ))}
        </div>
      ) : items.length === 0 ? (
        <Card className="border-dashed p-10 text-center">
          <p className="text-sm text-muted-foreground">
            02_简历工坊/ 下暂无文件。手写模板放 pdf/resume_&lt;版本&gt;.html。
          </p>
        </Card>
      ) : (
        <div className="grid gap-2 sm:grid-cols-2 lg:grid-cols-3">
          {items.map((item) => (
            <FileCard
              key={item.rel}
              name={item.rel}
              kind={item.kind}
              size={item.size}
              onClick={() => setSelected(item)}
            />
          ))}
        </div>
      )}
    </div>
  );
}
