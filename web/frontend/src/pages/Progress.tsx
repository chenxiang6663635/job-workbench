import { useState } from "react";
import { BookOpen, CalendarClock, Megaphone, Scale, Users } from "lucide-react";
import ContactList from "../components/ContactList";
import InterviewList from "../components/InterviewList";
import OfferCompare from "../components/OfferCompare";
import QuestionBank from "../components/QuestionBank";
import TalkList from "../components/TalkList";
import { Tabs, TabsContent, TabsList, TabsTrigger } from "../components/ui/tabs";
import { PageHeader } from "../components/ui/page-header";
import { useTranslation } from "react-i18next";
import type { TranslationKey } from "../i18n/locales/zh-CN";

type SubTab = "interviews" | "talks" | "contacts" | "offers" | "questions";

const SUBTABS: { key: SubTab; labelKey: TranslationKey; icon: React.ReactNode }[] = [
  { key: "interviews", labelKey: "progress.interviews", icon: <CalendarClock size={15} /> },
  { key: "talks", labelKey: "progress.talks", icon: <Megaphone size={15} /> },
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
        {/* 撑满视口剩余高度（批 4 编排总则）：内容少时页面下半部不再裸露背景——
            子面板内部的列表/详情两栏因此获得等比拉伸的高度（各自内部滚动） */}
        <div className="min-h-[calc(100dvh-17rem)]">
        <TabsContent value="interviews">
          <InterviewList />
        </TabsContent>
        <TabsContent value="talks">
          <TalkList />
        </TabsContent>
        <TabsContent value="questions">
          <QuestionBank />
        </TabsContent>
        <TabsContent value="contacts">
          <ContactList />
        </TabsContent>
        <TabsContent value="offers">
          <OfferCompare />
        </TabsContent>
        </div>
      </Tabs>
    </div>
  );
}
