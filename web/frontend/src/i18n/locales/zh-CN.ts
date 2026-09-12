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
  "error.renderFailed": "页面渲染出错",
  "error.forceReload": "强制刷新（清除缓存）",

  "common.retry": "重试",
  "common.close": "关闭提示",
  "loading.workspace": "正在定位工作区…",

  "lang.switch": "界面语言",

  "job.unscored": "未评分",
  "job.notScored": "尚未评分",
  "job.jdSaved": "JD 已存",
  "job.reapplyHint": "再投会新建一条记录",
  "job.applyHint": "投递后到追踪表继续跟进",
  "job.applying": "投递中…",
  "job.reapply": "再投一次",
  "job.apply": "一键投递",
  // 卡片 aria-label：屏幕阅读器要靠它读出「哪个岗位、几分、什么状态」
  "job.cardAria": "{{dir}}，匹配度 {{score}}，投递状态 {{state}}",

  "lineage.title": "版本谱系",
  "lineage.subtitle": "每个版本投了哪些岗位、走到哪一步",
  "lineage.loadFailed": "版本谱系加载失败：{{error}}",
  // 中文没有复数变化，_one 与 _other 同值；保留 _one 是因为英文需要它，
  // 而语言包的 key 集合以 zh-CN 为准——satisfies 会拒掉源语言里不存在的 key
  // （en.ts 多写一个 _one 会直接 TS2353，这正是想要的保护）。
  "lineage.jobCount_one": "{{count}} 个岗位",
  "lineage.jobCount_other": "{{count}} 个岗位",
  // 「简历版本」是追踪表 CSV 里的真实列名：英文里必须保留原字段名，否则用户找不到该填哪一列
  "lineage.tip": "提示：投递时在追踪表里填「简历版本」列，谱系才能把版本和岗位连起来。",

  "job.backToPool": "返回岗位池",
  "job.hardGates": "资格硬门槛",
  "job.gatePending": "待确认",
  "job.gateReason": "原因：{{reason}}",
  "job.jdSource": "JD 原文",
  "job.jdMissing": "（尚未保存 JD）",
  "job.parsedCard": "解析卡",
  "job.nextStep": "下一步：{{action}}",
  "job.cardMissing": "尚未生成解析卡",
  // 这两段被 <code>解析卡.md</code> 夹开：文件名是工作区的真实文件约定，不翻译，
  // 所以只能切成两个 key 把文件名留在中间
  "job.cardEmptyHint1": "评分由 AI 在 CodeBuddy 中完成（jd 工作流），写入",
  "job.cardEmptyHint2": "后此处会自动展示四维度得分与档位。",
} as const;

/** 所有合法 key；en 语言包用它做完整性约束 */
export type TranslationKey = keyof typeof zhCN;

export default zhCN;
