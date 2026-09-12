/** 界面文案的源语言（key 的单一真值）。新增 key 先加这里，再补 en。

    第一批只覆盖「导航与壳层」：页面和组件的文案留给「批量抽取」批，
    那里要先分清 UI 文案和用户数据（后者不该翻译）。
*/
const zhCN = {
  "app.title": "求职工作台",

  "nav.dashboard": "看板",
  "nav.applications": "追踪表",
  "nav.jobs": "岗位池",
  "nav.resume": "简历工坊",
  "nav.progress": "进展",
  "nav.library": "素材库",
  "nav.settings": "设置",

  "nav.workspacePlaceholder": "选择工作区",
  "nav.workspaceDefaultSuffix": "（默认）",
  "nav.switchWorkspaceTitle": "切换工作区",

  "status.connecting": "连接中",
  "status.online": "已连接本地数据",
  "status.offline": "后端未启动",
  "error.backend": "无法连接到后端（localhost:8765）",
  "error.backendHint": "请在仓库根目录运行：",
  "loading.workspace": "正在定位工作区…",

  "lang.switch": "界面语言",
} as const;

/** 所有合法 key；en 语言包用它做完整性约束 */
export type TranslationKey = keyof typeof zhCN;

export default zhCN;
