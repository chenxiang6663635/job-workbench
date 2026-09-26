import { useEffect, useState, type SyntheticEvent } from "react";
import { useTranslation } from "react-i18next";
import { Monitor } from "lucide-react";
import {
  getPrefs,
  hasDesktopPrefs,
  onZoomChanged,
  setZoomLevel,
  type PrefsSnapshot,
} from "../../lib/prefs";
import { Card, CardHeader, CardTitle } from "../ui/card";
import { Skeleton } from "../ui/skeleton";
import { cn } from "../../lib/utils";

/**
 * 「界面大小」卡（从 Settings.tsx 拆出——该页是登记过水位的存量文件，只许变小）。
 *
 * 级别真值在主进程（web/electron/main.js）：这里只是它的视图——拖动时预览、
 * 松手时落盘，并按主进程的广播回填（用快捷键调完，滑块会跟着动）。
 *
 * 与语言同为「设备级」偏好，紧挨着放。桌面端才有偏好通道——浏览器直连时降级成一句
 * 说明，而不是把整张卡藏起来：藏起来会让人以为功能不存在（那正是这次要修的那类
 * 「按了没反应」的老问题）。
 */
interface ZoomCardProps {
  hidden?: boolean;
}

export default function ZoomCard({ hidden = false }: ZoomCardProps) {
  const { t } = useTranslation();
  const [zoom, setZoom] = useState<PrefsSnapshot | null>(null);
  const desktopPrefs = hasDesktopPrefs();

  useEffect(() => {
    let alive = true;
    getPrefs()?.then((snap) => {
      if (alive) setZoom(snap);
    });
    const off = onZoomChanged((payload) => {
      if (alive) setZoom((s) => (s ? { ...s, level: payload.level, percent: payload.percent } : s));
    });
    return () => {
      alive = false;
      off();
    };
  }, []);

  /** 松手落盘：鼠标/触摸/键盘三类结束路径与失焦都走它。 */
  const commitZoom = (e: SyntheticEvent<HTMLInputElement>) => {
    void setZoomLevel(Number((e.target as HTMLInputElement).value), true);
  };

  return (
    <Card className={cn("space-y-4 p-5", hidden && "hidden")}>
      <CardHeader className="p-0">
        <CardTitle className="flex items-center gap-2 text-sm">
          <Monitor size={16} className="text-primary" /> {t("settings.zoomTitle")}
        </CardTitle>
      </CardHeader>

      <p className="text-xs leading-relaxed text-muted-foreground">
        {t("settings.zoomDesc")}
      </p>

      {desktopPrefs ? (
        zoom ? (
          <>
            <div className="flex items-center gap-3">
              <input
                type="range"
                min={zoom.min}
                max={zoom.max}
                step={zoom.step}
                value={zoom.level}
                aria-label={t("settings.zoomTitle")}
                className="h-1.5 w-full cursor-pointer appearance-none rounded-full bg-muted accent-primary"
                onChange={(e) => {
                  // 拖动中只预览（persist=false，不落盘）：输入事件本身已按帧调度，
                  // 不再叠一层节流。这里**不回写 IPC 返回值**——拖动很快时旧响应
                  // 可能盖掉新位置（独立审查提的竞态）；百分比松手后由广播校正。
                  const level = Number(e.target.value);
                  setZoom((s) => (s ? { ...s, level } : s));
                  void setZoomLevel(level, false);
                }}
                onPointerUp={commitZoom}
                onPointerCancel={commitZoom}
                onBlur={commitZoom}
                onKeyUp={commitZoom}
              />
              <span className="w-12 shrink-0 text-right text-xs font-medium tabular-nums font-numeric">
                {zoom.percent}%
              </span>
            </div>
            <p className="text-xs text-muted-foreground">{t("settings.zoomHint")}</p>
          </>
        ) : (
          <Skeleton className="h-1.5 w-full" />
        )
      ) : (
        <p className="text-xs leading-relaxed text-muted-foreground">
          {t("settings.zoomDesktopOnly")}
        </p>
      )}
    </Card>
  );
}
