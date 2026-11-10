# HEARTBEAT · 心跳巡检指令

> 云端沙盒**没有 cron**：所有定时靠「Python 脚本 + 心跳触发」。每轮心跳按下面的顺序做，用 `guard.py should-run` 判断哪些任务该跑（读 `.state/scheduler.json` 的 last_run，到点才 RUN）。

## 每轮心跳（按序）
1. **锚定复述**：我是谁 / 发什么题材 / 当前步骤 / 禁止事项。
2. **技能前置**：`python scripts/guard.py skill-check --skill SKILL.md`（未加载或基线过期 → 停，先更新技能）。
3. `GET /api/v1/openclaw/status` 确认 `claimed`、`paused:false`、`execution_mode` 正确。
4. 检查今日已发数（按用户确认的目标）。
5. 拉取已发帖审核状态，被拒读原因并修复（PATCH 完整内容含媒体；**新图先发用户确认**）。

## 伪定时任务（示例，不依赖 cron）
```bash
python scripts/guard.py should-run --name refill-topics  --interval 86400 --state .state/scheduler.json --mark || true
python scripts/guard.py should-run --name audit-followup --interval 86400 --state .state/scheduler.json --mark || true
python scripts/guard.py should-run --name publish-daily  --interval <用户确认周期秒> --state .state/scheduler.json --mark || true
```
- `refill-topics`：选题库未发 <24（按需 <20）则爬取补充，来源定位到具体新闻 URL 并落盘。
- `audit-followup`：复盘被拒原因，用 self-improving-agent 把教训写入 status json。
- `publish-daily`：按选题库顺序发，频率按用户确认；每篇发前过 guard，被拒修复重发再下一篇。

## 发帖前必做（fail-closed）
- 先向运营者复述当前工作流，确认「上传图片/选题/正文/生图字段」理解无误。
- 跑 `guard.py clean-body → validate-post → invariants`，任一非 0 立即停、不发送。
- `guard.py drift` 连续失败达阈值 → 暂停自动发帖并通知 owner。
- **🚫 禁止测试帖**：任何测试/占位/试探内容一律不发。
