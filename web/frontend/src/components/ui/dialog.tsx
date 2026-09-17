import * as React from "react";
import * as DialogPrimitive from "@radix-ui/react-dialog";
import { cn } from "../../lib/utils";

const Dialog = DialogPrimitive.Root;
const DialogTrigger = DialogPrimitive.Trigger;
const DialogPortal = DialogPrimitive.Portal;
const DialogClose = DialogPrimitive.Close;

const DialogOverlay = React.forwardRef<
  React.ElementRef<typeof DialogPrimitive.Overlay>,
  React.ComponentPropsWithoutRef<typeof DialogPrimitive.Overlay>
>(({ className, ...props }, ref) => (
  <DialogPrimitive.Overlay
    ref={ref}
    // data-dialog-overlay：拖动期间由 index.css 把全屏 backdrop-blur 降级为
    // 纯色（弱 GPU 的拖动掉帧大头就是它），松手即恢复
    data-dialog-overlay
    className={cn(
      "fixed inset-0 z-50 bg-scrim/80 backdrop-blur-md data-[state=open]:animate-in data-[state=closed]:animate-out data-[state=closed]:fade-out-0 data-[state=open]:fade-in-0",
      className
    )}
    {...props}
  />
));
DialogOverlay.displayName = DialogPrimitive.Overlay.displayName;

/* 自带焦点圈定、Esc 关闭与 aria-modal——此前 5 个手写弹窗都没有这些。
   - 垂直居中（#1 用户实测，两处根因都已修）：
     ① 居中位移曾被批量替换误伤成非法类名（弹窗从页面中点向下画）；
     ② tailwindcss-animate 的 zoom-in-95 关键帧会驱动 transform——现在居中
        改由 **CSS translate 属性**承担（与 transform 相互独立、先于 transform
        复合），关键帧的 transform 从 0 位移起步即"居中 + 缩放"，原先那组
        `--tw-enter/exit-translate-*` arbitrary 覆写因此不再需要（已删除）。
   - 可拖动：按住 DialogHeader（data-dialog-drag）即可整体位移——弹窗常挡住
     的恰是用户要对照的表格/正文；拖动是**叠加偏移**，默认仍居中；边界夹取
     保证弹窗始终留一部分在视口内（拖不丢）。
   - 长内容：max-h-[85vh] + 内部滚动，底部按钮永远够得着。 */
const DialogContent = React.forwardRef<
  React.ElementRef<typeof DialogPrimitive.Content>,
  React.ComponentPropsWithoutRef<typeof DialogPrimitive.Content>
>(({ className, children, ...props }, ref) => {
  // 拖动性能（#6 → 2026-09-17 实测反馈二轮，据 Chromium 合成层调研重做）：
  // · 位移走 **transform**（与 opacity 同级、唯一"只合成不布局"的属性）：
  //   rAF 合帧、全程只做加减法，绝不读布局（getBoundingClientRect/offset*）；
  // · **transform 完全不进 JSX**——React 只 diff 它管理的 style 键，重渲染碰不到
  //   直写的值，"拖动中重渲染把位置写回旧值"的弹回从机制上不存在；
  // · 固化值放 **ref 不放 state**：松手也零重渲染（旧版松手 setState 会重渲一次）；
  // · 居中与位移解耦：居中在 className 的 `[translate:-50%_-50%]`（translate
  //   属性），位移在 style.transform——两个属性独立复合、互不覆盖，也不与
  //   入场/退场动画的 keyframes transform 打架；
  // · 拖动期间给 body 挂 data-dialog-dragging：index.css 把遮罩的全屏
  //   backdrop-blur 降级为纯色（每帧全屏重采样是弱 GPU 掉帧的大头）。
  // 评估过但未采纳：contain: layout paint（会裁掉 shadow-elevated 的外扩阴影，
  // 且对本场景的合成路径收益不明）；pointerrawupdate / getCoalescedEvents
  // （鼠标拖动无收益）。
  const drag = React.useRef<{
    startX: number;
    startY: number;
    baseX: number;
    baseY: number;
    x: number;
    y: number;
    raf: number;
    el: HTMLDivElement;
  } | null>(null);
  // 上次松手固化的位移（下次拖动的基线）——只被拖动逻辑读写，不参与渲染
  const offset = React.useRef({ x: 0, y: 0 });

  // 卸载兜底（独立审查 MINOR）：拖动中按 Esc / 点遮罩会把本弹窗直接卸载，
  // endDrag 不会再跑——body 上的拖动标记若不清，之后所有弹窗的遮罩都会被
  // 降级规则命中（纯色代替模糊）。组件卸载时若有进行中的拖动则一并清理。
  React.useEffect(() => {
    return () => {
      if (drag.current) {
        document.body.removeAttribute("data-dialog-dragging");
        drag.current = null;
      }
    };
  }, []);

  const paint = () => {
    const d = drag.current;
    if (!d) return;
    d.raf = 0;
    d.el.style.transform = `translate(${d.x}px, ${d.y}px)`;
  };

  const onPointerDown = (event: React.PointerEvent<HTMLDivElement>) => {
    const target = event.target as HTMLElement;
    // 交互元素不触发拖动（标题里的链接/按钮仍可点）
    if (target.closest("button, a, input, select, textarea")) return;
    if (!target.closest("[data-dialog-drag]")) return;
    const el = event.currentTarget;
    drag.current = {
      startX: event.clientX,
      startY: event.clientY,
      baseX: offset.current.x,
      baseY: offset.current.y,
      x: offset.current.x,
      y: offset.current.y,
      raf: 0,
      el,
    };
    // 拖动期间提升为合成层，松手即撤（常驻会白占一层显存）
    el.style.willChange = "transform";
    document.body.setAttribute("data-dialog-dragging", "");
    event.currentTarget.setPointerCapture(event.pointerId);
  };
  const onPointerMove = (event: React.PointerEvent<HTMLDivElement>) => {
    const d = drag.current;
    if (!d) return;
    // 边界夹取（#1）：中心最多移到距视口边 80px——任何方向都留有可抓回的部分，
    // 不会出现「拖出屏幕丢了、只能重启」的死路。
    const limitX = Math.max(80, window.innerWidth / 2 - 80);
    const limitY = Math.max(80, window.innerHeight / 2 - 80);
    d.x = Math.min(limitX, Math.max(-limitX, d.baseX + (event.clientX - d.startX)));
    d.y = Math.min(limitY, Math.max(-limitY, d.baseY + (event.clientY - d.startY)));
    if (!d.raf) d.raf = requestAnimationFrame(paint);
  };
  const endDrag = () => {
    const d = drag.current;
    if (!d) return;
    if (d.raf) cancelAnimationFrame(d.raf);
    // 补写最终值（最后一帧可能被 cancel 掉）：与已绘位置逐像素一致，不跳变
    d.el.style.transform = `translate(${d.x}px, ${d.y}px)`;
    offset.current = { x: d.x, y: d.y };
    drag.current = null;
    document.body.removeAttribute("data-dialog-dragging");
    // 值稳定之后再摘 will-change：先摘会层降级、可能触发一次重光栅
    d.el.style.willChange = "";
  };

  return (
    <DialogPortal>
      <DialogOverlay />
      <DialogPrimitive.Content
        ref={ref}
        onPointerDown={onPointerDown}
        onPointerMove={onPointerMove}
        onPointerUp={endDrag}
        onPointerCancel={endDrag}
        className={cn(
          // left/top 50% 定基准（fixed 元素不写会落在静态位置上——2026-09-16
          // 实测回归）；居中走 translate 属性、拖动位移由 ref 直写 transform。
          // 退场只留 fade（独立审查 MINOR）：zoom-out 的 keyframes 动的是
          // transform，会压过内联位移——拖动过的弹窗关闭时会「滑回中心」；
          // 入场的 zoom-in-95 只声明 from，不压内联值，保留。
          "fixed left-1/2 top-1/2 z-50 grid max-h-[85vh] w-full max-w-lg gap-4 [translate:-50%_-50%] overflow-y-auto border border-border-strong bg-popover p-6 shadow-elevated ring-1 ring-highlight/5 duration-200 data-[state=open]:animate-in data-[state=closed]:animate-out data-[state=closed]:fade-out-0 data-[state=open]:fade-in-0 data-[state=open]:zoom-in-95 sm:rounded-lg",
          className
        )}
        {...props}
      >
        {children}
      </DialogPrimitive.Content>
    </DialogPortal>
  );
});
DialogContent.displayName = DialogPrimitive.Content.displayName;

const DialogHeader = ({
  className,
  children,
  ...props
}: React.HTMLAttributes<HTMLDivElement>) => (
  <div
    // data-dialog-drag：DialogContent 据此把标题区当作拖动把手（#1）
    data-dialog-drag
    className={cn(
      "flex cursor-move select-none flex-col space-y-1.5 text-left",
      className
    )}
    {...props}
  >
    {/* 拖动把手可视化（#1）：按住标题区任意位置都能拖，这条短杠是提示 */}
    <span
      aria-hidden="true"
      className="mx-auto h-1 w-8 rounded-full bg-border-strong/60"
    />
    {children}
  </div>
);
DialogHeader.displayName = "DialogHeader";

const DialogFooter = ({
  className,
  ...props
}: React.HTMLAttributes<HTMLDivElement>) => (
  <div
    className={cn(
      "flex flex-col-reverse gap-2 sm:flex-row sm:justify-end",
      className
    )}
    {...props}
  />
);
DialogFooter.displayName = "DialogFooter";

const DialogTitle = React.forwardRef<
  React.ElementRef<typeof DialogPrimitive.Title>,
  React.ComponentPropsWithoutRef<typeof DialogPrimitive.Title>
>(({ className, ...props }, ref) => (
  <DialogPrimitive.Title
    ref={ref}
    className={cn("text-base font-semibold leading-none", className)}
    {...props}
  />
));
DialogTitle.displayName = DialogPrimitive.Title.displayName;

const DialogDescription = React.forwardRef<
  React.ElementRef<typeof DialogPrimitive.Description>,
  React.ComponentPropsWithoutRef<typeof DialogPrimitive.Description>
>(({ className, ...props }, ref) => (
  <DialogPrimitive.Description
    ref={ref}
    className={cn("text-xs text-muted-foreground", className)}
    {...props}
  />
));
DialogDescription.displayName = DialogPrimitive.Description.displayName;

export {
  Dialog,
  DialogPortal,
  DialogOverlay,
  DialogTrigger,
  DialogClose,
  DialogContent,
  DialogHeader,
  DialogFooter,
  DialogTitle,
  DialogDescription,
};
