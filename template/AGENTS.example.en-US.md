# Candidate profile template — English companion

中文原版：`AGENTS.example.md`（两份结构逐节对齐；改动请同步）。

This is the English reading version of the candidate-profile template. **Headings keep their Chinese text** — the skills and docs reference sections by number and name (e.g. 「第三节 硬门槛事实」). Explanations are in English; the values you fill in may be in any language.

**How to use**: `jobws init` already creates `AGENTS.md` from the Chinese template. If you prefer English, copy this file's content into your workspace `AGENTS.md`, then fill in each item.

> This file is the factual baseline for any AI task in this workspace. JD scoring, resume rewriting and interview-material generation all read from here.
> Anything left unfilled is marked `[待填]`; when a scoring workflow meets `[待填]` it writes the gate verdict as "awaiting profile facts"（待补档案）— no score, no kill — and the parsed card names the missing fields (since 2026-09-24, no longer a fail). **Guessing is never allowed.**

---

## 一、定位 Positioning

<!-- One or two sentences: your background + the roles you target. This anchors the direction-fit score. -->

专业背景 Background：
求职方向 Target roles：
投递主线 Main thread：<!-- e.g. "thermal management", "front-end engineering", "data analysis". The two directions should be branches of one thread, not two unrelated lines -->

## 二、能力分层 Capability tiers

<!-- The criterion is not "have you heard of it" but "can you survive follow-up questions".
     Primary = can explain the principles, can derive, can take two layers of follow-ups
     Secondary = hands-on; you can support the claim but must state its boundary carefully
     Weak = book knowledge only, no engineering delivery
     Writing a Weak as Primary costs far more than omitting it: interviews expose it. -->

**Primary（核心技术底盘 core technical base）**

**Secondary（具备实操，谨慎表述 hands-on, state boundaries carefully）**

**Weak（知识性了解，无交付经历 book knowledge only, nothing delivered）**

## 三、硬门槛事实 Hard-gate facts

<!-- These six items directly decide whether a JD passes the eligibility gate; they are prerequisites for the workbench. Fill them in truthfully. -->

| 字段 Field | 取值 Value |
|---|---|
| 最高学历 Highest degree | `[待填]` |
| 毕业届数 Graduation cohort | `[待填]` |
| 专业方向 Major | `[待填]` |
| 外语水平 English level | `[待填]` |
| 可接受城市列表 Acceptable cities | `[待填]` |
| 其他硬性限制 Other hard constraints | `[待填]` |

## 四、经验资产 Experience assets

<!-- One block per experience asset. State: what it was, your own contribution boundary, verifiable numbers or evidence, and statements you must not overstate.
     Resume verbs, behavioural stories and the "experience match" dimension of JD scoring all come back here to verify. -->

**项目/经历一 Project / experience 1**

- 内容 What it was：
- 个人贡献边界 Your contribution boundary：
- 可验证证据 Verifiable evidence：
- 不能越界的说法 Statements you must not overstate：

**项目/经历二 Project / experience 2**

- 内容 What it was：
- 个人贡献边界 Your contribution boundary：
- 可验证证据 Verifiable evidence：
- 不能越界的说法 Statements you must not overstate：

**（按需增删 add or remove as needed）**

## 五、诚实红线 Honesty red lines

### 通用两条（任何人都适用，不可删除）Two universal lines (apply to everyone, do not delete)

1. Every resume verb must survive 5–10 minutes of follow-up questioning; verbs follow from the contribution facts — never upgrade "participated in" into "owned" across the board.
2. Answer knowledge gaps with an honest bridge (where the adjacent ability transfers from, how you are closing the gap) — never fabricate experience.

### 自定义红线 Custom red lines

<!-- Fill in the fact boundaries only you know — usually "what I cannot claim" and "how certain numbers must be phrased". Below is a real sample showing the level of detail to aim for. Replace it with your own. -->

**样例（暖通背景某候选人，替换掉）Sample (an HVAC-background candidate — replace it):**

- Do not claim the CNN front-end: the people-counting front-end was built by the team; my part was backend control, running the conditions, and result analysis
- "X%" must be phrased as "a research case shows", never as an engineering measurement
- Do not dress up data-center engineering delivery: simulation and case study only
- Project 1: only "validated conclusions vs exploratory candidates" — never say deployed
- Project 2: simulation, a single case, and the CO₂ trade-off only — never claim engineering rollout

**你的红线 Your red lines：**

- 
- 
- 

## 六、简历版本 Resume versions

| 用途 Use | 文件 File | 说明 Notes |
|---|---|---|
| 事实母版 Fact master | `02_简历工坊/简历_主版.md` | Not for applying; carries internal notes and contribution boundaries |
| 方向 A Direction A | `02_简历工坊/简历_<方向A>.md` | Submission copy |
| 方向 B Direction B | `02_简历工坊/简历_<方向B>.md` | Submission copy |

Multiple versions = one master + N derivatives; **only four things change**: target direction, profile, skill order, project phrasing. Project facts never change.

The PDF is generated from `02_简历工坊/pdf/resume_*.html`, not from the Markdown. Editing resume content means updating the HTML too.

Photo: overwrite `02_简历工坊/pdf/photo.jpg`. Without a photo, delete the `<img class="photo" ...>` line in the HTML.

## 七、领域与方向 Domain & direction

| 项 Item | 值 Value |
|---|---|
| 领域插件 Domain plugin | `template/profiles/<domain-id>/` |
| 默认方向 Default direction | `<direction-id>` |

## 八、待办 To-do

- [ ] 补齐第三节硬门槛事实 Fill in the Section 3 hard-gate facts (while unfilled, jobs land in "awaiting profile facts": not scored, not killed; scoring resumes once filled)
- [ ] 填写第五节自定义红线 Fill in your custom red lines (Section 5)
- [ ] 建立 ATS 关键事实清单 Create the ATS key-fact list `config/ats_required_facts.txt`
