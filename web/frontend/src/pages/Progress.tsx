import { useState } from "react";
import { BookOpen, CalendarClock, Scale, Users } from "lucide-react";
import ContactList from "../components/ContactList";
import InterviewList from "../components/InterviewList";
import OfferCompare from "../components/OfferCompare";
import QuestionBank from "../components/QuestionBank";
import { Tabs, TabsContent, TabsList, TabsTrigger } from "../components/ui/tabs";
import { useTranslation } from "react-i18next";
import type { TranslationKey } from "../i18n/locales/zh-CN";

type SubTab = "interviews" | "contacts" | "offers" | "questions";

const SUBTABS: { key: SubTab; labelKey: TranslationKey; icon: React.ReactNode }[] = [
  { key: "interviews", labelKey: "progress.interviews", icon: <CalendarClock size={15} /> },
  { key: "questions", labelKey: "progress.questions", icon: <BookOpen size={15} /> },
  { key: "contacts", labelKey: "progress.contacts", icon: <Users size={15} /> },
  { key: "offers", labelKey: "progress.offers", icon: <Scale size={15} /> },
];

export default function Progress() {
  const { t } = useTranslation();
  const [sub, setSub] = useState<SubTab>("interviews");

  return (
    <div className="space-y-6">
      <div>
        <h1 className="text-lg font-semibold text-foreground">{t("nav.progress")}</h1>
        <p className="mt-1 text-xs text-muted-foreground">{t("progress.subtitle")}</p>
      </div>

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
        <TabsContent value="interviews">
          <InterviewList />
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
      </Tabs>
    </div>
  );
}
