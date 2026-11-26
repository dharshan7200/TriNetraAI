"""Fig. 1: custody chain and per-journey pipeline (IEEE column width)."""
import sys
from pathlib import Path
import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
from matplotlib.patches import FancyBboxPatch, FancyArrowPatch
from matplotlib import font_manager

OUT = Path(sys.argv[1])
OUT.mkdir(parents=True, exist_ok=True)
for f in ["/usr/share/fonts/truetype/liberation/LiberationSerif-Regular.ttf",
          "/usr/share/fonts/truetype/liberation/LiberationSerif-Bold.ttf",
          "/usr/share/fonts/truetype/liberation/LiberationSerif-Italic.ttf"]:
    if Path(f).exists():
        font_manager.fontManager.addfont(f)
plt.rcParams.update({"font.family": "Liberation Serif", "font.size": 7.5, "axes.linewidth": 0.6, "mathtext.fontset": "stix"})
INK, MUTED, BLUE = "#1f1f1f", "#5f5f5f", "#2a78d6"
FILL, FILL_ACC = "#f2f2f2", "#e3edf9"

fig, ax = plt.subplots(figsize=(3.5, 3.92), dpi=300)
ax.set_xlim(0, 100)
ax.set_ylim(5, 118)
ax.axis("off")


def box(x, y, w, h, title, sub=None, fc=FILL, ec=INK, ty=None, sy=None, ssize=6.0, ls=1.2):
    ax.add_patch(FancyBboxPatch((x, y), w, h, boxstyle="round,pad=0.4,rounding_size=1.2", fc=fc, ec=ec, lw=0.7))
    if sub:
        ax.text(x + w / 2, y + h * (ty or 0.74), title, ha="center", va="center", fontsize=7.2, weight="bold", color=INK)
        ax.text(x + w / 2, y + h * (sy or 0.36), sub, ha="center", va="center", fontsize=ssize, color=MUTED, linespacing=ls)
    else:
        ax.text(x + w / 2, y + h / 2, title, ha="center", va="center", fontsize=7.2, weight="bold", color=INK)


def arrow(x1, y1, x2, y2, color=INK, lw=0.8):
    ax.add_patch(FancyArrowPatch((x1, y1), (x2, y2), arrowstyle="-|>", mutation_scale=7, lw=lw, color=color, shrinkA=0, shrinkB=0))


ax.text(50, 115.5, "(a) Custody chain", ha="center", fontsize=7.2, style="italic", color=MUTED)
cps = [("CP1", "origin\nhub"), ("CP2", "carrier\nfacility"), ("CP3", "doorstep /\npickup"), ("CP4", "return\nhub")]
xs = [1, 27, 53, 79]
for (t, sub), x in zip(cps, xs):
    box(x, 96, 19, 15, t, sub, fc=FILL_ACC, ec=BLUE, ty=0.76, sy=0.33)
for i, s in enumerate(["S1", "S2", "S3"]):
    x1, x2 = xs[i] + 19.7, xs[i + 1] - 0.7
    arrow(x1, 103.5, x2, 103.5, color=BLUE, lw=0.9)
    ax.text((x1 + x2) / 2, 106.2, s, ha="center", fontsize=6.8, weight="bold", color=BLUE)
ax.text(50, 90.5, "S1 forward transit    S2 customer custody    S3 reverse transit", ha="center", fontsize=6.0, color=MUTED)
ax.text(50, 84, "(b) Per-journey pipeline", ha="center", fontsize=7.2, style="italic", color=MUTED)
box(2, 66, 96, 14, "Checkpoint observation $o_k$,  $k$ = 1..4",
    "3 weighings and scale status · layered seals, serial, IMEI\nface photos (SHA-256) · UTC time · logged tare · glare flag")
arrow(50, 65.3, 50, 61.7)
box(2, 47, 96, 14, "Metadata-only quality gate  $\\rightarrow$  $q_k$",
    "scale: status, ≥ 3 readings, spread ≤ 4σ · photos: resolution, luminance,\nLaplacian variance, glare · a modality needs trust at CP$k$ and at CP1")
arrow(50, 46.3, 50, 42.7)
box(2, 27, 30, 15, "Weight", r"$|\Delta| > \delta_1+\delta_k$" + "\n" + r"$+\;z\sqrt{\sigma_1^2+\sigma_k^2}$", ty=0.83, sy=0.36, ls=1.65)
box(35, 27, 30, 15, "Identity", "layered seals, serial,\nIMEI vs CP1", sy=0.34)
box(68, 27, 30, 15, "Visual", "aligned, glare-\nmasked block SSIM", sy=0.34)
arrow(50, 26.3, 50, 22.7)
box(2, 6, 46, 16, "Fusion  $z_k$", "ANOM / INTACT / UNK\nfrom trusted modalities", sy=0.34)
arrow(48.7, 14, 52.3, 14)
box(53, 6, 45, 16, "Attribution", "Algorithm 1 or Bayes:\nstage, legitimate,\nor abstain (2 reasons)", fc=FILL_ACC, ec=BLUE, ty=0.80, sy=0.36)
fig.savefig(OUT / "fig1_pipeline.pdf", bbox_inches="tight", pad_inches=0.02)
fig.savefig(OUT / "fig1_pipeline.png", dpi=300, bbox_inches="tight", pad_inches=0.02)
print("ok")
