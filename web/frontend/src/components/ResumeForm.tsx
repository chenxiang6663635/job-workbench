import { useState } from "react";
import { ChevronDown, ChevronRight, Plus, Trash2 } from "lucide-react";
import { Input, Textarea } from "./ui/input";
import { Button } from "./ui/button";
import { FormField } from "./FormField";
import { useTranslation } from "react-i18next";

type ResumeData = Record<string, unknown>;

interface Props {
  data: ResumeData;
  onChange: (next: ResumeData) => void;
}

function Section({
  title,
  hint,
  children,
}: {
  title: string;
  hint?: string;
  children: React.ReactNode;
}) {
  const [open, setOpen] = useState(true);
  return (
    <div className="border-t border-border pt-3 first:border-0 first:pt-0">
      <button
        onClick={() => setOpen(!open)}
        className="flex w-full cursor-pointer items-center gap-1.5 text-left text-xs font-semibold uppercase tracking-wider text-muted-foreground transition-colors hover:text-foreground"
      >
        {open ? <ChevronDown size={13} /> : <ChevronRight size={13} />}
        {title}
      </button>
      {open && (
        <div className="mt-2 space-y-2">
          {hint && <p className="text-[11px] leading-relaxed text-muted-foreground">{hint}</p>}
          {children}
        </div>
      )}
    </div>
  );
}

function Row({
  label,
  value,
  onChange,
  placeholder,
}: {
  label: string;
  value: string;
  onChange: (v: string) => void;
  placeholder?: string;
}) {
  return (
    <FormField label={label}>
      <Input
        value={value}
        placeholder={placeholder}
        onChange={(e) => onChange(e.target.value)}
      />
    </FormField>
  );
}

export default function ResumeForm({ data, onChange }: Props) {
  const { t } = useTranslation();
  const meta = (data.meta ?? {}) as Record<string, string>;
  const basics = (data.basics ?? {}) as Record<string, string>;
  const extras = (data.extras ?? {}) as Record<string, unknown>;
  const education = (data.education ?? []) as Record<string, string>[];
  const projects = (data.projects ?? []) as Record<string, unknown>[];
  const work = (data.work ?? []) as Record<string, unknown>[];
  const skills = (data.skills ?? []) as Record<string, string>[];

  const patch = (key: string, value: unknown) => onChange({ ...data, [key]: value });
  const patchIn = (key: string, next: unknown) =>
    patch(key, { ...(data[key] as object), ...(next as object) });

  const patchList = (key: string, list: unknown[]) => patch(key, list);
  const patchItem = (key: string, idx: number, next: Record<string, unknown>) => {
    const list = [...((data[key] as Record<string, unknown>[]) ?? [])];
    list[idx] = { ...list[idx], ...next };
    patchList(key, list);
  };
  const addItem = (key: string, blank: Record<string, unknown>) =>
    patchList(key, [...((data[key] as unknown[]) ?? []), blank]);
  const delItem = (key: string, idx: number) =>
    patchList(
      key,
      ((data[key] as unknown[]) ?? []).filter((_, i) => i !== idx)
    );

  return (
    <div className="space-y-3">
      <Section title={t("resumeForm.sectionIntent")}>
        <Row
          label={t("resumeForm.intent")}
          value={meta.intent ?? ""}
          onChange={(v) => patchIn("meta", { intent: v })}
          placeholder={t("resumeForm.phIntent")}
        />
        <FormField label={t("resumeForm.profile")}>
          <Textarea
            className="min-h-[70px] resize-y leading-relaxed"
            value={meta.profile ?? ""}
            onChange={(e) => patchIn("meta", { profile: e.target.value })}
            placeholder={t("resumeForm.phProfile")}
          />
        </FormField>
      </Section>

      <Section title={t("resumeForm.sectionBasics")}>
        <div className="grid gap-2 sm:grid-cols-2">
          <Row label={t("resumeForm.name")} value={basics.name ?? ""} onChange={(v) => patchIn("basics", { name: v })} />
          <Row label={t("resumeForm.phone")} value={basics.phone ?? ""} onChange={(v) => patchIn("basics", { phone: v })} />
          <Row label={t("resumeForm.email")} value={basics.email ?? ""} onChange={(v) => patchIn("basics", { email: v })} />
          <Row label={t("resumeForm.city")} value={basics.location ?? ""} onChange={(v) => patchIn("basics", { location: v })} />
        </div>
      </Section>

      <Section title={t("resumeForm.sectionEducation")}>
        {education.map((e, i) => (
          <div key={i} className="space-y-2 rounded-lg bg-secondary/40 p-2">
            <div className="flex items-center justify-between">
              <span className="text-[11px] text-muted-foreground">{t("resumeForm.itemIndex", { index: i + 1 })}</span>
              <Button
                variant="ghost"
                size="icon"
                onClick={() => delItem("education", i)}
                className="h-6 w-6 text-muted-foreground hover:text-destructive"
                title={t("resumeForm.deleteItem")}
                >
                  <Trash2 size={13} />
                </Button>
            </div>
            <Row label={t("resumeForm.school")} value={e.school ?? ""} onChange={(v) => patchItem("education", i, { school: v })} />
            <Row label={t("resumeForm.major")} value={e.major ?? ""} onChange={(v) => patchItem("education", i, { major: v })} />
            <Row label={t("resumeForm.degree")} value={e.degree ?? ""} onChange={(v) => patchItem("education", i, { degree: v })} />
            <Row label={t("resumeForm.period")} value={e.period ?? ""} onChange={(v) => patchItem("education", i, { period: v })} placeholder={t("resumeForm.phPeriod")} />
            <Row label={t("resumeForm.extraNote")} value={e.note ?? ""} onChange={(v) => patchItem("education", i, { note: v })} />
          </div>
        ))}
        <Button
          variant="link"
          size="sm"
          onClick={() => addItem("education", { school: "", major: "", degree: "", period: "", note: "" })}
          className="h-auto gap-1 p-0 text-[11px] text-primary"
          >
          <Plus size={12} /> {t("resumeForm.addEducation")}
          </Button>
      </Section>

      <Section
        title={t("resumeForm.sectionProjects")}
        hint={`${t("resumeForm.projectHint1")}00_事实库${t("resumeForm.projectHint2")}`}
      >
        {projects.map((p, i) => (
          <div key={i} className="space-y-2 rounded-lg bg-secondary/40 p-2">
            <div className="flex items-center justify-between">
              <span className="text-[11px] text-muted-foreground">{t("resumeForm.projectIndex", { index: i + 1 })}</span>
              <Button
                variant="ghost"
                size="icon"
                onClick={() => delItem("projects", i)}
                className="h-6 w-6 text-muted-foreground hover:text-destructive"
                title={t("resumeForm.deleteItem")}
                >
                  <Trash2 size={13} />
                </Button>
            </div>
            <Row label={t("resumeForm.projectTitle")} value={(p.title as string) ?? ""} onChange={(v) => patchItem("projects", i, { title: v })} />
            <Row label={t("resumeForm.tag")} value={(p.tag as string) ?? ""} onChange={(v) => patchItem("projects", i, { tag: v })} placeholder={t("resumeForm.phTag")} />
            <FormField label={t("resumeForm.points")}>
              <Textarea
                className="min-h-[90px] resize-y leading-relaxed"
                value={((p.points as string[]) ?? []).join("\n")}
                onChange={(e) =>
                  patchItem("projects", i, { points: e.target.value.split("\n") })
                }
              />
            </FormField>
          </div>
        ))}
        <Button
          variant="link"
          size="sm"
          onClick={() => addItem("projects", { title: "", tag: "", points: [""] })}
          className="h-auto gap-1 p-0 text-[11px] text-primary"
          >
          <Plus size={12} /> {t("resumeForm.addProject")}
          </Button>
      </Section>

      <Section title={t("resumeForm.sectionWork")}>
        {work.map((w, i) => (
          <div key={i} className="space-y-2 rounded-lg bg-secondary/40 p-2">
            <div className="flex items-center justify-between">
              <span className="text-[11px] text-muted-foreground">{t("resumeForm.segmentIndex", { index: i + 1 })}</span>
              <Button
                variant="ghost"
                size="icon"
                onClick={() => delItem("work", i)}
                className="h-6 w-6 text-muted-foreground hover:text-destructive"
                title={t("resumeForm.deleteItem")}
                >
                  <Trash2 size={13} />
                </Button>
            </div>
            <Row label={t("resumeForm.org")} value={(w.org as string) ?? ""} onChange={(v) => patchItem("work", i, { org: v })} />
            <Row label={t("form.role")} value={(w.role as string) ?? ""} onChange={(v) => patchItem("work", i, { role: v })} />
            <Row label={t("resumeForm.period")} value={(w.period as string) ?? ""} onChange={(v) => patchItem("work", i, { period: v })} />
            <FormField label={t("resumeForm.points")}>
              <Textarea
                className="min-h-[70px] resize-y leading-relaxed"
                value={((w.points as string[]) ?? []).join("\n")}
                onChange={(e) => patchItem("work", i, { points: e.target.value.split("\n") })}
              />
            </FormField>
          </div>
        ))}
        <Button
          variant="link"
          size="sm"
          onClick={() => addItem("work", { org: "", role: "", period: "", points: [""] })}
          className="h-auto gap-1 p-0 text-[11px] text-primary"
          >
          <Plus size={12} /> {t("resumeForm.addWork")}
          </Button>
      </Section>

      <Section title={t("resumeForm.sectionSkills")}>
        {skills.map((s, i) => (
          <div key={i} className="flex items-start gap-2">
            <div className="flex-1 space-y-2">
              <Row label={t("resumeForm.group")} value={s.group ?? ""} onChange={(v) => patchItem("skills", i, { group: v })} placeholder={t("resumeForm.phGroup")} />
              <Row label={t("resumeForm.content")} value={s.items ?? ""} onChange={(v) => patchItem("skills", i, { items: v })} />
            </div>
            <Button
              variant="ghost"
              size="icon"
              onClick={() => delItem("skills", i)}
              className="mt-5 h-6 w-6 text-muted-foreground hover:text-destructive"
              title={t("resumeForm.deleteGroup")}
            >
              <Trash2 size={13} />
            </Button>
          </div>
        ))}
        <Button
          variant="link"
          size="sm"
          onClick={() => addItem("skills", { group: "", items: "" })}
          className="h-auto gap-1 p-0 text-[11px] text-primary"
          >
          <Plus size={12} /> {t("resumeForm.addSkillGroup")}
          </Button>
      </Section>

      <Section title={t("resumeForm.sectionExtras")}>
        <FormField label={t("resumeForm.research")}>
          <Textarea
            className="min-h-[60px] resize-y leading-relaxed"
            value={((extras.research as string[]) ?? []).join("\n")}
            onChange={(e) => patchIn("extras", { research: e.target.value.split("\n") })}
          />
        </FormField>
        <Row label={t("resumeForm.awards")} value={(extras.awards as string) ?? ""} onChange={(v) => patchIn("extras", { awards: v })} />
        <Row label={t("resumeForm.certificates")} value={(extras.certificates as string) ?? ""} onChange={(v) => patchIn("extras", { certificates: v })} />
      </Section>
    </div>
  );
}
