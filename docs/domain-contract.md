# 领域插件贡献契约

> 这份文档回答一个问题：**不改一行核心代码，怎样让一个新领域跑起来**。
> 契约的判据唯二：本文与 `python tools/jobws.py lint domains`——校验器是契约的
> 可执行版本；两处若不一致，**以校验器为准**（CI 跑的是它）。

## 1. 什么是领域插件

三层架构里的领域层：`template/profiles/<domain-id>/`。

- `jobws init --domain <id>` 把插件整树复制进工作区 `<workspace>/config/`——**已存在的文件不会被覆盖**，对已有工作区重复 init 不会冲掉你改过的词典；
- 评分（`jd_score`）按 **ID** 查找：工作区 `config/` 优先，回退到插件目录（`resolve_profile`）；
- 复盘聚类（`report`）只读工作区 `config/failure_keywords.txt`，**不做插件回退**；文件缺失时退化为按「状态原因」原文频次统计（绝不虚构分类名）；
- 因此「新增领域」= 新增一个目录。仓库里没有任何 `if domain == ...` 分支——这是架构承诺，`lint domains` 与一条「真实插件必须合规」的测试一起守着它。

现成参考实现：`software-backend/`（软件后端与数据工程）、`hvac-cooling/`（暖通制冷与数据中心冷却）。

## 2. 目录结构与必备文件

```
<domain-id>/
├── profile.md            身份与元信息（本插件的"说明书"）
├── lexicon.md            三级词典（Primary / Secondary / Weak）
├── failure_keywords.txt  失败原因聚类关键词表
└── directions/
    ├── <direction-a>.md  方向 A：特有词 + 方向锚点表
    └── <direction-b>.md  方向 B（至少一个方向文件）
```

`<domain-id>` 只能用小写字母 / 数字 / 连字符（如 `hvac-cooling`）——ID 会被当查找键：含大写时 Windows 上碰巧能用、Linux / CI 上直接「找不到插件」。

### 2.1 profile.md

以身份表开头，**插件 ID 必须与目录名一致**（校验器会核对）：

| 项 | 值 |
|---|---|
| 插件 ID | `<domain-id>` |
| 名称 | 领域中文名 |
| 适用人群 | 哪些专业 / 背景的候选人在用 |
| 覆盖岗位 | 这个插件服务的岗位类型 |
| 内置方向 | `方向a`（说明）、`方向b`（说明） |
| 建立日期 | YYYY-MM-DD |

其后自由组织：结构说明、维护记录等。

### 2.2 lexicon.md

三级分层，每级一个 `## <层名>` 小节；**层名必须以 Primary / Secondary / Weak 开头**（评分侧的解析器按前缀识别）：

```
## Primary（3 分/项）
词条一、词条二、词条三

## Secondary（1.5 分/项）
……

## Weak（登记不扣分，触发风险提示）
……
```

每行用**顿号**分隔词条。分层的含义不是「会不会」，而是**「能不能经得起追问」**——写错分层的代价（面试露馅）远大于漏写（少几分）。

分值写在文件里：Primary 3 分/项、Secondary 1.5 分/项，技术匹配维度上限 30 分——调整不用改代码。

### 2.3 failure_keywords.txt

每行「**类别=关键词1,关键词2**」，`#` 开头为注释行：

```
简历与匹配度=简历,匹配,经历不符
竞争与名额=竞争激烈,名额,缩招
```

- **顺序敏感**：更具体的类别写在前面（先「学历门槛」再「竞争」）；
- 复盘时按顺序匹配「状态原因」，都没命中归入「其他 / 未归类」；
- 这是**你自己的归因口径**，随时按实际情况调整。

### 2.4 directions/*.md

每个方向一个文件：**该方向特有的补充词** + **方向锚点表**。方向 ID 即文件名（`backend.md` → `--direction backend`）。

词典与方向分离的理由：同一领域内不同方向共享大部分技术词汇，差异只在少数特有词与评分锚点，分开维护避免两处词典漂移。

## 3. 校验

```bash
python tools/jobws.py lint domains            # 仓库内全部插件
python tools/jobws.py lint domains --root <dir>
```

CI 跑同一条（同一实现）。校验内容：目录 ID 命名、必备文件与方向文件、
词典可解析且三层齐全、关键词表行格式、插件 ID 与目录名一致。

## 4. 边界：什么能改、什么不能

**能**（插件内自由）：词条与分层、方向文件内容、关键词类别、分值文案、profile 说明。

**不能**（改动等于破坏契约，校验器与解析器都会对不上）：

- 目录位置（必须 `template/profiles/<id>/`）与 ID 命名规则；
- 层名前缀 Primary / Secondary / Weak；
- 分隔符（词条用顿号；关键词用 `=` 与逗号）；
- 文件名（`profile.md` / `lexicon.md` / `failure_keywords.txt` / `directions/*.md`）。

**想改核心行为**（新的解析规则、新的评分维度、新的文件类型）——那超出插件边界，
请开 issue 走 [CONTRIBUTING.md](../CONTRIBUTING.md) 的新需求四道门。
