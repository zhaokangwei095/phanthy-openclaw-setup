# 05 · 工作流与自动化脚本

本文件把「新闻 / 小说 / 漫画 / 短剧」四类发帖工作流和心跳自动化脚本整理成可执行步骤。所有接口前先查最新 `skill.md`。

## 0. 通用发帖前置（四类共用）

1. **接口实时校验**：每次注册/发帖/回复前查 `skill.md`，动态解析接口地址、Payload、Headers。
2. **视觉风格自适应**：按选题意境/受众/领域定义风格（3D 渲染、极简插画、日系动漫、复古胶片、赛博朋克、专业测评图…），**严禁固定「真人感」**。封面含**中文标题**，置于顶部 15-20%，白色+轻微阴影，不遮主体，规格 **3:4**。
3. **内容标准**：按题材调用**对应的 post-review**（小说 / 科普 / 短剧口径各不相同）多轮自检；不通过**本地改**，**严禁发测试帖**。
4. **字段纪律**：标题与正文分开；正文不放链接（图片走 `file_id`）；**正文不重复标题（发送前 `guard.py clean-body` 自动删除 body 开头重复标题）**；正文无 `<img>`。
5. **来源纪律**：**只有【科普】【新闻】需要附"定位到具体新闻 URL"的来源**；小说、短剧、漫画、娱乐等**不需要**来源。
6. **发帖前复述**：向用户说明「上传图片/选题/正文/生图字段是否清晰」，逐条点出注意项，用户确认后再发。
7. **🚫 发送瞬间闸门（禁止测试帖）**：调用发布接口前逐条自检——①是不是测试/占位/试探帖？②对应 post-review 过了吗？③用户明确同意了吗？④标题/正文/媒体 `file_id` 齐吗？⑤该选题已有 `post_id` 吗？任一不满足**禁止发送**；接口调试用 dry-run，绝不发线上（详见 `references/03` §0）。
8. **修复后媒体确认**：帖子被拒/出问题进入修复阶段后，**修复好的新图片必须先发用户查看确认**，用户确认「图可以」后才允许 PATCH 重发；未确认不得发送。

## 0.5 发布前试创作闸门（每个新智能体必做）

新智能体在**正式发布 / 开启自动发帖之前**，必须先走一遍「试创作 → 用户决策」：
1. 选题确认后，**完整创作一条**（标题 + 正文 + 封面/内容图，用 `gemini_image` 技能）。
2. 跑对应题材的 post-review 自检。
3. 把成品（正文 + 图片 + 审核结论 + 创作思路）发给用户，请其决定。
4. 按意见本地修改，可多轮，直到用户**明确说「满意，可以发」**。
5. 拿到明确同意后，才把该条置 `READY` 并开始正式发布。
6. **用户允许发布时，先询问「每天发多少篇、什么时间发」的频率/排期**，据此配置自动发帖；**不得擅自默认 12 篇/天**，未确认频率前不开启自动发帖。

> 台账状态约束：首条 `REVIEWING → AWAITING_USER_APPROVAL → READY`；**用户未同意前禁止 `READY`/`PUBLISHING`，也禁止开启自动发帖**。

## 0.6 题材 → 必用内容 skill 白名单（创作前必须加载）

> 创作前先按题材加载对应内容技能，并在台账记录 `skill` 名与版本；**未加载不得进入 `DRAFTING`**（防跑偏）。

| 题材/环节 | 必用 skill（匹配本环境已安装的） |
|---|---|
| 小说 / 网文 | `story`（及 `story-long-write` / `story-short-write` / `story-cover` / `story-deslop`） |
| 探险/脑洞图文 | `explore-uncanny` |
| 小说封面 | `story-cover` |
| 生图 / 上色 | `gemini_image`（内置，无需安装） |
| 审核 | 本工作区按题材自封装 `post-review`（`references/04`） |

- 若题材无匹配 skill：用通用创作 + 本文件工作流，并在台账记 `skill: none`。
- **每轮开工先「锚定复述」**：我是谁 / 发什么题材 / 当前步骤 / 禁止事项（防上下文漂移）。

## 1. 新闻/图文发帖工作流

- **选题**：从 `选题库/` 按序取未发选题；原文需写清来源并**定位到具体新闻 URL**。
- **封面**：按 `TOOLS.md` 风格，生成带不同中文标题排版的封面，存 `covers/<选题>/`。
- **正文仿写**：基于选题原文改写（去掉推广），<1500 字扩写至 1500+（按主题与审核标准定），>1500 字做最小改动仿写；结尾附原文参考链接。
- **配图**：生成 3-4 张与选题关键内容相关的图文（防错传）。
- **上传**：`files/upload-authorizations` → PUT → `complete` → 取 `file_id`。
- **审核**：post-review 自检通过后再发。
- **检查**：发后轮询 `GET /posts/<id>` 看 `review_status`，被拒读原因→修复→**PATCH 完整内容（含媒体）**。

## 2. 小说发帖工作流

详见 `references/03-publishing-api.md` 第 3 节。要点：
- 先装**蒸馏 skill**（nuwa-skill）严格复刻主角/作者「灵魂」，产出 SOUL/IDENTITY/TOOLS/USER。
- 爬取小说内容与图片存本地；用**选题库台账**（`references/07`：每章一条记录、状态机跟踪选题/发布/审核/帖子 id/驳回原因/防重复）统一管理，不要另建状态文件。
- 拆章：识别「第X章 / 第1章 / Chapter 1 / 序章 / 楔子 / 番外」；保留原文件不改写；不确定边界问用户。
- 发布前确认：精确书名、章节数、章节标题、chapterNumber 映射、起始章、发布 Agent、频率、封面方案。
- 章节审核：连载每章 ≥1500 字；正文段首 `U+3000 U+3000`；不重复标题；不发参考源（省略 `sourceUrls`）；不擅自扩写/合并/拆分。
- 封面：至少 1 张有效封面；上传后用 `GET/HEAD` 校验 `publicUrl`（200、`image/*`、长度>0）。
- 发布成功判定：`success=true`、`post.id` 存在、`novel` 非 null、`novel.title` 与目标一致、`novel.chapterNumber` 对、`review.passed=true`，满足才标 `AUTO_REVIEW_PASSED`；`novel=null` 说明误发成普通帖→立即停队交人工；`review.passed=false`→存 `post.id`/`url`/`reason`，停队，修复后用相同 `novelTitle`+`chapterNumber` 重提。

### 小说自动发布状态机
```
PENDING → VALIDATING → READY → UPLOADING_COVER → PUBLISHING
        → AUTO_REVIEW_PASSED → MANUAL_REVIEW_MONITORING
异常：BLOCKED / UPLOAD_FAILED / PUBLISH_FAILED / AUTO_REVIEW_FAILED
      / NOVEL_NOT_MATCHED / MANUALLY_REJECTED / NEED_HUMAN
```
- 每次只认 `manifest.json` + `publish-state.json`；按 `chapterNumber` 升序发下一章；用文件/DB 锁防并发；一次最多 1 章；失败即停不跳章。
- 幂等键：`发布Agent + novelTitle + chapterNumber`；超时先查本地是否已存响应，无法确认→`NEED_HUMAN`。
- 默认 `enabled=false`；生成脚本先 **dry-run**（只输出将发章节/书名/章号/标题/字数/封面状态/Payload 摘要/阻塞问题，**不调真实发布接口**）；用户明确「启用自动发布」后才置 `true`。

```json
{"enabled": false, "timezone": "Asia/Shanghai", "schedule": [],
 "maxChaptersPerRun": 1, "stopOnAnyFailure": true,
 "requireAutoReviewPassBeforeNext": true}
```

## 3. 漫画发帖工作流

- **源图**：命名 `{卷号}_{页码}.jpg`（卷 01-09 为 `01_xxx.jpg`，卷 10+ 为 `10_xxx.jpg`）。
- **分卷分组**：每卷约 190 张，按每话 10 张分组；卷末不足 9 张时并入上一组。
- **上色（调用内置 `gemini_image` 技能）**：
  - **不要自己配 Gemini API key、不要直连生图路由**——生图/上色是 OpenClaw 内置技能 `gemini_image`，创建小龙虾时已自带，直接调用即可（底层模型与鉴权由环境负责）。
  - 调用方式：把「黑白漫画原图 + 上色指令」交给 `gemini_image` 技能，由它返回彩色图。
  - 上色指令（prompt）：`将这张黑白漫画图片进行彩色化上色。保持原有漫画风格、线条和构图完全不变，只把黑白灰度转彩色。角色服装、场景、背景用合适颜色填充。日式少年漫画风格，色彩鲜明自然。不要添加文字或改变画面。`
  - 建议 `imageSize=2K`；失败重试 3 次、间隔 10s，串行避免限流；存 `.../v{卷号}/ch{章}_p{序号}.jpg`。
- **上传**：走第 1 节三步上传。
- **发帖**：`title="{书名} 卷{XX} 第{X}话"`（无「彩色修复版」「AI」字样）；正文=固定作品简介(~1000字)+章节概览；`images` ≥8-9 张；`tags` 含 `漫画`；`novelTitle` 填书名。
- **断点续传**：进度存 `/tmp/..._progress.json`（`{"published":{"v05_ch3":"post_id"}}`），已发跳过。

## 4. 短剧发帖工作流

- **素材**：用**夸克网盘技能**按 csv 里的分享链接转存到网盘目录并下载到 `workspace/downloads/序号-ID-剧名/`（内含 `第x集.mp4` 与 `covers/`）。
  - 集数缺失或单集 >50MB → 跳过该剧，在 csv「备注」写明，人工处理；先发正常下载的。
- **封面**：优先用分享自带图；无则搜同名短剧封面；仍无则生图（花字封面，上半部标题，体现主要情节，人物与视频一致——截关键帧解析后生成）。
- **发布**：`title="剧名|第x集|全x集"`；`body` 检索互联网剧情简介自拟；`tags` 必含 `视频`；`drama={"title"/"id", "episode_number"}`。
- **状态回写**：下载/发布完成后更新 csv 的「是否下载/是否发布/备注」；一部发完再下一部。

## 5. 心跳自动化脚本

### 5.0 调度模型（云沙盒无 cron · 用 Python 伪定时）

- 云端**不允许 cron / Windows 计划任务 / at / systemd timer**；系统有定期心跳即可。
- 每个脚本开跑先判断是否到窗口，用状态文件做伪定时：
  ```bash
  python scripts/guard.py should-run --name refill-topics --interval 86400 --state .state/scheduler.json --mark \
    || exit 0   # SKIP 时直接退出，不做活
  ```
- `should-run` 读 `.state/scheduler.json` 里的 `last_run`，`now-last >= interval` 且落在时间窗才 `RUN`（`--mark` 会写回 last_run）。**这就是替代 cron 的方式。**

| 脚本 | 触发（伪定时） | 动作 |
|---|---|---|
| `refill-topics` | `should-run` 86400s（每日） | 检查 `选题库` 是否 ≥24（按需 ≥20），不足则爬取新选题；**记录来源到具体新闻 URL**，落盘防丢 |
| `audit-followup` | `should-run` 86400s（每日） | 拉取已发帖审核状态；被拒读原因→对照 `skill.md` 与 post-review 复盘，用 self-improving-agent 把教训写入 status json |
| `publish-daily` | `should-run` 按用户确认频率 | 按选题库顺序自动发，**发帖频率由用户确认（见 §0.5 第6点，不默认 12 篇/天）**；每篇发前过 `guard.py` 校验；被拒读原因→修复→确认新图→**PATCH 完整内容(含媒体)**→再发下一篇 |
| `review-log` | 每次发帖后 | 记录机审/人审结果、帖子 id、驳回原因（发帖响应同步返回机审原因） |
| `heartbeat` | 每轮心跳 | 先 `guard.py skill-check`，再状态巡检；`guard.py drift` 连续失败达阈值→熔断暂停并通知 owner |

> 以上脚本的选题与状态**统一读写 `选题库/topics.jsonl`**（状态机与约束见 `references/07`，工具 `scripts/topic_library.py`），禁止在别处旁路维护状态。

### 自动发帖主流程（Step）
```
Step1 心跳触发：读 HEARTBEAT.md；选题库未发 <24(或<20) → 先补选题
Step2 检查今日已发数
Step3 生成内容：取下一篇原文 → 仿写 ≥1500 字（Markdown，标题不重复、H2/H3/列表/表格、参考来源）
Step4 生成图片：封面 3:4 + 内容图 3-5 张（3:4，贴合内容）
Step5 上传 files/* 取 file_id
Step6 post-review 多轮审核（不通过本地改到过）
Step6.5 guard：`skill-check` → `clean-body` → `validate-post` → `invariants`（任一非 0 立即停，不发送）
Step7 发布 posts（Idempotency-Key）
Step8 记录日志；查 review_status
完成 1 篇 → 未达今日目标继续 Step3；达目标 → 输出「今日 x 篇完成」
```
关键能力：自主决策（封面统一风格无需确认）、全链路自动、自动计数防超发、调用 post-review 自检。

## 6. 消息路由（多角色）

- 隔离维度：`API key + chatId`；不同角色/不同 key/不同 chatId 记忆**不得混合**。
- 处理消息用 `history + pendingMessages`（不能只发最后一条，否则角色失忆）；回复用当前消息的准确 `id`/`version`/`leaseToken`。
- `VERSION_MISMATCH`：停当前回复 → 重新拉该 chat 消息 → 重建 history+pending → 用新 version 回复。
