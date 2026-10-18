"""そら読みの X 自動投稿と数字の記録(GitHub Actions の x_bot.yml から動かす)。

python x_bot.py post      x_schedule.json の今日の予定どおりに投稿する(朝=前日21時の図、夕方=当日9時の図)。
                          公開中の図がまだ予定の時刻のものでなければ何もしない(30分後にもう一度呼ばれる)。
                          投稿 → (その回なら)アンケート。投稿済みは state/posted.json に残す。
                          リンクは投稿に入れない(リンク入りは料金が高く表示も減るので、プロフィールに置く)
python x_bot.py metrics   投稿済みの数字(表示・いいね・ブックマーク・プロフィールのクリック・返信・アンケート結果)を
                          state/metrics.csv に書き出す(X の非公開の数字は投稿から30日まで)。
                          もらったリプライ(感想)は state/replies.csv にためる(検索できるのは7日前までなので毎日呼ぶ)

X の鍵は環境変数 X_API_KEY / X_API_SECRET / X_ACCESS_TOKEN / X_ACCESS_SECRET(読み書き権限のアプリ)。
X_DRY_RUN=1 なら投稿せず、送る中身を表示するだけ。
"""
import csv
import json
import os
import sys
import time
import urllib.request
from datetime import datetime, timedelta, timezone

SITE_URL = os.environ.get("SITE_URL", "https://narabete-tenkizu.pages.dev/")
HERE = os.path.dirname(os.path.abspath(__file__))
STATE = os.environ.get("X_STATE_DIR", os.path.join(HERE, "state"))
API = "https://api.x.com/2/"
JST = timezone(timedelta(hours=9))
DRY = os.environ.get("X_DRY_RUN") == "1"

TEMPLATE = "【地上天気図 5枚まとめ】{m}/{d} {h}時({utc}UTC)\n48h前→24h前→最新→24h予想→48h予想\n{note}\n感想・見たい図のリクエストは、リプライでどうぞ\n出典：気象庁「地上天気図」を加工して作成\n#天気図 #気象予報士試験"


def get(url):
    req = urllib.request.Request(url, headers={"User-Agent": "Mozilla/5.0", "Cache-Control": "no-cache"})
    with urllib.request.urlopen(req, timeout=60) as r:
        return r.read()


def session():
    from requests_oauthlib import OAuth1Session
    return OAuth1Session(os.environ["X_API_KEY"], os.environ["X_API_SECRET"],
                         os.environ["X_ACCESS_TOKEN"], os.environ["X_ACCESS_SECRET"])


def load(name, default):
    try:
        with open(os.path.join(STATE, name), encoding="utf-8") as f:
            return json.load(f)
    except FileNotFoundError:
        return default


def save(name, data):
    os.makedirs(STATE, exist_ok=True)
    with open(os.path.join(STATE, name), "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=1)


def upload(x, jpg):
    if DRY:
        print("  画像", len(jpg) // 1024, "KB")
        return "dry"
    r = x.post(API + "media/upload", files={"media": ("chart.jpg", jpg, "image/jpeg")}, data={"media_category": "tweet_image"})
    r.raise_for_status()
    return r.json()["data"]["id"]


def tweet(x, body):
    if DRY:
        print("  投稿", json.dumps(body, ensure_ascii=False))
        return "dry"
    r = x.post(API + "tweets", json=body)
    if r.status_code >= 400:
        print(r.status_code, r.text)
    r.raise_for_status()
    time.sleep(3)
    return r.json()["data"]["id"]


def post():
    now = datetime.fromisoformat(os.environ["X_NOW"]) if os.environ.get("X_NOW") else datetime.now(JST)  # 試すとき用
    slot = "am" if now.hour < 12 else "pm"
    date = now.strftime("%Y-%m-%d")
    sched = json.load(open(os.path.join(HERE, "x_schedule.json"), encoding="utf-8"))
    day = sched["days"].get(date)
    posted = load("posted.json", {})
    key = date + slot
    if not day:
        print("今日の予定はありません", date)
        return
    if key in posted and not DRY:
        print("投稿済み", key)
        return
    # 朝は前日 12UTC(21時)、夕方は当日 00UTC(9時)の図
    want = (now - timedelta(days=1)).strftime("%Y-%m-%d 12:00") if slot == "am" else now.strftime("%Y-%m-%d 00:00")
    v = int(time.time())
    latest = json.loads(get(f"{SITE_URL}state.json?v={v}"))["latest_utc"]
    if latest != want:
        print("まだ予定の図ではありません", latest, "待っている図", want)
        return
    t = datetime.strptime(latest, "%Y-%m-%d %H:%M")
    j = t + timedelta(hours=9)
    text = TEMPLATE.format(m=j.month, d=j.day, h=j.hour, utc=f"{t:%H}", note=day[slot])
    files = ["x_post.jpg"] if day["set"] == 1 else [f"x_set/{i}.jpg" for i in range(1, 5)]

    x = None if DRY else session()
    print(key, latest)
    media = [upload(x, get(f"{SITE_URL}{f}?v={v}")) for f in files]
    ids = {"chart": latest, "set": day["set"], "main": tweet(x, {"text": text, "media": {"media_ids": media}})}
    poll = day.get("poll")
    if poll and poll["slot"] == slot:
        p = sched["polls"][str(poll["id"])]
        ids["poll"] = tweet(x, {"text": p["text"], "poll": {"options": p["options"], "duration_minutes": 3 * 24 * 60}})
        ids["poll_id"] = poll["id"]
    if not DRY:
        posted[key] = ids
        save("posted.json", posted)
    print("投稿しました", ids)


def metrics():
    posted = load("posted.json", {})
    rows = []
    for key, ids in posted.items():
        for kind in ("main", "poll"):
            if kind in ids:
                rows.append({"回": key, "種類": kind, "形": ids.get("set", ""), "id": ids[kind]})
    if not rows:
        print("投稿がまだありません")
        return
    x = session()
    found = {}
    for i in range(0, len(rows), 100):
        part = ",".join(r["id"] for r in rows[i:i + 100])
        params = {"ids": part, "tweet.fields": "public_metrics,non_public_metrics,created_at",
                  "expansions": "attachments.poll_ids", "poll.fields": "options,voting_status"}
        r = x.get(API + "tweets", params=params)
        if r.status_code >= 400:  # 30日を過ぎた投稿があると非公開の数字が取れない
            params["tweet.fields"] = "public_metrics,created_at"
            r = x.get(API + "tweets", params=params)
        r.raise_for_status()
        d = r.json()
        polls = {p["id"]: p for p in d.get("includes", {}).get("polls", [])}
        for tw in d.get("data", []):
            pid = (tw.get("attachments", {}).get("poll_ids") or [None])[0]
            found[tw["id"]] = (tw, polls.get(pid))
    stamp = datetime.now(JST).strftime("%Y-%m-%d %H:%M")
    cols = ["回", "種類", "形", "id", "表示", "いいね", "ブックマーク", "プロフィールのクリック", "リンクのクリック", "返信", "リポスト", "アンケート", "取得"]
    for r in rows:
        tw, poll = found.get(r["id"], ({}, None))
        pm, npm = tw.get("public_metrics", {}), tw.get("non_public_metrics", {})
        r.update({"表示": pm.get("impression_count", npm.get("impression_count", "")), "いいね": pm.get("like_count", ""),
                  "ブックマーク": pm.get("bookmark_count", ""), "プロフィールのクリック": npm.get("user_profile_clicks", ""),
                  "リンクのクリック": npm.get("url_link_clicks", ""), "返信": pm.get("reply_count", ""),
                  "リポスト": pm.get("retweet_count", ""),
                  "アンケート": " / ".join(f"{o['label']}:{o['votes']}" for o in poll["options"]) if poll else "", "取得": stamp})
    os.makedirs(STATE, exist_ok=True)
    with open(os.path.join(STATE, "metrics.csv"), "w", encoding="utf-8-sig", newline="") as f:
        w = csv.DictWriter(f, fieldnames=cols)
        w.writeheader()
        w.writerows(rows)
    print(len(rows), "件を書き出しました")
    replies(x, posted)


def replies(x, posted):
    """投稿へのリプライ(感想・リクエスト)を replies.csv にためる。"""
    path = os.path.join(STATE, "replies.csv")
    old = []
    if os.path.exists(path):
        with open(path, encoding="utf-8-sig", newline="") as f:
            old = list(csv.DictReader(f))
    seen = {r["id"] for r in old}
    week = (datetime.now(JST) - timedelta(days=6)).strftime("%Y-%m-%d")
    for key, ids in posted.items():
        for kind in ("main", "poll"):
            if kind not in ids or key[:10] < week:
                continue
            r = x.get(API + "tweets/search/recent", params={
                "query": f"conversation_id:{ids[kind]}", "tweet.fields": "created_at", "max_results": 100})
            if r.status_code >= 400:
                print("リプライを取れませんでした", r.status_code, r.text[:200])
                continue
            for tw in r.json().get("data", []):
                if tw["id"] not in seen:
                    seen.add(tw["id"])
                    old.append({"回": key, "種類": kind, "id": tw["id"], "日時": tw.get("created_at", ""), "本文": tw["text"]})
    with open(path, "w", encoding="utf-8-sig", newline="") as f:
        w = csv.DictWriter(f, fieldnames=["回", "種類", "id", "日時", "本文"])
        w.writeheader()
        w.writerows(old)
    print("リプライ", len(old), "件")


def check():
    """鍵が正しく登録されたかを確かめる(投稿はしない)。自分のアカウント名を表示する。"""
    r = session().get(API + "users/me")
    print(r.status_code, r.text[:300])
    r.raise_for_status()


if __name__ == "__main__":
    if not os.environ.get("X_API_KEY") and not DRY:
        print("X の鍵がまだ登録されていません(GitHub の Secrets に X_API_KEY などを入れると動きます)")
        sys.exit(0)
    {"post": post, "metrics": metrics, "check": check}[sys.argv[1]]()
