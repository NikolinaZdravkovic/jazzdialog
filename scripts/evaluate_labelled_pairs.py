"""Uporedi DTW i jednostavne osobine na rucno oznacenim CR parovima.

Skripta je samo za analizu. Ne menja CSV, MIDI fajlove ni parametre detektora.
Pokretanje iz korena projekta:

    .\\venv\\Scripts\\python.exe scripts\\evaluate_labelled_pairs.py
"""

import csv
import argparse
import hashlib
import json
import math
import statistics
from pathlib import Path

from dtaidistance import dtw


PROJECT_ROOT = Path(__file__).resolve().parents[1]
INPUT_CSV = PROJECT_ROOT / "output" / "wjd_phrase_call_response.csv"


def _dtw_distance_and_path(first, second):
    """Vrati DTW normalizovan pravom duzinom puta i najbolji put."""
    distance, paths = dtw.warping_paths(first, second)
    path = dtw.best_path(paths)
    return distance / len(path), path


def _auc_when_lower_is_better(values):
    """AUC bez dodatnih biblioteka; 0.5 znaci da mera ne razdvaja klase."""
    positives = [value for label, value in values if label == "DA"]
    negatives = [value for label, value in values if label == "NE"]
    wins = ties = 0
    for positive in positives:
        for negative in negatives:
            if positive < negative:
                wins += 1
            elif positive == negative:
                ties += 1
    return (wins + 0.5 * ties) / (len(positives) * len(negatives))


def _longest_approximate_interval_run(first, second, tolerance=2):
    """Duzina najduzeg uzastopnog intervalskog motiva, uz malu toleranciju."""
    previous = [0] * (len(second) + 1)
    longest = 0
    for first_interval in first:
        current = [0]
        for index, second_interval in enumerate(second, start=1):
            if abs(first_interval - second_interval) <= tolerance:
                current_length = previous[index - 1] + 1
            else:
                current_length = 0
            current.append(current_length)
            longest = max(longest, current_length)
        previous = current
    return longest


def _features(row):
    call = json.loads(row["call_pitches"])
    response = json.loads(row["response_pitches"])
    global_dtw, path = _dtw_distance_and_path(call, response)

    call_shape = [pitch - call[0] for pitch in call]
    response_shape = [pitch - response[0] for pitch in response]
    shape_dtw, _ = _dtw_distance_and_path(call_shape, response_shape)

    call_intervals = [b - a for a, b in zip(call, call[1:])]
    response_intervals = [b - a for a, b in zip(response, response[1:])]
    interval_dtw, _ = _dtw_distance_and_path(call_intervals, response_intervals)
    motif_run_fraction = _longest_approximate_interval_run(
        call_intervals, response_intervals
    ) / min(len(call_intervals), len(response_intervals))

    moves = [
        (next_i - current_i, next_j - current_j)
        for (current_i, current_j), (next_i, next_j) in zip(path, path[1:])
    ]
    diagonal_fraction = (
        sum(move == (1, 1) for move in moves) / len(moves) if moves else 1.0
    )
    max_path_offset = max(abs(call_index - response_index) for call_index, response_index in path)

    call_seconds = float(row["response_start_seconds"]) - float(row["call_start_seconds"])
    response_seconds = float(row["phrase_end_seconds"]) - float(row["response_start_seconds"])
    max_note_density = max(len(call) / call_seconds, len(response) / response_seconds)

    return {
        "global_dtw": global_dtw,
        "shape_dtw": shape_dtw,
        "interval_dtw": interval_dtw,
        "motif_run_fraction": motif_run_fraction,
        "diagonal_fraction": diagonal_fraction,
        "max_path_offset": max_path_offset,
        "max_note_density": max_note_density,
    }


def main(input_csv=INPUT_CSV):
    with Path(input_csv).open(encoding="utf-8-sig", newline="") as stream:
        rows = list(csv.DictReader(stream))

    items = []
    for row in rows:
        label = row.get("validnost", "").strip().upper()
        if label not in {"DA", "NE"}:
            continue
        features = _features(row)
        features["label"] = label
        items.append(features)

    da_count = sum(item["label"] == "DA" for item in items)
    ne_count = sum(item["label"] == "NE" for item in items)
    print(f"Rucno oznaceni parovi: {len(items)} (DA={da_count}, NE={ne_count})")
    if not da_count or not ne_count:
        print("Potrebne su obe oznake DA i NE za poredjenje.")
        return
    print("\nMere posmatrane odvojeno:")

    for name in (
        "global_dtw",
        "shape_dtw",
        "interval_dtw",
        "motif_run_fraction",
        "max_path_offset",
        "max_note_density",
        "diagonal_fraction",
    ):
        values = [(item["label"], item[name]) for item in items]
        da_values = [value for label, value in values if label == "DA"]
        ne_values = [value for label, value in values if label == "NE"]
        lower_auc = _auc_when_lower_is_better(values)
        # Smer je odredjen znacenjem mere, ne rezultatom na istim oznakama.
        if name in {"motif_run_fraction", "diagonal_fraction"}:
            auc = 1 - lower_auc
            direction = "hipoteza: vise je bolje"
        else:
            auc = lower_auc
            direction = "hipoteza: nize je bolje"
        print(
            f"  {name}: DA medijan={statistics.median(da_values):.3f}, "
            f"NE medijan={statistics.median(ne_values):.3f}, "
            f"AUC={auc:.3f} ({direction})"
        )

    print(
        "\nAUC blizu 0.5 znaci da mera ne razlikuje DA od NE. "
        "Veca vrednost znaci bolje razdvajanje, ali nije dokaz da se mera "
        "automatski dodaje u detektor."
    )


def _research_distances(call, response):
    """Fixed, independent hypotheses; no min across different features."""
    distance, paths = dtw.warping_paths(call, response)
    length = len(dtw.best_path(paths))
    first = [p - call[0] for p in call]
    second = [p - response[0] for p in response]
    shape_distance, shape_paths = dtw.warping_paths(first, second)
    shape_length = len(dtw.best_path(shape_paths))
    # Constrain normalized note positions. Every note must still be aligned.
    # Minimize summed squared errors, then report RMS on that selected path.
    n, m = len(first), len(second)
    costs = {(0, 0): (0.0, 0)}
    for i in range(1, n + 1):
        for j in range(1, m + 1):
            if abs((i - 1) / (n - 1) - (j - 1) / (m - 1)) > 0.2:
                continue
            options = [costs.get(k, (math.inf, 0))
                       for k in ((i - 1, j - 1), (i - 1, j), (i, j - 1))]
            cost, count = min(options, key=lambda x: x[0])
            costs[i, j] = (cost + (first[i - 1] - second[j - 1]) ** 2, count + 1)
    cost, count = costs.get((n, m), (math.inf, 1))
    return dict(pitch_legacy=distance / length,
                pitch_rms=distance / math.sqrt(length),
                shape_rms=shape_distance / math.sqrt(shape_length),
                shape_band_rms=math.sqrt(cost / count))


def _training_threshold(items, metric):
    """Choose on training solos only: precision >= .8, at least 3 selections.

    Maximize recovered training positives; ties prefer fewer negatives.
    No feasible threshold means abstain, rather than loosen the target.
    """
    best = None
    for threshold in sorted({x[metric] for x in items if math.isfinite(x[metric])}):
        selected = [x for x in items if x[metric] <= threshold]
        tp = sum(x["label"] == "DA" for x in selected)
        fp = len(selected) - tp
        if len(selected) < 3 or tp / len(selected) < .8:
            continue
        key = (tp, -fp, -threshold)
        if best is None or key > best[0]:
            best = (key, threshold)
    return best[1] if best is not None else -math.inf


def research(input_csv=INPUT_CSV):
    """Read-only experiment. Grouped validation concerns labelled candidates,
    not end-to-end recall across all phrases or unseen call-response pairs.
    """
    path = Path(input_csv)
    with path.open(encoding="utf-8-sig", newline="") as stream:
        rows = list(csv.DictReader(stream))
    unique = {}
    conflicts = set()
    labelled_count = 0
    for row in rows:
        label = row.get("validnost", "").strip().upper()
        if label not in {"DA", "NE"}:
            continue
        labelled_count += 1
        call, response = json.loads(row["call_pitches"]), json.loads(row["response_pitches"])
        key = (row["melid"], row["phrase_value"], row["split_point_local"],
               tuple(call), tuple(response))
        if key in unique and unique[key]["label"] != label:
            conflicts.add(key)
        unique[key] = dict(row=row, label=label, call=call, response=response)
    items = []
    for key, entry in unique.items():
        if key in conflicts or min(len(entry["call"]), len(entry["response"])) < 2:
            continue
        items.append(dict(melid=key[0], phrase=key[1], label=entry["label"],
                          **_research_distances(entry["call"], entry["response"])))
    groups = sorted({x["melid"] for x in items}, key=int)
    positives = sum(x["label"] == "DA" for x in items)
    print(json.dumps(dict(csv_sha256=hashlib.sha256(path.read_bytes()).hexdigest(),
                         labelled_rows=labelled_count, unique_keys=len(unique),
                         conflicts_excluded=len(conflicts), analysed=len(items),
                         DA=positives, NE=len(items)-positives, solos=len(groups))))
    if not positives or positives == len(items) or len(groups) < 2:
        print("Insufficient classes/groups for evaluation.")
        return
    for metric in ("pitch_legacy", "pitch_rms", "shape_rms", "shape_band_rms"):
        tp = fp = abstained = 0
        for group in groups:
            train = [x for x in items if x["melid"] != group]
            threshold = _training_threshold(train, metric)
            abstained += int(threshold == -math.inf)
            selected = [x for x in items if x["melid"] == group and x[metric] <= threshold]
            tp += sum(x["label"] == "DA" for x in selected)
            fp += sum(x["label"] == "NE" for x in selected)
        print(json.dumps(dict(metric=metric,
            descriptive_auc_lower_better=_auc_when_lower_is_better([(x["label"],x[metric]) for x in items]),
            median_DA=statistics.median(x[metric] for x in items if x["label"]=="DA"),
            median_NE=statistics.median(x[metric] for x in items if x["label"]=="NE"),
            heldout_TP=tp, heldout_FP=fp, precision=tp/(tp+fp) if tp+fp else None,
            recall_of_labelled_DA=tp/positives, abstained_folds=abstained)))
    print("Exploratory leave-one-solo-out evaluation; no production settings or labels changed.")


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--research", action="store_true", help="Compare DTW normalization with solo-held-out thresholds")
    args = parser.parse_args()
    research() if args.research else main()
