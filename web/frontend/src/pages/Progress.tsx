import { useState } from "react";
import { BookOpen, CalendarClock, Mail, Megaphone, Scale, Users } from "lucide-react";
import ContactList from "../components/ContactList";
import InterviewList from "../components/InterviewList";
import OfferCompare from "../components/OfferCompare";
import QuestionBank from "../components/QuestionBank";
import TalkList from "../components/TalkList";
import MailList from "../components/MailList";
import { Tabs, TabsContent, TabsList, TabsTrigger } from "../components/ui/tabs";
import { PageHeader } from "../components/ui/page-header";
import { useTranslation } from "react-i18next";
import type { TranslationKey } from "../i18n/locales/zh-CN";

type SubTab = "interviews" | "talks" | "mails" | "contacts" | "offers" | "questions";

const SUBTABS: { key: SubTab; labelKey: TranslationKey; icon: React.ReactNode }[] = [
  { key: "interviews", labelKey: "progress.interviews", icon: <CalendarClock size={15} /> },
  { key: "talks", labelKey: "progress.talks", icon: <Megaphone size={15} /> },
  { key: "mails", labelKey: "progress.mails", icon: <Mail size={15} /> },
  { key: "questions", labelKey: "progress.questions", icon: <BookOpen size={15} /> },
  { key: "contacts", labelKey: "progress.contacts", icon: <Users size={15} /> },
  { key: "offers", labelKey: "progress.offers", icon: <Scale size={15} /> },
];

export default function Progress() {
  const { t } = useTranslation();
  const [sub, setSub] = useState<SubTab>("interviews");

  return (
    <div className="space-y-6">
      <PageHeader title={t("nav.progress")} description={t("progress.subtitle")} />

      <Tabs value={sub} onValueChange={(v) => setSub(v as SubTab)}>
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
            实测 6 个面板各分到 55px、激活面板只剩 257px）。 */}
        <div className="flex min-h-[calc(100dvh-17rem)] flex-col">
        <TabsContent value="interviews" className="flex-1 flex-col data-[state=active]:flex">
          <InterviewList />
        </TabsContent>
        <TabsContent value="talks" className="flex-1 flex-col data-[state=active]:flex">
          <TalkList />
        </TabsContent>
        <TabsContent value="mails" className="flex-1 flex-col data-[state=active]:flex">
          <MailList />
        </TabsContent>
        <TabsContent value="questions" className="flex-1 flex-col data-[state=active]:flex">
          <QuestionBank />
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
