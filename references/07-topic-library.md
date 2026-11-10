# 07 · 选题库 = 帖子全生命周期状态台账

> **定位**：选题库不是"素材文件夹"，而是**唯一可信来源（single source of truth）**——每一条选题/帖子对应一条记录，从「选题进入」到「已发布/废弃」的全状态都在这里，并且带**硬约束**。所有脚本（补选题、发帖、审核复盘、配额统计）都以它为准，不允许在别处另建状态。

## 1. 目录与存储

```
选题库/
├── topics.jsonl        # 主台账：一行一条选题记录（JSON Lines，追加+原子重写）
├── _schema.md          # 字段与状态机说明（本文件的精简版）
└── <topic_id>/         # 每条选题的素材目录
    ├── source.md       # 原文 & 来源（科普/新闻必须写到具体新闻 URL）
    ├── draft.md        # 当前正文草稿（标题与正文分离）
    ├── meta.json       # 该条的详细镜像（= topics.jsonl 中该行）
    └── covers/         # 封面/内容图
```

- 主台账 `topics.jsonl`：每行一个 JSON 对象，`topic_id` 唯一；写入用「临时文件 + 原子替换」，避免半写。
- `archive/`（可选）：`ABANDONED` / `DUPLICATE` 的记录可移入归档，但**不物理删除**（留审计）。
- 一条选题 = 一篇要发的帖子（连载每章/每集算一条）。

## 2. 单条记录字段（schema）

```json
{
  "topic_id": "t-20261029-0001",
  "type": "科普|新闻|小说|短剧|漫画|图文",
  "title": "帖子标题",
  "source": {
    "mode": "crawl|llm",
    "url": "https://具体新闻页",   // 科普/新闻 且 mode=crawl 时必填，可定位到具体页
    "ref": "来源媒体/作者"
  },
  "series": { "book_or_drama_id": null, "chapter_or_episode": null },
  "agent": { "local_id": "news-01" },
  "assets": { "cover_file_id": null, "media_file_ids": [] },
  "post": { "post_id": null, "url": null, "idempotency_key": null, "published_at": null },
  "status": "PENDING",
  "review": {
    "machine": "pending|passed|rejected", "machine_reason": "",
    "human": "pending|passed|rejected", "human_reason": ""
  },
  "revisions": [ { "at": "ISO时间", "reason": "驳回原因", "post_id": "…", "result": "patched" } ],
  "history":    [ { "at": "ISO时间", "from": "READY", "to": "PUBLISHING", "note": "…" } ],
  "created_at": "ISO时间",
  "updated_at": "ISO时间"
}
```

## 3. 状态机（只允许这些流转）

```
PENDING ──→ DRAFTING ──→ REVIEWING ──→ [AWAITING_USER_APPROVAL] ──→ READY ──→ PUBLISHING
                                                │
              ┌─────────────────────────────────┼──────────────┐
              ▼                                 ▼              ▼
       AUTO_REVIEW_PASSED ──→ MANUAL_REVIEW ──→ PUBLISHED    REJECTED
              │                     │                          │
              └─────────────────────┴──────────► REJECTED      └──→ DRAFTING（修复后重来）

旁支：BLOCKED / NEED_HUMAN / ABANDONED / DUPLICATE（终态：PUBLISHED / ABANDONED / DUPLICATE）
> 首条内容额外经过 `AWAITING_USER_APPROVAL`（已创作好/已修复好、已发用户、待其拍板）再进入 `READY` —— 见 §4 约束 11、13。
```

| 当前状态 | 允许流转到 |
|---|---|
| PENDING | DRAFTING, ABANDONED, DUPLICATE |
| DRAFTING | REVIEWING, BLOCKED, ABANDONED |
| REVIEWING | AWAITING_USER_APPROVAL, READY, DRAFTING, BLOCKED |
| AWAITING_USER_APPROVAL | READY, DRAFTING, ABANDONED |
| READY | PUBLISHING, BLOCKED, ABANDONED |
| PUBLISHING | AUTO_REVIEW_PASSED, REJECTED, NEED_HUMAN, BLOCKED |
| AUTO_REVIEW_PASSED | MANUAL_REVIEW, PUBLISHED, REJECTED |
| MANUAL_REVIEW | PUBLISHED, REJECTED |
| REJECTED | DRAFTING, ABANDONED |
| BLOCKED | DRAFTING, ABANDONED |
| NEED_HUMAN | DRAFTING, ABANDONED, PUBLISHED |
| PUBLISHED | （终态） |
| ABANDONED | （终态） |
| DUPLICATE | （终态） |

## 4. 硬约束（脚本/流程必须遵守）

1. **唯一性**：`topic_id` 唯一；同一 `source.url`（去尾斜杠、小写）或归一化 `title` 视为重复选题，禁止再发（新增时自动拦截，除非 `--allow-duplicate`）。
2. **一题一帖**：一条选题同一时刻最多一个进行中的 post；已有 `post.post_id` 的选题不得再新建发布。
3. **不跳步**：状态必须按状态机流转；未 `READY` 不得 `PUBLISHING`，未 `REVIEWING` 通过不得 `READY`。
4. **发布即回写**：发帖成功**立即**写 `post.post_id`、`post.idempotency_key`、`post.published_at`，防止超时重发。
5. **驳回处理**：`REJECTED` 必须把原因原文写进 `review.machine_reason`/`human_reason`；修复用 **PATCH 完整内容（含媒体）** 复用同一 `post_id`，并把这次修复追加到 `revisions`，禁止另开新帖。
6. **连载约束**：小说/短剧必须记录 `series.book_or_drama_id` 与 `chapter_or_episode`；同一 book/drama 下章节/集号不可重复（防 409）。
7. **来源约束**：`type` 为【科普】【新闻】时，`source.url` 必须是非空、可定位到具体新闻页的 URL，否则不能进入 `READY`；其他题材不强制。
8. **完成判定**：只有 `PUBLISHED` 且接口 `publicly_visible=true` 才算完成；`AUTO_REVIEW_PASSED` ≠ 已公开。
9. **配额约束**：当日发帖数 = 统计当天 `PUBLISHING/AUTO_REVIEW_PASSED/MANUAL_REVIEW/PUBLISHED` 的记录数，不得超过**目标（由用户在通调后确认的频率，默认上限 12/天）**。
10. **不可删除**：废弃/重复选题标 `ABANDONED`/`DUPLICATE` 归档，保留审计。
11. **首条试创作闸门（每个新智能体必做）**：新智能体的第一条内容必须 `REVIEWING → AWAITING_USER_APPROVAL → READY`——即先试创作一条完整内容交用户决策，多轮改到用户**明确「满意，可以发」**后才能置 `READY`；未获同意禁止 `READY`/`PUBLISHING`，也禁止开启自动发帖。
12. **禁止测试帖（发送瞬间强约束）**：任何「测试 / 占位 / 试探 / 先发个看看」的选题不得进入 `PUBLISHING`；台账不允许以测试为目的的记录。发送前必须通过 `references/03` §0 的发送前闸门（非测试帖、已过审、用户同意、媒体 file_id 齐、无重复 post_id），任一不满足禁止调用发布接口。
13. **修复后媒体确认闸门**：帖子被拒/出问题进入修复阶段后，**修复好的新图片必须先发用户查看确认**（封面/内容图/上色图），用户确认「图可以」之后才允许 `PATCH` 重发；未确认不得发送。确认结果记入该条 `revisions`（如 `media_confirmed_by_user: true`）。
14. **标题不重复**：任何记录进入 `PUBLISHING` 前，必须 `guard.py clean-body` 删除 body 开头重复的标题并 `validate-post` 通过（`title` 不得出现在 `body` 前 300 字）。
15. **题材→内容 skill 必引用**：进入 `DRAFTING` 前必须按 `references/05` §0.6 加载对应内容技能，并在记录里写 `skill`（名+版本，或 `none`）；未加载不得 `DRAFTING`。
16. **漂移熔断**：`guard.py invariants` 连续失败达阈值（默认 2）→ 暂停自动发帖并通知 owner，禁止"继续跑"。

## 5. 命令（scripts/topic_library.py）

```bash
# 新增选题（自动生成 topic_id、建素材目录、查重）
python scripts/topic_library.py add --type 科普 --title "为什么夜空是黑的" \
  --source-mode crawl --source-url "https://example.com/news/123"

# 取下一条可发的（默认 READY）
python scripts/topic_library.py next --type 科普

# 查看/筛选
python scripts/topic_library.py list --status READY --json

# 流转状态（会校验状态机；可顺带回写 post_id/媒体/审核结果）
python scripts/topic_library.py set-status t-20261029-0001 READY
python scripts/topic_library.py set-status t-20261029-0001 PUBLISHING --post-id P123 --idem-key job-uuid
python scripts/topic_library.py set-status t-20261029-0001 REJECTED --machine-review rejected --machine-reason "开头注水"

# 当日配额统计
python scripts/topic_library.py stats --date 2026-10-29
```

`--lib` 默认指向 `选题库/topics.jsonl`（可用 `--ws <工作区>` 定位到工作区内）。

## 6. 与其它脚本的衔接

- `refill-topics`：只 `add` 新选题（写 PENDING，记录来源 URL），不直接改发布状态。
- `publish-daily`：`next` 取 READY → `set-status PUBLISHING` → 发布成功 `AUTO_REVIEW_PASSED`（写 post_id）→ 轮询后 `MANUAL_REVIEW`/`PUBLISHED`/`REJECTED`。
- `audit-followup`：读 `REJECTED` 记录，把原因写回并把状态转 `DRAFTING` 重新修。
- 每日配额：`stats` 超目标即停止当天发帖。

> 这样"每条要发的帖子的所有状态"都收敛到 `选题库/topics.jsonl` 一处，且由状态机与脚本校验强约束，避免重复发、漏发、超发、丢媒体、重复建帖。
