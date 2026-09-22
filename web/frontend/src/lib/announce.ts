// UX-6（体检）：成功播报的**发送端**（接收端是 components/LiveRegion.tsx）。
//
// 单独成文件而不是挂在 LiveRegion.tsx 上导出：那边要守 react-refresh 的
// 「一个文件只导出组件」规矩，混着导出会被 lint 点名。
//
// 走 window 自定义事件而不是 React context：调用方散落各处，为一个"说一句话"
// 的动作拉一条 provider 链路不值当；代价是接收端必须唯一（就是 LiveRegion）。
const EVENT = "jobws:announce";

export const ANNOUNCE_EVENT = EVENT;

/** 播报一句成功提示：写/导入/抓取完成后界面变了，读屏也该知道。 */
export function announce(message: string) {
  window.dispatchEvent(new CustomEvent(EVENT, { detail: message }));
}
