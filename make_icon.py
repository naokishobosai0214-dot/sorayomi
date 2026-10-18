"""X のプロフィール画像(400x400)。1600 で描いて縮小。案A=図だけ、案B=「そら読み」入り、案C=夜空。"""
import math, os, sys
from PIL import Image, ImageDraw, ImageFont, ImageFilter
OUT = sys.argv[1]
S = 1600
FB = r"C:\Windows\Fonts\BIZ-UDGothicB.ttc"

def sky(top, bottom):
    im = Image.new("RGB", (S, S))
    d = ImageDraw.Draw(im)
    for y in range(S):
        t = y / (S - 1)
        d.line([(0, y), (S, y)], fill=tuple(round(a + (b - a) * t) for a, b in zip(top, bottom)))
    return im

def ridge(im, color, base, amp, pts):
    d = ImageDraw.Draw(im)
    poly = [(0, S)] + [(x * S, base - h * amp) for x, h in pts] + [(S, S)]
    d.polygon(poly, fill=color)

def panel(im, box, red=False, phase=0.0):
    """白い図1枚。等圧線は枠の中だけに描く。phase で低気圧の位置をずらす(左→右へ動く)。"""
    x0, y0, x1, y1 = [round(v) for v in box]
    w, h = x1 - x0, y1 - y0
    card = Image.new("RGB", (w, h), (255, 255, 255))
    c = ImageDraw.Draw(card)
    cx, cy = w * (0.5 + phase), h * 0.52
    for r in (0.26, 0.46, 0.66):
        rw, rh = w * r, h * r * 0.75
        c.ellipse([cx - rw, cy - rh, cx + rw, cy + rh], outline=(40, 60, 90), width=max(6, w // 40))
    c.text((cx, cy), "L", font=ImageFont.truetype(FB, int(h * 0.30)), fill=(224, 48, 43), anchor="mm")
    m = Image.new("L", (w, h), 0)
    ImageDraw.Draw(m).rounded_rectangle([0, 0, w - 1, h - 1], radius=28, fill=255)
    im.paste(card, (x0, y0), m)
    ImageDraw.Draw(im).rounded_rectangle([x0, y0, x1, y1], radius=28, outline=(224, 48, 43) if red else (210, 225, 238), width=24 if red else 8)


def arrow(d, x0, x1, y, col):
    d.line([(x0, y), (x1 - 30, y)], fill=col, width=26)
    d.polygon([(x1, y), (x1 - 60, y - 42), (x1 - 60, y + 42)], fill=col)

def base_icon(night=False, text=False):
    im = sky((12, 24, 58), (45, 80, 140)) if night else sky((26, 90, 166), (201, 227, 246))
    if night:
        d = ImageDraw.Draw(im)
        import random; random.seed(3)
        for _ in range(140):
            x, y, r = random.randrange(S), random.randrange(int(S * .6)), random.choice((3, 4, 5, 7))
            d.ellipse([x - r, y - r, x + r, y + r], fill=(255, 255, 255))
    # 北アルプスの稜線(槍の穂先)
    far = [(0, .30), (.12, .42), (.22, .36), (.33, .55), (.40, .62), (.43, 1.0), (.46, .64), (.55, .58), (.66, .70), (.75, .55), (.86, .62), (1, .45)]
    near = [(0, .25), (.15, .32), (.3, .22), (.5, .30), (.7, .20), (.85, .28), (1, .22)]
    ridge(im, (90, 120, 165) if night else (120, 160, 205), S * .86, S * .30, far)
    ridge(im, (40, 60, 95) if night else (70, 110, 160), S * .95, S * .18, near)
    d = ImageDraw.Draw(im)
    top = S * (.20 if text else .26)
    sw, sh, mw, mh = S * .22, S * .19, S * .32, S * .27
    cy = top + mh / 2
    gap = S * .045
    mx0 = S / 2 - mw / 2
    panel(im, (mx0 - gap - sw, cy - sh / 2, mx0 - gap, cy + sh / 2), phase=-0.18)
    panel(im, (mx0, cy - mh / 2, mx0 + mw, cy + mh / 2), red=True)
    panel(im, (mx0 + mw + gap, cy - sh / 2, mx0 + mw + gap + sw, cy + sh / 2), phase=0.18)
    arrow(d, S * .12, S * .88, cy + mh / 2 + S * .07, (255, 159, 28))
    if text:
        f = ImageFont.truetype(FB, int(S * .17))
        d.text((S / 2 + 6, S * .80 + 8), "そら読み", font=f, fill=(0, 0, 0, 90), anchor="mm")
        d.text((S / 2, S * .80), "そら読み", font=f, fill=(255, 255, 255), anchor="mm")
    return im.resize((400, 400), Image.LANCZOS)

for name, kw in (("A_図だけ", {}), ("B_文字入り", {"text": True}), ("C_夜空", {"night": True})):
    base_icon(**kw).save(os.path.join(OUT, f"icon_{name}.png"))
# 3案を丸く切り抜いた見本を横に並べる(Xでは丸く表示される)
row = Image.new("RGB", (1300, 460), "white")
for i, name in enumerate(("A_図だけ", "B_文字入り", "C_夜空")):
    im = Image.open(os.path.join(OUT, f"icon_{name}.png"))
    m = Image.new("L", (400, 400), 0); ImageDraw.Draw(m).ellipse([0, 0, 399, 399], fill=255)
    row.paste(im, (30 + i * 430, 10), m)
    ImageDraw.Draw(row).text((230 + i * 430, 435), name, font=ImageFont.truetype(FB, 26), fill=(20, 40, 70), anchor="mm")
try:
    row.save(os.path.join(OUT, "見本_3案.png"))
except OSError:
    pass  # 見本を開いたままだと上書きできない
print("ok")


def alps_icon():
    """案C(夜空)を北アルプスに。左から槍ヶ岳の穂先 → 大キレット → 北穂・奥穂・ジャンダルム・前穂、手前に安曇野の森。尾根は月明かりで白く縁取る。"""
    import random
    im = sky((10, 20, 52), (52, 86, 140))
    d = ImageDraw.Draw(im)
    random.seed(3)
    for _ in range(150):
        x, y, r = random.randrange(S), random.randrange(int(S * .55)), random.choice((3, 4, 5, 6))
        d.ellipse([x - r, y - r, x + r, y + r], fill=(255, 255, 255))
    # 月
    glow = Image.new("L", (S, S), 0)
    ImageDraw.Draw(glow).ellipse([S * .58, S * .02, S * .76, S * .20], fill=120)
    im.paste((255, 250, 225), (0, 0), glow.filter(ImageFilter.GaussianBlur(60)))
    d.ellipse([S * .63, S * .065, S * .71, S * .145], fill=(255, 248, 220))
    pts = [(0, .30), (.05, .40), (.11, .50), (.15, .58), (.18, .66), (.195, .80), (.21, .98), (.225, .80), (.24, .67), (.25, .62), (.29, .66),
           (.33, .57), (.38, .46), (.42, .42), (.46, .50), (.50, .64), (.53, .60), (.57, .72), (.61, .82), (.635, .75),
           (.655, .80), (.68, .71), (.72, .68), (.76, .76), (.80, .64), (.86, .52), (.93, .44), (1, .38)]
    base, amp = S * .90, S * .40
    poly = [(0, S)] + [(x * S, base - h * amp) for x, h in pts] + [(S, S)]
    m_ridge = Image.new("L", (S, S), 0); ImageDraw.Draw(m_ridge).polygon(poly, fill=255)
    m_low = Image.new("L", (S, S), 0); ImageDraw.Draw(m_low).polygon([(x, y + 34) for x, y in poly], fill=255)
    im.paste((62, 84, 128), (0, 0), m_ridge)
    from PIL import ImageChops
    im.paste((215, 228, 245), (0, 0), ImageChops.subtract(m_ridge, m_low))  # 尾根の雪(月明かり)
    # 手前の森(安曇野)
    fx = [(0, .10)] + [(i / 40, .10 + (.05 if i % 2 else 0) + .03 * math.sin(i)) for i in range(41)]
    ridge(im, (20, 33, 58), S * 1.0, S * .9, [(x, h * .9) for x, h in fx])
    d = ImageDraw.Draw(im)
    top = S * .16
    sw, sh, mw, mh = S * .22, S * .19, S * .32, S * .27
    cy = top + mh / 2
    gap = S * .045
    mx0 = S / 2 - mw / 2
    panel(im, (mx0 - gap - sw, cy - sh / 2, mx0 - gap, cy + sh / 2), phase=-0.18)
    panel(im, (mx0, cy - mh / 2, mx0 + mw, cy + mh / 2), red=True)
    panel(im, (mx0 + mw + gap, cy - sh / 2, mx0 + mw + gap + sw, cy + sh / 2), phase=0.18)
    arrow(ImageDraw.Draw(im), S * .12, S * .88, cy + mh / 2 + S * .065, (255, 159, 28))
    return im


big = alps_icon()
big.resize((400, 400), Image.LANCZOS).save(os.path.join(OUT, "icon_C_北アルプス.png"))
m = Image.new("L", (800, 800), 0); ImageDraw.Draw(m).ellipse([0, 0, 799, 799], fill=255)
prev = Image.new("RGB", (900, 900), "white"); prev.paste(big.resize((800, 800), Image.LANCZOS), (50, 50), m)
prev.save(os.path.join(OUT, "見本_C_北アルプス.png"))
