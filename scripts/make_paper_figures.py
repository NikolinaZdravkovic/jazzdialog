"""Napravi dve figure za rad iz rucno ocenjenog CSV-a.

Figure su deskriptivne: ne pretvaraju kandidatske oznake u procenu tacnosti
na celoj WJD bazi.
"""

import csv
import json
from pathlib import Path

import matplotlib.pyplot as plt
import numpy as np

try:
    from .find_internal_split import _dtw_norm
except ImportError:
    from find_internal_split import _dtw_norm


ROOT = Path(__file__).resolve().parents[1]
CSV_PATH = ROOT / "output" / "wjd_phrase_call_response.csv"
FIGURE_DIR = ROOT / "output" / "figures"


def _read_rows():
    with CSV_PATH.open(encoding="utf-8-sig", newline="") as stream:
        rows = list(csv.DictReader(stream))
    return [row for row in rows if row.get("validnost", "").strip().upper() in {"DA", "NE"}]


def _pitches(row, field):
    return [float(value) for value in json.loads(row[field])]


def boundary_scope(rows):
    """Broj potvrdenih anotacija unutar i preko WJD granice."""
    positive = [row for row in rows if row["validnost"].strip().upper() == "DA"]
    cross = sum("+" in str(row.get("phrase_value", "")) for row in positive)
    within = len(positive) - cross
    fig, ax = plt.subplots(figsize=(6.0, 4.0), constrained_layout=True)
    bars = ax.bar(["u jednoj WJD frazi", "preko WJD granice"], [within, cross], color=["#3b82a0", "#d28145"])
    ax.bar_label(bars, padding=3, fontsize=12)
    ax.set_ylim(0, max(within, cross) + 4)
    ax.set_ylabel("broj potvrdenih anotacija")
    ax.set_title("Obuhvat WJD fraze u pilot anotacijama (n = %d)" % len(positive))
    ax.text(0.5, -0.22, "Anotacije se mogu preklapati; stubovi nisu broj nezavisnih dogadaja.",
            transform=ax.transAxes, ha="center", fontsize=8)
    path = FIGURE_DIR / "figure_1_annotation_scope.png"
    fig.savefig(path, dpi=220)
    plt.close(fig)
    return path, within, cross


def score_overlap(rows):
    """Jedinstveno ponovo izracunat pitch-DTW za DA/NE, bez istorijskih score kolona."""
    values = {"DA": [], "NE": []}
    for row in rows:
        label = row["validnost"].strip().upper()
        values[label].append(_dtw_norm(_pitches(row, "call_pitches"), _pitches(row, "response_pitches")))
    fig, ax = plt.subplots(figsize=(6.4, 4.0), constrained_layout=True)
    violin = ax.violinplot([values["DA"], values["NE"]], showmedians=True, showextrema=False)
    for body, color in zip(violin["bodies"], ["#3b82a0", "#c95d63"]):
        body.set_facecolor(color)
        body.set_alpha(0.75)
    violin["cmedians"].set_color("#222222")
    rng = np.random.default_rng(20260921)
    for pos, label, color in [(1, "DA", "#1f5570"), (2, "NE", "#8d3037")]:
        jitter = rng.normal(0, 0.035, len(values[label]))
        ax.scatter(np.full(len(values[label]), pos) + jitter, values[label], s=18, alpha=.72, color=color)
    ax.set_xticks([1, 2], ["rucno DA", "rucno NE"])
    ax.set_ylabel("globalni pitch-DTW / duzina putanje")
    ax.set_title("Preklapanje DTW skora na rucno ocenjenim kandidatima")
    ax.text(0.5, -0.22, "Manja vrednost znaci vecu slicnost; preklapanje pokazuje da skor sam nije dovoljna odluka.",
            transform=ax.transAxes, ha="center", fontsize=8)
    path = FIGURE_DIR / "figure_2_dtw_overlap.png"
    fig.savefig(path, dpi=220)
    plt.close(fig)
    return path


def main():
    FIGURE_DIR.mkdir(parents=True, exist_ok=True)
    rows = _read_rows()
    scope, within, cross = boundary_scope(rows)
    overlap = score_overlap(rows)
    print(f"Ocenjeni redovi: {len(rows)}")
    print(f"DA unutar fraze: {within}; DA preko granice: {cross}")
    print(scope)
    print(overlap)


if __name__ == "__main__":
    main()
