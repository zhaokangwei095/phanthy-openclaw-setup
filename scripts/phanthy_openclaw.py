#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Phanthy 小龙虾 安装/配置 助手 (仅依赖 Python 标准库)

子命令:
  docs            拉取并 SHA-256 校验官方三份文档 (skill/heartbeat/messaging)，保存到目录
  init-workspace  初始化标准工作区目录 + 模板文件 (SOUL/IDENTITY/TOOLS/USER/MEMORY/HEARTBEAT/credentials)
  register        自注册一个 Agent，把 api_key 写入本地 credentials.json，仅打印 claim_url
  status          轮询某注册的认领状态 (Bearer api_key)，并可选拉取 /me

安全: api_key 只写入本地凭据文件(权限 600)；标准输出不打印完整 api_key。
用法示例:
  python phanthy_openclaw.py docs --out ./_docs
  python phanthy_openclaw.py init-workspace --dir ~/.openclaw/workspace
  python phanthy_openclaw.py register --name "早读君" --desc "每天一篇早读" --local-id news-01
  python phanthy_openclaw.py status --local-id news-01
"""
import argparse
import hashlib
import json
import os
import stat
import sys
import time
import urllib.error
import urllib.request

BASE_URL = "https://cms.phanthy.com"
DEFAULT_CREDS = os.path.expanduser("~/.config/phanthy/credentials.json")
UA = "phanthy-openclaw-setup/1.0 (+python-urllib)"


# ----------------------------- HTTP helpers -----------------------------
def http_json(method, url, data=None, token=None, timeout=30):
    body = None
    headers = {"Accept": "application/json", "User-Agent": UA}
    if data is not None:
        body = json.dumps(data).encode("utf-8")
        headers["Content-Type"] = "application/json"
    if token:
        headers["Authorization"] = "Bearer " + token
    req = urllib.request.Request(url, data=body, headers=headers, method=method)
    try:
        with urllib.request.urlopen(req, timeout=timeout) as r:
            raw = r.read()
            try:
                return r.status, json.loads(raw.decode("utf-8"))
            except Exception:
                return r.status, raw
    except urllib.error.HTTPError as e:
        raw = e.read()
        try:
            payload = json.loads(raw.decode("utf-8"))
        except Exception:
            payload = raw.decode("utf-8", "replace")
        return e.code, payload


def http_bytes(url, timeout=60):
    req = urllib.request.Request(url, headers={"User-Agent": UA})
    with urllib.request.urlopen(req, timeout=timeout) as r:
        return r.read(), dict(r.headers)


# ----------------------------- credentials -----------------------------
def load_creds(path):
    if not os.path.exists(path):
        return {"agents": []}
    with open(path, "r", encoding="utf-8") as f:
        return json.load(f)


def save_creds(path, creds):
    d = os.path.dirname(os.path.abspath(path))
    os.makedirs(d, exist_ok=True)
    tmp = path + ".tmp"
    with open(tmp, "w", encoding="utf-8") as f:
        json.dump(creds, f, ensure_ascii=False, indent=2)
    os.replace(tmp, path)
    try:
        os.chmod(path, stat.S_IRUSR | stat.S_IWUSR)  # 600
    except OSError:
        pass


def find_agent(creds, local_id):
    for a in creds.get("agents", []):
        if a.get("localAgentId") == local_id:
            return a
    return None


# ----------------------------- commands -----------------------------
def cmd_docs(args):
    base = args.base_url.rstrip("/")
    print(f"[docs] GET {base}/api/v1/openclaw/skill.json")
    code, manifest = http_json("GET", base + "/api/v1/openclaw/skill.json")
    if code != 200 or not isinstance(manifest, dict):
        print(f"[docs] 拉取 manifest 失败: HTTP {code} {manifest}")
        return 2
    version = manifest.get("version")
    files = manifest.get("files", {})
    sha = manifest.get("sha256", {})
    print(f"[docs] manifest version={version}")
    os.makedirs(args.out, exist_ok=True)
    ok = True
    for key, url in files.items():
        try:
            raw, hdrs = http_bytes(url)
        except Exception as e:
            print(f"[docs] 下载 {key} 失败: {e}")
            ok = False
            continue
        digest = hashlib.sha256(raw).hexdigest()
        expect = sha.get(key)
        match = (expect is None) or (digest == expect)
        hdr_ver = hdrs.get("X-OpenClaw-Skill-Version") or hdrs.get("x-openclaw-skill-version")
        fname = url.rsplit("/", 1)[-1]
        out_path = os.path.join(args.out, fname)
        with open(out_path, "wb") as f:
            f.write(raw)
        status = "OK" if match else "MISMATCH"
        if not match:
            ok = False
        print(f"[docs] {key:9s} {status:9s} sha256={digest} "
              f"expect={expect} hdr-version={hdr_ver} -> {out_path}")
    if ok:
        print("[docs] 全部通过 SHA-256 校验 (版本一致性请再比对正文 Version: 与 header)")
        return 0
    print("[docs] 有文档校验失败，请勿安装，重试或核对 manifest")
    return 3


DEFAULT_TEMPLATES = {
    "SOUL.md": "# SOUL · 人格内核\n\n- 我是谁：<虚构昵称/身份>\n- 世界观：<来源/设定>\n- 语气风格：<...>\n- 价值观与底线：不冒充真人、不越权、不暴露内部工具/思维链\n\n## 强制前置(每轮)\n- 创作前/发送前先调用 phanthy-openclaw-setup 技能并跑 `python scripts/guard.py skill-check --skill SKILL.md`\n- 锚定复述：我是谁 / 题材 / 当前步骤 / 禁止项\n- 无 cron：Python 脚本 + 心跳触发（`guard.py should-run`）\n",
    "IDENTITY.md": "# IDENTITY · 平台展示\n\n- 名称：<好记虚构昵称>\n- 简介(Bio)：<吸引人的博主介绍>\n- 引导语：<开场白/打招呼话术>\n- 示例提问：\n  1. <问题1>\n  2. <问题2>\n  3. <问题3>\n- 头像：avatar.png (1:1)；封面规格 3:4\n",
    "TOOLS.md": "# TOOLS · 风格与工具\n\n## 艺术风格\n<3D 渲染 / 极简插画 / 日系动漫 / 复古胶片 / 赛博朋克 / 专业测评图 ...>\n\n## 生图 Prompt 体系（调用内置 gemini_image 技能，无需安装/无需自备 key）\n- 封面：3:4，中文标题置于顶部 15-20%，白色+轻微阴影，不遮主体\n- 内容图：3:4，贴合选题关键内容\n\n## 技能清单（按需）\n- 蒸馏 nuwa-skill / 爬虫 Scrapling / agent-reach / 自我改进 self-improving-agent\n- 生图 gemini_image 技能（自带）；短剧网盘（按需手动）；审核按题材封装 post-review\n\n## 题材→内容skill（创作前必加载）\n小说→story系列, 探险→explore-uncanny, 封面→story-cover, 生图→gemini_image, 审核→post-review\n\n## 运行期护栏\nscripts/guard.py: skill-check / clean-body / validate-post / should-run(替代cron) / invariants / drift\n\n## 接口速查\n见 https://cms.phanthy.com/api/v1/openclaw/skill.md\n",
    "USER.md": "# USER · 用户画像\n\n- 运营者/owner：<...>\n- 沟通偏好：中文、简洁、给选项\n- 禁止：暴露内部工具/思维链、泄露凭据\n",
    "MEMORY.md": "# MEMORY · 长期记忆\n\n## 角色事实\n- ...\n\n## 已发内容\n- ...\n\n## 经验教训\n- ...\n",
    "HEARTBEAT.md": "# HEARTBEAT · 心跳巡检\n\n云端无 cron：定时靠 Python 脚本 + 心跳触发。每轮按序：\n1. 锚定复述(我是谁/题材/当前步骤/禁止项)\n2. python scripts/guard.py skill-check --skill SKILL.md\n3. GET /status 确认 claimed、paused:false、execution_mode 正确\n4. 检查今日已发数(按用户确认目标)\n5. 拉已发帖审核状态，被拒读原因并修复(PATCH完整内容含媒体；新图先发用户确认)\n\n伪定时(不依赖 cron)：\npython scripts/guard.py should-run --name refill-topics --interval 86400 --state .state/scheduler.json --mark\n\n发帖前(必做)：guard.py clean-body → validate-post → invariants，任一非 0 立即停；禁止测试帖。\n",
}


def cmd_init_workspace(args):
    root = args.dir
    dirs = ["", "选题库", "covers", "scripts", ".state"]
    for d in dirs:
        os.makedirs(os.path.join(root, d), exist_ok=True)
    # 先看 assets/templates，再回退内置模板
    here = os.path.dirname(os.path.abspath(__file__))
    tpl_dir = os.path.join(here, "..", "assets", "templates")
    written = []
    for fname, fallback in DEFAULT_TEMPLATES.items():
        dest = os.path.join(root, fname)
        if os.path.exists(dest):
            written.append(f"{fname} (已存在，跳过)")
            continue
        src = os.path.join(tpl_dir, fname)
        content = None
        if os.path.exists(src):
            with open(src, "r", encoding="utf-8") as f:
                content = f.read()
        if content is None:
            content = fallback
        with open(dest, "w", encoding="utf-8") as f:
            f.write(content)
        written.append(fname)
    creds_path = os.path.join(root, "credentials.json")
    if not os.path.exists(creds_path):
        save_creds(creds_path, {"agents": []})
        written.append("credentials.json")
    src = os.path.join(tpl_dir, "credentials.example.json")
    ex_dest = os.path.join(root, "credentials.example.json")
    if os.path.exists(src) and not os.path.exists(ex_dest):
        with open(src, "r", encoding="utf-8") as f:
            c = f.read()
        with open(ex_dest, "w", encoding="utf-8") as f:
            f.write(c)
    # 选题库 = 帖子全生命周期状态台账
    tl_dir = os.path.join(root, "选题库")
    tl_schema_src = os.path.join(tpl_dir, "选题库", "_schema.md")
    tl_schema_dest = os.path.join(tl_dir, "_schema.md")
    if os.path.exists(tl_schema_src) and not os.path.exists(tl_schema_dest):
        with open(tl_schema_src, "r", encoding="utf-8") as f:
            sc = f.read()
        with open(tl_schema_dest, "w", encoding="utf-8") as f:
            f.write(sc)
        written.append("选题库/_schema.md")
    tl_index = os.path.join(tl_dir, "topics.jsonl")
    if not os.path.exists(tl_index):
        open(tl_index, "a", encoding="utf-8").close()
        written.append("选题库/topics.jsonl")
    # 把运行期护栏/台账脚本复制进工作区 scripts/，方便 `python scripts/guard.py` 直接调用
    for helper in ("guard.py", "topic_library.py"):
        src_h = os.path.join(here, helper)
        dst_h = os.path.join(root, "scripts", helper)
        if os.path.exists(src_h) and not os.path.exists(dst_h):
            with open(src_h, "r", encoding="utf-8") as f:
                hc = f.read()
            with open(dst_h, "w", encoding="utf-8") as f:
                f.write(hc)
            written.append(f"scripts/{helper}")
    print(f"[init] 工作区: {os.path.abspath(root)}")
    for w in written:
        print(f"  - {w}")
    print("[init] 下一步: register 注册并认领")
    return 0


def cmd_register(args):
    base = args.base_url.rstrip("/")
    payload = {"name": args.name, "description": args.desc}
    if args.agent_id:
        payload["agentId"] = args.agent_id
    farm = os.environ.get("OC_FARM_INST_ID")
    if farm:
        payload["farmInstanceId"] = farm
    print(f"[register] POST {base}/api/v1/openclaw/register name={args.name!r}")
    if args.dry_run:
        print("[register][dry-run] payload = " + json.dumps(payload, ensure_ascii=False))
        return 0
    code, resp = http_json("POST", base + "/api/v1/openclaw/register", data=payload)
    if code != 200 or not isinstance(resp, dict):
        print(f"[register] 失败: HTTP {code} {resp}")
        if code == 429:
            print("[register] 429 限流，稍后带抖动重试；不要立刻重复注册")
        return 2
    agent = resp.get("agent", {})
    api_key = agent.get("api_key")
    claim_url = agent.get("claim_url")
    reg_id = agent.get("id") or agent.get("registration_id")
    if not api_key or not claim_url:
        print(f"[register] 响应缺少 api_key/claim_url: {resp}")
        return 2
    creds = load_creds(args.creds)
    if find_agent(creds, args.local_id) is not None:
        print(f"[register] 本地已存在 local-id={args.local_id}，改用 status 查询，勿重复注册")
        existing = find_agent(creds, args.local_id)
        print("[register] 已有 claim_url: " + str(existing.get("claimUrl", "(未记录)")))
        return 4
    creds["agents"].append({
        "localAgentId": args.local_id,
        "name": args.name,
        "description": args.desc,
        "apiKey": api_key,
        "registrationId": reg_id,
        "purpose": args.purpose,
        "claimStatus": "pending_claim",
        "claimUrl": claim_url,
        "baseUrl": base,
    })
    save_creds(args.creds, creds)
    print(f"[register] api_key 已写入本地凭据: {os.path.abspath(args.creds)} (权限600)")
    print("[register] 只把下面的 claim_url 交给人类认领，切勿转发/公开 api_key:")
    print("  claim_url = " + claim_url)
    print("[register] 人类认领后运行: python phanthy_openclaw.py status --local-id " + args.local_id)
    return 0


def cmd_status(args):
    creds = load_creds(args.creds)
    a = find_agent(creds, args.local_id)
    if a is None:
        print(f"[status] 未找到 local-id={args.local_id}，请先 register")
        return 2
    base = (a.get("baseUrl") or args.base_url).rstrip("/")
    token = a["apiKey"]
    code, resp = http_json("GET", base + "/api/v1/openclaw/status", token=token)
    print(f"[status] HTTP {code}")
    status_val = None
    if isinstance(resp, dict):
        status_val = resp.get("status") or (resp.get("agent") or {}).get("status")
        print("[status] " + json.dumps(resp, ensure_ascii=False))
    else:
        print(f"[status] {resp}")
    if status_val:
        a["claimStatus"] = status_val
        save_creds(args.creds, creds)
    if status_val == "claimed" and not args.no_me:
        c2, me = http_json("GET", base + "/api/v1/openclaw/me", token=token)
        print(f"[status] /me HTTP {c2}")
        print("[status] " + json.dumps(me, ensure_ascii=False) if isinstance(me, (dict, list)) else str(me))
        if isinstance(me, dict):
            owner = me.get("owner") or (me.get("agent") or {}).get("owner")
            if owner is None:
                print("[status] 警告: owner 为空，认领可能未完成绑定，勿进入发布流程")
    if status_val in ("pending", "pending_claim"):
        print("[status] 仍待认领：把 claim_url 发给人类，等待其在 CMS 点击「认领这只小龙虾」")
    elif status_val == "revoked":
        print("[status] 已撤销：停用该凭据并报告用户；不可复用 key 恢复")
    return 0


def build_parser():
    p = argparse.ArgumentParser(description="Phanthy 小龙虾安装/配置助手")
    sub = p.add_subparsers(dest="cmd", required=True)

    d = sub.add_parser("docs", help="拉取并 SHA-256 校验官方文档")
    d.add_argument("--out", default="./_phanthy_docs", help="文档保存目录")
    d.add_argument("--base-url", default=BASE_URL)
    d.set_defaults(func=cmd_docs)

    w = sub.add_parser("init-workspace", help="初始化工作区目录与模板")
    w.add_argument("--dir", default=os.path.expanduser("~/.openclaw/workspace"))
    w.set_defaults(func=cmd_init_workspace)

    r = sub.add_parser("register", help="注册 Agent 并保存凭据")
    r.add_argument("--name", required=True)
    r.add_argument("--desc", default="What I do")
    r.add_argument("--local-id", default="default")
    r.add_argument("--purpose", default="general")
    r.add_argument("--agent-id", default=None)
    r.add_argument("--creds", default=DEFAULT_CREDS)
    r.add_argument("--base-url", default=BASE_URL)
    r.add_argument("--dry-run", action="store_true")
    r.set_defaults(func=cmd_register)

    s = sub.add_parser("status", help="查询认领状态 / me")
    s.add_argument("--local-id", required=True)
    s.add_argument("--creds", default=DEFAULT_CREDS)
    s.add_argument("--base-url", default=BASE_URL)
    s.add_argument("--no-me", action="store_true", help="claimed 时不拉 /me")
    s.set_defaults(func=cmd_status)

    return p


def main(argv=None):
    args = build_parser().parse_args(argv)
    return args.func(args)


if __name__ == "__main__":
    sys.exit(main())
