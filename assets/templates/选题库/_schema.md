# 选题库字段与状态机（简版，详见 references/07-topic-library.md）

主台账：`topics.jsonl`（一行一条选题记录，= 一篇要发的帖子）。唯一可信来源，所有发帖/审核/配额脚本都读写它。

## 状态机
PENDING → DRAFTING → REVIEWING → AWAITING_USER_APPROVAL → READY → PUBLISHING
→ AUTO_REVIEW_PASSED → MANUAL_REVIEW → PUBLISHED
异常旁支：REJECTED / BLOCKED / NEED_HUMAN / ABANDONED / DUPLICATE（终态：PUBLISHED/ABANDONED/DUPLICATE）

> AWAITING_USER_APPROVAL = 已创作好/已修复好、已发用户、待其拍板；新智能体首条与每次修复重发都适用。

## 硬约束
1. topic_id 唯一；同 source.url 或归一化 title 视为重复，禁止再发。
2. 一题一帖；已有 post_id 不再新建。
3. 不跳步：READY 才能 PUBLISHING；REVIEWING 通过才 READY。
4. 发布成功立即回写 post_id / idempotency_key / published_at。
5. REJECTED 记原因原文，修复用 PATCH 完整内容(含媒体)复用同一 post_id，追加 revisions。
6. 小说/短剧记 book_or_drama_id + chapter_or_episode，章节/集号不可重复。
7. 科普/新闻进入 READY 前 source.url 必须为可定位的具体新闻页；其他题材不强制。
8. 只有 PUBLISHED 且 publicly_visible=true 才算完成。
9. 当日发帖数(计数状态)不得超过目标(默认12)。
10. 废弃/重复标 ABANDONED/DUPLICATE 归档，不物理删除。
11. 首条试创作闸门：新智能体第一条必须 REVIEWING→AWAITING_USER_APPROVAL→READY，用户明确同意发布后才可 READY/PUBLISHING 并开自动发帖。
12. 禁止测试帖：任何测试/占位/试探内容不得进入 PUBLISHING；发送前过 references/03 §0 闸门（非测试帖、已过审、用户同意、媒体齐、无重复 post_id），任一不满足禁止发布。
13. 修复后媒体确认：修复阶段新生成/替换的图片必须先发用户查看确认，确认后才可 PATCH 重发；确认结果记入 revisions（media_confirmed_by_user）。
14. 标题不重复：进入 PUBLISHING 前必须 `guard.py clean-body` 删除 body 开头重复标题并 `validate-post` 通过（title 不得出现在 body 前 300 字）。
15. 题材→内容 skill 必引用：进入 DRAFTING 前按 references/05 §0.6 加载对应内容技能，记录 `skill`（名+版本，或 none）；未加载不得 DRAFTING。
16. 漂移熔断：`guard.py invariants` 连续失败达阈值（默认 2）→ 暂停自动发帖并通知 owner，禁止"继续跑"。

命令：`python scripts/topic_library.py {add|next|list|set-status|stats|schema}`
