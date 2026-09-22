import { useEffect, useState } from "react";
import { CalendarClock, Mail, Scale, Users } from "lucide-react";
import ContactList from "../components/ContactList";
import InterviewList from "../components/InterviewList";
import OfferCompare from "../components/OfferCompare";
import MailList from "../components/MailList";
import { Tabs, TabsContent, TabsList, TabsTrigger } from "../components/ui/tabs";
import { PageHeader } from "../components/ui/page-header";
import { useTranslation } from "react-i18next";
import type { TranslationKey } from "../i18n/locales/zh-CN";

// 「进展」= **投递之后**的事（面试 / 邮件 / 联系人 / Offer）。
// 宣讲会与题库 2026-09-18 迁到「准备」板块——它们都发生在投递之前，
// 与这页的定位（「投递之后才是真正的博弈」）本来就不符；
// 技能文档也早写着宣讲会「是投递之前最早的信息入口」。
type SubTab = "interviews" | "mails" | "contacts" | "offers";

const SUBTABS: { key: SubTab; labelKey: TranslationKey; icon: React.ReactNode }[] = [
  { key: "interviews", labelKey: "progress.interviews", icon: <CalendarClock size={15} /> },
  { key: "mails", labelKey: "progress.mails", icon: <Mail size={15} /> },
  { key: "contacts", labelKey: "progress.contacts", icon: <Users size={15} /> },
  { key: "offers", labelKey: "progress.offers", icon: <Scale size={15} /> },
];

// 下钻 + 记忆：与「准备」页同一套协议——写方（看板 / 邮件台账等）往 sessionStorage
// 写「要落在哪个页签」再跳 `#progress`，本页 mount 时读一次即清；localStorage 记
// 「上次停留」——指纹刷新会整页 reload，不记住就把用户打回第一个页签（UX-2）。
const DRILL_KEY = "jobws_progress_tab";
const LAST_KEY = "jobws_progress_tab_last";

const TAB_KEYS = ["interviews", "mails", "contacts", "offers"] as const;

function readTab(key: string, kind: "session" | "local"): SubTab | null {
  try {
    const storage = kind === "session" ? sessionStorage : localStorage;
    const raw = storage.getItem(key);
    if (raw && (TAB_KEYS as readonly string[]).includes(raw)) {
      return raw as SubTab;
    }
  } catch {
    // 存储不可用：退回默认页签（不值得因此让页面挂掉）
  }
  return null;
}

export default function Progress() {
  const { t } = useTranslation();
  // 初值：下钻（一次性指令）优先，其次上次停留，最后默认「面试」
  const [sub, setSub] = useState<SubTab>(
    () => readTab(DRILL_KEY, "session") ?? readTab(LAST_KEY, "local") ?? "interviews"
  );

  // 下钻只生效一次：读过就清，否则下次从导航进来还会停在旧页签
  useEffect(() => {
    try {
      sessionStorage.removeItem(DRILL_KEY);
    } catch {
      // 存储不可用：无妨
    }
  }, []);

  // 页签切换即记忆——reload（外部编辑 / 写回触发的指纹刷新）后回到原页签
  const onTabChange = (value: string) => {
    const next = value as SubTab;
    setSub(next);
    try {
      localStorage.setItem(LAST_KEY, next);
    } catch {
      // 存储不可用：记忆失效无妨（不影响使用）
    }
  };

  return (
    <div className="space-y-6">
      <PageHeader title={t("nav.progress")} description={t("progress.subtitle")} />

      <Tabs value={sub} onValueChange={onTabChange}>
        <TabsList>
          {/* 参数不能叫 t：会遮蔽 useTranslation 给的翻译函数（骨架那批踩过同一个坑） */}
          {SUBTABS.map((item) => (
            <TabsTrigger key={item.key} value={item.key} className="gap-1.5">
              {item.icon}
              {t(item.labelKey)}
            </TabsTrigger>
          ))}
        </TabsList>
        {/* min-h 撑出区块（用户反馈 #5：此前 min-h 只把「可滚动区域」撑开、内容仍贴
            顶，视觉上下面还是空的）。拉伸走全链 flex：wrap(flex-col + min-h) → 激活
            的 TabsContent(flex-1) → List 根(flex-1) → 空态卡(flex-1)——内容短时空态
            卡长成整块，内容长时容器自然增长、页面照常滚动。
            注意 display 必须挂在 data-[state=active] 上：常驻的 display:flex 会盖过
            UA 对 [hidden] 的 display:none（非激活面板就会分走 flex 空间，2026-09-16
            实测当年 6 个面板各分到 55px、激活面板只剩 257px）。 */}
        <div className="flex min-h-[calc(100dvh-17rem)] flex-col">
        <TabsContent value="interviews" className="flex-1 flex-col data-[state=active]:flex">
          <InterviewList />
        </TabsContent>
        <TabsContent value="mails" className="flex-1 flex-col data-[state=active]:flex">
          <MailList />
        </TabsContent>
        <TabsContent value="contacts" className="flex-1 flex-col data-[state=active]:flex">
          <ContactList />
        </TabsContent>
        <TabsContent value="offers" className="flex-1 flex-col data-[state=active]:flex">
          <OfferCompare />
        </TabsContent>
        </div>
      </Tabs>
    </div>
  );
}
