"""Uporedi DTW i jednostavne osobine na rucno oznacenim CR parovima.

Skripta je samo za analizu. Ne menja CSV, MIDI fajlove ni parametre detektora.
Pokretanje iz korena projekta:

    .\\venv\\Scripts\\python.exe scripts\\evaluate_labelled_pairs.py
"""

import csv
import json
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
        if lower_auc >= 0.5:
            auc = lower_auc
            direction = "nize vrednosti vise lice na DA"
        else:
            auc = 1 - lower_auc
            direction = "vise vrednosti vise lice na DA"
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


if __name__ == "__main__":
    main()
