# Glossary

The **internal terms** that appear across the docs and the changelog, defined once here; when you meet one in the text, look it up in this table.

Terms stay in Chinese on purpose (they are quoted verbatim in the changelog and in code comments); this page is their English reading companion.

简体中文版：[`glossary.md`](glossary.md)

| 术语（Term） | Meaning | Where it comes from / more |
|---|---|---|
| **两段式（写入）** | Every write first returns a preview + diff + token; it only lands after you confirm with the token — the single write channel across the project | contributing.zh-CN.md、（four-ends）`docs/four-ends.md` |
| **令牌** | The one-shot credential issued by step one of a two-phase write: bound to a workspace, carries a payload fingerprint, valid for 10 minutes, burned on use | `mcp/README.md`、contributing.zh-CN.md |
| **托管语义** | For mirror/sync, the destination directory is treated as *managed*: delete it there when it is deleted at the source, update it when the source changes | Usage guide, "Export to Obsidian notes" |
| **白名单（同步）** | The top-level entries `--sync-to` is allowed to touch (the eight table directories / `README.md` / `jobws.base` / material directories); everything outside the set is never touched | Usage guide、four-ends matrix |
| **四端矩阵** | Capability & error-code comparison across the four surfaces — CLI / AI host / editor plugin / desktop UI; source of truth `tools/four_ends_matrix.json` | `docs/four-ends.md` |
| **硬闸（闸门）** | A checkpoint that refuses to continue unless its condition holds (CI gates; historically the MCP "repo must sit beside the workspace" gate) | CHANGELOG |
| **壳层** | The outer layer of the MCP service: translates protocol calls into domain-layer calls and adds protocol-level test cases | CHANGELOG、`mcp/` |
| **shim（转发层）** | A compatibility file for an old import name: `sys.modules` forwarding + a deprecation warning, so old paths migrate smoothly | contributing.zh-CN.md、CHANGELOG |
| **领域层包化** | Moving the domain modules into the standalone `jobws-core` package (`jobws_core`), leaving only forwarding in the repo | Package README、CHANGELOG |
| **旧名水位** | The cap on how many old import names may remain: may only go down, and the shim is deleted at zero | `tools/legacy_imports_allowlist.txt` |
| **规模水位线** | The registered line-count cap for an oversized file: may only shrink; once below the threshold the entry must be removed (self-cleaning) | `tools/size_allowlist.txt`、contributing.zh-CN.md |
| **自洁强制** | When a watermark drops below its threshold the checker fails until the entry is deleted — keeps allowlists from rotting | contributing.zh-CN.md「代码卫生」 |
| **单一发布节点** | Mid-way batches do not bump / tag / release; everything ships once, after all batches are done | contributing.zh-CN.md「版本号体系」 |
| **版本号** | Month-granularity CalVer `YY.MM.N` (e.g. `26.9.0`): the tag, the changelog section, `package.json` and the in-app About box all show the same number; the third digit N = the Nth release of that month (a hotfix keeps the first two digits and only bumps N) | contributing.zh-CN.md「版本号体系」 |
| **指纹** | Three kinds: payload fingerprint (binds a token to its payload), row fingerprint (re-checks the row just before a delete lands), workspace fingerprint (the UI notices outside edits within ~10 s) | Usage guide、CHANGELOG |
| **应用根 / 数据根 / 允许根** | The three location concepts in path resolution: where the app's template lives (app root), where writable data lives (data root), the set of roots you may access (allowed roots) | CHANGELOG、`jobws_core.pathres` |
| **静默吞错** | The `except: pass` / empty `catch {}` style of "errors vanish without a word" — banned in this repo; at minimum, log it | contributing.zh-CN.md「代码卫生」 |
| **跨层测试** | A test that covers several layers cooperating (e.g. CLI → domain → files); stubs should target the package implementation, not the forwarding layer | CHANGELOG、`tests/` |
| **打桩** | Replacing dependency objects in tests to isolate the unit under test (e.g. replacing `approval._shell`) | CHANGELOG、`tests/` |
| **PEP 562 门面** | Module-level `__getattr__` that keeps the old "package as a single file" import semantics working | CHANGELOG |
| **拍板** | A decision point that needs the user's explicit confirmation; nothing is built before it | CHANGELOG.md、code comments |
| **截断诚实** | When content is truncated you must say so (e.g. "256 KB truncated") — never silently give less | Usage guide、contributing.zh-CN.md |
| **四道门** | The four-step admission check every new requirement goes through | contributing.zh-CN.md |
| **宿主提示缓存** | MCP hosts cache the tool list — always append new tools at the end of registration so the cache stays valid | CHANGELOG、`mcp/` |
| **批次（PR-A / PR-B / 批 4.6 / 批 8 / 收尾批）** | Internal plan batch numbers used to refer to a stretch of work; details live in the matching changelog entry | CHANGELOG |
| **候选池** | Where `ROADMAP.md` registers what was considered but deliberately not done now: one line + a **trigger condition** each; run the four gates before starting | `ROADMAP.md` |
| **毕业条件** | The checkable criteria under which the first proper release (`26.x`) counts as the 1.0-equivalent (14 days of unblocked self-use, main-flow smoke green, no open blocking findings, compatibility terms in force) | `docs/support-and-compatibility.md` |
| **ADR（决策记录）** | One-file-per-decision records (context / decision / alternatives considered / review triggers) under `docs/decisions/`; they answer "why it is this way", the roadmap only answers "what is next" | `docs/decisions/`、`docs/README.md` |
| **过渡纪律（Deprecated → Removed）** | A breaking change is deprecated first, stays read-compatible, is removed no earlier than one release later, and is listed explicitly in the changelog (even when no upgrade action is needed) | `CHANGELOG.md`、`docs/support-and-compatibility.md` |
| **冒烟** | The smallest end-to-end check (actually run the packaged artifact once); complements unit tests | contributing.zh-CN.md |
| **数据根契约** | The contract that the four surfaces resolve to the same root under the same configuration: priority `JOBWS_DATA_DIR > persisted choice > legacy default`, tri-state guards, contract matrix | `docs/specs/2026-10-04-single-canonical-data-root.md`、`tools/four_ends_matrix.json` |
| **canonical 数据根** | The domain data root uniquely picked by the resolver and confirmed by the user — **a logical role, not a fixed drive path**; fresh installs default to `<user_data_dir>/data` | Same as above |
| **legacy 根** | Locations that once served as the data root (repo checkout, `%APPDATA%\job-workbench` top level): kept for an observation window after migration, doubling as regression evidence | Same as above |
| **三态（数据根）** | The three non-normal outcomes of root resolution: `ambiguous` (multiple candidates) / `unavailable` (the persisted choice went stale — fail-closed) / `uninitialized` (root present, workspace not created yet — a normal first run) | Same as above |
| **root_id** | The **identity** of a data root (written into the root marker file): it survives moving the data, and it is what decides whether "two look-alike roots" are the same data | Same as above |
| **失效选择（stale selection）** | The persisted choice points at a path that is missing or not writable: reads / writes / destructive operations are all refused (`sys.dataRootUnavailable`); **silent fallback is forbidden** | Same as above |
| **控制面（`state/`）** | App-level state and pointers under `<user_data_dir>/state/` (data-root choice, migration state, …), kept separate from domain data (`personal/`) | Same as above |
