#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""guard.py — Phanthy OpenClaw 运行期护栏（fail-closed，仅标准库）。

把「该遵守的规则」变成「不满足就发不出去」，防止龙虾跑偏。解决四类问题：
  1) title/body 重复           -> clean-body / validate-post
  2) 云端无 cron，脚本驱动调度 -> should-run（Python 伪定时，读状态文件，不依赖 cron）
  3) 创作前/发送前必须调用本技能 -> skill-check（版本校验，落后即拒绝）
  4) 关键不变量/防跑偏熔断      -> invariants / drift

子命令与退出码：
  0 通过；2 参数/输入错；3 技能未加载或版本过期；4 校验/不变量失败；5 熔断暂停

典型用法：
  python guard.py skill-check --skill SKILL.md
  python guard.py clean-body --title "标题" --body-file body.txt
  python guard.py validate-post --title "标题" --body-file body.txt --cover-file-id f1 --media f1 f2
  python guard.py should-run --name refill-topics --interval 86400 --state .state/scheduler.json --mark
  python guard.py invariants --input inv.json
  python guard.py drift --state .state/drift.json --ok false --limit 2
"""
import argparse
import json
import os
import re
import sys
import time
import unicodedata
from datetime import datetime

PUNCT = r"[\s\u3000`#>*_\-—:：。.,，、!！?？\"'“”‘’()（）\[\]【】]+"


def _norm(s):
    if s is None:
        return ""
    s = unicodedata.normalize("NFKC", str(s))
    return re.sub(PUNCT, "", s).lower()


def clean_body(title, body):
    """删除 body 开头与 title 重复的标题行（含 Markdown 标题符），返回 (新body, 删除行数)。"""
    t = _norm(title)
    lines = str(body).replace("\r\n", "\n").split("\n")
    i = 0
    while i < len(lines) and not lines[i].strip():
        i += 1
    removed = 0
    while i < len(lines) and removed < 3 and t:
        cand = re.sub(r"^\s{0,3}#{1,6}\s*", "", lines[i]).strip()
        if _norm(cand) == t:
            i += 1
            removed += 1
            if i < len(lines) and not lines[i].strip():
                i += 1
        else:
            break
    return "\n".join(lines[i:]).lstrip("\n"), removed


def validate_post(title, body, cover_file_id=None, media=None, post_exists=False):
    """返回问题列表；空列表=通过。"""
    problems = []
    if not str(title or "").strip():
        problems.append("title 为空")
    if not str(body or "").strip():
        problems.append("body 为空")
    if title and body:
        head = _norm(body)[:300]
        if _norm(title) and _norm(title) in head:
            problems.append("body 开头重复了 title（请先用 clean-body 删除）")
    if cover_file_id is not None and not str(cover_file_id).strip():
        problems.append("cover_file_id 为空")
    if media is not None:
        if not media:
            problems.append("media 为空（只传 title/body 会把原帖媒体清空）")
        for m in media:
            if not str(m).strip():
                problems.append("media 含空 file_id")
    if post_exists:
        problems.append("该选题已有 post_id（重复发帖）")
    return problems


def _read_frontmatter_field(path, key):
    try:
        with open(path, "r", encoding="utf-8") as f:
            txt = f.read(4000)
    except OSError:
        return None
    m = re.search(rf"^{re.escape(key)}:\s*(.+)$", txt, re.M)
    return m.group(1).strip() if m else None


def _ver_tuple(v):
    return tuple(int(x) if x.isdigit() else 0 for x in re.split(r"[.\-]", str(v)))


def skill_check(skill_path, latest=None, manifest_url=None):
    """断言：技能已加载（能读到 version）；且声明的平台基线不低于 manifest 最新版。"""
    ver = _read_frontmatter_field(skill_path, "version")
    if ver is None:
        print(f"[skill-check] FAIL 未找到 {skill_path} 或其 version（技能未加载）；拒绝发送")
        return 3
    baseline = _read_frontmatter_field(skill_path, "baseline") or ver
    if latest is None and manifest_url:
        try:
            import urllib.request
            with urllib.request.urlopen(manifest_url, timeout=15) as r:
                latest = json.loads(r.read().decode("utf-8")).get("version")
        except Exception as e:  # noqa: BLE001
            print(f"[skill-check] WARN 无法获取 manifest（{e}），仅校验本地已加载 skill v{ver} / 基线 {baseline}")
    if latest and baseline and _ver_tuple(baseline) < _ver_tuple(latest):
        print(f"[skill-check] FAIL 技能基线 {baseline} < 平台最新 {latest}，请先更新技能再发送")
        return 3
    print(f"[skill-check] OK 已加载 skill v{ver}（平台基线 {baseline}；平台最新 {latest or 'n/a'}）")
    return 0


def should_run(name, interval, state_file, window=None, mark=False, now=None):
    """Python 伪定时：距 last_run 是否 >= interval 且在时间窗内。替代云端不可用的 cron。"""
    now = now if now is not None else time.time()
    state = {}
    if os.path.exists(state_file):
        try:
            with open(state_file, "r", encoding="utf-8") as f:
                state = json.load(f)
        except Exception:  # noqa: BLE001
            state = {}
    last = float(state.get(name, 0) or 0)
    due = (now - last) >= interval
    in_window = True
    reason = ""
    if window:
        start, end = window
        cur = datetime.fromtimestamp(now).strftime("%H:%M")
        in_window = (start <= cur <= end) if start <= end else (cur >= start or cur <= end)
        if not in_window:
            reason = f"不在窗口 {start}-{end}"
    run = due and in_window
    if run and mark:
        state[name] = now
        d = os.path.dirname(os.path.abspath(state_file))
        os.makedirs(d, exist_ok=True)
        with open(state_file, "w", encoding="utf-8") as f:
            json.dump(state, f, ensure_ascii=False, indent=2)
    print(f"[should-run] {name}: {'RUN' if run else 'SKIP'} (last={last:.0f}, interval={interval}s"
          f"{', ' + reason if reason else ''})")
    return 0


def invariants(payload):
    problems = []
    if payload.get("is_test_post") is True:
        problems.append("测试帖禁止发布")
    if payload.get("user_approved") is not True:
        problems.append("用户未明确同意发布")
    if payload.get("frequency_confirmed") is not True:
        problems.append("每日发帖频率未确认")
    tp = payload.get("topic_type")
    if tp in ("科普", "新闻") and not str(payload.get("source_url", "")).strip():
        problems.append(f"{tp} 缺少可定位来源 URL")
    if payload.get("title_in_body") is True:
        problems.append("body 重复了 title")
    if payload.get("media_ready") is not True:
        problems.append("媒体 file_id 未就绪")
    if problems:
        print("[invariants] FAIL: " + "; ".join(problems))
        return 4
    print("[invariants] OK 全部不变量通过")
    return 0


def drift(state_file, ok, limit=2):
    state = {}
    if os.path.exists(state_file):
        try:
            with open(state_file, "r", encoding="utf-8") as f:
                state = json.load(f)
        except Exception:  # noqa: BLE001
            state = {}
    fails = int(state.get("consecutive_fail", 0))
    fails = 0 if ok else fails + 1
    state["consecutive_fail"] = fails
    d = os.path.dirname(os.path.abspath(state_file))
    os.makedirs(d, exist_ok=True)
    with open(state_file, "w", encoding="utf-8") as f:
        json.dump(state, f, ensure_ascii=False, indent=2)
    if fails >= limit:
        print(f"[drift] BREAKER 连续 {fails} 次失败 → 暂停自动发帖并通知 owner")
        return 5
    print(f"[drift] ok={ok} consecutive_fail={fails}")
    return 0


def main(argv=None):
    p = argparse.ArgumentParser(prog="guard.py", description="Phanthy OpenClaw 运行期护栏（fail-closed）")
    sub = p.add_subparsers(dest="cmd")
    sub.required = True

    sp = sub.add_parser("skill-check", help="断言技能已加载且版本不小于平台最新")
    sp.add_argument("--skill", default="SKILL.md")
    sp.add_argument("--latest", default=None)
    sp.add_argument("--manifest-url", default="https://cms.phanthy.com/api/v1/openclaw/skill.json")

    sp = sub.add_parser("clean-body", help="删除 body 开头重复的 title")
    sp.add_argument("--title", required=True)
    g = sp.add_mutually_exclusive_group(required=True)
    g.add_argument("--body-file")
    g.add_argument("--body")
    sp.add_argument("--out")

    sp = sub.add_parser("validate-post", help="校验 title/body/media")
    sp.add_argument("--title", required=True)
    g = sp.add_mutually_exclusive_group(required=True)
    g.add_argument("--body-file")
    g.add_argument("--body")
    sp.add_argument("--cover-file-id", default=None)
    sp.add_argument("--media", nargs="*", default=None)
    sp.add_argument("--post-exists", action="store_true")

    sp = sub.add_parser("should-run", help="Python 伪定时（替代 cron）")
    sp.add_argument("--name", required=True)
    sp.add_argument("--interval", type=int, required=True)
    sp.add_argument("--state", default=".state/scheduler.json")
    sp.add_argument("--window", nargs=2, default=None)
    sp.add_argument("--mark", action="store_true")

    sp = sub.add_parser("invariants", help="关键不变量断言")
    sp.add_argument("--input", required=True)

    sp = sub.add_parser("drift", help="防跑偏熔断计数")
    sp.add_argument("--state", default=".state/drift.json")
    sp.add_argument("--ok", required=True)
    sp.add_argument("--limit", type=int, default=2)

    a = p.parse_args(argv)
    if a.cmd == "skill-check":
        return skill_check(a.skill, a.latest, a.manifest_url)
    if a.cmd == "clean-body":
        body = a.body if a.body is not None else open(a.body_file, encoding="utf-8").read()
        nb, removed = clean_body(a.title, body)
        if a.out:
            with open(a.out, "w", encoding="utf-8") as f:
                f.write(nb)
            print(f"[clean-body] 删除重复标题 {removed} 行 -> {a.out}", file=sys.stderr)
        else:
            sys.stdout.write(nb)
        return 0
    if a.cmd == "validate-post":
        body = a.body if a.body is not None else open(a.body_file, encoding="utf-8").read()
        probs = validate_post(a.title, body, a.cover_file_id, a.media, a.post_exists)
        if probs:
            print("[validate-post] FAIL: " + "; ".join(probs))
            return 4
        print("[validate-post] OK")
        return 0
    if a.cmd == "should-run":
        return should_run(a.name, a.interval, a.state, a.window, a.mark)
    if a.cmd == "invariants":
        with open(a.input, encoding="utf-8") as f:
            payload = json.load(f)
        return invariants(payload)
    if a.cmd == "drift":
        ok = str(a.ok).lower() in ("1", "true", "yes", "ok", "pass")
        return drift(a.state, ok, a.limit)
    p.print_help()
    return 2


if __name__ == "__main__":
    raise SystemExit(main())
