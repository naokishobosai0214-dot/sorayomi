"""「ならべて天気図」のページを作る(GitHub Actions から15分ごとに実行)。

python build_site.py --check   気象庁に新しい図が出たか調べるだけ(公開中の state.json と比べる)。
                               GitHub Actions では changed=true/false を出力に書く
python build_site.py           site\ に index.html・まとめ画像(JPG/PNG)・X投稿用画像・5枚の図・state.json を作る
"""
import html
import json
import os
import re
import shutil
import sys
import urllib.request
from datetime import timedelta

SITE_URL = os.environ.get("SITE_URL", "https://narabete-tenkizu.pages.dev/")
LINE_URL = "https://line.me/R/ti/p/@421edvfx"  # LINE公式アカウント「天気図配信」の友だち追加
HAISHIN = "https://naokishobosai0214-dot.github.io/tenkizu-haishin/"  # LINEで届く並べ図(tenkizu-haishin)
LIST = "https://www.jma.go.jp/bosai/weather_map/data/list.json"
HERE = os.path.dirname(os.path.abspath(__file__))
SITE = os.path.join(HERE, "site")


def get(url):
    req = urllib.request.Request(url, headers={"User-Agent": "Mozilla/5.0", "Cache-Control": "no-cache"})
    with urllib.request.urlopen(req, timeout=60) as r:
        return r.read()


def current_key():
    """FSAS24・48 のファイル名(初期値 00/12UTC)。2枚の初期値がそろったときだけ返し、そろっていなければ None。
    ASAS の「最新」はこの初期値と同じ時刻の図を使うので、1日2回(9時・21時の図)だけ作り直す。"""
    lst = json.loads(get(LIST))["asia_monochrome"]
    # ファイル名の2つ目の14桁が初期値(UTC)。check はライブラリを入れる前に動くので asas_view は使わない
    if len({re.findall(r"_(\d{14})_MET", lst[k][-1])[0] for k in ("ft24", "ft48")}) != 1:
        return None
    return {"ft24": lst["ft24"][-1], "ft48": lst["ft48"][-1]}


def published_key():
    try:
        return json.loads(get(SITE_URL + "state.json"))["key"]
    except Exception:
        return None


def check():
    key = current_key()
    changed = key is not None and (os.environ.get("FORCE") == "true" or key != published_key())
    print("changed:", changed)
    out = os.environ.get("GITHUB_OUTPUT")
    if out:
        with open(out, "a") as f:
            f.write(f"changed={'true' if changed else 'false'}\n")


def save_pdf(src, out, dpi=200, margin_mm=8):
    """まとめ画像を A4 横 1ページの PDF にする(余白 8mm・中央寄せ)"""
    from PIL import Image
    w, h = round(297 / 25.4 * dpi), round(210 / 25.4 * dpi)
    m = round(margin_mm / 25.4 * dpi)
    img = Image.open(src).convert("RGB")
    r = min((w - 2 * m) / img.width, (h - 2 * m) / img.height)
    img = img.resize((round(img.width * r), round(img.height * r)), Image.LANCZOS)
    page = Image.new("RGB", (w, h), "white")
    page.paste(img, ((w - img.width) // 2, (h - img.height) // 2))
    page.save(out, "PDF", resolution=dpi)


def line_samples():
    """LINEで届く並べ図(高層の実況 p2・数値予報 p3)の縮小版を site/line/ に置く。取れなくてもページは作る。"""
    from PIL import Image
    import io
    os.makedirs(os.path.join(SITE, "line"))
    try:
        for i, item in enumerate(json.loads(get(HAISHIN + "latest.json"))[1:3], 2):
            im = Image.open(io.BytesIO(get(HAISHIN + item["preview"]))).convert("RGB")
            im.thumbnail((360, 600))
            im.save(os.path.join(SITE, "line", f"p{i}.jpg"), quality=82)
    except Exception as e:
        print("LINEの見本画像を取れませんでした:", e)


def build():
    import asas_view
    import x_post
    from PIL import Image

    key = current_key()
    work = os.path.join(HERE, "work")
    shutil.rmtree(work, ignore_errors=True)
    shutil.rmtree(SITE, ignore_errors=True)
    os.makedirs(os.path.join(SITE, "charts"))
    asas_view.OUT = work
    charts = asas_view.fetch_charts()

    latest = x_post.make_image(charts, os.path.join(SITE, "latest.jpg"), cta="page", url=SITE_URL.replace("https://", ""))
    Image.open(os.path.join(SITE, "latest.jpg")).save(os.path.join(SITE, "latest.png"), optimize=True)
    save_pdf(os.path.join(SITE, "latest.jpg"), os.path.join(SITE, "latest.pdf"))
    x_post.make_image(charts, os.path.join(SITE, "x_post.jpg"), cta="x")
    # X 投稿用の4枚セット(x_bot.py が x_set/1.jpg〜4.jpg を取りに来る)
    os.makedirs(os.path.join(SITE, "x_set"))
    for i, p in enumerate(x_post.make_set(charts, os.path.join(work, "x_set")), 1):
        shutil.copy(p, os.path.join(SITE, "x_set", f"{i}.jpg"))
    line_samples()
    items = []
    for title, when, png in charts:
        name = png.replace(".png", ".jpg")
        Image.open(os.path.join(work, png)).convert("RGB").save(os.path.join(SITE, "charts", name), quality=88)
        items.append((title, when, name))

    j = latest + timedelta(hours=9)
    stamp = f"{j.year}年{j.month}月{j.day}日 {j.hour}時"
    v = latest.strftime("%Y%m%d%H") + key["ft24"][-20:-4]
    links = "".join(
        f'<a class="c{" now" if "最新" in t else ""}" href="charts/{n}?v={v}" target="_blank">'
        f'<b>{html.escape(t)}</b><span>{html.escape(w)}</span></a>'
        for t, w, n in items
    )
    page = PAGE.replace("__LINE_URL__", LINE_URL).replace("__STAMP__", stamp).replace("__V__", v).replace("__LINKS__", links)
    with open(os.path.join(SITE, "index.html"), "w", encoding="utf-8") as f:
        f.write(page)
    with open(os.path.join(SITE, "state.json"), "w", encoding="utf-8") as f:
        json.dump({"key": key, "latest_utc": latest.strftime("%Y-%m-%d %H:00")}, f, ensure_ascii=False)
    with open(os.path.join(SITE, ".nojekyll"), "w") as f:
        pass
    print("built", stamp, key)


PAGE = """<!doctype html>
<html lang="ja">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width,initial-scale=1">
<title>そら読み｜天気図は、並べると読める</title>
<meta name="description" content="天気図は「並べて」見ると流れが読める。地上天気図の48時間前・24時間前・最新・24時間予想・48時間予想を時間の流れどおり1枚に並べて、1日2回（9時・21時の図）お届け。高層天気図・数値予報図の並べ図も順次公開します。">
<meta property="og:title" content="そら読み">
<meta property="og:description" content="地上天気図 5枚まとめ(最新 __STAMP__)">
<meta property="og:image" content="latest.jpg?v=__V__">
<meta name="twitter:card" content="summary_large_image">
<meta name="theme-color" content="#7cc6f2">
<style>
:root{
  --sky1:#5fb4ec;--sky2:#a9dcf8;--sky3:#eaf7ff;
  --bg:#f6fbff;--card:#ffffff;--fg:#17324d;--muted:#5a7189;--line:#d7e9f6;
  --accent:#0f7fd0;--accent2:#ff9f1c;--now:#e0302b;--save:#06c755;
  --shadow:0 6px 24px rgba(23,80,140,.10);
  --sun:#ffd34d;--cloud:#ffffff;
}
@media (prefers-color-scheme:dark){:root{
  --sky1:#0b1b36;--sky2:#17335e;--sky3:#1d3f6e;
  --bg:#0e1828;--card:#16243a;--fg:#e6effa;--muted:#9fb3cc;--line:#26395a;
  --accent:#5db8ff;--accent2:#ffb648;--now:#ff6159;
  --shadow:0 6px 24px rgba(0,0,0,.35);
  --sun:#f3e6a8;--cloud:#c9d7ea;
}}
*{box-sizing:border-box}
html{scroll-behavior:smooth}
body{margin:0;background:var(--bg);color:var(--fg);font-family:"BIZ UDPGothic","Hiragino Sans","Yu Gothic UI",sans-serif;line-height:1.75;overflow-x:hidden}
a{color:var(--accent)}
.wrap{max-width:1080px;margin:0 auto;padding:0 16px}

/* ヒーロー(時刻に合わせた空: 朝・昼・夕方・夜) */
.hero{position:relative;overflow:hidden;background:#0c1a36;color:#fff;padding:22px 0 210px;isolation:isolate}
.sky{position:absolute;inset:0;z-index:-3;opacity:0;transition:opacity 1.6s ease}
.hero[data-sky=morning] .s-morning,.hero[data-sky=day] .s-day,.hero[data-sky=evening] .s-evening,.hero[data-sky=night] .s-night{opacity:1}
.s-night{background:linear-gradient(180deg,#040916 0%,#0a1630 45%,#172a4e 100%)}
.s-night::after{content:"";position:absolute;right:16%;top:30%;width:44px;height:44px;border-radius:50%;background:radial-gradient(circle at 38% 36%,#fffdf4 0%,#ece6cf 62%,#d8d1b8 100%);box-shadow:0 0 50px 14px rgba(244,241,228,.14);opacity:.9}
.s-morning{background:radial-gradient(90% 60% at 20% 105%,rgba(255,236,190,.95) 0%,rgba(255,205,160,.6) 30%,rgba(255,205,160,0) 62%),linear-gradient(180deg,#2d4f86 0%,#6b7fb0 34%,#b8a3c4 60%,#f2c3ad 82%,#fde7c6 100%)}
.s-day{background:radial-gradient(60% 55% at 82% 0%,rgba(255,255,255,.55) 0%,rgba(255,255,255,0) 60%),linear-gradient(180deg,#1a5aa6 0%,#3480c8 42%,#86bde8 82%,#c9e3f6 100%)}
.s-evening{background:radial-gradient(110% 70% at 84% 110%,rgba(255,170,90,.95) 0%,rgba(240,110,70,.55) 32%,rgba(240,110,70,0) 64%),linear-gradient(180deg,#121838 0%,#352a5a 34%,#83405f 60%,#d8673f 84%,#f3ad66 100%)}
#stars{position:absolute;inset:0;z-index:-2;width:100%;height:100%;opacity:0;transition:opacity 1.6s ease}
.hero[data-sky=night] #stars{opacity:1}
.hero[data-sky=morning] #stars{opacity:.25}
/* 山(北アルプスの稜線を重ねた風景画)と雲海。色は時刻で変わる */
.hero{--far:#8fb4d6;--mid:#4f7aa6;--near:#23405e;--rim:rgba(255,255,255,.85);--sea:#ffffff;--sea-op:.75}
.hero[data-sky=morning]{--far:#9a93b8;--mid:#565a86;--near:#1f2442;--rim:rgba(255,196,168,.95);--sea:#ffe6da;--sea-op:.7}
.hero[data-sky=evening]{--far:#a3788f;--mid:#5b3f62;--near:#21172e;--rim:rgba(255,150,92,.95);--sea:#ffcfb0;--sea-op:.5}
.hero[data-sky=night]{--far:#1f2d4c;--mid:#131d35;--near:#070c18;--rim:rgba(205,215,245,.4);--sea:#a8b6d6;--sea-op:.16}
.mtn{position:absolute;left:0;right:0;bottom:0;height:62%;z-index:-1;pointer-events:none}
.mtn svg{position:absolute;left:0;bottom:0;width:100%;height:100%;will-change:transform}
.mtn path{transition:fill 1.6s ease,stroke 1.6s ease}
.mtn .far path{fill:var(--far)}
.mtn .mid path.body{fill:var(--mid)}
.mtn .mid path.rim{fill:none;stroke:var(--rim);stroke-width:1.6;stroke-linejoin:round}
.mtn .near path{fill:var(--near)}
.sea{position:absolute;left:0;width:200%;pointer-events:none;will-change:transform;opacity:var(--sea-op);transition:opacity 1.6s ease;
  background-repeat:repeat-x;filter:blur(10px);animation:sea linear infinite}
.sea.s1{bottom:21%;height:22%;background-size:50% 100%;animation-duration:150s;
  background-image:radial-gradient(28% 40% at 12% 60%,var(--sea),transparent 70%),radial-gradient(22% 34% at 40% 45%,var(--sea),transparent 70%),radial-gradient(30% 42% at 72% 62%,var(--sea),transparent 70%),radial-gradient(18% 30% at 92% 50%,var(--sea),transparent 70%)}
.sea.s2{bottom:7%;height:20%;background-size:50% 100%;animation-duration:230s;animation-direction:reverse;
  background-image:radial-gradient(32% 44% at 22% 55%,var(--sea),transparent 70%),radial-gradient(26% 38% at 58% 62%,var(--sea),transparent 70%),radial-gradient(24% 36% at 86% 48%,var(--sea),transparent 70%)}
@keyframes sea{from{transform:translate3d(0,0,0)}to{transform:translate3d(-50%,0,0)}}
.hero::after{content:"";position:absolute;left:0;right:0;bottom:0;height:90px;z-index:-1;background:linear-gradient(180deg,rgba(0,0,0,0),var(--bg))}
.top{display:flex;justify-content:space-between;align-items:flex-start;gap:12px;position:relative}
.brand{display:flex;align-items:center;gap:8px;font-weight:bold;font-size:18px;letter-spacing:.08em}
.brand svg{width:28px;height:28px}
.nm{font-size:22px;letter-spacing:.18em;font-weight:bold}
.nm small{font-size:10px;letter-spacing:.32em;font-weight:normal;opacity:.75;margin-left:10px;vertical-align:middle}
.clock{text-align:right;line-height:1.15;text-shadow:0 1px 10px rgba(0,0,0,.25)}
.clock .ct{font-size:44px;letter-spacing:.06em;font-variant-numeric:tabular-nums;font-weight:300}
.clock .cd{font-size:13px;letter-spacing:.12em;opacity:.85;margin-top:4px}
.hero-body{position:relative;margin-top:40px;max-width:660px}
.hero h1{font-size:clamp(28px,6vw,46px);line-height:1.3;margin:0 0 14px;letter-spacing:.02em;text-shadow:0 2px 16px rgba(0,0,0,.28)}
.hero .lead{font-size:clamp(15px,2.6vw,18px);margin:0 0 24px;text-shadow:0 1px 10px rgba(0,0,0,.3);opacity:.95}
.badge{display:inline-block;background:rgba(255,255,255,.14);color:#fff;border:1px solid rgba(255,255,255,.35);backdrop-filter:blur(6px);border-radius:999px;padding:4px 14px;font-size:14px;margin-bottom:18px}
.badge b{color:#fff}
.cta{display:inline-block;background:var(--accent2);color:#fff;font-weight:bold;font-size:17px;padding:14px 28px;border-radius:999px;text-decoration:none;box-shadow:0 6px 18px rgba(255,140,0,.35)}
.hero .cta{background:#fff;color:#0f2a4a;box-shadow:0 8px 24px rgba(0,0,0,.22)}
.cta:hover{filter:brightness(1.05)}
.skytest{position:absolute;right:16px;bottom:120px;display:none;gap:6px;z-index:2}
.skytest.on{display:flex}
.skytest button{font:inherit;font-size:12px;padding:5px 11px;border-radius:999px;border:1px solid rgba(255,255,255,.5);background:rgba(0,0,0,.25);color:#fff;cursor:pointer}
.skytest button.sel{background:#fff;color:#0f2a4a}

/* セクション */
section{padding:56px 0 8px}
h2{font-size:clamp(21px,4vw,28px);text-align:center;margin:0 0 6px}
.sub{text-align:center;color:var(--muted);margin:0 0 26px}
.card{background:var(--card);border-radius:18px;box-shadow:var(--shadow);border:1px solid var(--line)}

/* 今日の図 */
#today{margin-top:-56px;position:relative;z-index:3;padding-top:0}
#today .card{padding:18px}
#today h2{text-align:left;font-size:20px;margin:0 0 4px}
#today .stamp{margin:0 0 12px;color:var(--muted);font-size:14px}
#today .stamp b{color:var(--now)}
.main-img{display:block;width:100%;height:auto;border-radius:10px;background:#fff;border:1px solid var(--line)}
.btns{display:flex;gap:10px;flex-wrap:wrap;margin:14px 0 8px}
.btns a,.btns button{flex:1 1 160px;padding:13px;border:0;border-radius:12px;font-size:16px;font-weight:bold;font-family:inherit;text-align:center;text-decoration:none;cursor:pointer;color:#fff;background:var(--accent)}
.btns .png{background:var(--save)}
.hint{font-size:13px;color:var(--muted);margin:0 0 14px}
#today h3{font-size:16px;margin:14px 0 8px}
.grid{display:grid;grid-template-columns:repeat(auto-fill,minmax(180px,1fr));gap:8px}
.c{display:block;padding:10px 12px;border-radius:12px;background:var(--bg);color:var(--fg);text-decoration:none;border:2px solid var(--line)}
.c.now{border-color:var(--now)}
.c b{display:block}
.c span{font-size:13px;color:var(--muted)}

/* 悩みと解決 */
.pair{display:grid;grid-template-columns:1fr 1fr;gap:18px}
.pair .card{padding:22px}
.pair h3{margin:0 0 12px;font-size:18px}
.pair ul{list-style:none;margin:0;padding:0}
.pair li{position:relative;padding:8px 0 8px 34px;border-top:1px dashed var(--line)}
.pair li:first-child{border-top:0}
.pair li::before{position:absolute;left:0;top:8px;width:24px;height:24px;border-radius:50%;text-align:center;line-height:24px;font-size:13px;font-weight:bold;color:#fff}
.before li::before{content:"！";background:#9aa9b9}
.after{border-color:var(--accent)!important}
.after h3{color:var(--accent)}
.after li::before{content:"✓";background:var(--accent)}

/* こんな方に */
.who{display:grid;grid-template-columns:repeat(3,1fr);gap:18px}
.who .card{padding:22px;text-align:center}
.who svg{width:56px;height:56px;margin-bottom:8px}
.who h3{margin:0 0 6px;font-size:17px}
.who p{margin:0;color:var(--muted);font-size:15px;text-align:left}

/* 使い方 */
.road-h{text-align:center;margin:34px 0 14px;font-size:18px}
.road{list-style:none;margin:0;padding:0;display:grid;grid-template-columns:repeat(4,1fr);gap:0;counter-reset:r}
.road li{position:relative;padding:44px 10px 0;text-align:center}
.road li::before{counter-increment:r;content:counter(r);position:absolute;top:0;left:50%;transform:translateX(-50%);width:32px;height:32px;border-radius:50%;background:var(--muted);color:#fff;font-weight:bold;line-height:32px;z-index:1}
.road li::after{content:"";position:absolute;top:15px;left:50%;width:100%;height:3px;background:var(--line)}
.road li:last-child::after{display:none}
.road li.done::before{background:var(--now)}
.road li.now::before{background:var(--accent)}
.road b{display:block;font-size:16px}
.road span{display:block;color:var(--muted);font-size:14px}
.steps{display:grid;grid-template-columns:repeat(3,1fr);gap:18px;counter-reset:s}
.steps .card{padding:22px;position:relative}
.steps .card::before{counter-increment:s;content:counter(s);position:absolute;top:-14px;left:18px;width:32px;height:32px;border-radius:50%;background:var(--accent2);color:#fff;font-weight:bold;text-align:center;line-height:32px}
.steps h3{margin:6px 0 6px;font-size:17px}
.steps p{margin:0;color:var(--muted);font-size:15px}
.again{text-align:center;margin:34px 0 0}

footer{margin-top:56px;background:linear-gradient(180deg,var(--bg),var(--sky3));padding:28px 0 36px;font-size:12px;color:var(--muted)}
footer .brand{color:var(--fg);font-size:15px;margin-bottom:6px}

/* メニュー(無料→LINE→有料→ツール) */
.plans{display:grid;grid-template-columns:1fr 2fr 1fr;gap:16px;align-items:stretch}
.stack{display:flex;flex-direction:column;gap:16px}
.stack .plan{flex:1}
.plan{padding:22px 18px;display:flex;flex-direction:column}
.plan .tag{align-self:flex-start;font-size:12px;font-weight:bold;border-radius:999px;padding:2px 12px;margin-bottom:10px;color:#fff;background:var(--muted)}
.plan h3{margin:0 0 8px;font-size:17px}
.plan p{margin:0 0 14px;color:var(--muted);font-size:14px;flex:1}
.plan.free .tag{background:var(--accent)}
.plan.line{border:2px solid var(--save)!important;flex-direction:row;gap:18px;align-items:center}
.plan.line .txt{flex:1;display:flex;flex-direction:column;align-self:stretch}
.plan.line .tag{background:var(--save)}
.plan.line ul{margin:0 0 14px;padding:0;list-style:none;font-size:14px;color:var(--muted);flex:1}
.plan.line li{padding:3px 0 3px 22px;position:relative}
.plan.line li::before{content:"✓";position:absolute;left:0;color:var(--save);font-weight:bold}
.plan.paid .tag{background:var(--accent2)}
.stack p{flex:0;margin-bottom:10px}
.plan.free p{flex:0}
.thumb{flex:1;display:flex;align-items:center;margin:0 0 14px}
.thumb img{display:block;width:100%;height:auto;border-radius:10px;border:1px solid var(--line);box-shadow:0 4px 14px rgba(23,80,140,.12);background:#fff}
.plan .go{display:block;text-align:center;padding:11px;border-radius:12px;font-weight:bold;text-decoration:none;color:#fff;background:var(--accent)}
.plan.line .go{background:var(--save)}
.plan .soon{display:block;text-align:center;padding:8px;border-radius:12px;font-size:13px;font-weight:bold;color:var(--muted);background:var(--bg);border:1px dashed var(--line)}
.line-btn{display:inline-block;background:var(--save);color:#fff;font-weight:bold;font-size:17px;padding:14px 28px;border-radius:999px;text-decoration:none;box-shadow:0 6px 18px rgba(6,199,85,.3)}
.again{display:flex;gap:12px;justify-content:center;flex-wrap:wrap}

/* LINEで届くイメージ(スマホのトーク画面) */
.phone{flex:0 0 210px;width:210px;height:380px;border-radius:30px;background:#1d2633;padding:9px;box-shadow:0 10px 28px rgba(10,40,80,.25);position:relative}
.phone .scr{height:100%;border-radius:22px;overflow:hidden;background:#8cabd8;display:flex;flex-direction:column;font-size:10.5px;line-height:1.5;color:#1a1a1a}
.ph-head{background:#2b3a55;color:#fff;font-weight:bold;padding:12px 12px 8px;font-size:11.5px}
.ph-body{flex:1;padding:8px;display:flex;flex-direction:column;gap:7px;overflow:hidden}
.msg{display:flex;gap:5px;align-items:flex-start}
.av{flex:0 0 22px;height:22px;border-radius:50%;background:#fff;display:grid;place-items:center;font-size:12px}
.av.blank{visibility:hidden}
.bub{background:#fff;border-radius:12px;padding:6px 9px;max-width:150px}
.pics{display:flex;gap:4px}
.pics img{display:block;height:118px;border-radius:9px;background:#fff;object-fit:cover;object-position:top}
.pics img.tall{width:38px}
.pics img.wide{width:100px}
.bub.link{color:#0b63c4;font-weight:bold}
.ph-menu{display:grid;grid-template-columns:repeat(3,1fr);background:#fff;border-top:1px solid #ddd}
.ph-menu span{text-align:center;padding:9px 0 12px;font-size:10px;font-weight:bold;color:#2b3a55;border-left:1px solid #eee}
.ph-menu span:first-child{border-left:0}
@media (prefers-color-scheme:dark){.phone{background:#000}}
@media (max-width:960px){.plans{grid-template-columns:1fr 1fr}.plan.line{grid-column:1 / -1}.stack{grid-column:1 / -1;flex-direction:row}}
@media (max-width:560px){.plans{grid-template-columns:1fr}.plan.line{flex-direction:column}.phone{flex-basis:auto;margin:4px auto 0}.stack{flex-direction:column}}

@media (max-width:760px){
  .pair,.who,.steps{grid-template-columns:1fr}
  .road{grid-template-columns:1fr 1fr;row-gap:22px}
  .road li:nth-child(2)::after{display:none}
  .steps{gap:26px}
  .clock .ct{font-size:30px}
  .clock .cd{font-size:11px;letter-spacing:.04em}
  .brand{font-size:16px}
  .hero{padding-bottom:76px}
  .hero-body{margin-top:30px}
}
@media (prefers-reduced-motion:reduce){
  html{scroll-behavior:auto}
  .sea{animation:none}
}
</style>
</head>
<body>

<header class="hero" data-sky="day">
  <div class="sky s-morning"></div><div class="sky s-day"></div><div class="sky s-evening"></div><div class="sky s-night"></div>
  <canvas id="stars" aria-hidden="true"></canvas>
  <div class="mtn" aria-hidden="true">
    <svg class="far" viewBox="0 0 1600 400" preserveAspectRatio="xMidYMax slice"><path d="M0 250L70 228L140 240L215 205L290 222L360 190L430 212L520 172L600 196L680 162L745 182L820 150L890 176L965 142L1045 168L1125 146L1205 180L1285 158L1365 186L1445 166L1525 196L1600 178V400H0Z"/></svg>
    <div class="sea s1"></div>
    <svg class="mid" viewBox="0 0 1600 400" preserveAspectRatio="xMidYMax slice"><path class="body" d="M0 300L90 282L170 290L260 262L330 274L410 236L470 196L500 172L530 194L590 240L660 252L740 230L800 244L880 214L940 226L1000 196L1050 178L1075 146L1090 104L1098 78L1106 104L1120 146L1150 166L1190 156L1222 138L1246 146L1268 124L1290 140L1312 116L1334 132L1360 122L1392 150L1440 180L1500 200L1560 220L1600 230V400H0Z"/><path class="rim" d="M410 236L470 196L500 172L530 194L590 240M1000 196L1050 178L1075 146L1090 104L1098 78L1106 104L1120 146L1150 166L1190 156L1222 138L1246 146L1268 124L1290 140L1312 116L1334 132L1360 122L1392 150L1440 180"/></svg>
    <div class="sea s2"></div>
    <svg class="near" viewBox="0 0 1600 400" preserveAspectRatio="xMidYMax slice"><path d="M0 340C150 318 260 330 400 312S640 290 800 318S1080 340 1240 312S1480 296 1600 318V400H0Z"/></svg>
  </div>
  <div class="wrap">
    <div class="top">
      <div class="brand">
        <svg viewBox="0 0 32 32" aria-hidden="true"><rect x="2" y="7" width="8" height="18" rx="2" fill="#fff" opacity=".6"/><rect x="12" y="7" width="8" height="18" rx="2" fill="#fff"/><rect x="22" y="7" width="8" height="18" rx="2" fill="#fff" opacity=".6"/></svg>
        <span class="nm">そら読み<small>SORAYOMI</small></span>
      </div>
      <div class="clock"><div class="ct" id="ck-t">--:--</div><div class="cd" id="ck-d">日本時間</div></div>
    </div>
    <div class="hero-body">
      <span class="badge">最新の実況：<b>__STAMP__</b></span>
      <h1>天気図は、<br>並べると読める。</h1>
      <p class="lead">1枚だけでは見えない低気圧や前線の動きも、時間の順に並べれば流れとして読めてきます。地上天気図の 48時間前・24時間前・最新・24時間予想・48時間予想 を、左から右へ時間の流れどおり1枚に並べて、1日2回お届けします。高層天気図・数値予報図の並べ図も順次公開していきます。</p>
      <a class="cta" href="#today">今日の天気図を見る</a>
    </div>
  </div>
  <div class="skytest" id="skytest"><button data-k="auto">自動</button><button data-k="morning">朝</button><button data-k="day">昼</button><button data-k="evening">夕方</button><button data-k="night">夜</button></div>
</header>
<script>
(function(){
  var hero=document.querySelector(".hero"), override=null;
  var NAMES={morning:"朝",day:"昼",evening:"夕方",night:"夜"};
  var fmt=new Intl.DateTimeFormat("ja-JP",{timeZone:"Asia/Tokyo",month:"numeric",day:"numeric",weekday:"short",hour:"2-digit",minute:"2-digit",hour12:false});
  function period(h){return h>=5&&h<8?"morning":h>=8&&h<16?"day":h>=16&&h<19?"evening":"night";}
  function tick(){
    var p={};fmt.formatToParts(new Date()).forEach(function(x){p[x.type]=x.value;});
    var h=parseInt(p.hour,10)%24, k=override||period(h);
    document.getElementById("ck-t").textContent=("0"+h).slice(-2)+":"+p.minute;
    document.getElementById("ck-d").textContent=p.month+"月"+p.day+"日("+p.weekday+")・"+NAMES[k]+"　日本時間";
    hero.setAttribute("data-sky",k);
  }
  tick();setInterval(tick,10000);
  // 試し用: URL に ?skytest を付けると 朝・昼・夕方・夜 を切り替えるボタンが出る
  if(location.search.indexOf("skytest")>=0){
    var box=document.getElementById("skytest");box.className+=" on";
    var m=location.search.match(/skytest=(morning|day|evening|night)/);if(m)override=m[1];
    box.addEventListener("click",function(e){var k=e.target.getAttribute("data-k");if(!k)return;
      override=k==="auto"?null:k;[].forEach.call(box.children,function(b){b.classList.toggle("sel",b===e.target);});tick();});
    tick();
  }
  // 星空(夜)。動きを減らす設定のときは瞬かない
  var cv=document.getElementById("stars"),cx=cv.getContext("2d"),stars=[],still=matchMedia("(prefers-reduced-motion: reduce)").matches,shoot=null;
  function size(){var r=window.devicePixelRatio||1;cv.width=hero.clientWidth*r;cv.height=hero.clientHeight*r;cx.setTransform(r,0,0,r,0,0);
    stars=[];var n=Math.round(hero.clientWidth*hero.clientHeight/2600);
    for(var i=0;i<n;i++)stars.push({x:Math.random()*hero.clientWidth,y:Math.random()*hero.clientHeight*.85,r:Math.random()*1.1+.25,a:Math.random()*.6+.3,s:Math.random()*.002+.0006,o:Math.random()*6.3});}
  function draw(t){
    cx.clearRect(0,0,cv.width,cv.height);
    for(var i=0;i<stars.length;i++){var s=stars[i],a=still?s.a:s.a*(.55+.45*Math.sin(t*s.s+s.o));
      cx.globalAlpha=a;cx.fillStyle="#fff";cx.beginPath();cx.arc(s.x,s.y,s.r,0,6.283);cx.fill();}
    if(!still&&hero.getAttribute("data-sky")==="night"){
      if(!shoot&&Math.random()<.003)shoot={x:Math.random()*hero.clientWidth*.7+hero.clientWidth*.2,y:Math.random()*hero.clientHeight*.3,l:0};
      if(shoot){shoot.l+=9;var g=cx.createLinearGradient(shoot.x,shoot.y,shoot.x-shoot.l,shoot.y+shoot.l*.45);
        g.addColorStop(0,"rgba(255,255,255,.9)");g.addColorStop(1,"rgba(255,255,255,0)");cx.globalAlpha=1;cx.strokeStyle=g;cx.lineWidth=1.4;
        cx.beginPath();cx.moveTo(shoot.x,shoot.y);cx.lineTo(shoot.x-shoot.l,shoot.y+shoot.l*.45);cx.stroke();shoot.x+=4;shoot.y-=1.8;if(shoot.l>160)shoot=null;}
    }
    cx.globalAlpha=1;if(!still)requestAnimationFrame(draw);
  }
  size();addEventListener("resize",size);requestAnimationFrame(draw);
  if(!still){var lay=[[".mtn .far",.08],[".mtn .mid",.16],[".mtn .near",.26]].map(function(x){return [document.querySelector(x[0]),x[1]];}),busy=false;
    addEventListener("scroll",function(){if(busy)return;busy=true;requestAnimationFrame(function(){var y=Math.min(scrollY,hero.clientHeight);
      lay.forEach(function(l){l[0].style.transform="translate3d(0,"+(-y*l[1])+"px,0)";});busy=false;});},{passive:true});}
})();
</script>

<main>
<section id="today">
  <div class="wrap"><div class="card">
    <h2>今日の並べ図</h2>
    <p class="stamp">最新の実況：<b>__STAMP__</b>　9時・21時（数値予報の初期値と同じ時刻）の図で、予想図がそろいしだい自動で新しくなります</p>
    <a href="latest.jpg?v=__V__" target="_blank"><img class="main-img" src="latest.jpg?v=__V__" alt="地上天気図5枚まとめ（ASAS 48時間前・24時間前・最新、FSAS24・FSAS48）"></a>
    <div class="btns">
      <a class="png" href="latest.png?v=__V__" download="sorayomi___V__.png">PNGで保存</a>
      <a class="pdf" href="latest.pdf?v=__V__" download="sorayomi___V__.pdf">PDFで保存</a>
    </div>
    <p class="hint">LINEの中で保存できないときは、画像を長押しして保存するか、右上のメニューから「ブラウザで開く」を選んでください。</p>
    <h3>1枚ずつ大きく見る</h3>
    <div class="grid">__LINKS__</div>
  </div></div>
</section>

<section class="pr" id="kodawari">
  <div class="wrap">
    <h2>並べ方へのこだわり</h2>
    <p class="sub">同じ図でも、並べ方ひとつで読みやすさが変わります。</p>
    <div class="who">
      <div class="card">
        <svg viewBox="0 0 56 56" aria-hidden="true"><circle cx="28" cy="28" r="26" fill="var(--sky3)"/><rect x="10" y="20" width="9" height="16" rx="2" fill="var(--accent)" opacity=".55"/><rect x="23.5" y="18" width="9" height="20" rx="2" fill="var(--now)"/><rect x="37" y="20" width="9" height="16" rx="2" fill="var(--accent)" opacity=".55"/><path d="M12 44h30l-4-3m4 3-4 3" stroke="var(--accent)" stroke-width="2.4" fill="none" stroke-linecap="round" stroke-linejoin="round"/></svg>
        <h3>時間の流れどおりに</h3>
        <p>左に過去、真ん中に最新、右に予想。矢印に沿って目を動かすだけで、低気圧や前線がどこから来て、どこへ向かうのかが追えます。</p>
      </div>
      <div class="card">
        <svg viewBox="0 0 56 56" aria-hidden="true"><circle cx="28" cy="28" r="26" fill="var(--sky3)"/><circle cx="28" cy="28" r="13" fill="#fff" stroke="var(--accent)" stroke-width="3"/><path d="M28 20v8l6 4" stroke="var(--accent2)" stroke-width="3" fill="none" stroke-linecap="round"/></svg>
        <h3>起点をそろえる</h3>
        <p>真ん中の最新の実況は、数値予報の初期値と同じ9時・21時の図。実況と予想を、同じ時刻を起点にそのまま読み比べられます。</p>
      </div>
      <div class="card">
        <svg viewBox="0 0 56 56" aria-hidden="true"><circle cx="28" cy="28" r="26" fill="var(--sky3)"/><rect x="16" y="14" width="24" height="28" rx="3" fill="#fff" stroke="var(--accent)" stroke-width="2.4"/><path d="M20 22c4-3 8 3 12 0s6-2 6-2M20 29c4-3 8 3 12 0s6-2 6-2M20 36c4-3 8 3 12 0" stroke="#444" stroke-width="1.6" fill="none"/></svg>
        <h3>気象庁の図をそのまま</h3>
        <p>色付けや書き込みはせず、気象庁の白黒の図をそのまま並べています。元の情報を崩さずに、自分の目で解析できます。</p>
      </div>
    </div>
    <h3 class="road-h">これから並べていく図</h3>
    <ol class="road">
      <li class="done"><b>地上天気図</b><span>このページで公開中</span></li>
      <li class="now"><b>高層天気図の実況</b><span>200hPa → 地上。LINEで配信中</span></li>
      <li class="now"><b>数値予報天気図</b><span>12〜48時間予想。LINEで配信中</span></li>
      <li><b>解析の補助つき</b><span>準備中</span></li>
    </ol>
  </div>
</section>

<section class="pr">
  <div class="wrap">
    <h2>集めて、並べる。その準備に時間を取られていませんか？</h2>
    <p class="sub">本当に時間をかけたいのは、天気図を読み解くこと。準備はそら読みにまかせてください。</p>
    <div class="pair">
      <div class="card before">
        <h3>これまで</h3>
        <ul>
          <li>気象庁のホームページから、実況図と予想図を1枚ずつ開いて取り寄せている</li>
          <li>48時間前・24時間前の図までさかのぼって探し、集めるだけでひと手間</li>
          <li>集めた図を時刻の順に並べ替えて、ようやく解析を始められる</li>
        </ul>
      </div>
      <div class="card after">
        <h3>そら読みなら</h3>
        <ul>
          <li>取り寄せ・並べ替えはおまかせ。ページを開いた瞬間から解析に入れる</li>
          <li>過去 → 最新 → 予想 が左から右へ、矢印つきで1枚に並んでいる</li>
          <li>最新の実況は数値予報の初期値（9時・21時）にそろえてあるので、予想図とそのまま読み比べられる</li>
        </ul>
      </div>
    </div>
  </div>
</section>

<section class="pr">
  <div class="wrap">
    <h2>こんな方に</h2>
    <p class="sub">準備の時間を、天気図を読む時間に。</p>
    <div class="who">
      <div class="card">
        <svg viewBox="0 0 56 56" aria-hidden="true"><circle cx="28" cy="28" r="26" fill="var(--sky3)"/><circle cx="22" cy="24" r="9" fill="var(--accent2)"/><path d="M20 40h18a7 7 0 0 0 0-14 10 10 0 0 0-18 3 6 6 0 0 0 0 11z" fill="var(--accent)"/></svg>
        <h3>天気が好きな方</h3>
        <p>図を集める手間なしで、低気圧や前線がどう動いてきたか、どこへ向かうのかを追うことに集中できます。</p>
      </div>
      <div class="card">
        <svg viewBox="0 0 56 56" aria-hidden="true"><circle cx="28" cy="28" r="26" fill="var(--sky3)"/><path d="M14 18h12a4 4 0 0 1 4 4v18a3 3 0 0 0-3-3H14z" fill="var(--accent)"/><path d="M42 18H30a4 4 0 0 0-4 4v18a3 3 0 0 1 3-3h13z" fill="var(--accent)" opacity=".7"/></svg>
        <h3>予報士試験を受ける方</h3>
        <p>実況図と予想図を読み解く練習を、毎日の習慣に。図を集める時間を、解析の勉強の時間に変えられます。</p>
      </div>
      <div class="card">
        <svg viewBox="0 0 56 56" aria-hidden="true"><circle cx="28" cy="28" r="26" fill="var(--sky3)"/><rect x="15" y="17" width="26" height="22" rx="3" fill="var(--accent)"/><path d="M19 33l6-6 4 4 8-8" stroke="#fff" stroke-width="3" fill="none" stroke-linecap="round" stroke-linejoin="round"/></svg>
        <h3>予報士・気象のお仕事の方</h3>
        <p>天気図を集めて並べる下準備を省いて、解析と判断に力を注げます。</p>
      </div>
    </div>
  </div>
</section>

<section class="pr" id="menu">
  <div class="wrap">
    <h2>そら読みのメニュー</h2>
    <p class="sub">まずは地上天気図から。もっと読み込みたい方には、高層・数値予報の並べ図を自動でお届けします。</p>
    <div class="plans">
      <div class="card plan free">
        <span class="tag">無料・このページ</span>
        <h3>地上天気図の並べ図</h3>
        <p>ASAS 48時間前・24時間前・最新、FSAS 24・48時間予想の5枚。ページを開くだけで見られます。</p>
        <a class="thumb" href="#today"><img src="latest.jpg?v=__V__" alt="地上天気図の並べ図のイメージ" loading="lazy"></a>
        <a class="go" href="#today">今日の図を見る</a>
      </div>
      <div class="card plan line">
        <div class="txt">
          <span class="tag">LINE登録で無料</span>
          <h3>高層・数値予報の並べ図が、LINEに自動で届く</h3>
          <ul>
            <li>高層天気図の実況の並べ図（200hPa → 地上）</li>
            <li>数値予報天気図の並べ図（12〜48時間予想）</li>
            <li>1日2回、図がそろうと自動で届く</li>
            <li>PDFでまとめて保存。メニューからいつでも開ける</li>
          </ul>
          <a class="go" href="__LINE_URL__" target="_blank" rel="noopener">LINEで友だち追加</a>
        </div>
        <div class="phone" aria-label="LINEに届くイメージ" role="img">
          <div class="scr">
            <div class="ph-head">‹　天気図配信</div>
            <div class="ph-body">
              <div class="msg"><span class="av">☀</span><div class="bub">最新の天気図がそろいました。高層の実況と数値予報の並べ図です。</div></div>
              <div class="msg"><span class="av blank"></span><div class="pics"><img class="tall" src="line/p2.jpg" alt="" onerror="this.style.visibility='hidden'"><img class="wide" src="line/p3.jpg" alt="" onerror="this.style.visibility='hidden'"></div></div>
              <div class="msg"><span class="av blank"></span><div class="bub link">PDFでまとめて保存 ›</div></div>
            </div>
            <div class="ph-menu"><span>地上</span><span>実況</span><span>数値予報</span></div>
          </div>
        </div>
      </div>
      <div class="stack">
        <div class="card plan paid">
          <span class="tag">有料・準備中</span>
          <h3>解析の補助つき</h3>
          <p>特定の等高度線をなぞる、相当温位(K)に色を付けるなど、解析の手がかりを書き込んだ並べ図。</p>
          <span class="soon">LINEで先行してご案内します</span>
        </div>
        <div class="card plan">
          <span class="tag">今後</span>
          <h3>自分で描けるツール</h3>
          <p>線の引き方や色分けを、自分の思うように設定して描けるツール。</p>
          <span class="soon">準備中</span>
        </div>
      </div>
    </div>
  </div>
</section>

<section class="pr">
  <div class="wrap">
    <h2>使い方は 3ステップ</h2>
    <p class="sub">登録もアプリも要りません。</p>
    <div class="steps">
      <div class="card"><h3>ページを開く</h3><p>このページをブックマークしておけば、いつでも最新のまとめが開きます。</p></div>
      <div class="card"><h3>見比べる</h3><p>左の列が48時間前・24時間前、真ん中が最新（赤枠）、右の列が24時間予想・48時間予想。矢印に沿って見るだけです。</p></div>
      <div class="card"><h3>保存する</h3><p>「PNGで保存」か「PDFで保存」を押すだけ。タブレットに入れて、解析の書き込みにも。</p></div>
    </div>
    <p class="again"><a class="cta" href="#today">今日の天気図を見る</a><a class="line-btn" href="__LINE_URL__" target="_blank" rel="noopener">高層・数値予報はLINEで自動で届く</a></p>
  </div>
</section>
</main>

<footer>
  <div class="wrap">
    <div class="brand"><span class="nm">そら読み<small>SORAYOMI</small></span></div>
    出典：気象庁ホームページ（地上天気図）を加工して作成。編集・加工の責任はそら読みにあります。天気図は気象庁の発表内容をそのまま並べたもので、独自の予報ではありません。
  </div>
</footer>
</body>
</html>
"""

if __name__ == "__main__":
    check() if "--check" in sys.argv else build()
