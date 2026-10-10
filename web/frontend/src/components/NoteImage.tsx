import { useState } from "react";
import type { ImgHTMLAttributes } from "react";
import { useTranslation } from "react-i18next";
import { ImageOff } from "lucide-react";

/**
 * 笔记正文里的图片（图片端点批，2026-10-09）。
 *
 * 两条纪律（与渲染器的其余降级同款：解析成功才升级）：
 * 1. `url` 为 null（外链 / 越界 / 非位图白名单）→ 明确占位，不发起请求；
 * 2. 加载失败（文件被删 / 超限 413 / 后端过旧）→ **onError 回落同一个占位**——
 *    浏览器的破图图标说不出原因，占位能说清"这里有一张图，但没显示"。
 */
type NoteImageProps = {
  /** 解析出的只读字节 URL；null = 不升级成 <img> */
  url: string | null;
} & ImgHTMLAttributes<HTMLImageElement>;

export default function NoteImage({ url, src, alt, ...props }: NoteImageProps) {
  const { t } = useTranslation();
  const [failed, setFailed] = useState(false);

  if (url && !failed) {
    return (
      <img
        {...props}
        src={url}
        alt={alt || src || ""}
        loading="lazy"
        onError={() => setFailed(true)}
        className="my-2 max-w-full rounded-md border border-border"
      />
    );
  }

  return (
    <span
      {...props}
      className="my-1 inline-flex max-w-full items-center gap-1.5 rounded-md border border-dashed border-border px-2 py-1 align-middle text-[0.6875rem] text-muted-foreground"
      title={t("notes.imageSkippedHint")}
    >
      <ImageOff size={12} className="shrink-0" />
      <span className="shrink-0">{t("notes.imageSkipped")}</span>
      <span className="truncate font-mono" title={src}>
        {alt || src}
      </span>
    </span>
  );
}
