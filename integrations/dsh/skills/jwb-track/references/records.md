# 从属表：面试 / 宣讲会 / 邮件 / 题库

四张表都是**独立文件**，靠 `关联记录` 外键指回主表 `tracker.csv`（可空），
**不改主表结构、不推进阶段、不入主表时间线**（唯一的例外是记录面试会在主表
时间线入账一条「面试」变更）。

## 面试记录

面试与岗位是一对多，存独立文件 `05_投递追踪/interviews.csv`（`面试id` 从 I001 起）。

```
jobws track interview add --app A001 --round 一面 --when "2026-09-08 14:00" --form 视频 --interviewer 张工 --questions "..." --answers "..." --retro "..."
jobws track interview add --company 某内推公司 --role 热力仿真 --round 笔试   # 未投递的面试也可记录
jobws track interview list                    # 时间倒序
jobws track interview list --app A001         # 只看某岗位的面试
jobws track interview show --id I001
jobws track interview update --id I001 --result 通过 --retro "..."
```

- 轮次：测评 / 笔试 / AI面 / 群面 / 一面 / 二面 / 三面 / HR面 / 终面 / 其他；形式：现场 / 视频 / 电话 / 其他；结果：待定 / 通过 / 未通过 / 取消
- 关联了记录时公司/岗位自动从主表带出，不必重复输入
- `--link` 存会议/作答链接（在线面试的入会地址、线上笔试的作答页）
- Web 端「进展」页可录入面试并导出 `.ics` 日程（提前 1 小时提醒）

## 宣讲会 / 招聘会

宣讲会存独立文件 `05_投递追踪/talks.csv`（`宣讲会id` 从 T001 起），是投递之前
最早的信息入口。

```
jobws track talk add --company 某公司 --when "2026-09-20 14:00" --form 线上 --attend 待定 --gain "讲了流程"
jobws track talk add --app A001 --attend 参加     # 关联已有投递记录（公司自动带出）
jobws track talk list                             # 时间倒序
jobws track talk update --id T001 --attend 参加
```

- 形式：线上 / 线下 / 其他；是否参加：待定 / 参加 / 不参加
- 未关联记录时必须给 `--company`；`--app` 指到不存在的记录会被拒绝
- 写入支持 `--preview` 两段式（同 `track add`：预览拿令牌 → `jobws apply <令牌>` 落盘）
- Web 端「准备」页的「宣讲会」页签可录入并导出 `.ics` 日程（看板「近 7 天宣讲会」可直达）

## 邮件

往来邮件（面试邀约、笔试通知、拒信……）存独立文件 `05_投递追踪/mails.csv`
（`邮件id` 从 M001 起），用「关联记录」指回投递（可空）；**只入账与查询，
不自动推进任何阶段**——改阶段一律人工确认。

```
jobws track mail add --subject "面试邀请（一面）" --app A001 --tag 邀约 --from "hr@example.com" --when "2026-09-16 10:00"
jobws track mail add --subject "笔试通知" --message-id "abc@example.com"   # 消息id（Message-ID）可空，有则用于去重
jobws track mail add --subject "面试邀请" --meeting-link "https://meeting.tencent.com/dm/abc123"  # 入会链接（可空）
jobws track mail list --app A001                  # 某条投递的往来邮件
jobws track mail update --id M001 --tag 面试
```

- 方向：收 / 发（默认收）；标签：通知 / 邀约 / 笔试 / 面试 / 拒信 / 其他（默认其他）
- 主题必填；`--app` 指到不存在的记录会被拒绝；消息id 重复会被拒绝（同一封邮件不要导两遍）
- **会议链接**列承接解析出的入会地址（腾讯会议 / Zoom / Teams / Meet…）：界面「从邮箱拉取」的解析建议卡可一键写入，也可在「进展 → 邮件」行内打开或复制
- 写入支持 `--preview` 两段式（预览拿令牌 → `jobws apply <令牌>` 落盘）
- Web 端「进展」页的「邮件」页签可录入、行内改标签；有 Message-ID 的邮件可「打开原邮件」（Gmail 搜索深链），其余邮箱（Outlook / QQ / 163 等）给「复制主题去邮箱搜索」的降级提示

## 题库

题库是「要准备的题」，与面试记录（「被问过的事实」）**分开**存：独立文件
`05_投递追踪/questions.csv`（`题目id` 从 Q001 起）。状态三态：`未看` / `看过` /
`会了`（改成「会了」时自动记「最近复习」）；来源四类：`自拟` / `笔试回忆` /
`面试记录` / `导入`。

```
jobws bank add --title "讲讲 TCP 三次握手" --domain 技术面 --subject 网络 --answer "三次握手……"
jobws bank list --status 未看 -k TCP
jobws bank update --id Q001 --status 会了
jobws bank import                      # 从 03_面试准备/**/*.md 只读解析 → 预览 → 确认落盘
```

- `add` / `update` / `import` 都是预览后凭 `jobws apply <令牌>` 落盘的**两段式**；`import` 跳过模板（`_模板_*`）与 README，解析是启发式（题目取一级标题、领域取子目录），**Markdown 只读、不动用户文件**
- 这道题被哪家公司问过：靠 `关联公司` / `关联岗位` 自由文本（岗位还没进投递表也能先记）
- Web 端「准备」页题库 tab 两个视图：「我的题库」（可筛选、可导入，点开行可改答案要点 / 标三态 / 调难度）/「被问过的」（按公司 + 岗位聚合的面试问题）
