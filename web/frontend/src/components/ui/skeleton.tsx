import { cn } from "../../lib/utils";

/** 加载占位骨架。本库此前 0 处骨架屏，加载态都是一行文字或 spinner——迁移时用它替换 */
function Skeleton({
  className,
  ...props
}: React.HTMLAttributes<HTMLDivElement>) {
  return (
    <div
      className={cn("relative overflow-hidden rounded-md bg-secondary/60", className)}
      {...props}
    >
      {/* shimmer 横扫光带：比 opacity 脉冲更有「加载中」的方向感 */}
      <div className="absolute inset-0 -translate-x-full animate-shimmer bg-gradient-to-r from-transparent via-white/10 to-transparent" />
    </div>
  );
}

export { Skeleton };
