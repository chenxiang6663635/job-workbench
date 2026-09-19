import { useEffect, useState } from "react";
import { BookOpen, Megaphone, NotebookPen } from "lucide-react";
import NotesBrowser from "../components/NotesBrowser";
import QuestionBank from "../components/QuestionBank";
import TalkList from "../components/TalkList";
import { Tabs, TabsContent, TabsList, TabsTrigger } from "../components/ui/tabs";
import { PageHeader } from "../components/ui/page-header";
import { useTranslation } from "react-i18next";
import type { TranslationKey } from "../i18n/locales/zh-CN";

// 「准备」板块：**投递之前**的事归一处（宣讲会 + 题库 + 笔记）。
// 2026-09-18 从「进展」页迁出——那页的定位是「投递之后才是真正的博弈」，
// 而技能文档早就写着宣讲会「是投递之前最早的信息入口」（jwb-track/SKILL.md），
// 两句话一直是矛盾的；这次把页面归属对齐到语义。
type SubTab = "talks" | "questions" | "notes";

const SUBTABS: { key: SubTab; labelKey: TranslationKey; icon: React.ReactNode }[] = [
  { key: "talks", labelKey: "prepare.talks", icon: <Megaphone size={15} /> },
  { key: "questions", labelKey: "prepare.questions", icon: <BookOpen size={15} /> },
  { key: "notes", labelKey: "prepare.notes", icon: <NotebookPen size={15} /> },
];

// 看板「近 7 天宣讲会」点进来时带的页签初值（与追踪表/邮件台账的下钻同一套
// sessionStorage 协议：写方是 Dashboard，读方在 mount 时取一次后即清）。
const DRILL_KEY = "jobws_prepare_tab";

function readDrillTab(): SubTab | null {
  try {
    const raw = sessionStorage.getItem(DRILL_KEY);
    if (raw === "talks" || raw === "questions") return raw;
  } catch {
    // 存储不可用：退回默认页签（不值得因此让页面挂掉）
  }
  return null;
}

export default function Prepare() {
  const { t } = useTranslation();
  // 初值：下钻优先，其次默认「宣讲会」（时间敏感的事先看到）
  const [sub, setSub] = useState<SubTab>(() => readDrillTab() ?? "talks");

  // 下钻只生效一次：读过就清，否则下次从导航进来还会停在旧页签
  useEffect(() => {
    try {
      sessionStorage.removeItem(DRILL_KEY);
    } catch {
      // 存储不可用：无妨
    }
  }, []);

  return (
    <div className="space-y-6">
      <PageHeader title={t("nav.prepare")} description={t("prepare.subtitle")} />

      <Tabs value={sub} onValueChange={(v) => setSub(v as SubTab)}>
        <TabsList>
          {/* 参数不能叫 t：会遮蔽 useTranslation 给的翻译函数（进展页同款坑） */}
          {SUBTABS.map((item) => (
            <TabsTrigger key={item.key} value={item.key} className="gap-1.5">
              {item.icon}
              {t(item.labelKey)}
            </TabsTrigger>
          ))}
        </TabsList>
        {/* min-h 撑出区块 + display 挂 data-[state=active]：与进展页同一套。
            常驻 display:flex 会盖过 UA 对 [hidden] 的 display:none，非激活面板
            会分走 flex 空间（2026-09-16 实测：6 个面板各分 55px）。 */}
        <div className="flex min-h-[calc(100dvh-17rem)] flex-col">
          <TabsContent value="talks" className="flex-1 flex-col data-[state=active]:flex">
            <TalkList />
          </TabsContent>
          <TabsContent value="questions" className="flex-1 flex-col data-[state=active]:flex">
            <QuestionBank />
          </TabsContent>
          <TabsContent value="notes" className="flex-1 flex-col data-[state=active]:flex">
            <NotesBrowser />
          </TabsContent>
        </div>
      </Tabs>
    </div>
  );
}
