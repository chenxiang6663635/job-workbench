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
     ② 更隐蔽的一处：tailwindcss-animate 的 zoom-in-95 关键帧把 transform
        从 translate3d(0,0,0) 开始动画——入场 200ms 内居中位移被覆盖，
        弹窗左上角落在视口中心、观感"从下往上冒"。修法 = 用 arbitrary
        property 把 enter/exit 的起始位移也设为 -50%（见下方 className）。
   - 可拖动：按住 DialogHeader（data-dialog-drag）即可整体位移——弹窗常挡住
     的恰是用户要对照的表格/正文；拖动是**叠加偏移**，默认仍居中；边界夹取
     保证弹窗始终留一部分在视口内（拖不丢）。
   - 长内容：max-h-[85vh] + 内部滚动，底部按钮永远够得着。 */
const DialogContent = React.forwardRef<
  React.ElementRef<typeof DialogPrimitive.Content>,
  React.ComponentPropsWithoutRef<typeof DialogPrimitive.Content>
>(({ className, children, ...props }, ref) => {
  const [offset, setOffset] = React.useState({ x: 0, y: 0 });
  // 拖动完全绕开 React 状态（#6 用户实测「拖着卡」）：pointermove 里 setState 会把
  // 整个弹窗子树（可能是 50 封邮件的列表）每帧重渲染一次；left/top 又是布局属性，
  // 每帧触发 reflow。现在：move 只更新 ref 并用 rAF 合帧，直接写 DOM 的 transform
  // （合成器友好），pointerup 才把最终位置固化进 state——与已绘位置一致，不跳变。
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

  const paint = () => {
    const d = drag.current;
    if (!d) return;
    d.raf = 0;
    d.el.style.transform = `translate(calc(-50% + ${d.x}px), calc(-50% + ${d.y}px))`;
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
      baseX: offset.x,
      baseY: offset.y,
      x: offset.x,
      y: offset.y,
      raf: 0,
      el,
    };
    // 拖动期间提升为合成层，松手即撤（常驻会白占一层显存）
    el.style.willChange = "transform";
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
    d.el.style.willChange = "";
    drag.current = null;
    setOffset({ x: d.x, y: d.y });
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
        // 拖动经 transform 偏移（translate 走合成器；-50% 居中一并写进同一个
        // transform，内联值恒存在，与入场动画的 enter/exit 变量天然衔接）
        style={{
          transform: `translate(calc(-50% + ${offset.x}px), calc(-50% + ${offset.y}px))`,
        }}
        className={cn(
          // left/top 50% 定基准（此前由内联 left/top 承担，改 transform 偏移后必须
          // 显式给出，否则 fixed 元素落在静态位置上——2026-09-16 实测回归）
          "fixed left-1/2 top-1/2 z-50 grid max-h-[85vh] w-full max-w-lg gap-4 overflow-y-auto border border-border-strong bg-popover p-6 shadow-elevated ring-1 ring-highlight/5 duration-200 data-[state=open]:animate-in data-[state=closed]:animate-out data-[state=closed]:fade-out-0 data-[state=open]:fade-in-0 data-[state=closed]:zoom-out-95 data-[state=open]:zoom-in-95 [--tw-enter-translate-x:-50%] [--tw-enter-translate-y:-50%] [--tw-exit-translate-x:-50%] [--tw-exit-translate-y:-50%] sm:rounded-lg",
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
