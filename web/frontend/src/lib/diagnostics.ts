// 诊断包导出的 URL 构造（首发前收口批 笔 3）。
//
// 为什么不进 src/api.ts：那个文件登记过水位（460 行，只许变小），窄需求走窄模块
// ——与 lib/bank.ts、lib/snapshotApi.ts 同一条理由。
//
// 为什么工作区**由调用方传**、而不是在这里 import lib/http 的 currentWorkspace：
// lib/http 会连带初始化 i18n，而 i18n 在模块顶层就碰 `document`——单测环境刻意不装
// jsdom（见 CONTRIBUTING 的"前端单测只守纯逻辑"），连带上它就等于这条纯函数无法被测。
// 依赖显式传入，函数保持纯的，判定就落得下断言。
//
// 必须带 ?ws=：后端每个请求都要显式工作区（tools/ 的模块级 WORKSPACE 全局在并发下会
// 互相覆盖），响应头还会回显实际服务的工作区供前端自检（issue #22）。导出链接走的是
// 浏览器下载、不经 requestJson，所以这里手拼一次——编码方式与 api.exportUrl() 一致。
export function diagnosticsUrl(workspace: string): string {
  const base = "/api/system/diagnostics";
  return workspace ? `${base}?ws=${encodeURIComponent(workspace)}` : base;
}
