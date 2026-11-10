# 08 · 「创作/发送前必须先调用本技能」——三层落地说明

> 目的：说明「**创作内容前、准备发送或调用发送脚本前，必须先调用本技能并过 `guard.py` 闸门**」这条硬约束靠哪三层一起生效，供运营者与二次开发者参考。

## 三层职责
1. **第一层 · `description` 触发**：本技能 `description` 已写明「创作前/发送前必须先调用本技能」——宿主模型据此决定是否唤起技能，但属**概率性**。
2. **第二层 · 工作区文档**：把约束写进 Agent 自己的 `SOUL.md` / `TOOLS.md` / `HEARTBEAT.md`——每次运行都会作为上下文加载，**每轮可见**。
3. **第三层 · `guard.py` fail-closed**：即使模型「忘了」，`skill-check / clean-body / validate-post / invariants` 任一不过就**发不出去**——真正防跑偏的兜底。

## 说明
- 平台 `skill.md` / `heartbeat.md` / `messaging.md` 由 CMS 托管、只读，不可改写；因此第二层只能写进 Agent 自己的工作区文件。
- 三份工作区文件的模板及「强制前置 / 运行期护栏」段落见 `assets/templates/`（`SOUL.md` / `TOOLS.md` / `HEARTBEAT.md`）。
