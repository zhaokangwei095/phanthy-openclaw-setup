# TOOLS · 风格与工具

## 艺术风格（视觉自适应）
> 严禁固定「真人感」。按选题意境/受众/领域选择并锁定一种主风格。
- 主风格：<3D 渲染 / 极简插画 / 日系动漫 / 复古胶片 / 赛博朋克 / 专业测评图 / …>
- 一致性：同账号发帖保持同一封面风格；自动发帖时选择与已发最接近的封面。

## 生图 Prompt 体系（调用内置 gemini_image 技能）
> 生图/上色走**内置 `gemini_image` 技能**：创建小龙虾时已自带，无需安装、无需自备 Gemini API key，直接调用。
- 封面（3:4）：中文标题置于顶部 15-20%，现代简约字体，白色+轻微阴影，严禁遮挡主体。
- 内容图（3:4，3-5 张）：展示本次选题的关键内容/知识点，必须与正文切合。
- 调用方式：把 prompt（+可选参考图）交给 `gemini_image` 技能，由它返回图片。
  - 建议 `imageSize=2K`；超时原地等待重试，不换旧图、不跳过。

## 技能清单（按需安装）
- 蒸馏：`https://github.com/alchaincyf/nuwa-skill`
- 爬虫：`https://github.com/D4Vinci/Scrapling`、`https://github.com/Panniantong/agent-reach`
- 自我改进：`https://github.com/pskoett/self-improving-agent`
- 网盘（短剧）：夸克网盘 skill —— **仅发短剧的账号按需手动安装**，非标准流程
- 审核：本工作区**按题材**自封装 **post-review**（小说/科普/短剧口径不同，标准见 skill 的 references/04）

## 接口速查
- 总纲：`https://cms.phanthy.com/api/v1/openclaw/skill.md`
- 心跳：`.../heartbeat.md`；对话：`.../messaging.md`；清单：`.../skill.json`
- 发布前必须查最新 skill.md，动态解析地址/Payload/Headers。

## 题材 → 必用内容 skill（创作前必须加载，记入台账）
- 小说/网文：`story`（及 `story-long-write` / `story-short-write` / `story-cover` / `story-deslop`）
- 探险/脑洞图文：`explore-uncanny`
- 封面：`story-cover`；生图/上色：`gemini_image`（内置）
- 审核：按题材自封装 `post-review`（references/04）

## 运行期护栏（fail-closed，必用）
- 发送脚本入口：`python scripts/guard.py skill-check --skill SKILL.md`（未加载/基线过期→拒发）
- 标题去重：`guard.py clean-body`；发送校验：`guard.py validate-post`
- 伪定时（替代 cron）：`guard.py should-run --name <job> --interval <秒> --state .state/scheduler.json --mark`
- 不变量/熔断：`guard.py invariants` / `guard.py drift`
