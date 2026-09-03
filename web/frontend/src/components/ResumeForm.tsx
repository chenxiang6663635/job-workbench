import { useState } from "react";
import { ChevronDown, ChevronRight, Plus, Trash2 } from "lucide-react";

type ResumeData = Record<string, unknown>;

interface Props {
  data: ResumeData;
  onChange: (next: ResumeData) => void;
}

const inputCls =
  "w-full rounded border border-white/10 bg-ink-950 px-2 py-1.5 text-xs text-slate-200 outline-none transition-colors placeholder:text-slate-600 focus:border-accent/50";

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
    <div className="border-t border-white/5 pt-3 first:border-0 first:pt-0">
      <button
        onClick={() => setOpen(!open)}
        className="flex w-full cursor-pointer items-center gap-1.5 text-left text-xs font-semibold uppercase tracking-wider text-slate-400 transition-colors hover:text-slate-200"
      >
        {open ? <ChevronDown size={13} /> : <ChevronRight size={13} />}
        {title}
      </button>
      {open && (
        <div className="mt-2 space-y-2">
          {hint && <p className="text-[11px] leading-relaxed text-slate-500">{hint}</p>}
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
    <label className="block">
      <span className="mb-1 block text-[11px] text-slate-500">{label}</span>
      <input
        className={inputCls}
        value={value}
        placeholder={placeholder}
        onChange={(e) => onChange(e.target.value)}
      />
    </label>
  );
}

export default function ResumeForm({ data, onChange }: Props) {
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
      <Section title="求职意向与概况">
        <Row
          label="求职意向"
          value={meta.intent ?? ""}
          onChange={(v) => patchIn("meta", { intent: v })}
          placeholder="按岗位改，如：空调制冷 / HVAC 系统工程"
        />
        <label className="block">
          <span className="mb-1 block text-[11px] text-slate-500">个人概况</span>
          <textarea
            className={`${inputCls} min-h-[70px] resize-y leading-relaxed`}
            value={meta.profile ?? ""}
            onChange={(e) => patchIn("meta", { profile: e.target.value })}
            placeholder="两三句话概括方向与能力，留空则该区块不出现在 PDF 中"
          />
        </label>
      </Section>

      <Section title="基本信息">
        <div className="grid gap-2 sm:grid-cols-2">
          <Row label="姓名" value={basics.name ?? ""} onChange={(v) => patchIn("basics", { name: v })} />
          <Row label="电话" value={basics.phone ?? ""} onChange={(v) => patchIn("basics", { phone: v })} />
          <Row label="邮箱" value={basics.email ?? ""} onChange={(v) => patchIn("basics", { email: v })} />
          <Row label="城市" value={basics.location ?? ""} onChange={(v) => patchIn("basics", { location: v })} />
        </div>
      </Section>

      <Section title="教育经历">
        {education.map((e, i) => (
          <div key={i} className="space-y-2 rounded-lg bg-white/5 p-2">
            <div className="flex items-center justify-between">
              <span className="text-[11px] text-slate-500">第 {i + 1} 条</span>
              <button
                onClick={() => delItem("education", i)}
                className="cursor-pointer text-slate-500 transition-colors hover:text-bad"
              >
                <Trash2 size={13} />
              </button>
            </div>
            <Row label="学校" value={e.school ?? ""} onChange={(v) => patchItem("education", i, { school: v })} />
            <Row label="专业" value={e.major ?? ""} onChange={(v) => patchItem("education", i, { major: v })} />
            <Row label="学历" value={e.degree ?? ""} onChange={(v) => patchItem("education", i, { degree: v })} />
            <Row label="起止" value={e.period ?? ""} onChange={(v) => patchItem("education", i, { period: v })} placeholder="2024.09 — 至今" />
            <Row label="补充说明" value={e.note ?? ""} onChange={(v) => patchItem("education", i, { note: v })} />
          </div>
        ))}
        <button
          onClick={() => addItem("education", { school: "", major: "", degree: "", period: "", note: "" })}
          className="flex cursor-pointer items-center gap-1 text-[11px] text-accent transition-colors hover:text-accent-soft"
        >
          <Plus size={12} /> 添加教育经历
        </button>
      </Section>

      <Section
        title="项目经历"
        hint="每个要点写清「你做了什么 + 用什么方法 + 可验证的结果」。事实来自 00_事实库，改动需回查。"
      >
        {projects.map((p, i) => (
          <div key={i} className="space-y-2 rounded-lg bg-white/5 p-2">
            <div className="flex items-center justify-between">
              <span className="text-[11px] text-slate-500">项目 {i + 1}</span>
              <button
                onClick={() => delItem("projects", i)}
                className="cursor-pointer text-slate-500 transition-colors hover:text-bad"
              >
                <Trash2 size={13} />
              </button>
            </div>
            <Row label="项目名称" value={(p.title as string) ?? ""} onChange={(v) => patchItem("projects", i, { title: v })} />
            <Row label="标签" value={(p.tag as string) ?? ""} onChange={(v) => patchItem("projects", i, { tag: v })} placeholder="（如 SCI 二区 · 第二作者）" />
            <label className="block">
              <span className="mb-1 block text-[11px] text-slate-500">要点（每行一条）</span>
              <textarea
                className={`${inputCls} min-h-[90px] resize-y leading-relaxed`}
                value={((p.points as string[]) ?? []).join("\n")}
                onChange={(e) =>
                  patchItem("projects", i, { points: e.target.value.split("\n") })
                }
              />
            </label>
          </div>
        ))}
        <button
          onClick={() => addItem("projects", { title: "", tag: "", points: [""] })}
          className="flex cursor-pointer items-center gap-1 text-[11px] text-accent transition-colors hover:text-accent-soft"
        >
          <Plus size={12} /> 添加项目
        </button>
      </Section>

      <Section title="实习 / 工作经历">
        {work.map((w, i) => (
          <div key={i} className="space-y-2 rounded-lg bg-white/5 p-2">
            <div className="flex items-center justify-between">
              <span className="text-[11px] text-slate-500">第 {i + 1} 段</span>
              <button
                onClick={() => delItem("work", i)}
                className="cursor-pointer text-slate-500 transition-colors hover:text-bad"
              >
                <Trash2 size={13} />
              </button>
            </div>
            <Row label="单位" value={(w.org as string) ?? ""} onChange={(v) => patchItem("work", i, { org: v })} />
            <Row label="岗位" value={(w.role as string) ?? ""} onChange={(v) => patchItem("work", i, { role: v })} />
            <Row label="起止" value={(w.period as string) ?? ""} onChange={(v) => patchItem("work", i, { period: v })} />
            <label className="block">
              <span className="mb-1 block text-[11px] text-slate-500">要点（每行一条）</span>
              <textarea
                className={`${inputCls} min-h-[70px] resize-y leading-relaxed`}
                value={((w.points as string[]) ?? []).join("\n")}
                onChange={(e) => patchItem("work", i, { points: e.target.value.split("\n") })}
              />
            </label>
          </div>
        ))}
        <button
          onClick={() => addItem("work", { org: "", role: "", period: "", points: [""] })}
          className="flex cursor-pointer items-center gap-1 text-[11px] text-accent transition-colors hover:text-accent-soft"
        >
          <Plus size={12} /> 添加经历
        </button>
      </Section>

      <Section title="专业技能">
        {skills.map((s, i) => (
          <div key={i} className="flex items-start gap-2">
            <div className="flex-1 space-y-2">
              <Row label="分类" value={s.group ?? ""} onChange={(v) => patchItem("skills", i, { group: v })} placeholder="如 暖通 / 制冷" />
              <Row label="内容" value={s.items ?? ""} onChange={(v) => patchItem("skills", i, { items: v })} />
            </div>
            <button
              onClick={() => delItem("skills", i)}
              className="mt-5 cursor-pointer text-slate-500 transition-colors hover:text-bad"
            >
              <Trash2 size={13} />
            </button>
          </div>
        ))}
        <button
          onClick={() => addItem("skills", { group: "", items: "" })}
          className="flex cursor-pointer items-center gap-1 text-[11px] text-accent transition-colors hover:text-accent-soft"
        >
          <Plus size={12} /> 添加技能分类
        </button>
      </Section>

      <Section title="科研成果 / 奖项 / 证书">
        <label className="block">
          <span className="mb-1 block text-[11px] text-slate-500">科研成果（每行一条）</span>
          <textarea
            className={`${inputCls} min-h-[60px] resize-y leading-relaxed`}
            value={((extras.research as string[]) ?? []).join("\n")}
            onChange={(e) => patchIn("extras", { research: e.target.value.split("\n") })}
          />
        </label>
        <Row label="奖项" value={(extras.awards as string) ?? ""} onChange={(v) => patchIn("extras", { awards: v })} />
        <Row label="证书" value={(extras.certificates as string) ?? ""} onChange={(v) => patchIn("extras", { certificates: v })} />
      </Section>
    </div>
  );
}
