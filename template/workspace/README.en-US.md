# Workspace skeleton — English companion

中文原版：`README.md`（两份结构逐节对齐；改动请同步）。

This directory is an empty workspace skeleton. Running `python tools/jobws.py init --target <dir> --domain <plugin>` (e.g. `--domain hvac-cooling`; pick from the domain table in `docs/README.en-US.md`) copies it into your workspace, where you fill in your own content.

## The six modules

| Module | What goes in | Entry file |
|---|---|---|
| `00_事实库/` | Project fact cards — **the single source of facts; fill this first** | `_模板_事实卡.md` |
| `01_岗位池/` | One directory per job: the JD text + the parsed card | `_模板_解析卡.md` |
| `02_简历工坊/` | Resume Markdown + HTML templates + generated PDFs | `pdf/_模板_resume.html` |
| `03_面试准备/` | Self-introduction, project stories, question bank, behavioural & technical interviews, retros | `README.md` |
| `04_知识库/` | Know-how dictionaries and quick-reference cards, consulted on demand | `README.md` |
| `05_投递追踪/` | Tracker + one archive per application | `README.md`、`_示例_tracker.csv` |

Files starting with `_模板_` are samples to copy and fill in; files starting with `_示例_` are reference data for viewing only (safe to delete).

## Suggested filling order

**1. Build the fact base first.** It is the single source of facts — resume verbs, behavioural stories and the "experience match" dimension of JD scoring all trace back to it. Without it, everything downstream works from impressions: the verbs you write cannot survive questioning, and scores are guesses.

**2. Write the resume, generate the PDF.** Copy `pdf/_模板_resume.html` into `resume_<version>.html`. Note the PDF is generated from HTML, not from the Markdown.

**3. Parse JDs and start applying.** For each JD: create a job directory, save the original text, fill the parsed card, and run the full flow.

**4. Fill interview prep as needed.** Write the self-introduction and project narration first; note where you get stuck, then go patch the knowledge base at that point.

## Module notes

### 00_事实库 — the single source of facts

Each fact card states four things: what it was, **your contribution boundary**, verifiable evidence, and **statements you must not overstate**.

The last two are the ones people skip, and the ones that matter — they decide which resume verbs you may use and what you may not say in interviews.

### 03_面试准备 — express first, patch knowledge later

Do not start by learning. Compress your answer into something you can say in 30–90 seconds, get questioned and exposed, then come back and patch the specific gap.

Getting it wrong is the effective learning signal.

### 04_知识库 — come here only after getting stuck

Daily practice does not start here. Come back only when you said something wrong, or a follow-up went beyond what you can currently express.

### 05_投递追踪 — archiving is how you fight forgetting

JDs change, resumes iterate, memory blurs. Saving the JD snapshot and the resume version of each application is what lets you answer — three months later — "which version did I send them?"

## About 99_归档

Archived files and retired scripts go here — append only. Old directory names in historical documents are not rewritten: recording the state of that time faithfully is the whole point of it.
