import * as React from "react";
import { cva, type VariantProps } from "class-variance-authority";
import { cn } from "../../lib/utils";

const badgeVariants = cva(
  "inline-flex items-center gap-1.5 rounded-full border px-2.5 py-0.5 text-xs font-semibold transition-all",
  {
    variants: {
      variant: {
        // 语义色只做底色、文字统一前景色（独立审查 MAJOR：success/primary 等
        // 当 12px 文字色在 tint 底上只有 3.2–4.0:1，低于 AA 4.5）
        default: "border-transparent bg-primary/15 text-foreground",
        secondary: "border-transparent bg-secondary text-secondary-foreground",
        outline: "border-border text-muted-foreground",
        success: "border-transparent bg-success/15 text-foreground",
        warning: "border-transparent bg-warning/15 text-foreground",
        destructive:
          "border-transparent bg-destructive/15 text-foreground",
      },
    },
    defaultVariants: {
      variant: "default",
    },
  }
);

export interface BadgeProps
  extends React.HTMLAttributes<HTMLDivElement>,
    VariantProps<typeof badgeVariants> {}

function Badge({ className, variant, ...props }: BadgeProps) {
  return (
    <div className={cn(badgeVariants({ variant }), className)} {...props} />
  );
}

export { Badge, badgeVariants };
