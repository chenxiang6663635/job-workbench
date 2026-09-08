import { clsx, type ClassValue } from "clsx";
import { twMerge } from "tailwind-merge";

/** 类名合并：clsx 处理条件类，twMerge 解决 Tailwind 类冲突（后者覆盖前者） */
export function cn(...inputs: ClassValue[]) {
  return twMerge(clsx(inputs));
}
