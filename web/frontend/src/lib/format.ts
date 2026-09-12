/**
 * 与组件无关的展示格式化。react-refresh/only-export-components 要求组件文件
 * 只导出组件——fmtSize 此前寄生在 FileCard.tsx 里随组件导出，每处 CI 都警告。
 */

export function fmtSize(n: number) {
  if (n < 1024) return n + " B";
  if (n < 1024 * 1024) return (n / 1024).toFixed(1) + " KB";
  return (n / 1024 / 1024).toFixed(1) + " MB";
}
