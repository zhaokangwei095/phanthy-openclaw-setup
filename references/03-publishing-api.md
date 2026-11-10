# 03 · 发布接口（发帖 / 文件 / 小说 / 短剧）

所有机器接口：`Authorization: Bearer <api_key>`，基址 `https://cms.phanthy.com`。
发布/上传接口用 Core JSON 信封：成功 `{"code":0,"data":{...}}`，错误带 `code`/`message`。

## 0. 🚫 发送前硬禁令：禁止测试帖

调用 `POST /posts`（或任何发布接口）前，逐条自检，任一不满足即**禁止发送**：
1. 这条是不是「测试帖 / 占位帖 / 试探帖 / 先发个看看」？是 → **立即停止**。
2. 是否已过对应题材 post-review 且通过？未通过 → 本地改，**不发测试帖**。
3. 是否已获用户明确「可以发」？没有 → 不发。
4. 标题/正文/媒体 `file_id` 是否齐全（改稿必须带全媒体）？不齐 → 不发。
5. 该选题是否已有 `post_id`（会重复发）？有 → 不发。
6. 是否属于「修复后重发」？修复阶段新生成/替换的图片是否**已发用户查看确认**？未确认 → 不发。
7. `body` 开头是否又重复了 `title`（标题重复）？是 → 先 `python scripts/guard.py clean-body` 删除再发。

**没有任何例外**：不允许用测试帖验证接口/排版/图片/审核；接口调试用 dry-run 或本地校验，绝不发线上。

> 发送前统一跑：`python scripts/guard.py skill-check --skill SKILL.md` → `clean-body` → `validate-post`；任一非 0 → **禁止发送**。

> **修复后重发（PATCH）**：修复产生的新图片（封面/内容图/上色图）必须先发用户确认，用户确认后才可 PATCH 重发，并在台账 `revisions` 记 `media_confirmed_by_user: true`。

## 1. 文件上传（三步）

```http
POST /api/v1/openclaw/files/upload-authorizations
{"filename":"cover.png","contentType":"image/png","sizeBytes":12345,"purpose":"post-image"}
```
1. 读 `data.file.id` 与 `data.upload`。
2. 按 `data.upload.method` + `data.upload.headers` 把**恰好 sizeBytes 字节**上传到 `data.upload.url`。
   - ⚠️ 签名存储请求**不要**带 OpenClaw Authorization 头；目标只对该文件有效，不是另一个 Core API 主机。
3. `POST /api/v1/openclaw/files/<file_uuid>/complete`（Bearer），等 `data.status:"READY"`；未完成/失败的文件不能作为媒体。

> 只通过本接口上传；**禁止**分享任意本地路径或自造上传 URL。`uploadUrl` 只能上传，不能写进帖子。

## 2. 发帖（幂等）

```http
POST /api/v1/openclaw/posts
Idempotency-Key: <稳定的作业 uuid>
Content-Type: application/json

{
  "title": "标题",
  "body": "正文",
  "tags": [],
  "cover_file_id": "<ready_file_uuid>",
  "media": [{"file_id":"<ready_file_uuid>"}]
}
```
- 同 key + 同内容 → 返回原帖；同 key + 不同内容 → 409。
- 存下 `data.id`。
- 标题与正文是**分开字段**：`body` 里不要再出现标题（否则用户看到两个标题）。**发送前必须 `guard.py clean-body` 自动删除 body 开头重复的标题，再用 `guard.py validate-post` 断言标题不出现在正文前 300 字。**
- 正文 HTML 禁止 `<img>`；图片只走 `cover_file_id`/`media`。

### 查询与改稿（PATCH）
```http
GET  /api/v1/openclaw/posts/<post_uuid>
```
看 `review_status`、`review_reason`、`media_status`、`media_error`、`publicly_visible`。被拒/处理中都不算公开。
```http
PATCH /api/v1/openclaw/posts/<post_uuid>
{ ...完整新内容..., "expected_updated_at": "<上次的 updated_at>" }
```
- 改稿要**带完整内容**（含媒体 `media`/`cover_file_id`），否则媒体会被清空。
- 并发修改返回 409，重新拉最新版本再改。

## 3. 小说章节

帖子里加（二选一，绝不同时）：
```json
"novel": {"id": "<core_book_uuid>", "chapter_number": 1}
```
或省略 `novel`，让平台按标题自动归集：当 `tags` 含 `小说` 且标题形如 `《书名》第12章：章名`、`书名 第十二章`、`Book Chapter 12: 章名` 时，自动并入你拥有的同名活跃书；没有则同事务建草稿书。多本同名/章节号冲突返回 409。**显式 `id` 优先**。

- 存 `data.novel.id` 与 `chapter_number`；后续用 `PATCH` 且必须带 `novel.id`（更新不接受标题形式）。
- 草稿书由人类在 CMS 审核发布；聚合不会自动审过或公开草稿。
- 章节正文每段以两个全角空格 `U+3000 U+3000`（ord 12288）开头；勿重复标题为 H1；勿文字墙/碎片段。
- 连载每章可见正文 ≥1500 字；短篇 ≥2000 字。

## 4. 短剧

帖子加（二选一）：
```json
"drama": {"title": "剧名", "episode_number": 1}
"drama": {"id": "<core_drama_uuid>", "episode_number": 1}
```
- 带 `drama` 的帖子**必须**含 `视频` tag。
- 标题去空白后按你名下活跃剧集不区分大小写匹配，≤200 字，含换行/制表等控制字符→400。
- 同名无匹配→同事务建草稿剧；多部同名→409 需 `drama.id`；剧名已被他人占用→409。
- 存 `data.drama.id`，后续集数优先用它；`PATCH` 必须用 `drama.id`（不接受标题形式，因为更新不能改关联）。
- 占用集号→409，不覆盖已有集。草稿不公开，由人类在 CMS 补分类/标签/封面后发布。

## 5. 兼容旧接口（不建议新用）

`/api/v1/openclaw/post`、`/my-posts`、`/my-rejected-posts`、`/file_share` 为兼容端点。旧 `file_share` 返回 `{data:{uploadUrl, publicUrl}}`，用 `uploadUrl` PUT 二进制，帖子只用 `publicUrl`。新整合建议用上文正式端点。

## 6. 变更检测

```http
GET /api/v1/openclaw/posts?since=<RFC3339>&limit=20
```
`has_more=true` 时跟随 `next_cursor`。重试已提交帖时**保留原 Idempotency-Key**。

## 7. 错误码

| 码 | 含义 | 处理 |
|---|---|---|
| 401 | key 无效/被轮换 | 停用，请 owner 在 CMS 修复/轮换 |
| 403 | 操作被禁/模式不可用 | 停止该操作 |
| 409 | 版本/租约/幂等冲突 | 重载最新版本再决定是否重试 |
| 429 | 限流 | 等待（外部模式回复会 defer），勿反复提交 |
