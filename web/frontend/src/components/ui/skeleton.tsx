import { cn } from "../../lib/utils";

/** 加载占位骨架。本库此前 0 处骨架屏，加载态都是一行文字或 spinner——迁移时用它替换 */
function Skeleton({
  className,
  ...props
}: React.HTMLAttributes<HTMLDivElement>) {
  return (
    <div
      className={cn("rounded-md bg-gradient-to-r from-secondary/60 via-muted to-secondary/60 animate-pulse", className)}
      {...props}
    />
  );
}

export { Skeleton };
