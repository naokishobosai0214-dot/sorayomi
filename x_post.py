"""X 投稿用の画像(地上天気図5枚まとめ + LINE への誘導)を1枚作る。
左の列に ASAS 48時間前・24時間前、真ん中に最新、右の列に FSAS24・48 を並べ、矢印で流れを示す。最新の下に LINE 案内。
使い方: python -X utf8 x_post.py
出力: C:\\Users\\endo-\\Documents\\kishobosai\\tenkizu\\x_post_YYYYMMDDHH.jpg (最新ASASの時刻・UTC)
"""
import os
import re
from datetime import datetime, timedelta

from PIL import Image, ImageDraw, ImageFont

import asas_view

# ---- ここを書き換える(決まるまでは仮) ----
BRAND = "空読み"                 # サービス名(そらよみ)
LINE_ID = "@421edvfx"            # LINE 公式アカウント「天気図配信」のID
EDITOR = "空読み"                # 加工・編集の責任者として出典に書く名前
# ----------------------------------------

OUT_DIR = r"C:\Users\endo-\Documents\kishobosai\tenkizu"
W, H = 2400, 1350                # 16:9。X のタイムラインで切れずに出る比率
PAD, GAP = 24, 18
HEAD, FOOT, CAP = 118, 64, 46    # 見出し帯・出典帯・各図のキャプションの高さ
NAVY, RED, GRAY = (16, 42, 84), (208, 0, 0), (235, 238, 242)
RATIO = 2151 / 1521              # 天気図(PDFを画像にしたもの)の横/縦
# フォントは BIZ UDゴシック。このフォルダの fonts\ (クラウド用) → Windows の順に探す
_here = os.path.dirname(os.path.abspath(__file__))
FONT_B, FONT_R = next(
    (b, r) for b, r in (
        (os.path.join(_here, "fonts", "BIZUDGothic-Bold.ttf"), os.path.join(_here, "fonts", "BIZUDGothic-Regular.ttf")),
        (r"C:\Windows\Fonts\BIZ-UDGothicB.ttc", r"C:\Windows\Fonts\BIZ-UDGothicR.ttc"),
    ) if os.path.exists(b)
)


def font(size, bold=True):
    return ImageFont.truetype(FONT_B if bold else FONT_R, size)


SIDE_W, ARROW_W, COL_HEAD = 610, 100, 56   # 左右の列の幅・矢印の幅・列見出しの高さ
BLUE, ORANGE = (15, 127, 208), (255, 159, 28)


def cell_boxes():
    """5枚の枠 [ASAS 48h前, 24h前, 最新, FSAS24, FSAS48] と、最新の上下の空き(案内用)。
    左の列に過去の実況2枚(縦)、真ん中に最新の実況(大きく)、右の列に予想2枚(縦)。"""
    top, bottom = HEAD + COL_HEAD, H - FOOT
    side_h = round(SIDE_W / RATIO) + CAP
    sy = top + (bottom - top - side_h * 2 - GAP) // 2
    mid_x = PAD + SIDE_W + ARROW_W
    mid_w = W - PAD * 2 - SIDE_W * 2 - ARROW_W * 2
    mid_h = round(mid_w / RATIO) + CAP
    my = sy + side_h + GAP // 2 - mid_h // 2
    right_x = W - PAD - SIDE_W
    boxes = [(PAD, sy, SIDE_W, side_h), (PAD, sy + side_h + GAP, SIDE_W, side_h), (mid_x, my, mid_w, mid_h),
             (right_x, sy, SIDE_W, side_h), (right_x, sy + side_h + GAP, SIDE_W, side_h)]
    above = (mid_x, top, mid_w, my - top - 12)
    below = (mid_x, my + mid_h + 12, mid_w, bottom - (my + mid_h + 12))
    return boxes, above, below


def arrow(img, box):
    """box(x, y, w, h)の中に右向きの太い矢印を1本。左は淡い空色で透け、右へ行くほど濃い青(未来へ向かう流れ)。"""
    x, y, w, h = box
    shaft, head = h * 0.36, w * 0.42
    cy = h / 2
    mask = Image.new("L", (w, h), 0)
    ImageDraw.Draw(mask).polygon([(0, cy - shaft / 2), (w - head, cy - shaft / 2), (w - head, 0), (w, cy),
                                  (w - head, h), (w - head, cy + shaft / 2), (0, cy + shaft / 2)], fill=255)
    grad = Image.new("RGBA", (w, h))
    gd = ImageDraw.Draw(grad)
    for i in range(w):
        t = i / (w - 1)
        c = tuple(round(a + (b - a) * t) for a, b in zip((150, 215, 250), BLUE))
        gd.line([(i, 0), (i, h)], fill=c + (round(90 + 165 * t),))
    alpha = Image.composite(grad.getchannel("A"), Image.new("L", (w, h), 0), mask)
    grad.putalpha(alpha)
    img.paste(grad, (x, y), grad)


def draw_arrows(img, boxes):
    """左の列 → 最新 → 右の列 の流れを、列のあいだの真ん中に1本ずつの矢印で示す。"""
    mx, my, mw, mh = boxes[2]
    cy = my + mh // 2
    ah = 120
    for x0, x1 in ((PAD + SIDE_W, mx), (mx + mw, W - PAD - SIDE_W)):
        arrow(img, (x0 + 8, cy - ah // 2, x1 - x0 - 16, ah))


def draw_col_heads(d, boxes):
    for (x, _, w, _), t in zip((boxes[0], boxes[2], boxes[3]), ("過去の実況", "最新の実況（数値予報の初期値）", "予想")):
        d.text((x + w // 2, HEAD + COL_HEAD // 2 - 6), t, font=font(30), fill=NAVY, anchor="mm")


def utc_of(png):
    return datetime.strptime(re.findall(r"_(\d{10})\.png$", png)[0], "%Y%m%d%H")


def draw_chart(img, d, box, title, when, png, now):
    x, y, w, h = box
    d.rectangle([x, y, x + w, y + CAP], fill=RED if now else GRAY)
    d.text((x + 12, y + CAP // 2), title, font=font(26), fill="white" if now else NAVY, anchor="lm")
    d.text((x + w - 12, y + CAP // 2), when, font=font(20, False), fill="white" if now else (40, 40, 40), anchor="rm")
    chart = Image.open(os.path.join(asas_view.OUT, png)).convert("RGB")
    ih = h - CAP
    iw = round(chart.width * ih / chart.height)
    if iw > w:
        iw, ih = w, round(chart.height * w / chart.width)
    img.paste(chart.resize((iw, ih), Image.LANCZOS), (x + (w - iw) // 2, y + CAP))
    d.rectangle([x, y, x + w, y + h], outline=RED if now else (150, 150, 150), width=6 if now else 2)


def draw_cta(d, box):
    """X 投稿用: 最新の下に LINE への案内。"""
    x, y, w, h = box
    d.rounded_rectangle([x, y, x + w, y + h], radius=18, fill=(6, 199, 85))
    d.text((x + w // 2, y + h // 2), f"最新の天気図はLINEで  {LINE_ID}", font=font(34), fill="white", anchor="mm")


def draw_info(d, box, url):
    """ページ用: 最新の下にページのURL。"""
    x, y, w, h = box
    d.rounded_rectangle([x, y, x + w, y + h], radius=18, fill=NAVY)
    d.text((x + w // 2, y + h // 2 - (18 if url else 0)), "1日2回、9時・21時の図で自動更新", font=font(30), fill="white", anchor="mm")
    if url:
        d.text((x + w // 2, y + h // 2 + 24), url, font=font(24, False), fill=(200, 215, 240), anchor="mm")


def make_image(charts, path, cta="x", url=""):
    """charts = asas_view.fetch_charts() の結果。cta="x" は X 投稿用(LINE 案内)、"page" は LINE で開くページ用。"""
    latest = next(utc_of(p) for a, _, p in charts if "最新" in a)
    j = latest + timedelta(hours=9)

    img = Image.new("RGB", (W, H), "white")
    d = ImageDraw.Draw(img)
    d.rectangle([0, 0, W, HEAD - 22], fill=NAVY)
    d.text((PAD, (HEAD - 22) // 2), "地上天気図 5枚まとめ", font=font(50), fill="white", anchor="lm")
    d.text((PAD + 540, (HEAD - 22) // 2), f"最新 {j.year}年{j.month}月{j.day}日 {j.hour}時 ({latest:%H}UTC)",
           font=font(34, False), fill=(220, 230, 245), anchor="lm")
    d.text((W - PAD, (HEAD - 22) // 2), "48h前 → 24h前 → 最新 → 24h予想 → 48h予想", font=font(28, False),
           fill=(220, 230, 245), anchor="rm")

    boxes, _, below = cell_boxes()
    draw_col_heads(d, boxes)
    for box, (title, when, png) in zip(boxes, charts):
        when = re.sub(r"\s*\(.*?\)", "", when).replace("初期値", "/ 初期値")
        if box[2] < 700:
            when = when.split(" / ")[0]  # 左右の小さい枠は時刻だけ(初期値は見出しの「最新」と同じ)
        draw_chart(img, d, box, title.replace("時間予想", "h予想"), when, png, "最新" in title)
    draw_arrows(img, boxes)
    bx, by, bw, bh = below
    band = (bx + 60, by + (bh - 90) // 2, bw - 120, 90)
    if cta == "x":
        draw_cta(d, band)
    else:
        draw_info(d, band, url)

    d.text((PAD, H - FOOT // 2), f"出典：気象庁ホームページ（地上天気図）を加工して作成。編集・加工の責任は{EDITOR}にあります。",
           font=font(22, False), fill=(60, 60, 60), anchor="lm")
    d.text((W - PAD, H - FOOT // 2), BRAND, font=font(26), fill=NAVY, anchor="rm")
    img.save(path, quality=90)
    return latest


SET_W = 1600                     # 4枚セットの1枚の幅。スマホで画像を開いたとき画面の幅いっぱいに出る


def set_page(charts, idx, head, page, stamp):
    """4枚セットの2〜4枚目。charts[idx] の図を縦に積む(スマホの縦画面で開いたとき1枚ずつ大きく見える)。"""
    bar, cap, foot = 110, 56, 56
    ch = round(SET_W / RATIO)
    img = Image.new("RGB", (SET_W, bar + (cap + ch) * len(idx) + foot), "white")
    d = ImageDraw.Draw(img)
    d.rectangle([0, 0, SET_W, bar], fill=NAVY)
    d.text((PAD, bar // 2), head, font=font(46), fill="white", anchor="lm")
    d.text((SET_W - PAD, bar // 2), f"{page}/4", font=font(34, False), fill=(200, 215, 240), anchor="rm")
    y = bar
    for i in idx:
        title, when, png = charts[i]
        now = "最新" in title
        when = re.sub(r"\s*\(.*?\)", "", when).replace("初期値", "/ 初期値")
        d.rectangle([0, y, SET_W, y + cap], fill=RED if now else GRAY)
        d.text((PAD, y + cap // 2), title.replace("時間予想", "h予想"), font=font(32), fill="white" if now else NAVY, anchor="lm")
        d.text((SET_W - PAD, y + cap // 2), when, font=font(28, False), fill="white" if now else (40, 40, 40), anchor="rm")
        chart = Image.open(os.path.join(asas_view.OUT, png)).convert("RGB")
        img.paste(chart.resize((SET_W, ch), Image.LANCZOS), (0, y + cap))
        y += cap + ch
    d.text((PAD, y + foot // 2), f"出典：気象庁ホームページ（地上天気図）を加工して作成（{EDITOR}）",
           font=font(24, False), fill=(60, 60, 60), anchor="lm")
    d.text((SET_W - PAD, y + foot // 2), stamp, font=font(24, False), fill=NAVY, anchor="rm")
    return img


def make_set(charts, folder):
    """X 投稿用の4枚セット。1=5枚まとめ(表紙) 2=過去の実況(48h前・24h前) 3=最新の実況 4=予想(24h・48h)。"""
    os.makedirs(folder, exist_ok=True)
    paths = [os.path.join(folder, "1_まとめ.jpg")]
    latest = make_image(charts, paths[0])
    j = latest + timedelta(hours=9)
    stamp = f"最新 {j.month}月{j.day}日{j.hour}時({latest:%H}UTC)"
    for page, (idx, head, name) in enumerate((((0, 1), "過去の実況　48時間前・24時間前", "2_過去"),
                                              ((2,), "最新の実況（数値予報の初期値）", "3_最新"),
                                              ((3, 4), "予想　24時間後・48時間後", "4_予想")), 2):
        p = os.path.join(folder, f"{name}.jpg")
        set_page(charts, idx, head, page, stamp).save(p, quality=90)
        paths.append(p)
    return paths


def main():
    charts = asas_view.fetch_charts()
    latest = next(utc_of(p) for a, _, p in charts if "最新" in a)
    os.makedirs(OUT_DIR, exist_ok=True)
    path = os.path.join(OUT_DIR, f"x_post_{latest:%Y%m%d%H}.jpg")
    make_image(charts, path)
    print(path, round(os.path.getsize(path) / 1024), "KB")
    folder = os.path.join(OUT_DIR, f"x_set_{latest:%Y%m%d%H}")
    for p in make_set(charts, folder):
        print(p, round(os.path.getsize(p) / 1024), "KB")
    return folder


if __name__ == "__main__":
    os.startfile(main())
