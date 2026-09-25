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
import sqlite3
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

    # Stariji MLU review redovi nisu cuvali sekunde. Ostale melodijske mere
    # i dalje vaze za njih; gustina se racuna samo tamo gde su granice u
    # sekundama zaista zapisane, umesto da analiza puca ili izmisli nulu.
    time_fields = ("call_start_seconds", "response_start_seconds", "phrase_end_seconds")
    if all(str(row.get(field, "")).strip() for field in time_fields):
        call_seconds = float(row["response_start_seconds"]) - float(row["call_start_seconds"])
        response_seconds = float(row["phrase_end_seconds"]) - float(row["response_start_seconds"])
        max_note_density = (
            max(len(call) / call_seconds, len(response) / response_seconds)
            if call_seconds > 0 and response_seconds > 0 else None
        )
    else:
        max_note_density = None

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
        values = [(item["label"], item[name]) for item in items
                  if item[name] is not None and math.isfinite(item[name])]
        if not values:
            print(f"  {name}: nema dovoljno zapisanih vrednosti")
            continue
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


def _rhythm_distance(row, call, response, events):
    """Map declared indices exactly; never locate a repeated motif by guessing."""
    start = int(row["phrase_start_index"])
    end = int(row["phrase_end_index_inclusive"])
    split = int(row["split_point_local"])
    left = int(row.get("call_start_local") or 0)
    right = int(row.get("response_end_local_exclusive") or (end - start + 1))
    if not (0 <= start <= end < len(events) and 0 <= left < split < right <= end-start+1):
        raise ValueError("invalid_bounds")
    for field, expected in (("split_point_solo", start+split),
                            ("call_start_solo", start+left),
                            ("response_end_solo_inclusive", start+right-1)):
        if row.get(field) and int(row[field]) != expected:
            raise ValueError("inconsistent_" + field)
    first, second = events[start+left:start+split], events[start+split:start+right]
    if [round(e[1]) for e in first] != call or [round(e[1]) for e in second] != response:
        raise ValueError("pitch_or_length_mismatch")
    for field, expected in (("call_start_seconds", first[0][0]),
                            ("response_start_seconds", second[0][0])):
        if row.get(field) and not math.isclose(float(row[field]), expected, abs_tol=1e-5, rel_tol=0):
            raise ValueError("inconsistent_" + field)
    def representation(notes):
        iois = [b[0]-a[0] for a,b in zip(notes, notes[1:])]
        if len(iois) < 2 or any(not math.isfinite(x) or x <= 0 for x in iois):
            raise ValueError("insufficient_or_nonpositive_ioi")
        median = statistics.median(iois)
        return [math.log2(x/median) for x in iois]
    distance, paths = dtw.warping_paths(representation(first), representation(second))
    return float(distance/math.sqrt(len(dtw.best_path(paths))))


def _contour_pair_features(call, response):
    """Small MIDI adaptation, NOT the audio melodiness model from Salamon 2012.

    Describe differences of transposition-invariant mean, spread and net motion.
    No pitch salience or vibrato can be reconstructed from MIDI note numbers.
    """
    first = [p-call[0] for p in call]
    second = [p-response[0] for p in response]
    return [abs(statistics.mean(first)-statistics.mean(second)),
            abs(statistics.pstdev(first)-statistics.pstdev(second)),
            abs(first[-1]-second[-1])]


def _gaussian_score(train, query):
    """Negative log posterior odds for DA; shared diagonal covariance.

    Class means, variances and priors come from training solos only.
    Fixed variance floor avoids division by zero; no hyperparameter search.
    This is a small Gaussian baseline, not a calibrated confidence estimate.
    """
    da = [x for label,x in train if label=='DA']
    ne = [x for label,x in train if label=='NE']
    if len(da)<2 or len(ne)<2:
        return math.inf
    score = -math.log(len(da)/len(ne))
    for i,value in enumerate(query):
        a, b = statistics.mean(x[i] for x in da), statistics.mean(x[i] for x in ne)
        variance = max(1e-6, (sum((x[i]-a)**2 for x in da)+sum((x[i]-b)**2 for x in ne))/(len(train)-2))
        score += ((value-a)**2-(value-b)**2)/(2*variance)
    return score


def _evaluate_contour_model(items, with_rhythm=False):
    values = []
    predictions = []
    for item in items:
        def vector(row):
            return row['contour_features'] + ([row['rhythm_rms']] if with_rhythm else [])
        train = [(row['label'],vector(row)) for row in items if row['melid']!=item['melid']]
        score = _gaussian_score(train,vector(item))
        values.append((item['label'],score))
        if score < 0:  # Fixed equal-error posterior decision; no tuned threshold.
            predictions.append(dict(melid=item['melid'],phrase=item['phrase'],label=item['label']))
    tp = sum(x['label']=='DA' for x in predictions)
    fp = len(predictions)-tp
    positives = sum(x['label']=='DA' for x in items)
    print(json.dumps(dict(model='contour_plus_rhythm_gaussian' if with_rhythm else 'contour_gaussian',
        decision='negative_log_odds < 0; training class priors',
        heldout_auc_lower_better=_auc_when_lower_is_better(values),
        heldout_TP=tp,heldout_FP=fp,precision=tp/(tp+fp) if tp+fp else None,
        recall_of_labelled_DA=tp/positives,predictions=predictions)))


def _median3(pitches):
    """One nonrecursive pass, preserving endpoints and sequence length."""
    result = list(pitches)
    for i in range(1, len(pitches)-1):
        result[i] = statistics.median(pitches[i-1:i+2])
    return result


def _median3_shape_rms(call, response):
    first, second = _median3(call), _median3(response)
    first = [p-first[0] for p in first]
    second = [p-second[0] for p in second]
    distance, paths = dtw.warping_paths(first, second)
    return float(distance/math.sqrt(len(dtw.best_path(paths))))


def research(input_csv=INPUT_CSV, rhythm=False, contours=False, median3=False):
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
    events_by_solo = {}
    if rhythm:
        database = PROJECT_ROOT / "data_midi" / "wjazzd.db"
        conn = sqlite3.connect(database.resolve().as_uri() + "?mode=ro", uri=True)
        try:
            ids = sorted({int(k[0]) for k in unique})
            placeholders = ",".join("?" for _ in ids)
            for melid, onset, pitch in conn.execute(
                    f"SELECT melid,onset,pitch FROM melody WHERE melid IN ({placeholders}) ORDER BY melid,eventid", ids):
                events_by_solo.setdefault(melid, []).append((onset, pitch))
        finally:
            conn.close()
    items = []
    excluded = []
    for key, entry in unique.items():
        if key in conflicts or min(len(entry["call"]), len(entry["response"])) < 2:
            continue
        extra = {}
        if median3:
            extra['median3_shape_rms'] = _median3_shape_rms(entry['call'], entry['response'])
        if rhythm:
            try:
                extra["rhythm_rms"] = _rhythm_distance(entry["row"], entry["call"],
                    entry["response"], events_by_solo.get(int(key[0]), []))
            except (ValueError, KeyError, IndexError, TypeError) as error:
                excluded.append(dict(melid=key[0], phrase=key[1], split=key[2],
                                     label=entry["label"], reason=str(error)))
                continue
        items.append(dict(melid=key[0], phrase=key[1], label=entry["label"],
                          contour_features=_contour_pair_features(entry['call'],entry['response']),
                          **_research_distances(entry["call"], entry["response"]), **extra))
    groups = sorted({x["melid"] for x in items}, key=int)
    positives = sum(x["label"] == "DA" for x in items)
    print(json.dumps(dict(csv_sha256=hashlib.sha256(path.read_bytes()).hexdigest(),
                         labelled_rows=labelled_count, unique_keys=len(unique),
                         conflicts_excluded=len(conflicts), analysed=len(items),
                         DA=positives, NE=len(items)-positives, solos=len(groups))))
    if rhythm:
        print(json.dumps(dict(mapping_exclusions=excluded)))
    if not positives or positives == len(items) or len(groups) < 2:
        print("Insufficient classes/groups for evaluation.")
        return
    metrics = ["pitch_legacy", "pitch_rms", "shape_rms", "shape_band_rms"]
    if median3:
        metrics = ['shape_rms', 'median3_shape_rms']
    if rhythm:
        metrics.append("rhythm_rms")
    for metric in metrics:
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
    if contours:
        _evaluate_contour_model(items)
        if rhythm:
            _evaluate_contour_model(items,with_rhythm=True)
    print("Exploratory leave-one-solo-out evaluation; no production settings or labels changed.")


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--research", action="store_true", help="Compare DTW normalization with solo-held-out thresholds")
    parser.add_argument("--rhythm", action="store_true", help="Research rhythm and melody on exactly mapped WJD candidates")
    parser.add_argument("--contours", action="store_true", help="Test a learned contour baseline, alone and with rhythm; implies WJD mapping")
    parser.add_argument("--median3", action="store_true", help="Compare fixed median-3 smoothing with unchanged shape RMS")
    args = parser.parse_args()
    research(rhythm=args.rhythm or args.contours, contours=args.contours, median3=args.median3) if args.research or args.rhythm or args.contours or args.median3 else main()
