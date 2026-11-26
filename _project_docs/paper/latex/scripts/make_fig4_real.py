import sys

import cv2
from PIL import Image, ImageDraw, ImageFont
R = sys.argv[1]
def load(box, name, rects):
    im = cv2.cvtColor(cv2.imread(f"{R}/JRN-2026-BOX{box}/images/{name}.jpg"), cv2.COLOR_BGR2RGB)
    h, w = im.shape[:2]
    for (x0, y0, x1, y1) in rects:  # pixelate label regions (fractions of width/height)
        a, b, c, d = int(x0*w), int(y0*h), int(x1*w), int(y1*h)
        roi = im[b:d, a:c]
        small = cv2.resize(roi, (max(1, (c-a)//40), max(1, (d-b)//40)), interpolation=cv2.INTER_AREA)
        im[b:d, a:c] = cv2.resize(small, (c-a, d-b), interpolation=cv2.INTER_NEAREST)
    return Image.fromarray(im)
panels = [
    ("A", "CP1_TOP", [], "(a) Box A, CP1"), ("A", "CP2_TOP", [], "(b) Box A, CP2"),
    ("B", "CP1_FRONT", [(0.08, 0.46, 0.39, 0.70)], "(c) Box B, CP1"), ("B", "CP2_FRONT", [(0.41, 0.52, 0.71, 0.85)], "(d) Box B, CP2"),
]
CELL_W, CELL_H, PAD, CAP = 640, 900, 18, 96
canvas = Image.new("RGB", (4*CELL_W + 5*PAD, CELL_H + CAP + 2*PAD), "white")
try:
    font = ImageFont.truetype("DejaVuSans.ttf", 70)
except OSError:
    font = ImageFont.load_default()
d = ImageDraw.Draw(canvas)
for k, (box, name, rects, cap) in enumerate(panels):
    im = load(box, name, rects)
    im.thumbnail((CELL_W, CELL_H))
    cx = PAD + k * (CELL_W + PAD)
    cy = PAD
    canvas.paste(im, (cx + (CELL_W - im.width)//2, cy + (CELL_H - im.height)//2))
    tw = d.textlength(cap, font=font)
    d.text((cx + (CELL_W - tw) / 2, cy + CELL_H + 10), cap, fill=(23, 32, 51), font=font)
canvas.save(sys.argv[2], dpi=(300, 300))
canvas.resize((canvas.width//3, canvas.height//3)).save(sys.argv[2].replace(".png", "_preview.png"))
