#!/usr/bin/env python3
"""社群經營 CLI：佇列、發佈、成效同步、回覆。支援 Threads、Bluesky。僅用標準函式庫。

資料全是純文字檔（posts/、metrics/、replies/），沒有資料庫。
多角色：每個角色一個資料夾 accounts/<代號>/，各自有檔案與 .env，彼此完全獨立。
一個角色可以經營多個平台（accounts/<代號>/platforms.md）；每篇貼文屬於一個平台，
同一則內容發到多個平台時會各存一篇，用 group 欄位連起來，核准、發佈、成效都按平台獨立。
除 accounts / init-account / overview 外，每個指令都必須明確指定 --account <代號>（不做「目前選中」的記憶，避免發錯帳號）。
該平台沒有憑證時自動 dry-run（不打 API，只動本地檔案）。
"""
import argparse
import json
import os
import re
import secrets
import shutil
import sys
import urllib.error
import urllib.parse
import urllib.request
from datetime import datetime, timezone, timedelta
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
ACCOUNTS = ROOT / "accounts"
TEMPLATE = ROOT / "templates" / "account"
SLUG_RE = re.compile(r"^[a-z0-9][a-z0-9-]*$")
ACCOUNT_DIR = None   # main() 依 --account 設定
TZ = timezone(timedelta(hours=8))  # 台北時間，排程與報表皆以此為準
ENV_KEYS = ("THREADS_ACCESS_TOKEN", "THREADS_USER_ID", "BLUESKY_HANDLE", "BLUESKY_APP_PASSWORD", "BLUESKY_SERVICE")


def out(obj):
    print(json.dumps(obj, ensure_ascii=False, indent=2, default=str))


def now():
    return datetime.now(TZ)


# ---------- 儲存層：純文字檔（git 即歷史與同步） ----------
# posts/<id>.md                       一篇貼文一個檔：frontmatter（單行 key: value）＋空行＋正文
# metrics/<平台>__<遠端id>.json        成效快照清單（只有 sync 會寫）
# replies/<平台>__<遠端id>.json        留言與草稿回覆
POST_KEYS = ("id", "status", "platform", "group", "scheduled_at", "published_at", "remote_id", "permalink",
             "tags", "strategy_version", "created_at", "note")


def _dir(name):
    d = ACCOUNT_DIR / name
    d.mkdir(exist_ok=True)
    return d


def _oneline(v):
    return " ".join(str(v if v is not None else "").split())


def safe(s):
    return re.sub(r"[^A-Za-z0-9_.-]", "_", str(s))


def parse_dt(s):
    if not s:
        return None
    d = datetime.fromisoformat(str(s).replace("Z", "+00:00"))
    return d if d.tzinfo else d.replace(tzinfo=TZ)


def post_path(pid):
    pid = str(pid)
    return _dir("posts") / (f"{int(pid):04d}.md" if pid.isdigit() else f"{pid}.md")


def read_post(path):
    raw = path.read_text(encoding="utf-8")
    head, _, body = raw.partition("\n---\n")
    p = {k: "" for k in POST_KEYS}
    for line in head.removeprefix("---\n").splitlines():
        if ":" in line:
            k, v = line.split(":", 1)
            k = {"threads_id": "remote_id"}.get(k.strip(), k.strip())   # 舊格式相容
            p[k] = v.strip()
    body = body.removeprefix("\n")
    p["text"] = body[:-1] if body.endswith("\n") else body
    if str(p["id"]).isdigit():
        p["id"] = int(p["id"])
    p["platform"] = p["platform"] or "threads"   # 舊貼文都是 Threads
    return p


def write_post(p):
    lines = ["---"] + [f"{k}: {_oneline(p.get(k))}" for k in POST_KEYS] + ["---", "", p["text"], ""]
    post_path(p["id"]).write_text("\n".join(lines), encoding="utf-8")


def all_posts():
    ps = [read_post(f) for f in sorted(_dir("posts").glob("*.md"))]
    return sorted(ps, key=lambda p: parse_dt(p["scheduled_at"] or p["created_at"]) or datetime.min.replace(tzinfo=TZ))


def get_post(pid):
    path = post_path(pid)
    return read_post(path) if path.exists() else None


def next_id():
    ids = [int(f.stem) for f in _dir("posts").glob("*.md") if f.stem.isdigit()]
    return max(ids, default=0) + 1


def mkey(platform, rid):
    return f"{platform}__{safe(rid)}"


def load_metrics(key):
    f = _dir("metrics") / f"{key}.json"
    return json.loads(f.read_text(encoding="utf-8")) if f.exists() else []


def add_metrics(platform, rid, m):
    """快照跟上一筆一樣、且不到 24 小時就不重複記，避免無意義的 commit。"""
    key = mkey(platform, rid)
    snaps = load_metrics(key)
    keys = ("views", "likes", "replies", "reposts", "quotes", "shares")
    if snaps:
        last = snaps[-1]
        same = all(last.get(k, 0) == m.get(k, 0) for k in keys)
        if same and now() - parse_dt(last["fetched_at"]) < timedelta(hours=24):
            return False
    snaps.append({"fetched_at": now().isoformat(), **{k: m.get(k, 0) for k in keys}})
    (_dir("metrics") / f"{key}.json").write_text(json.dumps(snaps, ensure_ascii=False, indent=1), encoding="utf-8")
    return True


def latest_metrics(platform, rid):
    s = load_metrics(mkey(platform, rid))
    return s[-1] if s else None


def all_replies():
    return [json.loads(f.read_text(encoding="utf-8")) for f in sorted(_dir("replies").glob("*.json"))]


def save_reply(r):
    (_dir("replies") / f"{r['key']}.json").write_text(json.dumps(r, ensure_ascii=False, indent=1), encoding="utf-8")


def get_reply(key):
    f = _dir("replies") / f"{key}.json"
    if not f.exists():
        raise SystemExit(f"找不到留言 {key}（請用 replies 列出的 key）")
    return json.loads(f.read_text(encoding="utf-8"))


# ---------- 平台 ----------
def http(method, url, form=None, body=None, headers=None):
    data, h = None, dict(headers or {})
    if form is not None:
        if method == "GET":
            url += "?" + urllib.parse.urlencode(form)
        else:
            data = urllib.parse.urlencode(form).encode()
    if body is not None:
        data = json.dumps(body).encode()
        h["Content-Type"] = "application/json"
    req = urllib.request.Request(url, data=data, method=method, headers=h)
    try:
        with urllib.request.urlopen(req, timeout=30) as r:
            return json.load(r)
    except urllib.error.HTTPError as e:
        raise SystemExit(json.dumps({"error": e.code, "body": e.read().decode()}, ensure_ascii=False))


class Threads:
    name, limit, has_views = "threads", 500, True
    API = "https://graph.threads.net/v1.0"

    def configured(self):
        return bool(os.environ.get("THREADS_ACCESS_TOKEN"))

    def _call(self, method, path, params=None):
        p = dict(params or {})
        p["access_token"] = os.environ.get("THREADS_ACCESS_TOKEN")
        return http(method, f"{self.API}/{path}", form=p)

    def _uid(self):
        return os.environ.get("THREADS_USER_ID", "me")

    def publish(self, text, reply_to=None):
        p = {"media_type": "TEXT", "text": text}
        if reply_to:
            p["reply_to_id"] = reply_to
        c = self._call("POST", f"{self._uid()}/threads", p)
        r = self._call("POST", f"{self._uid()}/threads_publish", {"creation_id": c["id"]})
        info = self._call("GET", r["id"], {"fields": "permalink"})
        return {"id": r["id"], "permalink": info.get("permalink", "")}

    def recent(self, days):
        since = int((now() - timedelta(days=days)).timestamp())
        listing = self._call("GET", f"{self._uid()}/threads", {"fields": "id,text,timestamp,permalink", "since": since, "limit": 50})
        res = []
        for t in listing.get("data", []):
            ins = self._call("GET", f"{t['id']}/insights", {"metric": "views,likes,replies,reposts,quotes,shares"})
            m = {x["name"]: x["values"][0]["value"] for x in ins.get("data", [])}
            res.append({"id": t["id"], "text": t.get("text", ""), "timestamp": t["timestamp"],
                        "permalink": t.get("permalink", ""), "metrics": m})
        return res

    def replies(self, post_id):
        data = self._call("GET", f"{post_id}/replies", {"fields": "id,text,username,timestamp"}).get("data", [])
        return [{"id": x["id"], "text": x.get("text", ""), "username": x.get("username", ""),
                 "timestamp": x.get("timestamp", ""), "ref": {}} for x in data]

    def reply(self, r, text):
        return self.publish(text, reply_to=r["id"])

    def refresh_token(self):
        return self._call("GET", "refresh_access_token", {"grant_type": "th_refresh_token"})


class Bluesky:
    name, limit, has_views = "bluesky", 300, False   # Bluesky 沒有瀏覽數

    def __init__(self):
        self._s = None

    def configured(self):
        return bool(os.environ.get("BLUESKY_HANDLE") and os.environ.get("BLUESKY_APP_PASSWORD"))

    def _host(self):
        return os.environ.get("BLUESKY_SERVICE", "https://bsky.social").rstrip("/")

    def _session(self):
        if not self._s:
            self._s = http("POST", f"{self._host()}/xrpc/com.atproto.server.createSession",
                           body={"identifier": os.environ["BLUESKY_HANDLE"], "password": os.environ["BLUESKY_APP_PASSWORD"]})
        return self._s

    def _call(self, method, nsid, params=None, body=None):
        h = {"Authorization": f"Bearer {self._session()['accessJwt']}"}
        return http(method, f"{self._host()}/xrpc/{nsid}", form=params if method == "GET" else None, body=body, headers=h)

    def publish(self, text, reply=None):
        s = self._session()
        rec = {"$type": "app.bsky.feed.post", "text": text,
               "createdAt": datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%S.000Z")}
        if reply:
            rec["reply"] = reply
        r = self._call("POST", "com.atproto.repo.createRecord",
                       body={"repo": s["did"], "collection": "app.bsky.feed.post", "record": rec})
        return {"id": r["uri"], "permalink": f"https://bsky.app/profile/{s['handle']}/post/{r['uri'].rsplit('/', 1)[-1]}"}

    def recent(self, days):
        s = self._session()
        since = now() - timedelta(days=days)
        feed = self._call("GET", "app.bsky.feed.getAuthorFeed",
                          {"actor": s["did"], "limit": 50, "filter": "posts_no_replies"}).get("feed", [])
        res = []
        for item in feed:
            p = item["post"]
            if item.get("reason") or p["author"]["did"] != s["did"]:   # 略過轉發別人的
                continue
            ts = p["record"].get("createdAt", "")
            if not ts or parse_dt(ts) < since:
                continue
            res.append({"id": p["uri"], "text": p["record"].get("text", ""), "timestamp": ts,
                        "permalink": f"https://bsky.app/profile/{s['handle']}/post/{p['uri'].rsplit('/', 1)[-1]}",
                        "metrics": {"likes": p.get("likeCount", 0), "replies": p.get("replyCount", 0),
                                    "reposts": p.get("repostCount", 0), "quotes": p.get("quoteCount", 0)}})
        return res

    def replies(self, post_uri):
        s = self._session()
        th = self._call("GET", "app.bsky.feed.getPostThread", {"uri": post_uri, "depth": 1}).get("thread", {})
        root = {"uri": th["post"]["uri"], "cid": th["post"]["cid"]} if th.get("post") else None
        res = []
        for x in th.get("replies", []) or []:
            p = x.get("post")
            if not p or not root or p["author"]["did"] == s["did"]:   # 略過自己的回覆
                continue
            res.append({"id": p["uri"], "text": p["record"].get("text", ""), "username": p["author"].get("handle", ""),
                        "timestamp": p["record"].get("createdAt", ""),
                        "ref": {"root": root, "parent": {"uri": p["uri"], "cid": p["cid"]}}})
        return res

    def reply(self, r, text):
        ref = r.get("ref") or {}
        if not ref.get("root") or not ref.get("parent"):
            raise SystemExit("這則留言沒有 root/parent 資訊，請重新 pull-replies")
        return self.publish(text, reply={"root": ref["root"], "parent": ref["parent"]})


PLATFORMS = {"threads": Threads, "bluesky": Bluesky}
_clients = {}


def client(platform):
    if platform not in PLATFORMS:
        raise SystemExit(f"不支援的平台 {platform}。支援：{', '.join(PLATFORMS)}")
    if platform not in _clients:
        _clients[platform] = PLATFORMS[platform]()
    return _clients[platform]


def dry(platform):
    return not client(platform).configured() or os.environ.get("SOCIAL_DRY_RUN") == "1" or os.environ.get("THREADS_DRY_RUN") == "1"


def publish_one(platform, text, reply_to=None):
    """reply_to 是留言記錄（回覆時用），None 表示發新貼文。"""
    if dry(platform):
        return {"id": f"dry-{platform}-{secrets.token_hex(4)}", "permalink": ""}
    c = client(platform)
    return c.reply(reply_to, text) if reply_to else c.publish(text)


# ---------- 帳號與設定 ----------
def load_env():
    """只讀該角色自己的 .env。先清掉 shell 繼承來的憑證，避免別的帳號的被拿來用。"""
    for k in ENV_KEYS:
        os.environ.pop(k, None)
    _clients.clear()
    env_file = ACCOUNT_DIR / ".env"
    if env_file.exists():
        for line in env_file.read_text().splitlines():
            if "=" in line and not line.strip().startswith("#"):
                k, v = line.split("=", 1)
                if v.strip():
                    os.environ[k.strip()] = v.strip()


def use_account(slug):
    global ACCOUNT_DIR
    if not SLUG_RE.match(slug or ""):
        raise SystemExit("角色代號只能用小寫英文、數字、連字號（例：ai-hype-tsukkomi）")
    ACCOUNT_DIR = ACCOUNTS / slug
    if not ACCOUNT_DIR.is_dir():
        raise SystemExit(f"找不到角色 {slug}。現有角色：{', '.join(list_accounts()) or '（無）'}；新增請用 init-account {slug}")


def list_accounts():
    return sorted(p.name for p in ACCOUNTS.iterdir() if p.is_dir()) if ACCOUNTS.exists() else []


def _front(path, key):
    if path.exists():
        for line in path.read_text(encoding="utf-8").splitlines():
            if line.startswith(key + ":"):
                return line.split(":", 1)[1].strip()
    return ""


def enabled_platforms():
    """這個角色經營哪些平台，唯一來源是 platforms.md 的 platforms: 欄位。"""
    ps = [x.strip() for x in _front(ACCOUNT_DIR / "platforms.md", "platforms").split(",") if x.strip()]
    for p in ps:
        if p not in PLATFORMS:
            raise SystemExit(f"platforms.md 裡有不支援的平台 {p}。支援：{', '.join(PLATFORMS)}")
    return ps


# ---------- commands ----------
def cmd_add(a):
    enabled = enabled_platforms()
    if not enabled:
        raise SystemExit("這個角色還沒設定平台。請先在 accounts/<代號>/platforms.md 填 platforms:（threads / bluesky）")
    targets = [x.strip() for x in a.platform.split(",")] if a.platform else enabled
    for t in targets:
        if t not in enabled:
            raise SystemExit(f"這個角色沒有啟用 {t}（已啟用：{', '.join(enabled)}）")
        if len(a.text) > PLATFORMS[t].limit:
            raise SystemExit(f"{t} 上限 {PLATFORMS[t].limit} 字（目前 {len(a.text)}）。要依平台改寫，請分開用 --platform 各加一篇")
    ids, group = {}, ""
    for t in targets:
        pid = next_id()
        group = group or (str(pid) if len(targets) > 1 else "")
        write_post({"id": pid, "status": "draft", "platform": t, "group": group, "scheduled_at": a.at or "", "tags": a.tags,
                    "strategy_version": a.strategy, "note": a.note, "created_at": now().isoformat(), "text": a.text})
        ids[t] = pid
    out({"ids": ids, "status": "draft", "group": group or None})


def cmd_list(a):
    rows = [p for p in all_posts() if (not a.status or p["status"] == a.status) and (not a.platform or p["platform"] == a.platform)]
    out([{"id": p["id"], "platform": p["platform"], "group": p["group"] or None, "status": p["status"],
          "scheduled_at": p["scheduled_at"] or None, "tags": p["tags"], "preview": p["text"][:80]} for p in rows[:a.limit]])


def cmd_set_status(status):
    def run(a):
        for pid in a.ids:
            p = get_post(pid)
            if not p:
                raise SystemExit(f"找不到貼文 {pid}")
            p["status"] = status
            if getattr(a, "note", ""):
                p["note"] = a.note
            write_post(p)
        out({"ids": a.ids, "status": status})
    return run


def publish_due_core(max_n):
    """只發 status=approved 且排程時間已到的貼文。回傳結果清單。"""
    t = now()
    rows = [p for p in all_posts() if p["status"] == "approved" and (not p["scheduled_at"] or parse_dt(p["scheduled_at"]) <= t)]
    results, n = [], 0
    for p in rows:
        if n >= max_n:
            break
        plat = p["platform"]
        if plat not in PLATFORMS:
            p.update(status="failed", note=f"不支援的平台 {plat}")
            write_post(p)
            results.append({"id": p["id"], "ok": False, "error": p["note"]})
            continue
        n += 1
        try:
            res = publish_one(plat, p["text"])
            p.update(status="published", published_at=now().isoformat(), remote_id=res["id"], permalink=res["permalink"])
            results.append({"id": p["id"], "platform": plat, "ok": True, **res, "dry_run": dry(plat)})
        except SystemExit as e:
            p.update(status="failed", note=str(e))
            results.append({"id": p["id"], "platform": plat, "ok": False, "error": str(e)})
        write_post(p)
    return results


def cmd_publish_due(a):
    if a.all:
        # 逐一處理每個角色：各用各自的檔案與憑證，互不影響；一個角色出錯不影響其他角色
        res = {}
        for slug in list_accounts():
            try:
                use_account(slug)
                load_env()
                res[slug] = publish_due_core(a.max)
            except (SystemExit, Exception) as e:
                res[slug] = {"error": str(e)}
        return out(res)
    out(publish_due_core(a.max))


def cmd_sync(a):
    """抓近期貼文與成效，寫入 metrics/。每個啟用且有憑證的平台各跑一次。"""
    res = {}
    for plat in enabled_platforms():
        if dry(plat):
            res[plat] = {"skipped": "dry-run，沒有憑證"}
            continue
        known = {p["remote_id"] for p in all_posts() if p["platform"] == plat and p["remote_id"]}
        n = 0
        for t in client(plat).recent(a.days):
            add_metrics(plat, t["id"], t["metrics"])
            # 補登未經本工具發出的貼文，讓報表完整（檔名 ext-…，不佔用數字編號，避免本機與雲端撞號）
            if t["id"] not in known:
                write_post({"id": f"ext-{plat}-{safe(t['id'])}", "status": "published", "platform": plat,
                            "published_at": t["timestamp"], "remote_id": t["id"], "permalink": t["permalink"],
                            "created_at": t["timestamp"], "text": t["text"]})
            n += 1
        res[plat] = {"synced": n}
    out(res or {"skipped": "這個角色還沒設定平台"})


def cmd_pull_replies(a):
    have = {r["key"] for r in all_replies()}
    res = {}
    for plat in enabled_platforms():
        if dry(plat):
            res[plat] = {"skipped": "dry-run"}
            continue
        posts = sorted((p for p in all_posts() if p["platform"] == plat and p["status"] == "published" and p["remote_id"]),
                       key=lambda p: p["published_at"], reverse=True)[:a.recent]
        new = 0
        for p in posts:
            for x in client(plat).replies(p["remote_id"]):
                key = mkey(plat, x["id"])
                if key in have:
                    continue
                save_reply({"key": key, "id": x["id"], "platform": plat, "post_remote_id": p["remote_id"],
                            "username": x["username"], "text": x["text"], "ts": x["timestamp"], "ref": x["ref"],
                            "draft_reply": "", "status": "new"})
                have.add(key)
                new += 1
        res[plat] = {"new_replies": new}
    out(res or {"skipped": "這個角色還沒設定平台"})


def cmd_replies(a):
    out(sorted((r for r in all_replies() if r["status"] == a.status), key=lambda r: r["ts"]))


def cmd_draft_reply(a):
    r = get_reply(a.key)
    limit = PLATFORMS[r["platform"]].limit
    if len(a.text) > limit:
        raise SystemExit(f"{r['platform']} 上限 {limit} 字（目前 {len(a.text)}）")
    r.update(draft_reply=a.text, status="drafted")
    save_reply(r)
    out({"key": a.key, "status": "drafted"})


def cmd_approve_reply(a):
    for key in a.keys:
        r = get_reply(key)
        r["status"] = "ignored" if a.ignore else "approved"
        save_reply(r)
    out({"keys": a.keys})


def cmd_send_replies(a):
    res = []
    for r in [r for r in all_replies() if r["status"] == "approved"]:
        p = publish_one(r["platform"], r["draft_reply"], reply_to=r)
        r["status"] = "sent"
        save_reply(r)
        res.append({"reply_to": r["key"], **p, "dry_run": dry(r["platform"])})
    out(res)


def cmd_report(a):
    """每篇貼文取最新一筆 metrics，按平台分開輸出明細並依 tag 聚合（不同平台的指標不可直接比），供 review-performance 使用。"""
    since = now() - timedelta(days=a.days)
    plats = {}
    for p in all_posts():
        m = latest_metrics(p["platform"], p["remote_id"]) if p["remote_id"] else None
        if p["status"] != "published" or not m or not p["published_at"] or parse_dt(p["published_at"]) < since:
            continue
        hv = PLATFORMS[p["platform"]].has_views
        eng = m["likes"] + m["replies"] + m["reposts"] + m["quotes"] + m["shares"]
        d = {"id": p["id"], "published_at": p["published_at"], "tags": p["tags"], "strategy_version": p["strategy_version"],
             "preview": p["text"][:60], "likes": m["likes"], "replies": m["replies"], "reposts": m["reposts"],
             "quotes": m["quotes"], "shares": m["shares"], "engagement": eng,
             "hour": parse_dt(p["published_at"]).astimezone(TZ).hour}
        if hv:
            d["views"] = m["views"]
            d["engagement_rate"] = round(eng / m["views"], 4) if m["views"] else 0
        b = plats.setdefault(p["platform"], {"posts": [], "agg": {}, "has_views": hv})
        b["posts"].append(d)
        for tag in [t for t in (p["tags"] or "").split(",") if t] + [f"hour:{d['hour']}", f"strategy:{p['strategy_version']}"]:
            g = b["agg"].setdefault(tag, {"n": 0, "views": 0, "eng": 0})
            g["n"] += 1; g["views"] += m["views"] if hv else 0; g["eng"] += eng
    result = {}
    for plat, b in plats.items():
        summary = {}
        for tag, g in b["agg"].items():
            s = {"n": g["n"], "avg_engagement": round(g["eng"] / g["n"], 1)}
            if b["has_views"]:
                s.update(avg_views=round(g["views"] / g["n"]), eng_rate=round(g["eng"] / g["views"], 4) if g["views"] else 0)
            summary[tag] = s
        result[plat] = {"post_count": len(b["posts"]), "metric": "engagement_rate（互動數／瀏覽數）" if b["has_views"] else "avg_engagement（此平台沒有瀏覽數，只能比互動數）",
                        "by_tag": summary, "posts": b["posts"]}
    out({"days": a.days, "platforms": result, "note": "樣本數 n<5 的 tag 不可當結論，只能當假設；不同平台不可直接比較"})


def cmd_accounts(a):
    global ACCOUNT_DIR
    res = []
    for slug in list_accounts():
        ACCOUNT_DIR = ACCOUNTS / slug
        res.append({"account": slug, "persona_status": _front(ACCOUNT_DIR / "persona.md", "status"),
                    "platforms": _platform_state(ACCOUNT_DIR)})
    out(res)


def _platform_state(d):
    """每個啟用的平台是否有憑證（只看本機 .env，不顯示內容）。"""
    global ACCOUNT_DIR
    ACCOUNT_DIR = d
    try:
        ps = enabled_platforms()
    except SystemExit:
        return {"error": "platforms.md 設定有誤"}
    load_env()
    state = {p: client(p).configured() for p in ps}
    return state


def cmd_init_account(a):
    """用 templates/account 建立一個空白角色資料夾（不含任何預設風格或範本內容）。"""
    if not SLUG_RE.match(a.slug):
        raise SystemExit("角色代號只能用小寫英文、數字、連字號")
    dest = ACCOUNTS / a.slug
    if dest.exists():
        raise SystemExit(f"{a.slug} 已存在，不覆蓋")
    plats = [x.strip() for x in (a.platforms or "").split(",") if x.strip()]
    for p in plats:
        if p not in PLATFORMS:
            raise SystemExit(f"不支援的平台 {p}。支援：{', '.join(PLATFORMS)}")
    shutil.copytree(TEMPLATE, dest)
    today = now().strftime("%Y-%m-%d")
    for f in ("persona.md", "brand-guide.md", "user.md", "platforms.md", "strategy.md", "changelog.md"):
        p = dest / f
        p.write_text(p.read_text(encoding="utf-8").replace("(日期)", today).replace("platforms: \n", f"platforms: {','.join(plats)}\n"), encoding="utf-8")
    out({"created": str(dest.relative_to(ROOT)), "next": "請執行 set-persona 訪談建立角色，再 set-style 定風格"})


def overview_rows():
    """所有角色一張表：誰在等你核准、誰快要發、誰沒動。不含成效比較（不同帳號、不同平台不可直接比）。"""
    global ACCOUNT_DIR
    rows = []
    for slug in list_accounts():
        d = ACCOUNTS / slug
        platforms = _platform_state(d)   # 會設定 ACCOUNT_DIR
        ps = all_posts()
        counts = {}
        for p in ps:
            counts[p["status"]] = counts.get(p["status"], 0) + 1
        approved = [p["scheduled_at"] for p in ps if p["status"] == "approved" and p["scheduled_at"]]
        published = [p["published_at"] for p in ps if p["status"] == "published" and p["published_at"]]
        syncs = [s[-1]["fetched_at"] for s in (load_metrics(f.stem) for f in _dir("metrics").glob("*.json")) if s]
        row = {"account": slug,
               "persona_status": _front(d / "persona.md", "status"),
               "strategy_version": _front(d / "strategy.md", "version"),
               "platforms": platforms,
               "counts": counts, "next_scheduled": min(approved, key=parse_dt) if approved else None,
               "last_published": max(published, key=parse_dt) if published else None,
               "last_sync": max(syncs, key=parse_dt) if syncs else None}
        c = row["counts"]
        row["need_you"] = {"draft_to_review": c.get("draft", 0), "failed": c.get("failed", 0),
                           "persona_unconfirmed": not row["persona_status"].startswith("已確認"),
                           "no_platform": not platforms}
        rows.append(row)
    return rows


def cmd_overview(a):
    out(overview_rows())


def cmd_refresh_token(a):
    """目前只有 Threads 的長效 token 需要定期換。"""
    if dry("threads"):
        return out({"skipped": "dry-run"})
    r = client("threads").refresh_token()
    out({"expires_in": r.get("expires_in"), "note": "請把新 access_token 寫回 .env 與 GitHub Secrets"})
    print(r.get("access_token"), file=sys.stderr)


def main():
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--account", help="角色代號（accounts/ 底下的資料夾名）；除 accounts / init-account / overview 外必填")
    sp = ap.add_subparsers(dest="cmd", required=True)

    s = sp.add_parser("accounts", help="列出所有角色"); s.set_defaults(f=cmd_accounts)
    s = sp.add_parser("overview", help="所有角色的狀態總覽"); s.set_defaults(f=cmd_overview)
    s = sp.add_parser("init-account", help="建立空白角色資料夾"); s.add_argument("slug")
    s.add_argument("--platforms", help="這個角色經營的平台，逗號分隔，例 threads,bluesky（可之後再填 platforms.md）"); s.set_defaults(f=cmd_init_account)

    s = sp.add_parser("add", help="新增草稿"); s.add_argument("text")
    s.add_argument("--platform", help="發到哪些平台（逗號分隔），預設為該角色啟用的全部；每個平台各存一篇")
    s.add_argument("--tags", default=""); s.add_argument("--strategy", default="")
    s.add_argument("--at", help="排程時間 ISO8601，例 2026-10-13T20:30:00+08:00"); s.add_argument("--note", default="")
    s.set_defaults(f=cmd_add)

    s = sp.add_parser("list"); s.add_argument("--status"); s.add_argument("--platform"); s.add_argument("--limit", type=int, default=30)
    s.set_defaults(f=cmd_list)

    for name, st in (("approve", "approved"), ("reject", "rejected")):
        s = sp.add_parser(name); s.add_argument("ids", type=int, nargs="+"); s.add_argument("--note", default="")
        s.set_defaults(f=cmd_set_status(st))

    s = sp.add_parser("publish-due", help="發出已核准且到時間的貼文"); s.add_argument("--max", type=int, default=3)
    s.add_argument("--all", action="store_true", help="一次處理所有角色（各用各自的憑證與檔案），此時不需 --account")
    s.set_defaults(f=cmd_publish_due)

    s = sp.add_parser("sync", help="同步貼文與成效"); s.add_argument("--days", type=int, default=14); s.set_defaults(f=cmd_sync)
    s = sp.add_parser("pull-replies"); s.add_argument("--recent", type=int, default=10); s.set_defaults(f=cmd_pull_replies)
    s = sp.add_parser("replies"); s.add_argument("--status", default="new"); s.set_defaults(f=cmd_replies)
    s = sp.add_parser("draft-reply"); s.add_argument("key"); s.add_argument("text"); s.set_defaults(f=cmd_draft_reply)
    s = sp.add_parser("approve-reply"); s.add_argument("keys", nargs="+"); s.add_argument("--ignore", action="store_true")
    s.set_defaults(f=cmd_approve_reply)
    s = sp.add_parser("send-replies"); s.set_defaults(f=cmd_send_replies)
    s = sp.add_parser("report"); s.add_argument("--days", type=int, default=14); s.set_defaults(f=cmd_report)
    s = sp.add_parser("refresh-token"); s.set_defaults(f=cmd_refresh_token)

    a = ap.parse_args()
    if a.cmd not in ("accounts", "init-account", "overview") and not (a.cmd == "publish-due" and a.all):
        if not a.account:
            raise SystemExit("必須指定 --account <代號>。現有角色：" + (", ".join(list_accounts()) or "（無）"))
        use_account(a.account)
        load_env()
    a.f(a)


if __name__ == "__main__":
    main()
