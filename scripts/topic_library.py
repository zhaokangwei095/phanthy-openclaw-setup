#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
选题库 = 帖子全生命周期状态台账 (仅标准库)

把「每一条选题/帖子」的状态收敛到 topics.jsonl 一处，并用状态机硬约束，
防止重复发、漏发、超发、丢媒体、重复建帖。

子命令:
  add        新增选题(生成 topic_id、建素材目录、查重)
  next       取下一条可发的选题(默认 READY)
  list       列出/筛选选题
  set-status 状态流转(校验状态机；可回写 post_id/媒体/审核结果)
  stats      当日配额统计
  schema     打印状态机与字段说明

常用:
  python topic_library.py add --type 科普 --title "..." --source-mode crawl --source-url "https://..."
  python topic_library.py next --type 科普
  python topic_library.py set-status t-20261029-0001 READY
  python topic_library.py set-status t-20261029-0001 PUBLISHING --post-id P123 --idem-key job-uuid
  python topic_library.py set-status t-20261029-0001 REJECTED --machine-review rejected --machine-reason "..."
  python topic_library.py stats --date 2026-10-29
"""
import argparse
import json
import os
import sys
import tempfile
from datetime import datetime, timezone

DEFAULT_LIB = os.path.join("选题库", "topics.jsonl")

# 状态机：当前 -> 允许流转集合
TRANSITIONS = {
    "PENDING": {"DRAFTING", "ABANDONED", "DUPLICATE"},
    "DRAFTING": {"REVIEWING", "BLOCKED", "ABANDONED"},
    "REVIEWING": {"AWAITING_USER_APPROVAL", "READY", "DRAFTING", "BLOCKED"},
    "AWAITING_USER_APPROVAL": {"READY", "DRAFTING", "ABANDONED"},
    "READY": {"PUBLISHING", "BLOCKED", "ABANDONED"},
    "PUBLISHING": {"AUTO_REVIEW_PASSED", "REJECTED", "NEED_HUMAN", "BLOCKED"},
    "AUTO_REVIEW_PASSED": {"MANUAL_REVIEW", "PUBLISHED", "REJECTED"},
    "MANUAL_REVIEW": {"PUBLISHED", "REJECTED"},
    "REJECTED": {"DRAFTING", "ABANDONED"},
    "BLOCKED": {"DRAFTING", "ABANDONED"},
    "NEED_HUMAN": {"DRAFTING", "ABANDONED", "PUBLISHED"},
    "PUBLISHED": set(),
    "ABANDONED": set(),
    "DUPLICATE": set(),
}
TERMINAL = {"PUBLISHED", "ABANDONED", "DUPLICATE"}
# 计入当日配额的状态
COUNTED = {"PUBLISHING", "AUTO_REVIEW_PASSED", "MANUAL_REVIEW", "PUBLISHED"}
SOURCE_REQUIRED_TYPES = {"科普", "新闻"}


def now_iso():
    return datetime.now(timezone.utc).astimezone().isoformat(timespec="seconds")


def die(msg, code=2):
    print("错误: " + msg, file=sys.stderr)
    sys.exit(code)


def _norm(s):
    return (s or "").strip().lower()


def _norm_url(u):
    return (u or "").strip().rstrip("/").lower()


# ------------------------------ 存储 ------------------------------
def resolve_lib(args):
    if args.lib:
        return args.lib
    if args.ws:
        return os.path.join(args.ws, DEFAULT_LIB)
    return DEFAULT_LIB


def load(lib):
    if not os.path.exists(lib):
        return []
    rows = []
    with open(lib, "r", encoding="utf-8") as f:
        for ln, line in enumerate(f, 1):
            line = line.strip()
            if not line:
                continue
            try:
                rows.append(json.loads(line))
            except json.JSONDecodeError as e:
                die(f"{lib} 第 {ln} 行不是合法 JSON: {e}")
    return rows


def save(lib, rows):
    d = os.path.dirname(os.path.abspath(lib))
    os.makedirs(d, exist_ok=True)
    fd, tmp = tempfile.mkstemp(dir=d, prefix=".topics.", suffix=".tmp")
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as f:
            for r in rows:
                f.write(json.dumps(r, ensure_ascii=False) + "\n")
            f.flush()
            os.fsync(f.fileno())
        os.replace(tmp, lib)
    finally:
        if os.path.exists(tmp):
            try:
                os.remove(tmp)
            except OSError:
                pass


def find(rows, topic_id):
    for r in rows:
        if r.get("topic_id") == topic_id:
            return r
    return None


def gen_topic_id(rows):
    day = datetime.now().strftime("%Y%m%d")
    prefix = f"t-{day}-"
    seq = 0
    for r in rows:
        tid = r.get("topic_id", "")
        if tid.startswith(prefix):
            try:
                seq = max(seq, int(tid[len(prefix):]))
            except ValueError:
                pass
    return f"{prefix}{seq + 1:04d}"


# ------------------------------ 子命令 ------------------------------
def cmd_add(args):
    lib = resolve_lib(args)
    rows = load(lib)
    title_n = _norm(args.title)
    url_n = _norm_url(args.source_url)
    if not args.allow_duplicate:
        for r in rows:
            if r.get("status") in ("ABANDONED", "DUPLICATE"):
                continue
            if url_n and _norm_url((r.get("source") or {}).get("url")) == url_n:
                die(f"重复选题：来源 URL 已存在（{r.get('topic_id')}）。如确需新增用 --allow-duplicate")
            if title_n and _norm(r.get("title")) == title_n:
                die(f"重复选题：标题已存在（{r.get('topic_id')}）。如确需新增用 --allow-duplicate")
    if args.type in SOURCE_REQUIRED_TYPES and args.source_mode == "crawl" and not url_n:
        die(f"{args.type} 且 source-mode=crawl 时必须提供 --source-url（定位到具体新闻页）")
    tid = gen_topic_id(rows)
    rec = {
        "topic_id": tid,
        "type": args.type,
        "title": args.title,
        "source": {"mode": args.source_mode, "url": args.source_url or "", "ref": args.source_ref or ""},
        "series": {"book_or_drama_id": args.series_id, "chapter_or_episode": args.chapter},
        "agent": {"local_id": args.agent or ""},
        "assets": {"cover_file_id": None, "media_file_ids": []},
        "post": {"post_id": None, "url": None, "idempotency_key": None, "published_at": None},
        "status": "PENDING",
        "review": {"machine": "pending", "machine_reason": "", "human": "pending", "human_reason": ""},
        "revisions": [],
        "history": [{"at": now_iso(), "from": "", "to": "PENDING", "note": "created"}],
        "created_at": now_iso(),
        "updated_at": now_iso(),
    }
    rows.append(rec)
    save(lib, rows)
    # 建素材目录
    base_dir = os.path.join(os.path.dirname(os.path.abspath(lib)), tid)
    os.makedirs(os.path.join(base_dir, "covers"), exist_ok=True)
    with open(os.path.join(base_dir, "meta.json"), "w", encoding="utf-8") as f:
        json.dump(rec, f, ensure_ascii=False, indent=2)
    with open(os.path.join(base_dir, "source.md"), "w", encoding="utf-8") as f:
        f.write(f"# 来源\n\n- 模式: {args.source_mode}\n- URL: {args.source_url or ''}\n- 出处: {args.source_ref or ''}\n")
    print(f"✓ 新增选题 {tid}  status=PENDING  -> {base_dir}")
    return 0


def cmd_next(args):
    lib = resolve_lib(args)
    rows = load(lib)
    want = "READY" if not args.include_pending else None
    for r in rows:
        if args.type and r.get("type") != args.type:
            continue
        if want and r.get("status") != want:
            continue
        if not want and r.get("status") not in ("READY", "PENDING", "DRAFTING"):
            continue
        print(json.dumps(r, ensure_ascii=False))
        return 0
    print("无可用选题", file=sys.stderr)
    return 1


def cmd_list(args):
    lib = resolve_lib(args)
    rows = load(lib)
    out = []
    for r in rows:
        if args.status and r.get("status") != args.status:
            continue
        if args.type and r.get("type") != args.type:
            continue
        out.append(r)
    if args.json:
        print(json.dumps(out, ensure_ascii=False, indent=2))
    else:
        if not out:
            print("(空)")
        for r in out:
            p = r.get("post") or {}
            print(f"{r.get('topic_id')}  {r.get('status'):18s} {r.get('type'):4s}  "
                  f"{r.get('title','')[:30]:30s}  post={p.get('post_id') or '-'}")
    return 0


def cmd_set_status(args):
    lib = resolve_lib(args)
    rows = load(lib)
    r = find(rows, args.topic_id)
    if r is None:
        die(f"找不到 topic_id={args.topic_id}")
    cur = r.get("status")
    new = args.new_status
    if new not in TRANSITIONS:
        die(f"未知状态: {new}")
    if new != cur and new not in TRANSITIONS.get(cur, set()):
        if not args.force:
            allowed = ", ".join(sorted(TRANSITIONS.get(cur, set()))) or "(终态)"
            die(f"非法状态流转: {cur} -> {new}；允许: {allowed}（确需强制用 --force）")
    # 来源强约束：进入 READY 前，科普/新闻必须有可定位 URL
    if new == "READY" and r.get("type") in SOURCE_REQUIRED_TYPES:
        if not (r.get("source") or {}).get("url"):
            die(f"{r.get('type')} 进入 READY 前必须填写 source.url（具体新闻页）")
    # 回写 post/媒体/审核
    if args.post_id:
        r.setdefault("post", {})["post_id"] = args.post_id
    if args.post_url:
        r.setdefault("post", {})["url"] = args.post_url
    if args.idem_key:
        r.setdefault("post", {})["idempotency_key"] = args.idem_key
    if args.cover_file_id:
        r.setdefault("assets", {})["cover_file_id"] = args.cover_file_id
    if args.media_file_id:
        r.setdefault("assets", {})["media_file_ids"] = args.media_file_id
    rv = r.setdefault("review", {})
    if args.machine_review:
        rv["machine"] = args.machine_review
    if args.machine_reason:
        rv["machine_reason"] = args.machine_reason
    if args.human_review:
        rv["human"] = args.human_review
    if args.human_reason:
        rv["human_reason"] = args.human_reason
    if args.chapter is not None:
        r.setdefault("series", {})["chapter_or_episode"] = args.chapter
    if new == "REJECTED" and args.machine_reason:
        r.setdefault("revisions", []).append(
            {"at": now_iso(), "reason": args.machine_reason, "post_id": (r.get("post") or {}).get("post_id"), "result": "recorded"})
    if new == "PUBLISHED":
        r.setdefault("post", {})["published_at"] = r.get("post", {}).get("published_at") or now_iso()
    r.setdefault("history", []).append({"at": now_iso(), "from": cur, "to": new, "note": args.note or ""})
    prev = r["status"]
    r["status"] = new
    r["updated_at"] = now_iso()
    save(lib, rows)
    # 同步 meta.json
    base_dir = os.path.join(os.path.dirname(os.path.abspath(lib)), r["topic_id"])
    if os.path.isdir(base_dir):
        with open(os.path.join(base_dir, "meta.json"), "w", encoding="utf-8") as f:
            json.dump(r, f, ensure_ascii=False, indent=2)
    print(f"✓ {r['topic_id']}: {prev} -> {new}")
    return 0


def cmd_stats(args):
    lib = resolve_lib(args)
    rows = load(lib)
    day = args.date or datetime.now().strftime("%Y-%m-%d")
    counts = {}
    today_posts = 0
    for r in rows:
        counts[r.get("status")] = counts.get(r.get("status"), 0) + 1
        pa = (r.get("post") or {}).get("published_at")
        if r.get("status") in COUNTED and pa and str(pa)[:10] == day:
            today_posts += 1
    target = args.target
    print(f"日期 {day}: 当日发帖(计数状态) = {today_posts} / 目标 {target}"
          + ("  ⚠️超配额" if target and today_posts > target else ""))
    print("全库状态分布: " + json.dumps(counts, ensure_ascii=False, sort_keys=True))
    if counts or True:
        print("配额计入状态: " + ", ".join(sorted(COUNTED)))
    return 0


def cmd_schema(args):
    print("状态流转:")
    for s, nxt in TRANSITIONS.items():
        print(f"  {s:18s} -> " + (", ".join(sorted(nxt)) if nxt else "(终态)"))
    print("\n来源强约束类型: " + ", ".join(sorted(SOURCE_REQUIRED_TYPES)))
    print("配额计入状态: " + ", ".join(sorted(COUNTED)))
    print("\n记录字段见 references/07-topic-library.md 第 2 节")
    return 0


def build():
    p = argparse.ArgumentParser(description="选题库 = 帖子全生命周期状态台账")
    p.add_argument("--lib", default=None, help="topics.jsonl 路径 (默认 选题库/topics.jsonl)")
    p.add_argument("--ws", default=None, help="工作区目录(用它拼 选题库/topics.jsonl)")
    sub = p.add_subparsers(dest="cmd", required=True)

    a = sub.add_parser("add", help="新增选题")
    a.add_argument("--type", required=True, help="科普|新闻|小说|短剧|漫画|图文")
    a.add_argument("--title", required=True)
    a.add_argument("--source-mode", choices=["crawl", "llm"], default="llm")
    a.add_argument("--source-url", default="")
    a.add_argument("--source-ref", default="")
    a.add_argument("--series-id", default=None)
    a.add_argument("--chapter", default=None)
    a.add_argument("--agent", default=None)
    a.add_argument("--allow-duplicate", action="store_true")
    a.set_defaults(func=cmd_add)

    n = sub.add_parser("next", help="取下一条可发选题")
    n.add_argument("--type", default=None)
    n.add_argument("--include-pending", action="store_true")
    n.set_defaults(func=cmd_next)

    l = sub.add_parser("list", help="列出/筛选")
    l.add_argument("--status", default=None)
    l.add_argument("--type", default=None)
    l.add_argument("--json", action="store_true")
    l.set_defaults(func=cmd_list)

    s = sub.add_parser("set-status", help="状态流转")
    s.add_argument("topic_id")
    s.add_argument("new_status")
    s.add_argument("--post-id", default=None)
    s.add_argument("--post-url", default=None)
    s.add_argument("--idem-key", default=None)
    s.add_argument("--cover-file-id", default=None)
    s.add_argument("--media-file-id", action="append", default=None)
    s.add_argument("--machine-review", default=None)
    s.add_argument("--machine-reason", default=None)
    s.add_argument("--human-review", default=None)
    s.add_argument("--human-reason", default=None)
    s.add_argument("--chapter", default=None)
    s.add_argument("--note", default=None)
    s.add_argument("--force", action="store_true")
    s.set_defaults(func=cmd_set_status)

    st = sub.add_parser("stats", help="当日配额统计")
    st.add_argument("--date", default=None)
    st.add_argument("--target", type=int, default=12)
    st.set_defaults(func=cmd_stats)

    sc = sub.add_parser("schema", help="打印状态机")
    sc.set_defaults(func=cmd_schema)
    return p


def main(argv=None):
    args = build().parse_args(argv)
    return args.func(args)


if __name__ == "__main__":
    sys.exit(main())
