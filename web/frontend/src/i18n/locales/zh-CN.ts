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
  "common.clear": "清空",
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

  "a4.previewTitle": "简历预览",
  "a4.scaledNotice": "预览已缩放至 {{percent}}%（布局与生成 PDF 一致）",

  "question.searchPlaceholder": "搜问题、回答或复盘关键词…",
  "question.searching": "检索中…",
  "question.roundMissing": "未填轮次",
  "question.myAnswer": "我的回答",
  "question.retrospective": "复盘：{{value}}",
  "question.emptyNoMatch": "没有匹配的问题",
  "question.emptyNoData": "题库还是空的",
  "question.emptyHintNoMatch": "换个关键词试试，或者清空搜索看全部。",
  // 「问题记录」是面试记录里的真实字段名：英文必须保留原字段名，否则用户找不到该填哪一列
  "question.emptyHintNoData": "面过之后在面试记录里填上「问题记录」字段，这里会攒下你被问过的问题——下次面试前可以照着过一遍。",
  // 复数同理：_one/_other 两套都要在源语言里定义（见 lineage.jobCount 的说明）
  "question.count_one": "共 {{count}} 条",
  "question.count_other": "共 {{count}} 条",
  "question.groupCount_one": "{{count}} 条",
  "question.groupCount_other": "{{count}} 条",

  // offer 的字段 label 是展示用表头，翻译；key 仍是 CSV 列名本身，不参与翻译
  "offer.field.role": "岗位",
  "offer.field.monthly": "月薪",
  "offer.field.bonus": "年终",
  "offer.field.signOn": "签字费",
  "offer.field.equity": "股票期权",
  "offer.field.location": "工作地点",
  "offer.field.deadline": "答复截止日",
  "offer.field.other": "其他条件",
  "offer.emptyTitle": "还没有 Offer 记录",
  "offer.emptyHint1": "拿到 offer 后把已知事实录进来，多个 offer 会并排在这里——",
  "offer.emptyHint2": "数字放在一张表里，选择依然是你自己的",
  "offer.emptyCta": "录入第一个 Offer",
  "offer.add": "录入 Offer",
  "offer.summary_one": "{{count}} 个 offer · 按答复截止日排列（越先要答复的越靠左）",
  "offer.summary_other": "{{count}} 个 offer · 按答复截止日排列（越先要答复的越靠左）",
  "offer.composition": "构成：{{value}}",
  "offer.related": "关联 {{value}}",
  "offer.disclaimer": "这里只并排展示你录入的已知事实，最终选择由你决定。",
} as const;

/** 所有合法 key；en 语言包用它做完整性约束 */
export type TranslationKey = keyof typeof zhCN;

export default zhCN;
