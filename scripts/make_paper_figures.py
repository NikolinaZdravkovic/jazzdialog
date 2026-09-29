"""Napravi dve figure za rad iz rucno ocenjenog CSV-a.

Figure su deskriptivne: ne pretvaraju kandidatske oznake u procenu tacnosti
na celoj WJD bazi.
"""

import csv
import gzip
import json
import sqlite3
from pathlib import Path

import matplotlib.pyplot as plt
import numpy as np

try:
    from .find_internal_split import _dtw_norm
except ImportError:
    from find_internal_split import _dtw_norm


ROOT = Path(__file__).resolve().parents[1]
CSV_PATH = ROOT / "output" / "wjd_phrase_call_response.csv"
DATABASE_PATH = ROOT / "data_midi" / "wjazzd.db"
FIGURE_DIR = ROOT / "rad" / "figure"


def _read_rows():
    with CSV_PATH.open(encoding="utf-8-sig", newline="") as stream:
        rows = list(csv.DictReader(stream))
    return [row for row in rows if row.get("validnost", "").strip().upper() in {"DA", "NE"}]


def _pitches(row, field):
    return [float(value) for value in json.loads(row[field])]


def boundary_scope(rows):
    """Broj potvrđenih anotacija unutar i preko WJD granice."""
    positive = [row for row in rows if row["validnost"].strip().upper() == "DA"]
    # MLU kandidati nemaju phrase_value sa znakom +, zato granicu proveravamo
    # prema samoj WJD tabeli sections za svaku potvrđenu apsolutnu granicu.
    cross = 0
    with sqlite3.connect(DATABASE_PATH) as conn:
        for row in positive:
            start = int(row["call_start_solo"])
            end = int(row["response_end_solo_inclusive"])
            contained = conn.execute(
                "SELECT COUNT(*) FROM sections WHERE melid=? AND type='PHRASE' "
                "AND start <= ? AND end >= ?", (row["melid"], start, end)
            ).fetchone()[0]
            count = conn.execute(
                "SELECT COUNT(*) FROM sections WHERE melid=? AND type='PHRASE' "
                "AND NOT (end < ? OR start > ?)",
                (row["melid"], start, end),
            ).fetchone()[0]
            if not contained and count < 2:
                raise ValueError(f"Uncovered annotation: {row['melid']}:{start}:{end}")
            cross += not contained
    within = len(positive) - cross
    fig, ax = plt.subplots(figsize=(6.0, 4.0), constrained_layout=True)
    bars = ax.bar(["u jednoj WJD frazi", "preko WJD granice"], [within, cross], color=["#3b82a0", "#d28145"])
    ax.bar_label(bars, padding=3, fontsize=12)
    ax.set_ylim(0, max(within, cross) + 15)
    ax.set_ylabel("broj potvrđenih anotacija")
    ax.set_title("Obuhvat WJD fraze u potvrđenim anotacijama (n = %d)" % len(positive))
    ax.text(0.5, -0.22, "Anotacije se mogu preklapati; stubovi nisu broj nezavisnih događaja.",
            transform=ax.transAxes, ha="center", fontsize=8)
    path = FIGURE_DIR / "figure_1_annotation_scope.png"
    fig.savefig(path, dpi=320)
    fig.savefig(path.with_suffix('.svg'))
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
    ax.set_xticks([1, 2], ["ručno DA", "ručno NE"])
    ax.set_ylabel("globalni pitch-DTW / dužina putanje")
    ax.set_title("Preklapanje DTW skora na ručno ocenjenim kandidatima")
    ax.text(0.5, -0.22, "Manja vrednost znači veću sličnost; preklapanje pokazuje da skor sam nije dovoljna odluka.",
            transform=ax.transAxes, ha="center", fontsize=8)
    path = FIGURE_DIR / "figure_2_dtw_overlap.png"
    fig.savefig(path, dpi=320)
    fig.savefig(path.with_suffix('.svg'))
    plt.close(fig)
    return path


def main():
    FIGURE_DIR.mkdir(parents=True, exist_ok=True)
    rows = _read_rows()
    scope, within, cross = boundary_scope(rows)
    # Manual references are purposefully selected positives, not detector proposals.
    from export_reviewed_dataset import candidate_family
    automatic = [r for r in rows if candidate_family(r.get('candidate_source', '')) != 'manual_reference']
    assert len(automatic) == 299, 'Update the paper snapshot explicitly if labels changed.'
    overlap = score_overlap(automatic)
    # Published tables must retain their frozen evaluation, even if a later
    # experiment overwrites the working report in output/.
    report = json.loads(gzip.decompress((ROOT/'rad/evaluacija.json.gz').read_bytes()))
    methods = ['dtw_incipit', 'existing_ne_penalty', 'existing_ranker', 'refitted_ranker',
               'pattern_rate', 'soft_pattern_penalty', 'soft_neighbor_penalty', 'interval_ranker']
    names = ['DTW + incipit', 'DTW + stara kazna', 'Postojeći model', 'Ponovo obučeni model',
             'Samo obrasci', 'Model + kazna za obrasce', 'Model + kazna po susedima', 'Model + intervalske osobine']
    summary = {}
    fig, ax = plt.subplots(figsize=(7, 4.8), constrained_layout=True)
    for key, offset, color, label in [('all_automatic_solo', -.16, '#356b88', 'Svi automatski kandidati (n=299)'),
                                     ('mlu_only_solo', .16, '#cf8346', 'MLU podskup (n=238)')]:
        values = np.array([[run['metrics'][m]['review_top_20pct']['precision']*100
                            for m in methods] for run in report['experiments'][key]['evaluations']])
        means = values.mean(axis=0)
        ax.barh(np.arange(len(methods))+offset, means, height=.29, color=color, label=label)
        ax.errorbar(means, np.arange(len(methods))+offset,
                    xerr=[means-values.min(axis=0), values.max(axis=0)-means], fmt='none',
                    ecolor='#333333', capsize=2, linewidth=.9)
        summary[key] = {m: {'mean_precision_percent': float(means[i]),
                           'seed_precision_percent': values[:, i].tolist()} for i,m in enumerate(methods)}
    ax.set_yticks(np.arange(len(methods)), names, fontsize=9)
    ax.invert_yaxis(); ax.set_xlim(0, 70)
    ax.set_xlabel('Preciznost (%)')
    ax.set_ylim(len(methods)+.65, -.6)
    ax.legend(loc='lower right', fontsize=8)
    ax.set_title('Isti budžet pregleda')
    fig.savefig(FIGURE_DIR/'figure_3_ranking.png', dpi=320)
    fig.savefig(FIGURE_DIR/'figure_3_ranking.svg')
    plt.close(fig)
    equations = [r"$D(x,y)=\frac{\sqrt{\sum_{(i,j)\in P}(x_i-y_j)^2}}{|P|}\qquad (1)$",
                 r"$S(x,y)=\alpha D(x,y)+(1-\alpha)I(x,y)\qquad (2)$"]
    for number, equation in enumerate(equations, 1):
        fig, ax = plt.subplots(figsize=(6, .8))
        ax.axis('off'); ax.text(.5, .5, equation, ha='center', va='center', fontsize=15)
        fig.savefig(FIGURE_DIR/f'equation_{number}.png', dpi=320, bbox_inches='tight', pad_inches=.04)
        plt.close(fig)
    summary.update(annotation_count=len([r for r in rows if r['validnost'].strip().upper()=='DA']),
                   within_phrase=within, across_phrases=cross,
                   experiment_source_sha256=report['source_sha256'],
                   labelled_source_sha256=__import__('hashlib').sha256(CSV_PATH.read_bytes()).hexdigest())
    (ROOT/'rad/statistika.json').write_text(json.dumps(summary, ensure_ascii=False, indent=2)+'\n', encoding='utf-8')
    print(f"Ocenjeni redovi: {len(rows)}")
    print(f"DA unutar fraze: {within}; DA preko granice: {cross}")
    print(scope)
    print(overlap)


if __name__ == "__main__":
    main()
