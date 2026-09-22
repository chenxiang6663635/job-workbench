// 页面间下钻（drill）的**单一出口**：跳转前把意图写进 sessionStorage，
// 目标页 mount 时读一次即清。
//
// 三条约定：
// - 存储不可用（隐私模式 / 配额满）就退化为"只跳页面"——**不抛错**，
//   用户的动作不能因为存不下就消失，最多是落不到具体页签 / 不展开那一行；
// - 键名与目标页自己的 DRILL_KEY 必须是同一个字符串，改一处就漂；
// - 只写意图，不解释意图：怎么消费由目标页决定（页签 / 展开行 / 打开详情）。

export const DRILL_KEY = "jobws_drill";
export const PREPARE_TAB_KEY = "jobws_prepare_tab";
export const PROGRESS_TAB_KEY = "jobws_progress_tab";

/** 跳到某个页面的指定页签（页签键由目标页自己读）。 */
export function drillToTab(page: string, tabKey: string, tab: string): void {
  try {
    sessionStorage.setItem(tabKey, tab);
  } catch {
    // 存储不可用：退化为只跳页面
  }
  window.location.hash = page;
}

// UX-3：投递行 → 岗位池的对应岗位详情。dir 由表格容器按 (公司, 岗位) 反查好，
// 没有对应岗位的行根本不显示这个入口（不做点了没反应的入口）。
export function drillToJob(dir: string): void {
  try {
    sessionStorage.setItem(DRILL_KEY, JSON.stringify({ focusDir: dir }));
  } catch {
    // 存储不可用：退化为只跳页面
  }
  window.location.hash = "jobs";
}
