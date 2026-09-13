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
  "common.cancel": "取消",
  "common.save": "保存",
  "common.saving": "保存中…",
  "common.collapse": "收起",
  "common.all": "全部",
  "common.closeAction": "关闭",
  "common.notRecorded": "（未记录）",
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

  // 表单通用：多处表单/对话框共用同一句校验与占位，集中放 form.* 便于复用
  "form.companyRequired": "公司（必填）",
  "form.roleRequired": "岗位（必填）",
  "form.companyRoleRequired": "公司和岗位都需要填写",
  "form.selectStage": "选择阶段",

  "status.title": "粘贴邮件更新投递状态",
  "status.desc": "把笔试 / 面试 / offer / 拒信的原文整段粘进来，解析出「改哪条、改成什么、依据哪句话」。",
  "status.descNote": "解析不会改动任何数据，只有你逐条确认后才会写入，并记入变更时间线。",
  // 示例文本：英文版换成英文招聘邮件的写法，不是逐字直译
  "status.placeholder": "例如：您好！感谢您投递某某科技热管理工程师岗位，现邀请您参加第二轮面试，面试时间 9月25日 14:00……",
  "status.pickRecord": "指定记录（可选）",
  "status.autoMatch": "自动识别（按原文里的公司名）",
  "status.manualHint": "站内信经常通篇不写公司名，这时在这条记录上手选一次",
  "status.parse": "解析原文",
  "status.apply": "应用更新",
  "status.pasteRequired": "请先粘贴邮件或站内信原文",
  "status.pickRequired": "请先勾选要应用的记录",
  "status.reasonRequired": "进入终态必须填写原因：{{label}}",
  // {{label}} 是「公司 岗位」两个数据字段拼出来的展示串，外层负责拼，key 只包一层壳
  "status.applyFailed": "{{label}}：{{error}}",
  "status.failedHeader": "以下记录没能写入（其余已成功）：",
  "status.createdNotice": "已创建记录：{{label}}（当前阶段 {{stage}}）。若这封邮件只是投递确认，到此就够了；若它还包含新进展（面试、offer 等），再点「解析原文」写回。",
  "status.footerPartial": "成功的那几条已经落盘（勾选已摘掉）；剩下的修正后可直接重试",
  "status.footerPicked_one": "逐条写入 {{count}} 条，并记入变更时间线（一条失败不影响其余）",
  "status.footerPicked_other": "逐条写入 {{count}} 条，并记入变更时间线（一条失败不影响其余）",
  "status.footerNeedPick": "勾选要应用的记录后才会写入",
  "status.footerNeedParse": "先解析原文，确认建议后再写入",
  "status.noMatchHint": "没有匹配到追踪表里的记录。请在上方「指定记录」里选一条后重新解析。",
  "status.ambiguous": "原文里既有拒信措辞又有 offer 措辞，无法判断方向——已不给出阶段建议，请人工核对。",
  "status.newRecordHint": "没有匹配到追踪表里的记录。如果这条投递还没有记录（投递确认类邮件常常如此），在这里直接建一条：",
  "status.create": "创建记录",
  "status.created": "已创建",
  "status.newRecordNote": "当前阶段默认取邮件信号（{{stage}}）；方向与批次创建后不可改",
  "status.pickStageFirst": "请先选择要改成的阶段",
  "status.ruleSuggestion": "（规则建议，可改）",
  "status.reasonLabel": "状态原因",
  "status.reasonPlaceholder": "进入终态必须填写（默认填入命中的原句，可改）",

  "interview.icsTitle": "把面试日程导入手机/电脑日历，提前 1 小时提醒",
  "interview.exportIcs": "导出日程 .ics",
  "interview.add": "记录面试",
  "interview.emptyTitle": "还没有面试记录",
  "interview.emptyHint1": "每一场面试都值得记下来——问题、回答、复盘，",
  "interview.emptyHint2": "复盘是唯一能复利的部分",
  "interview.companyMissing": "（未填公司）",
  "interview.timeTbd": "时间待定",
  "interview.hoursLater_one": "· {{hours}} 小时后",
  "interview.hoursLater_other": "· {{hours}} 小时后",
  "interview.inTwoDays": "· 明后两天",
  // 轮次为空时的兜底占位；轮次本身是数据枚举，不翻
  "interview.fallbackRound": "面试",
  "interview.related": "关联 {{value}}",
  "interview.interviewer": "面试官 {{value}}",
  // 三段的标题是给人看的表头；取值用的 CSV 列名仍是中文，不受影响
  "interview.sectionQuestions": "问题记录",
  "interview.sectionAnswers": "我的回答要点",
  "interview.sectionRetro": "复盘与改进",
  "interview.selectHint": "从左侧选择一场面试查看记录",

  "contact.add": "记联系人",
  "contact.nameRequired": "姓名必填",
  "contact.phName": "姓名 *",
  "contact.phRole": "角色（HR / 技术面 / 猎头）",
  "contact.phCompany": "公司",
  "contact.phContact": "联系方式（微信 / 手机 / 邮箱）",
  "contact.phSource": "来源（BOSS / 内推 / 官网）",
  "contact.nextFollow": "下次跟进",
  "contact.phNote": "备注（聊了什么、注意事项）",
  "contact.summary_one": "{{count}} 位联系人 · 有下次跟进日期的排最前，超期的会标琥珀色",
  "contact.summary_other": "{{count}} 位联系人 · 有下次跟进日期的排最前，超期的会标琥珀色",
  "contact.emptyTitle": "还没有联系人记录",
  "contact.emptyHint1": "HR 的名字、聊到哪一步、答应什么时候回——",
  "contact.emptyHint2": "流程感很强的招聘，靠这些细节维系",
  "contact.roleMissing": "（未填角色）",
  "contact.overdue": "跟进超期：{{date}}",
  "contact.dueToday": "今天该跟进",
  "contact.nextFollowAt": "下次跟进：{{date}}",
  "contact.noPlan": "暂无跟进计划",
  "contact.markTitle": "把最近联系记为今天，并清掉跟进计划",
  "contact.marked": "已联系",
} as const;

/** 所有合法 key；en 语言包用它做完整性约束 */
export type TranslationKey = keyof typeof zhCN;

export default zhCN;
