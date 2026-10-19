# `py/path-injection` 182 条存量分诊（2026-10-18，第二版：外部审计后修正口径）

> **目的**：把"182 条告警"从一句笼统的话变成**可逐条处置**的清单，并说明为什么其中相当一部分
> 不是缺口。**本文只做分诊，不做任何 dismissal**——那是风险接受动作，须用户批准后执行。
>
> **与 #325 的关键区别**（决定了能不能动手）：这 182 条是 `main` 上的**既有告警，有告警编号**
> （`gh api .../code-scanning/alerts/{n}` 可取）；而 #325 那 4 条只存在于 PR 分析结果里、
> **没有编号、无法 dismiss**。所以本文的结论是可执行的。

## 一、数据（可复核）

182 条，分布在 **31 个文件**。按层：

| 层 | 条数 |
|---|---:|
| 协议层 `web/backend/**` | 82 |
| 领域层 `packages/jobws-core/**` | 89 |
| CLI `tools/**` | 11 |

头部 6 个文件占 **102 条（56%）**：`routers/resume.py` 32、`routers/system.py` 17、
`routers/jobs.py` 14、`core:dataroot_migrate.py` 14、`core:jd_gap.py` 13、
`core:workspace_io.py` 12。其余 25 个文件共 80 条。

## 二、分诊方法与它的上限（先说清，免得被当成结论）

**方法**：对每条告警取**所在函数**的源码，看其中是否引用本仓自研校验器——
`containment.escape_reason` / `deps.safe_join` / `containment.within_any` /
`workspace_read.read_in_workspace` / `ro_files.inside` / `resolve_within_workspace`。

**上限（重要）**：校验**常常在调用方**。领域层与 helper 文件的函数级判定会大面积显示"无"，
但那不代表没防——协议层验完路径再调 core 做 I/O，正是本仓的既有形状。所以函数级判定只是
**第一道筛子**，真正的判据是**调用链**。

## 三、函数级判定（头部 6 文件，102 条）

| 文件 | 条数 | 函数内有校验器 | 无 |
|---|---:|---:|---:|
| `routers/jobs.py` | 14 | **14** | 0 |
| `routers/resume.py` | 32 | 8 | 24 |
| `routers/system.py` | 17 | 0 | 17 |
| `core:dataroot_migrate.py` | 14 | 0 | 14 |
| `core:jd_gap.py` | 13 | 0 | 13 |
| `core:workspace_io.py` | 12 | 0 | 12 |

形态很清楚：**协议层有校验器，core/helper 全无**——与上面的上限一致。

## 四、已验证"上游已防"的两类（附证据）

### A. 协议层验完再调 core —— `jobs.py` 全部 14 条

`jobs.py` 的 14 条所在函数**全都**引用校验器，其中 `job_gap` 是最清楚的样本：

```python
def job_gap(job_id: str, ws: str = Depends(workspace_dir), resume: str = None):
    job_dir = safe_join(ws, DIR_JOBS, job_id)        # ← 校验在这里
    if not os.path.isdir(job_dir):
        raise ApiError(404, "job.notFound", ...)     # ← 越界即 404，不落盘
    ...
    jd_gap.resolve_profile(...)                      # ← core 只拿到已验过的路径
```

→ 因此 `core:jd_gap.py` 的 **13 条**属"上游已防"（CodeQL 追不到跨函数的校验）。

### B. 白名单范式 —— `system.py` 的 `open_folder`

S2 边界矩阵已核实：`_open_target` 只接受**预设键**（workspace/snapshots/dataRoot），
可执行文件是**字面量**——正是 CodeQL 自己示例里的 GOOD 范式。本文的校验器清单没覆盖这种
形态，所以它显示"无"，但结论是**安全**。

## 五、仍待人工核的（不猜，列清单）

| 对象 | 条数 | 要核什么 |
|---|---:|---|
| `routers/system.py` 除 open_folder 外 | 15 | `system_paths` / `backup_workspace` / `_apply_retention` / `_iter_files`——预设键白名单是否覆盖全部路径来源 |
| `routers/resume.py` 的 24 条 | 24 | 逐个函数看路径是否经 `safe_join`/`escape_reason`（该文件另有 8 条已有，说明范式在；剩下的是漏检还是真缺） |
| `core:workspace_io.py` | 12 | 这是**helper 本身**；核它的调用方是否都传已验路径 |
| `core:dataroot_migrate.py` | 14 | 调用方 `data_root.py` 是否已做计划校验（blocked → 409 / 指纹复核）；注意迁移是"用户指定目标根"，属功能本身 |
| 其余 22 个文件 | 80 | 未逐条过（只做了文件级：其中 57 条在"文件引用过校验器"的 Web 文件里） |

**结论（2026-10-18 外部审计后修正）**：

| 分组 | 原口径 | 修正后 |
|---|---|---|
| `jobs.py` 14 | 全部已防 | 逐条核对 source→sink 后裁决（函数内有校验器 ≠ 每条流都安全） |
| `jd_gap.py` 13 | Web 上游已防 | **不成立**——Web 之外还有 CLI 入口；且 #339 实测该文件的 `domain`/`direction` 可穿越、上游防护此前并不存在 |
| `resume.py` 8 | 函数内有校验器 | 尚不能直接视为已防，需补各自的数据流 |
| `system.open_folder` 2 | 白名单保护 | 证据相对充分，可作首批精审 |

**待人工核 145 条**（口径不变）。

> #339 已把 `jd_gap.py` 从「上游已防」里划掉：外部审计质疑「不能仅凭模板目录位于应用根下就把 `domain` 视为可信」，探针实证 `domain="../../x"` 与 `direction="../../../../x"` 都能读到 `template/profiles` 之外且**零警告**——即该处上游防护此前并不存在。这是「补证据」的第一批实际产出。

## 六、建议的推进方式（须批准后执行）

1. **先 dismiss 证据充分的**：A 类（jobs 14 + jd_gap 13）+ B 类（system 的 open_folder 2），
   共约 29 条，理由统一为"本地单用户工具；路径已由 `safe_join` 校验，CodeQL 不识别自定义
   sanitizer；详见 report_path_injection_triage.md"；
2. **第五节清单逐个人工核**，每核完一批 dismiss 一批，**每批在 PR 留记录**（风险接受必须可审计）；
3. **不按文件 `paths-ignore`**：那会连带关掉该文件未来真正的告警（#325 已示范过这个代价）。

命令模式（**本文未执行**）：

```bash
gh api --method PATCH repos/chenxiang6663635/job-workbench/code-scanning/alerts/{n} \
  -f state=dismissed -f dismissed_reason="won't fix" \
  -f dismissed_comment="路径已由 safe_join 校验；CodeQL 不识别自定义 sanitizer。见 docs/research/report_path_injection_triage.md"
```

## 七、复现（不依赖任何未入库文件）

分诊用的是两步，都可以用仓库现成工具重跑：

**① 拉全量告警并统计**

```powershell
1..3 | ForEach-Object { gh api "repos/chenxiang6663635/job-workbench/code-scanning/alerts?state=open&per_page=100&page=$_" }
```

**② 对某文件做函数级判定**（判据见 §二）：从告警行往上找最近的 `def`，取该函数体，
检查是否出现 `escape_reason` / `safe_join` / `within_any` / `read_in_workspace` / `inside(`。

第一轮用的临时脚本放在 `.codebuddy/tmp/triage*.py`（**不入库、会随会话清理**）——若要固化，
应移进 `tools/` 并补测试，这是后续项，本文不主张现在做。
