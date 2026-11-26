"""One-page dispute evidence report (PDF) for an analysed journey."""
from __future__ import annotations

import io
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List, Optional

from PIL import Image as PILImage
from reportlab.lib import colors
from reportlab.lib.enums import TA_LEFT
from reportlab.lib.pagesizes import A4
from reportlab.lib.styles import ParagraphStyle
from reportlab.lib.units import mm
from reportlab.platypus import Flowable, Image, KeepTogether, Paragraph, SimpleDocTemplate, Spacer, Table, TableStyle

from trinetra_link import __version__

INK = colors.HexColor("#172033")
SOFT = colors.HexColor("#4A5568")
RULE = colors.HexColor("#C5CED8")
PAPER = colors.HexColor("#E8EDF2")
TAPE = colors.HexColor("#F2B705")
KIND = {"clear": colors.HexColor("#1E6B45"), "fault": colors.HexColor("#B3261E"), "abstain": colors.HexColor("#2F4A9A")}
STATE_TEXT = {"REFERENCE": "Reference", "INTACT": "Unchanged", "ANOM": "Changed", "UNK": "Unclear"}

BASE = ParagraphStyle("base", fontName="Helvetica", fontSize=9, leading=12, textColor=INK, alignment=TA_LEFT)
SMALL = ParagraphStyle("small", parent=BASE, fontSize=7.6, leading=10, textColor=SOFT)
LABEL = ParagraphStyle("label", parent=BASE, textColor=SOFT)
TITLE = ParagraphStyle("title", parent=BASE, fontName="Helvetica-Bold", fontSize=19, leading=22)
H2 = ParagraphStyle("h2", parent=BASE, fontName="Helvetica-Bold", fontSize=10.5, leading=13, spaceBefore=8, spaceAfter=4)


def _esc(s: Any) -> str:
    return str(s if s is not None else "").replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;")


class Stamp(Flowable):
    """Rubber-stamp style verdict mark."""

    def __init__(self, text: str, color: colors.Color):
        super().__init__()
        self.text, self.color = text, color
        self.width, self.height = 60 * mm, 17 * mm

    def draw(self) -> None:
        c = self.canv
        c.saveState()
        c.translate(4 * mm, 3 * mm)
        c.rotate(-4)
        w = c.stringWidth(self.text, "Helvetica-Bold", 17) + 9 * mm
        c.setStrokeColor(self.color)
        c.setLineWidth(1.6)
        c.roundRect(0, 0, w, 11 * mm, 1.5 * mm)
        c.setLineWidth(0.6)
        c.roundRect(1.1 * mm, 1.1 * mm, w - 2.2 * mm, 11 * mm - 2.2 * mm, 1 * mm)
        c.setFillColor(self.color)
        c.setFont("Helvetica-Bold", 17)
        c.drawString(4.5 * mm, 3.3 * mm, self.text)
        c.restoreState()


def _thumb(path: Path, width_mm: float, folder: Optional[Path] = None) -> Optional[Image]:
    """Photo for the report: the stamped copy (time and place under the photo) when the journey has that data."""
    try:
        src: Any = path
        if folder is not None:
            from trinetra_link.console.app import stamped_lines_for
            from trinetra_link.integrity.stamp import render_stamped

            lines = stamped_lines_for(folder, path.resolve())
            if lines:
                src = io.BytesIO(render_stamped(path, lines, max_width=900))
        im = PILImage.open(src).convert("RGB")
    except Exception:
        return None
    im.thumbnail((600, 600))
    buf = io.BytesIO()
    im.save(buf, "JPEG", quality=82)
    buf.seek(0)
    w = width_mm * mm
    return Image(buf, width=w, height=w * im.height / im.width)


def _key_checkpoint(r: Dict[str, Any]) -> int:
    v = r["verdict"]
    if v.get("interval") and v["interval"][1] in {c["k"] for c in r["checkpoints"]}:
        return v["interval"][1]
    bad = [c["k"] for c in r["checkpoints"] if c["k"] > 1 and (not c["trusted"] or c["glare_reported"])]
    return bad[0] if bad else max(c["k"] for c in r["checkpoints"])


def build_report(r: Dict[str, Any], folder: Path) -> bytes:
    buf = io.BytesIO()
    doc = SimpleDocTemplate(buf, pagesize=A4, leftMargin=15 * mm, rightMargin=15 * mm, topMargin=13 * mm,
                            bottomMargin=13 * mm, title=f"Dispute report {r['code']}", author="TriNetra-Link")
    v = r["verdict"]
    kind_color = KIND.get(v["kind"], SOFT)
    now = datetime.now(timezone.utc).strftime("%d %b %Y, %H:%M UTC")
    story: List[Any] = []

    # Header
    head = Table([[Paragraph("<b>TriNetra-Link</b>  dispute evidence report", ParagraphStyle("hd", parent=BASE, fontSize=12, leading=15)),
                   Paragraph(f"Journey <b>{_esc(r['code'])}</b><br/>{_esc(r['product'] or 'Product not named')}<br/>Generated {now}",
                             ParagraphStyle("hr", parent=SMALL, alignment=2, fontSize=8.4, leading=11))]],
                 colWidths=[105 * mm, 75 * mm])
    head.setStyle(TableStyle([("VALIGN", (0, 0), (-1, -1), "TOP"), ("LINEBELOW", (0, 0), (-1, 0), 2.2, TAPE),
                              ("BOTTOMPADDING", (0, 0), (-1, -1), 6), ("LEFTPADDING", (0, 0), (-1, -1), 0),
                              ("RIGHTPADDING", (0, 0), (-1, -1), 0)]))
    story += [head, Spacer(1, 3 * mm)]
    if r.get("simulated"):
        story.append(Paragraph("Simulated demo input: these photos and readings were generated for demonstration, not captured from a real parcel.",
                               ParagraphStyle("sim", parent=SMALL, textColor=KIND["fault"])))
        story.append(Spacer(1, 2 * mm))

    # Verdict
    facts = [
        ["What to do", Paragraph(_esc(v["decision"]), BASE)],
        ["Why", Paragraph(_esc(v["reason"]), BASE)],
    ]
    if v.get("stage_name"):
        facts.insert(0, ["Responsible stage", Paragraph(f"<b>{_esc(v['stage_name'])}</b>", BASE)])
    if v.get("breach"):
        facts.append(["Seals", Paragraph(_esc(v["breach"]), BASE)])
    facts.append(["Output", Paragraph(_esc(v["label"]), BASE)])
    if r.get("expected"):
        ok = r.get("matches_expected")
        facts.append(["Expected", Paragraph(("Matches the expected output" if ok else f"Differs from expected ({_esc(r['expected'])})"),
                                            ParagraphStyle("ex", parent=BASE, textColor=KIND["clear"] if ok else KIND["fault"]))])
    integ = r.get("integrity", {})
    icolor = {"intact": KIND["clear"], "broken": KIND["fault"]}.get(integ.get("status"), SOFT)
    facts.append(["Evidence", Paragraph(_esc(integ.get("summary", "")), ParagraphStyle("ev", parent=BASE, textColor=icolor))])
    prov = r.get("provenance") or {}
    if prov:
        pcolor = {"flagged": KIND["fault"], "ok": KIND["clear"]}.get(prov.get("status"), SOFT)
        moves = "; ".join(f"CP{m['from']} to CP{m['to']}: {m['km']} km" for m in prov.get("moves", []))
        facts.append(["Time and place", Paragraph(_esc(prov.get("summary", "")) + (f"<br/><font color='#4A5568'>{_esc(moves)}</font>" if moves else ""),
                                                  ParagraphStyle("pv", parent=BASE, textColor=pcolor))])
    ft = Table([[Paragraph(a, LABEL), b] for a, b in facts], colWidths=[30 * mm, 145 * mm])
    ft.setStyle(TableStyle([("VALIGN", (0, 0), (-1, -1), "TOP"), ("LEFTPADDING", (0, 0), (-1, -1), 0),
                            ("TOPPADDING", (0, 0), (-1, -1), 1.5), ("BOTTOMPADDING", (0, 0), (-1, -1), 1.5)]))
    verdict_block = Table([[Stamp(v["stamp"], kind_color)],
                           [Paragraph(_esc(v["title"]), TITLE)],
                           [Paragraph(_esc(v["lead"]), BASE)],
                           [Spacer(1, 2 * mm)],
                           [ft]], colWidths=[180 * mm])
    verdict_block.setStyle(TableStyle([("LINEBEFORE", (0, 0), (0, -1), 3, kind_color), ("LEFTPADDING", (0, 0), (-1, -1), 4 * mm),
                                       ("TOPPADDING", (0, 0), (-1, -1), 1), ("BOTTOMPADDING", (0, 0), (-1, -1), 1)]))
    story += [verdict_block, Spacer(1, 2 * mm)]
    if integ.get("status") == "broken":
        story.append(Paragraph("<b>Warning:</b> the evidence was changed after it was captured. Do not rely on this verdict until the records are explained.",
                               ParagraphStyle("warn", parent=BASE, textColor=KIND["fault"])))

    # Checkpoint table
    rows = [["Checkpoint", "Weights (g)", "Trust q", "State", "Weight vs CP1", "Largest photo change"]]
    for c in r["checkpoints"]:
        weights = ", ".join(f"{w:.1f}" for w in c["weights"]) if c["weights"] else f"none (scale {c['scale_status']})"
        st = "Reference" if c["k"] == 1 else ("Not used" if not c["trusted"] else STATE_TEXT.get(c["state"], c["state"]))
        if c["k"] > 1 and c.get("glare_reported") and c["state"] != "ANOM":
            st = "Glare on photos"
        wt = c.get("weight_test")
        wtxt = "reference" if c["k"] == 1 else (f"{wt['delta_g']:.1f} g (limit {wt['bound_g']:.1f})" if wt else "not compared")
        changes = [p["change"] for p in c["photos"] if p.get("change") is not None]
        ptxt = "reference" if c["k"] == 1 else (f"{max(changes):.3f} (limit {r['settings']['gamma']:.2f})" if changes else "not compared")
        if c["k"] > 1 and (not c["trusted"] or c.get("glare_reported")) and changes:
            ptxt = "not used (photos untrusted)"
        if c["k"] > 1 and not c["trusted"] and wt:
            wtxt = "not used (untrusted)"
        rows.append([Paragraph(f"<b>CP{c['k']}</b> {_esc(c['place'])}", BASE), Paragraph(weights, BASE),
                     f"{c['q']:.2f}", st, wtxt, ptxt])
    tbl = Table(rows, colWidths=[34 * mm, 38 * mm, 15 * mm, 25 * mm, 32 * mm, 36 * mm], repeatRows=1)
    style = [("FONT", (0, 0), (-1, 0), "Helvetica-Bold", 8.4), ("FONT", (0, 1), (-1, -1), "Helvetica", 8.4),
             ("TEXTCOLOR", (0, 0), (-1, 0), SOFT), ("LINEBELOW", (0, 0), (-1, 0), 0.8, INK),
             ("LINEBELOW", (0, 1), (-1, -1), 0.4, RULE), ("VALIGN", (0, 0), (-1, -1), "MIDDLE"),
             ("LEFTPADDING", (0, 0), (-1, -1), 3), ("RIGHTPADDING", (0, 0), (-1, -1), 3)]
    for i, c in enumerate(r["checkpoints"], start=1):
        if c["k"] > 1 and c["trusted"] and c["state"] == "ANOM":
            style.append(("TEXTCOLOR", (3, i), (3, i), KIND["fault"]))
        elif c["k"] > 1 and (not c["trusted"] or c.get("glare_reported")):
            style.append(("TEXTCOLOR", (3, i), (3, i), KIND["abstain"]))
    tbl.setStyle(TableStyle(style))
    story += [Paragraph("Checkpoints", H2), tbl]

    # Photo comparison
    kk = _key_checkpoint(r)
    cp1 = next((c for c in r["checkpoints"] if c["k"] == 1), None)
    ck = next((c for c in r["checkpoints"] if c["k"] == kk), None)
    if cp1 and ck and kk != 1:
        ref = {p["side"]: p for p in cp1["photos"]}
        cells_top, cells_bot, heads = [], [], []
        for p in ck["photos"][:3]:
            side = p["side"]
            rp = ref.get(side)
            a = _thumb(folder / rp["url"].split("/", 4)[-1], 50, folder) if rp else None
            b = _thumb(folder / p["url"].split("/", 4)[-1], 50, folder)
            chg = p.get("change")
            chg_txt = (f"change {chg:.3f}" + (" (changed)" if chg > r["settings"]["gamma"] else " (same)")) if chg is not None else ""
            heads.append(Paragraph(f"<b>{_esc(side)}</b>  <font color='#4A5568'>{chg_txt}</font>", SMALL))
            cells_top.append(a or Paragraph("no CP1 photo", SMALL))
            cells_bot.append(b or Paragraph("photo missing", SMALL))
        n = len(heads)
        grid = Table([heads, cells_top, [Paragraph(f"CP1 {cp1['place']} (reference)", SMALL)] * n, cells_bot,
                      [Paragraph(f"CP{kk} {ck['place']}", SMALL)] * n], colWidths=[60 * mm] * n)
        grid.setStyle(TableStyle([("VALIGN", (0, 0), (-1, -1), "TOP"), ("LEFTPADDING", (0, 0), (-1, -1), 0),
                                  ("TOPPADDING", (0, 0), (-1, -1), 1), ("BOTTOMPADDING", (0, 0), (-1, -1), 1)]))
        story.append(KeepTogether([Paragraph(f"Photos: CP1 compared with CP{kk} ({_esc(ck['place'])})", H2), grid]))

    # Footer: settings and fingerprints
    fps = "; ".join(f"CP{c['k']} {c['record_hash'][:12]}" for c in r["checkpoints"] if c.get("record_hash"))
    story += [Spacer(1, 2 * mm), Paragraph(
        f"Method: TriNetra-Link {__version__}, Algorithm 1 with the settings fitted in the simulation study "
        f"(trust threshold {r['settings']['theta']:.2f}, photo change limit {r['settings']['gamma']:.2f}, weight test z = {r['settings']['z']:.0f}). "
        + (f"Evidence fingerprints (SHA-256, first 12 characters): {fps}." if fps else "These records carry no evidence fingerprints."),
        SMALL)]
    doc.build(story)
    return buf.getvalue()
