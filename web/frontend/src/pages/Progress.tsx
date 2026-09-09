import { useState } from "react";
import { BookOpen, CalendarClock, Scale, Users } from "lucide-react";
import ContactList from "../components/ContactList";
import InterviewList from "../components/InterviewList";
import OfferCompare from "../components/OfferCompare";
import QuestionBank from "../components/QuestionBank";
import { Tabs, TabsContent, TabsList, TabsTrigger } from "../components/ui/tabs";

type SubTab = "interviews" | "contacts" | "offers" | "questions";

const SUBTABS: { key: SubTab; label: string; icon: React.ReactNode }[] = [
  { key: "interviews", label: "面试", icon: <CalendarClock size={15} /> },
  { key: "questions", label: "题库", icon: <BookOpen size={15} /> },
  { key: "contacts", label: "联系人", icon: <Users size={15} /> },
  { key: "offers", label: "Offer 对比", icon: <Scale size={15} /> },
];

export default function Progress() {
  const [sub, setSub] = useState<SubTab>("interviews");

  return (
    <div className="space-y-6">
      <div>
        <h1 className="text-lg font-semibold text-foreground">进展</h1>
        <p className="mt-1 text-xs text-muted-foreground">
          投递之后才是真正的博弈——面试、联系人、Offer，都记在这里
        </p>
      </div>

      <Tabs value={sub} onValueChange={(v) => setSub(v as SubTab)}>
        <TabsList>
          {SUBTABS.map((t) => (
            <TabsTrigger key={t.key} value={t.key} className="gap-1.5">
              {t.icon}
              {t.label}
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
