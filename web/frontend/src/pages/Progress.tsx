import { useState } from "react";
import { CalendarClock, Scale, Users } from "lucide-react";
import ContactList from "../components/ContactList";
import InterviewList from "../components/InterviewList";
import OfferCompare from "../components/OfferCompare";

type SubTab = "interviews" | "contacts" | "offers";

const SUBTABS: { key: SubTab; label: string; icon: React.ReactNode }[] = [
  { key: "interviews", label: "面试", icon: <CalendarClock size={15} /> },
  { key: "contacts", label: "联系人", icon: <Users size={15} /> },
  { key: "offers", label: "Offer 对比", icon: <Scale size={15} /> },
];

export default function Progress() {
  const [sub, setSub] = useState<SubTab>("interviews");

  return (
    <div className="space-y-6">
      <div>
        <h1 className="text-lg font-semibold text-white">进展</h1>
        <p className="mt-1 text-xs text-slate-500">
          投递之后才是真正的博弈——面试、联系人、Offer，都记在这里
        </p>
      </div>

      <div className="flex items-center gap-1">
        {SUBTABS.map((t) => (
          <button
            key={t.key}
            onClick={() => setSub(t.key)}
            className={`flex cursor-pointer items-center gap-1.5 rounded-full px-4 py-2 text-sm transition-all duration-200 ${
              sub === t.key
                ? "bg-accent/15 text-accent"
                : "text-slate-400 hover:bg-white/5 hover:text-slate-200"
            }`}
          >
            {t.icon}
            {t.label}
          </button>
        ))}
      </div>

      {sub === "interviews" && <InterviewList />}
      {sub === "contacts" && <ContactList />}
      {sub === "offers" && <OfferCompare />}
    </div>
  );
}
