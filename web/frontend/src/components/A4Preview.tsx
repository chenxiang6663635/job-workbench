import { useEffect, useRef, useState } from "react";
import { cn } from "../lib/utils";

/**
 * A4 预览公共组件。此前重复实现两份：Resume.tsx:418-459 与
 * ResumeTemplates.tsx:44-98（TemplatePreview）——同一套 A4_WIDTH / contentH /
 * scale + ResizeObserver，按 rule of three 收敛为一处。
 *
 * 两件事：
 * ① 高度按 iframe 内容真实高度展开（写死高度会截断内容，只能内部滚动，用户往往
 *    不知道下面还有）；
 * ② 按 A4 宽（794px）1:1 渲染再等比缩小——全宽渲染会让行宽达真实的 1.6 倍，
 *    与导出的 PDF 完全不是一回事。
 */
export const A4_WIDTH = 794;
export const A4_HEIGHT = 1123;

export function A4Preview({
  html,
  src,
  title = "简历预览",
  onHeight,
  className,
}: {
  /** srcDoc 内联 HTML（简历实时预览） */
  html?: string;
  /** 或外部地址（模板文件浏览） */
  src?: string;
  title?: string;
  /** 内容真实高度回调（用于防超页护栏计算） */
  onHeight?: (height: number) => void;
  className?: string;
}) {
  const [contentH, setContentH] = useState(A4_HEIGHT);
  const [scale, setScale] = useState(1);
  const wrapRef = useRef<HTMLDivElement>(null);

  const measure = (frame: HTMLIFrameElement) => {
    const h = frame.contentDocument?.documentElement?.scrollHeight;
    if (h && h > 0) {
      // 内部按 h+24 留白展示；对外回传原始高度，避免调用方的防超页护栏多算
      setContentH(h + 24);
      onHeight?.(h);
    }
  };

  useEffect(() => {
    const el = wrapRef.current;
    if (!el) return;
    const fit = () => setScale(Math.min(1, el.clientWidth / A4_WIDTH));
    fit();
    const ro = new ResizeObserver(fit);
    ro.observe(el);
    return () => ro.disconnect();
  }, [html, src]);

  return (
    <div className={cn("overflow-hidden rounded-lg border border-border bg-background/60 p-6", className)}>
      <div
        ref={wrapRef}
        className="mx-auto overflow-hidden"
        style={{ height: contentH * scale }}
      >
        <div
          className="origin-top-left bg-white shadow-elevated"
          style={{ width: A4_WIDTH, transform: `scale(${scale})`, transformOrigin: "top left" }}
        >
          <iframe
            title={title}
            srcDoc={html}
            src={html ? undefined : src}
            className="w-full border-0"
            style={{ height: contentH }}
            onLoad={(e) => {
              measure(e.currentTarget);
              // 图片/字体后加载会改变高度，稳定后再量一次
              setTimeout(() => measure(e.currentTarget), 300);
            }}
          />
        </div>
      </div>
      {scale < 1 && (
        <p className="mt-2 text-center text-[11px] text-muted-foreground/70">
          预览已缩放至 {Math.round(scale * 100)}%（布局与生成 PDF 一致）
        </p>
      )}
    </div>
  );
}
