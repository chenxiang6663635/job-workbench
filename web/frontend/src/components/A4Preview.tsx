import { useEffect, useRef, useState } from "react";
import { useTranslation } from "react-i18next";
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
  title,
  onHeight,
  className,
}: {
  /** srcDoc 内联 HTML（简历实时预览） */
  html?: string;
  /** 或外部地址（模板文件浏览） */
  src?: string;
  /** iframe 的无障碍标题；不传则用默认文案（调用方可按场景覆盖） */
  title?: string;
  /** 内容真实高度回调（用于防超页护栏计算） */
  onHeight?: (height: number) => void;
  className?: string;
}) {
  const { t } = useTranslation();
  const [contentH, setContentH] = useState(A4_HEIGHT);
  const [scale, setScale] = useState(1);
  const wrapRef = useRef<HTMLDivElement>(null);
  const remeasureTimer = useRef<number | null>(null);

  const measure = (frame: HTMLIFrameElement | null) => {
    const doc = frame?.contentDocument;
    // contentDocument 为空（卸载中/跨域）时直接跳过
    if (!frame || !doc) return;
    // 先把 iframe 高度压到 0 再量：否则读到的是自己刚写进去的高度
    // （scrollHeight >= 视口高），形成「每次 +24、永不回缩」的反馈环——
    // 会让调用方的防超页护栏误报并禁用生成按钮（独立审查抓出的 BLOCKER）。
    // 量完必须把「量之前的内联高度」原样写回：直接置空等于交给 React，
    // 而 React 只在该 prop 值变化时才写 DOM——高度没变的那次（第二次及以后）
    // 会留下空高度，iframe 退化成默认 150px，简历被裁掉大半。
    const prevHeight = frame.style.height;
    frame.style.height = "0px";
    const h = doc.body?.scrollHeight || doc.documentElement?.scrollHeight || 0;
    if (h > 0) {
      setContentH(h);
      onHeight?.(h); // 对外回传纯内容高度，不含任何展示留白
    }
    frame.style.height = prevHeight;
  };

  // 卸载时清掉待执行的二次测量：否则它会用旧文档的高度回调父组件，污染防超页护栏
  useEffect(
    () => () => {
      if (remeasureTimer.current !== null) window.clearTimeout(remeasureTimer.current);
    },
    []
  );

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
            title={title ?? t("a4.previewTitle")}
            srcDoc={html}
            src={html ? undefined : src}
            className="w-full border-0"
            style={{ height: contentH }}
            onLoad={(e) => {
              // 必须把 frame 先存进闭包：React 在事件处理结束后会把 currentTarget 置空，
              // 延后 300ms 再读 e.currentTarget 会拿到 null 并抛异常
              //（原先的写法等于「稳定后再量一次」从未生效，且每次加载都报错）
              const frame = e.currentTarget;
              measure(frame);
              // 图片/字体后加载会改变高度，稳定后再量一次
              remeasureTimer.current = window.setTimeout(() => measure(frame), 300);
            }}
          />
        </div>
      </div>
      {scale < 1 && (
        <p className="mt-2 text-center text-[11px] text-muted-foreground/70">
          {t("a4.scaledNotice", { percent: Math.round(scale * 100) })}
        </p>
      )}
    </div>
  );
}
