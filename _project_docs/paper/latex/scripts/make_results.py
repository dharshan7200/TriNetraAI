"""Figures, tables and number macros for the conference paper.

Usage: python make_results.py RUN_DIR OUT_DIR
Every number in the paper comes from RUN_DIR (the simulation study output), so text and tables
cannot drift apart. All values are SIMULATED.
"""
import csv
import json
import sys
from pathlib import Path

import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
from matplotlib import font_manager

RUN, OUT = Path(sys.argv[1]), Path(sys.argv[2])
FIG, GEN = OUT / "fig", OUT / "gen"
FIG.mkdir(parents=True, exist_ok=True)
GEN.mkdir(parents=True, exist_ok=True)
for f in ["/usr/share/fonts/truetype/liberation/LiberationSerif-Regular.ttf",
          "/usr/share/fonts/truetype/liberation/LiberationSerif-Bold.ttf",
          "/usr/share/fonts/truetype/liberation/LiberationSerif-Italic.ttf"]:
    if Path(f).exists():
        font_manager.fontManager.addfont(f)
plt.rcParams.update({"font.family": ["Liberation Serif", "Times New Roman", "DejaVu Serif"], "font.size": 7.5, "axes.linewidth": 0.6, "mathtext.fontset": "stix"})
INK, GRID = "#1f1f1f", "#d9d9d9"
BLUE, ORANGE, GREEN, GREY, PURPLE = "#2a78d6", "#eb6834", "#2e9e5b", "#8c8c8c", "#7d5ab8"

res = RUN / "results"
full = json.loads((res / "methods_full.json").read_text(encoding="utf-8"))
field = json.loads((res / "methods_field.json").read_text(encoding="utf-8"))
abl = json.loads((res / "ablations_full.json").read_text(encoding="utf-8"))
fit = json.loads((RUN / "fit_params.json").read_text(encoding="utf-8"))
rows = {r["journey_code"]: r for r in csv.DictReader(open(RUN / "main" / "staging_log.csv", encoding="utf-8"))}
preds = list(csv.DictReader(open(res / "predictions_methods_full.csv", encoding="utf-8")))

ALG, BAY, GLO = "TriNetra-Link (Alg. 1)", "TriNetra-Link (Bayes)", "TriNetra-Link (Alg. 1, global SSIM)"
B1, B2, B3, B5 = "B1 CP4-only", "B2 endpoints", "B3 detection = origin", "B5 legacy rules"
ORDER = [ALG, BAY, GLO, B1, B2, B3, B5]
SHORT = {ALG: "Alg. 1 (local)", BAY: "Bayes (local)", GLO: "Alg. 1 (global)", B1: "B1 CP4-only",
         B2: "B2 endpoints", B3: "B3 det.\\,=\\,origin", B5: "B5 legacy rules"}
PLAIN = {k: v.replace("\\,", " ") for k, v in SHORT.items()}
T = {r["method"]: r for r in full["table"]}
TF = {r["method"]: r for r in field["table"]}
SG = full["subgroups"]

# ------------------------------------------------------------------ sweeps
sweeps = {}
for f in sorted((RUN / "sweeps").glob("*.json")):
    d = json.loads(f.read_text(encoding="utf-8"))
    sweeps.setdefault(d["param"], []).append(d)
for v in sweeps.values():
    v.sort(key=lambda d: d["value"])


def sw(param, value, method, key):
    d = next(d for d in sweeps[param] if d["value"] == value)
    return next(r for r in d["table"] if r["method"] == method)[key]


# ------------------------------------------------------------------ Fig. 2
fig, axes = plt.subplots(1, 2, figsize=(3.5, 2.5), dpi=300, gridspec_kw={"width_ratios": [1.25, 1]}, sharey=True)
ys = list(range(len(ORDER)))[::-1]
h = 0.36
for ax, key, cikey, xlabel in ((axes[0], "stage_acc_det", "stage_acc_ci", "Stage accuracy (determinable)"),
                               (axes[1], "customer_misblame", "customer_misblame_ci", "Customer mis-blame rate")):
    for i, (m, y) in enumerate(zip(ORDER, ys)):
        for tab, off, col, hatch, lab in ((T, h / 2, BLUE, None, "Full mask"), (TF, -h / 2, ORANGE, "////", "Field mask")):
            r = tab[m]
            ax.barh(y + off, r[key], height=h, color=col, edgecolor="white", linewidth=0.5, hatch=hatch,
                    label=lab if i == 0 else None, zorder=2)
            if r.get(cikey):
                ax.plot(r[cikey], [y + off] * 2, color=INK, lw=0.5, zorder=3)
    ax.set_xlim(0, 1.0)
    ax.set_xlabel(xlabel, fontsize=6.8)
    ax.xaxis.grid(True, color=GRID, lw=0.5, zorder=0)
    ax.set_axisbelow(True)
    for s in ("top", "right"):
        ax.spines[s].set_visible(False)
    ax.tick_params(width=0.5, length=2, labelsize=6.3)
axes[0].set_yticks(ys)
axes[0].set_yticklabels([PLAIN[m] for m in ORDER], fontsize=6.5)
axes[0].legend(loc="upper center", bbox_to_anchor=(1.05, 1.17), ncol=2, frameon=False, fontsize=6.5)
fig.tight_layout(w_pad=0.6)
for ext in ("pdf", "png"):
    fig.savefig(FIG / f"fig2_e1.{ext}", dpi=300, bbox_inches="tight", pad_inches=0.02)
plt.close(fig)

# ------------------------------------------------------------------ Fig. 3 (full width)
PANELS = [("sigma_multiplier", "Scale noise (× nominal σ)"), ("nuisance_scale", "Nuisance rate (× nominal)"),
          ("pose_jitter_px", "Pose displacement (px)")]
LINES = [(ALG, BLUE, "o", "-"), (BAY, GREEN, "s", "-"), (GLO, PURPLE, "^", "--"), (B3, ORANGE, "D", ":"), (B1, GREY, "v", ":")]
fig, axes = plt.subplots(1, 6, figsize=(7.16, 1.5), dpi=300)
for c, (param, label) in enumerate(PANELS):
    pts = sweeps[param]
    xs = [d["value"] for d in pts]
    for r_i, key in enumerate(("stage_acc_det", "customer_misblame")):
        ax = axes[2 * c + r_i]
        for name, col, mk, ls in LINES:
            vals = [next(r[key] for r in d["table"] if r["method"] == name) for d in pts]
            ax.plot(range(len(xs)), vals, color=col, marker=mk, ms=2.4, lw=0.8, ls=ls, label=PLAIN[name])
        ax.set_xticks(range(len(xs)))
        ax.set_xticklabels([f"{x:g}" for x in xs])
        ax.set_ylim(0, 1.02 if key == "stage_acc_det" else 0.85)
        ax.grid(True, color=GRID, lw=0.4)
        for s in ("top", "right"):
            ax.spines[s].set_visible(False)
        ax.tick_params(width=0.5, length=2, labelsize=5.8)
        ax.set_xlabel(label, fontsize=6.0)
        ax.set_title("Stage accuracy" if key == "stage_acc_det" else "Customer mis-blame", fontsize=6.4, pad=2)
axes[0].legend(loc="upper center", bbox_to_anchor=(3.6, 1.42), ncol=5, frameon=False, fontsize=6.2, handlelength=2.2)
fig.tight_layout(w_pad=0.5)
for ext in ("pdf", "png"):
    fig.savefig(FIG / f"fig3_sweeps.{ext}", dpi=300, bbox_inches="tight", pad_inches=0.02)
plt.close(fig)

# ------------------------------------------------------------------ number macros
def p1(x):
    return f"{100 * float(x):.1f}"


def f3(x):
    return f"{float(x):.3f}"


fa = [p for p in preds if p["truth"] == "ATTR_CONFIRMED_LEGITIMATE" and p["omega"] == "OBS_DETERMINABLE"
      and p[ALG].startswith("ATTR_STAGE")]
VIS = OUT / "vis_check.json"
if not VIS.exists():
    VIS = Path(__file__).resolve().parent / "vis_check.json"
vis = json.loads(VIS.read_text(encoding="utf-8"))
ac = abl["subgroups"]["assigned_cell"]
A = {r["method"]: r for r in abl["table"]}
a, b, g, b1, b3 = T[ALG], T[BAY], T[GLO], T[B1], T[B3]
M = {
    "NTotal": len(rows), "NTest": full["n_test"], "NCal": len(rows) - full["n_test"],
    "NDet": a["n_det"], "NNonDet": a["n_non_det"], "NNuis": SG["nuisance"]["any nuisance"]["n"],
    "NLegitDet": sum(1 for p in preds if p["truth"] == "ATTR_CONFIRMED_LEGITIMATE" and p["omega"] == "OBS_DETERMINABLE"),
    # journeys staged in a determinable cell whose ground truth became DEG through a nuisance effect
    "NCellDet": sum(1 for p in preds if p["assigned_cell"] not in ("degraded_evidence", "ambiguous_evidence")),
    "NNuisDeg": sum(1 for p in preds if p["assigned_cell"] not in ("degraded_evidence", "ambiguous_evidence")
                    and p["omega"] != "OBS_DETERMINABLE"),
    "NLegitNuisDeg": sum(1 for p in preds if p["assigned_cell"] in ("intact", "permitted_flyer") and p["omega"] != "OBS_DETERMINABLE"),
    "ThetaLocal": f"{fit['local']['theta']:.2f}", "GammaLocal": f"{fit['local']['visual_threshold']:.2f}",
    "ThetaGlobal": f"{fit['global']['theta']:.2f}", "GammaGlobal": f"{fit['global']['visual_threshold']:.2f}",
    "AlgAcc": p1(a["stage_acc_det"]), "AlgAccLo": p1(a["stage_acc_ci"][0]), "AlgAccHi": p1(a["stage_acc_ci"][1]),
    "AlgAAR": p1(a["aar"]), "AlgUAR": p1(a["uar"]), "AlgUBR": p1(a["ubr"]), "AlgMis": p1(a["customer_misblame"]),
    "AlgFA": p1(a["false_accusation_legit"]),
    "BayAcc": p1(b["stage_acc_det"]), "BayMis": p1(b["customer_misblame"]), "BayFA": p1(b["false_accusation_legit"]),
    "BayAAR": p1(b["aar"]),
    "GloAcc": p1(g["stage_acc_det"]),
    "BoneAcc": p1(b1["stage_acc_det"]), "BoneMis": p1(b1["customer_misblame"]), "BoneFA": p1(b1["false_accusation_legit"]),
    "BthreeAcc": p1(b3["stage_acc_det"]), "BthreeUBR": p1(b3["ubr"]), "BthreeFA": p1(b3["false_accusation_legit"]),
    "McBoneRef": b1["mcnemar_vs_ref"]["ref_only_correct"], "McBoneOther": b1["mcnemar_vs_ref"]["other_only_correct"],
    "McBthreeRef": b3["mcnemar_vs_ref"]["ref_only_correct"], "McBthreeOther": b3["mcnemar_vs_ref"]["other_only_correct"],
    "FwdGlo": p1(SG["assigned_cell"]["forward_transit_damage"][GLO]["stage_acc_det"]),
    "FwdAlg": p1(SG["assigned_cell"]["forward_transit_damage"][ALG]["stage_acc_det"]),
    "FwdBayLegit": sum(1 for p in preds if p["assigned_cell"] == "forward_transit_damage" and p["omega"] == "OBS_DETERMINABLE" and p[BAY] == "ATTR_CONFIRMED_LEGITIMATE"),
    "FwdNDet": SG["assigned_cell"]["forward_transit_damage"][ALG]["n_det"],
    "NoNuisAcc": p1(SG["nuisance"]["no nuisance"][ALG]["stage_acc_det"]),
    "NuisAcc": p1(SG["nuisance"]["any nuisance"][ALG]["stage_acc_det"]),
    "FATotal": len(fa), "FAMisread": sum(1 for p in fa if rows[p["journey_code"]]["nuisance_misread_cps"]),
    "FAGlare": sum(1 for p in fa if rows[p["journey_code"]]["nuisance_unflagged_glare_cps"]),
    "FABoth": sum(1 for p in fa if rows[p["journey_code"]]["nuisance_misread_cps"] and rows[p["journey_code"]]["nuisance_unflagged_glare_cps"]),
    "FANeither": sum(1 for p in fa if not rows[p["journey_code"]]["nuisance_misread_cps"] and not rows[p["journey_code"]]["nuisance_unflagged_glare_cps"]),
    "MassBig": p1(SG["mass_band"][">=15"][ALG]["stage_acc_det"]), "MassSmall": p1(SG["mass_band"]["<15"][ALG]["stage_acc_det"]),
    "MassZero": p1(SG["mass_band"]["0"][ALG]["stage_acc_det"]), "Cloned": p1(SG["seal_action"]["cloned"][ALG]["stage_acc_det"]),
    "FAlgAcc": p1(TF[ALG]["stage_acc_det"]), "FAlgUAR": p1(TF[ALG]["uar"]), "FAlgMis": p1(TF[ALG]["customer_misblame"]),
    "FGloAcc": p1(TF[GLO]["stage_acc_det"]), "FBayAcc": p1(TF[BAY]["stage_acc_det"]), "FBthreeAcc": p1(TF[B3]["stage_acc_det"]),
    "AbFullAAR": p1(A["Full (Alg. 1)"]["aar"]), "AbNoQAAR": p1(A["No quality gate"]["aar"]),
    "AbNoQUBR": p1(A["No quality gate"]["ubr"]), "AbNoQFA": p1(A["No quality gate"]["false_accusation_legit"]),
    "AbNoVisDrop": f"{100 * (A['Full (Alg. 1)']['stage_acc_det'] - A['No visual']['stage_acc_det']):.1f}",
    "AbNoVisFA": p1(A["No visual"]["false_accusation_legit"]),
    "AbFwdFull": p1(ac["forward_transit_damage"]["Full (Alg. 1)"]["stage_acc_det"]),
    "AbFwdNoVis": p1(ac["forward_transit_damage"]["No visual"]["stage_acc_det"]),
    "AbNoSealAcc": f3(A["No layered seals"]["stage_acc_det"]), "AbNoSealFA": p1(A["No layered seals"]["false_accusation_legit"]),
    "AbDoorFull": p1(ac["doorstep_substitution"]["Full (Alg. 1)"]["stage_acc_det"]),
    "AbDoorNoSeal": p1(ac["doorstep_substitution"]["No layered seals"]["stage_acc_det"]),
    "SwNuisZeroAcc": p1(sw("nuisance_scale", 0, ALG, "stage_acc_det")),
    "SwNuisFourAcc": p1(sw("nuisance_scale", 4, ALG, "stage_acc_det")),
    "SwNuisFourUAR": p1(sw("nuisance_scale", 4, ALG, "uar")),
    "SwNuisMaxMis": p1(max(sw("nuisance_scale", d["value"], ALG, "customer_misblame") for d in sweeps["nuisance_scale"])),
    "SwSigFourBthreeFA": p1(sw("sigma_multiplier", 4, B3, "false_accusation_legit")),
    "SwSigFourBoneMis": p1(sw("sigma_multiplier", 4, B1, "customer_misblame")),
    "SwSigFourAlgAcc": p1(sw("sigma_multiplier", 4, ALG, "stage_acc_det")),
    "SwSigFourAlgUAR": p1(sw("sigma_multiplier", 4, ALG, "uar")),
    "SwPoseMinAlg": p1(min(sw("pose_jitter_px", d["value"], ALG, "stage_acc_det") for d in sweeps["pose_jitter_px"])),
    "SwPoseMaxAlg": p1(max(sw("pose_jitter_px", d["value"], ALG, "stage_acc_det") for d in sweeps["pose_jitter_px"])),
    "VisGloPose": f3(vis["nominal"]["intact"]["global_median"]), "VisGloNoPose": f3(vis["nopose"]["intact"]["global_median"]),
    "VisGloMark": f3(vis["nopose"]["t06"]["global_median"]), "VisLocIntactMax": f3(vis["nominal"]["intact"]["local_max"]),
    "VisLocMarkMin": f3(vis["nominal"]["t03"]["local_min"]),
}
(GEN / "numbers.tex").write_text("".join(f"\\newcommand{{\\{k}}}{{{v}}}\n" for k, v in M.items()), encoding="utf-8")

# ------------------------------------------------------------------ tables
def ci(r):
    return f"{f3(r['stage_acc_det'])} [{f3(r['stage_acc_ci'][0])}, {f3(r['stage_acc_ci'][1])}]"


lines = []
for m in ORDER:
    r = T[m]
    bold = m == ALG
    cells = [SHORT[m], ci(r), f3(r["aar"]), f3(r["ubr"]), f3(r["uar"]), f3(r["customer_misblame"]), f3(r["false_accusation_legit"])]
    if bold:
        cells = [f"\\textbf{{{c}}}" for c in cells]
    lines.append(" & ".join(cells) + r" \\")
    if m == GLO:
        lines.append(r"\midrule")
(GEN / "table_e1.tex").write_text("\n".join(lines) + "\n\\bottomrule\n", encoding="utf-8")

CELLS = [("intact", "Intact", "LEG", 30), ("permitted_flyer", "Flyer replaced, logged", "LEG", 12),
         ("forward_transit_damage", "Forward-transit damage", "$S_1$", 14), ("doorstep_substitution", "Doorstep substitution", "$S_1$", 14),
         ("customer_tamper", "Customer tamper", "$S_2$", 14), ("reverse_transit_tamper", "Reverse-transit tamper", "$S_3$", 12),
         ("degraded_evidence", "Degraded evidence", "DEG", 12), ("ambiguous_evidence", "Ambiguous (glare)", "IND", 12)]
cell_lines = []
for k, name, truth, n in CELLS:
    s = SG["assigned_cell"][k]
    if s[ALG]["n_det"] > 0:
        accs = [f3(s[m]["stage_acc_det"]) for m in (ALG, GLO, BAY, B1, B3)]
    else:
        accs = [f"({p1(s[ALG]['aar'])}\\%)", "--", "--", "--", "--"]
    cell_lines.append(" & ".join([name, truth, str(8 * n), str(s["n"]), str(s[ALG]["n_det"])] + accs) + r" \\")
cell_lines.append(r"\midrule")
cell_lines.append(" & ".join(["Total", "", str(len(rows)), str(full["n_test"]), str(a["n_det"])]
                             + [f3(T[m]["stage_acc_det"]) for m in (ALG, GLO, BAY, B1, B3)]) + r" \\")
(GEN / "table_cells.tex").write_text("\n".join(cell_lines) + "\n\\bottomrule\n", encoding="utf-8")

abl_lines = []
for name in ("Full (Alg. 1)", "No quality gate", "No visual", "No layered seals", "Fixed 10 g weight threshold"):
    r = A[name]
    label = {"Full (Alg. 1)": "Full Algorithm 1", "Fixed 10 g weight threshold": "Fixed 10\\,g weight test"}.get(name, name)
    abl_lines.append(" & ".join([label, f3(r["stage_acc_det"]), f3(r["aar"]), f3(r["ubr"]), f3(r["customer_misblame"]), f3(r["false_accusation_legit"])]) + r" \\")
(GEN / "table_ablation.tex").write_text("\n".join(abl_lines) + "\n\\bottomrule\n", encoding="utf-8")

(OUT / "summary.json").write_text(json.dumps({"macros": M}, indent=1), encoding="utf-8")
print("ok", len(M), "macros")
