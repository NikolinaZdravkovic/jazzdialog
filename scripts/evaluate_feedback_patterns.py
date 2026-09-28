"""Read-only test of soft penalties learned from reviewed interval patterns.

Run from the project root with the existing venv. Only the experiment JSON
is written; annotations, published data and production scoring stay intact.
All settings below are fixed before evaluating held-out labels. This is a
retrospective candidate-ranking experiment, not full-WJD detection accuracy.
"""

import argparse
from collections import Counter, defaultdict
import csv
import hashlib
import json
import math
from pathlib import Path
import sqlite3

import numpy as np

from export_reviewed_dataset import candidate_family
from find_internal_split import _dtw_norm
from generate_mlu_review_batch import _fit_review_ranker, _rank_probability, _review_features
from search_wjd_phrase_splits import (
    ALPHA, INCIPIT_K, NEGATIVE_PENALTY_WEIGHT, NEGATIVE_SIMILARITY_LIMIT,
    _negative_example_penalty, _score_split_with_tempo, _transposition_aware_distance,
)

ROOT = Path(__file__).resolve().parents[1]
SOURCE = ROOT / "output/wjd_phrase_call_response.csv"
DATABASE = ROOT / "data_midi/wjazzd.db"
OUTPUT = ROOT / "output/feedback_pattern_experiment.json"
SEEDS = (11, 29, 47)
FOLDS = 5
REVIEW_FRACTION = .20
SOFT_WEIGHT = .35
PATTERN_PRIOR_STRENGTH = 5
MIN_PATTERN_ROWS = 5
MIN_PATTERN_SOLOS = 3
NEIGHBORS = 15
METHODS = (
    "dtw_incipit", "existing_ne_penalty", "existing_ranker",
    "refitted_ranker", "pattern_rate", "soft_pattern_penalty",
    "interval_ranker", "soft_neighbor_penalty",
)


def interval_bins(pitches):
    """Signed movements in semitones; stable under pitch transposition."""
    return np.digitize(np.diff(pitches), [-4, -2, -1, 0, 1, 2, 3, 5]).tolist()


def patterns(call, response):
    """Presence of 2/3 consecutive movements, once per pair and role.

    A repeated ostinato does not cast many votes just because it is long.
    Shared patterns encode a relation between the two sides as well.
    """
    sides = []
    for pitches in (call, response):
        intervals = interval_bins(pitches)
        sides.append({tuple(intervals[i:i + size])
                      for size in (2, 3)
                      for i in range(len(intervals) - size + 1)})
    return {(role, *p) for role, tokens in
            (("call", sides[0]), ("response", sides[1]),
             ("shared", sides[0] & sides[1])) for p in tokens}


def interval_features(call, response):
    """Movement distribution plus direction changes and two-note loops."""
    values = []
    for pitches in (call, response):
        bins = interval_bins(pitches)
        values.extend(np.bincount(bins, minlength=9) / len(bins))
        steps = np.diff(pitches)
        values.append(float(np.mean(steps[:-1] * steps[1:] < 0)))
        values.append(float(np.mean(np.asarray(pitches)[2:] == pitches[:-2])))
    return values


def load_items():
    """Validate every label against exact WJD note boundaries, without MIDI I/O."""
    snapshot = SOURCE.read_bytes()
    with SOURCE.open(encoding="utf-8-sig", newline="") as stream:
        rows = list(csv.DictReader(stream))
    unique, excluded, cache = {}, [], {}
    conn = sqlite3.connect(DATABASE.resolve().as_uri() + "?mode=ro", uri=True)
    try:
        for row in rows:
            label = row.get("validnost", "").strip().upper()
            if label not in {"DA", "NE"}:
                continue
            try:
                melid = int(row["melid"])
                if melid not in cache:
                    notes = conn.execute(
                        "SELECT onset,pitch,duration FROM melody WHERE melid=? ORDER BY eventid",
                        (melid,),
                    ).fetchall()
                    tempo = conn.execute("SELECT avgtempo FROM solo_info WHERE melid=?",
                                         (melid,)).fetchone()[0]
                    cache[melid] = notes, tempo
                notes, tempo = cache[melid]
                start = int(row["phrase_start_index"])
                left = start + int(row.get("call_start_local") or 0)
                split = start + int(row["split_point_local"])
                end = int(row["phrase_end_index_inclusive"]) + 1
                right = start + int(row.get("response_end_local_exclusive") or end-start)
                if not 0 <= start <= left < split < right <= end <= len(notes):
                    raise ValueError("invalid boundaries")
                for field, value in (("call_start_solo", left), ("split_point_solo", split),
                                     ("response_end_solo_inclusive", right-1)):
                    if row.get(field) and int(row[field]) != value:
                        raise ValueError("inconsistent " + field)
                call, response = [json.loads(row[f"{side}_pitches"])
                                  for side in ("call", "response")]
                if min(len(call), len(response)) < 3:
                    raise ValueError("fewer than three notes")
                if call != [round(n[1]) for n in notes[left:split]] or response != [round(n[1]) for n in notes[split:right]]:
                    raise ValueError("pitch mismatch")
                key = f"wjd:{melid}:{left}:{split}:{right}"
                if key in unique:
                    raise ValueError("duplicate/conflicting absolute boundaries")
                pitch = _dtw_norm(call, response)
                shape = _dtw_norm([p-call[0] for p in call], [p-response[0] for p in response])
                base = _score_split_with_tempo(call + response, [n[2] for n in notes[left:right]],
                                              len(call), tempo, INCIPIT_K, ALPHA)
                unique[key] = dict(
                    id=key, melid=melid, performer=row["performer"], title=row["title"],
                    left=left, split=split, right=right, y=int(label == "DA"),
                    source=row["candidate_source"], family=candidate_family(row["candidate_source"]),
                    call=call, response=response, base=base,
                    x=_review_features(call, response, pitch, shape).tolist(),
                    extra=interval_features(call, response), tokens=patterns(call, response),
                )
            except (ValueError, KeyError, TypeError, IndexError) as error:
                excluded.append(dict(melid=row.get("melid"), phrase=row.get("phrase_value"), reason=str(error)))
    finally:
        conn.close()
    if SOURCE.read_bytes() != snapshot:
        raise RuntimeError("Labels changed during the experiment; rerun.")
    # A mapping error must be resolved, not silently dropped from evaluation.
    if excluded:
        raise ValueError(json.dumps(excluded, ensure_ascii=False))
    return sorted(unique.values(), key=lambda item: item["id"]), hashlib.sha256(snapshot).hexdigest()


def folds_for(items, indices, group, seed, count=FOLDS):
    """Assign whole groups with label-independent, size-balanced shuffling."""
    groups = defaultdict(list)
    for i in indices:
        groups[items[i][group]].append(i)
    keys = sorted(groups, key=str)
    np.random.default_rng(seed).shuffle(keys)
    keys.sort(key=lambda key: -len(groups[key]))  # shuffled ties remain stable
    buckets = [[] for _ in range(min(count, len(keys)))]
    for key in keys:
        min(buckets, key=len).extend(groups[key])
    for bucket in buckets:
        test = np.array(sorted(bucket), dtype=int)
        train = np.array(sorted(set(indices) - set(bucket)), dtype=int)
        assert {items[i][group] for i in train}.isdisjoint(items[i][group] for i in test)
        yield train, test


def logistic_predict(xtrain, ytrain, xtest):
    """Same optimizer/L2 settings as the existing ten-feature MLU ranker."""
    if not len(ytrain):
        raise ValueError("empty training fold")
    if len(set(ytrain)) < 2:
        return np.full(len(xtest), (sum(ytrain) + 1) / (len(ytrain) + 2))
    mean, std = xtrain.mean(axis=0), xtrain.std(axis=0)
    std[std < 1e-9] = 1
    train = np.column_stack([np.ones(len(xtrain)), (xtrain-mean)/std])
    test = np.column_stack([np.ones(len(xtest)), (xtest-mean)/std])
    weights = np.zeros(train.shape[1])
    for _ in range(2500):
        probability = 1 / (1 + np.exp(-np.clip(train @ weights, -25, 25)))
        gradient = train.T @ (probability-ytrain) / len(train)
        gradient[1:] += .02 * weights[1:]
        weights -= .08 * gradient
    return 1 / (1 + np.exp(-np.clip(test @ weights, -25, 25)))


def fit_patterns(items, train, labels):
    counts = defaultdict(lambda: [0, 0, set()])
    for i in train:
        for token in items[i]["tokens"]:
            counts[token][0] += 1
            counts[token][1] += int(labels[i])
            counts[token][2].add(items[i]["melid"])
    prior = (sum(labels[train]) + 1) / (len(train) + 2)
    rates = {token: (yes + PATTERN_PRIOR_STRENGTH * prior) / (n + PATTERN_PRIOR_STRENGTH)
             for token, (n, yes, groups) in counts.items()
             if n >= MIN_PATTERN_ROWS and len(groups) >= MIN_PATTERN_SOLOS}
    return float(prior), rates, counts


def pattern_prediction(item, prior, rates):
    # Every role has equal weight; no minimum over many chances to match.
    roles = []
    for role in ("call", "response", "shared"):
        values = [rates[token] for token in sorted(item["tokens"])
                  if token[0] == role and token in rates]
        roles.append(float(np.mean(values)) if values else prior)
    return float(np.mean(roles))


def soft_penalty(base_probability, pattern_probability, training_prior):
    """Reduce priority continuously only for worse-than-average patterns."""
    return base_probability - SOFT_WEIGHT * np.maximum(0, training_prior-pattern_probability)


def distance_matrix(items):
    """Exact clipped *directed* reference distances, cached in memory only.

    DTW cost is symmetric, but tie-broken paths may have different lengths
    when inputs are swapped. The legacy distance/path-length need not be
    symmetric. Preserve query->reference order to reproduce its penalty.
    """
    matrix = np.full((len(items), len(items)), NEGATIVE_SIMILARITY_LIMIT)
    for i, first in enumerate(items):
        for j, second in enumerate(items):
            if i == j:
                matrix[i, j] = 0
                continue
            call_distance = _transposition_aware_distance(first["call"], second["call"])
            if call_distance < 2 * NEGATIVE_SIMILARITY_LIMIT:
                response_distance = _transposition_aware_distance(first["response"], second["response"])
                matrix[i, j] = min(NEGATIVE_SIMILARITY_LIMIT, (call_distance + response_distance) / 2)
        if (i + 1) % 80 == 0:
            print(f"Reference distances: {i+1}/{len(items)}", flush=True)
    return matrix


def predict(items, train, test, distances, labels=None):
    """Fit only on train. Test labels never enter preprocessing or scores."""
    labels = np.array([item["y"] for item in items]) if labels is None else labels
    x = np.array([item["x"] for item in items])
    expanded = np.array([item["x"] + item["extra"] for item in items])
    base = -np.array([items[i]["base"] for i in test])
    rejected = train[labels[train] == 0]
    nearest = distances[np.ix_(test, rejected)].min(axis=1) if len(rejected) else np.full(len(test), np.inf)
    penalty = NEGATIVE_PENALTY_WEIGHT * np.maximum(0, 1-nearest/NEGATIVE_SIMILARITY_LIMIT)
    old_train = np.array([i for i in train if items[i]["source"] == "wjd_mlu_back_reference_v1"], dtype=int)
    old = logistic_predict(x[old_train], labels[old_train], x[test])
    refit = logistic_predict(x[train], labels[train], x[test])
    extended = logistic_predict(expanded[train], labels[train], expanded[test])
    prior, rates, _ = fit_patterns(items, train, labels)
    pattern = np.array([pattern_prediction(items[i], prior, rates) for i in test])
    mean, std = expanded[train].mean(axis=0), expanded[train].std(axis=0)
    std[std < 1e-9] = 1
    ztrain, ztest = (expanded[train]-mean)/std, (expanded[test]-mean)/std
    distances_knn = ((ztest[:, None, :]-ztrain[None, :, :])**2).mean(axis=2)
    nearest_ids = np.argsort(distances_knn, axis=1, kind="stable")[:, :min(NEIGHBORS, len(train))]
    neighbor = (labels[train][nearest_ids].sum(axis=1) + PATTERN_PRIOR_STRENGTH*prior) / (nearest_ids.shape[1]+PATTERN_PRIOR_STRENGTH)
    return dict(zip(METHODS, (base, base-penalty, old, refit, pattern,
                             soft_penalty(refit, pattern, prior), extended,
                             soft_penalty(refit, neighbor, prior))))


def auc(y, score):
    positive, negative = score[y == 1], score[y == 0]
    if not len(positive) or not len(negative):
        return None
    return float(np.mean((positive[:, None] > negative) + .5*(positive[:, None] == negative)))


def average_precision(y, score):
    # Threshold groups prevent tie ordering from changing AP.
    total, recovered, area = int(sum(y)), 0, 0.
    for threshold in sorted(set(score), reverse=True):
        chosen = score >= threshold
        tp = int(sum(y[chosen]))
        area += (tp-recovered) * tp / sum(chosen)
        recovered = tp
    return area / total if total else None


def select_top(score, fraction=REVIEW_FRACTION):
    mask = np.zeros(len(score), dtype=bool)
    mask[np.argsort(-score, kind="stable")[:max(1, math.ceil(len(score)*fraction))]] = True
    return mask


def training_threshold(y, score, groups):
    """Choose using INNER held-out scores only; 80% precision, >=10 rows/3 solos."""
    best = None
    for threshold in sorted(set(score), reverse=True):
        mask = score >= threshold
        tp, count = int(sum(y[mask])), int(sum(mask))
        if count < 10 or tp/count < .8 or len(set(groups[mask])) < 3:
            continue
        key = (tp, -(count-tp), threshold)
        if best is None or key > best[0]:
            best = key, threshold
    return best[1] if best else math.inf


def counts(y, selected):
    tp, n = int(sum(y[selected])), int(sum(selected))
    return dict(DA=tp, NE=n-tp, selected=n, precision=tp/n if n else None,
                labelled_positive_coverage=tp/int(sum(y)) if sum(y) else None)


def paired_bootstrap(items, indices, y, selected, baseline, group, seed=92026):
    """Paired cluster bootstrap of a fixed OOF selection, not model refitting."""
    groups = sorted({items[i][group] for i in indices}, key=str)
    totals = np.zeros((len(groups), 4))
    for k, value in enumerate(groups):
        mask = np.array([items[i][group] == value for i in indices])
        totals[k] = (sum(y[mask]*selected[mask]), sum(selected[mask]),
                     sum(y[mask]*baseline[mask]), sum(baseline[mask]))
    rng = np.random.default_rng(seed)
    samples = totals[rng.integers(0, len(groups), (2000, len(groups)))].sum(axis=1)
    samples = samples[(samples[:, 1] > 0) & (samples[:, 3] > 0)]
    delta = samples[:, 0]/samples[:, 1] - samples[:, 2]/samples[:, 3]
    return np.quantile(delta, [.025, .975]).tolist()


def evaluate(items, indices, distances, group, seeds=SEEDS, nested=True):
    y = np.array([item["y"] for item in items])
    evaluations, predictions = [], []
    for seed in seeds:
        score = {name: np.full(len(items), np.nan) for name in METHODS}
        selected = {name: np.zeros(len(items), dtype=bool) for name in METHODS}
        accepted = {name: np.zeros(len(items), dtype=bool) for name in METHODS}
        for train, test in folds_for(items, indices, group, seed):
            outer = predict(items, train, test, distances)
            thresholds = {name: math.inf for name in METHODS}
            if nested:
                inner = {name: np.full(len(items), np.nan) for name in METHODS}
                for inner_train, inner_test in folds_for(items, train, group, seed+1000, count=3):
                    for name, values in predict(items, inner_train, inner_test, distances).items():
                        inner[name][inner_test] = values
                for name in METHODS:
                    assert np.isfinite(inner[name][train]).all()
                    thresholds[name] = training_threshold(y[train], inner[name][train],
                                                         np.array([items[i][group] for i in train]))
            for name, values in outer.items():
                score[name][test] = values
                selected[name][test] = select_top(values)
                accepted[name][test] = values >= thresholds[name]
        metrics = {}
        for name in METHODS:
            scores = score[name][indices]
            assert np.isfinite(scores).all()
            metric = dict(auc=auc(y[indices], scores), average_precision=average_precision(y[indices], scores),
                          review_top_20pct=counts(y[indices], selected[name][indices]),
                          nested_target_80pct=counts(y[indices], accepted[name][indices]) if nested else None,
                          delta_precision_vs_refit_ci95=paired_bootstrap(
                              items, indices, y[indices], selected[name][indices],
                              selected["refitted_ranker"][indices], group))
            metrics[name] = metric
        evaluations.append(dict(seed=seed, metrics=metrics))
        predictions.append(dict(seed=seed, rows=[dict(
            id=items[i]["id"], label="DA" if y[i] else "NE",
            scores={name: float(score[name][i]) for name in METHODS},
            selected_top20pct={name: bool(selected[name][i]) for name in METHODS},
        ) for i in indices]))
        print(f"  {group}, seed {seed}: " + "; ".join(
            f"{name} {metrics[name]['review_top_20pct']['DA']}/{metrics[name]['review_top_20pct']['selected']}"
            for name in ("existing_ranker", "refitted_ranker", "soft_pattern_penalty", "interval_ranker", "soft_neighbor_penalty")), flush=True)
    return dict(rows=len(indices), DA=int(sum(y[indices])), NE=int(len(indices)-sum(y[indices])),
                groups=len({items[i][group] for i in indices}), group=group,
                evaluations=evaluations, predictions=predictions)


def self_test():
    call, response = [60, 62, 64, 62, 60, 61], [65, 67, 66, 65, 67, 70]
    assert patterns(call, response) == patterns([p+7 for p in call], [p-5 for p in response])
    assert interval_features(call, response) == interval_features([p+7 for p in call], [p-5 for p in response])
    assert patterns(call, response) != patterns(call, response[::-1])
    assert 0 < soft_penalty(.9, 0., .5) < .9
    assert soft_penalty(.9, 1., .5) == .9
    assert auc(np.array([0, 1]), np.array([0., 1.])) == 1.
    assert average_precision(np.array([0, 1]), np.array([.5, .5])) == .5
    assert math.isinf(training_threshold(np.array([0, 1]), np.array([0., 1.]), np.array([1, 2])))
    print("Control tests passed.", flush=True)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--self-test", action="store_true")
    parser.add_argument("--output", type=Path, default=OUTPUT)
    args = parser.parse_args()
    self_test()
    if args.self_test:
        return
    items, source_hash = load_items()
    print(f"Validated {len(items)} rows: {sum(x['y'] for x in items)} DA.", flush=True)
    distances = distance_matrix(items)
    auto = np.array([i for i, x in enumerate(items) if x["family"] != "manual_reference"])
    mlu = np.array([i for i, x in enumerate(items) if x["family"] == "wjd_midlevel_unit_link"])
    # Fixed label-independent representative of each overlapping event.
    representatives = []
    for i in sorted(auto, key=lambda i: (items[i]["melid"], items[i]["left"], items[i]["right"], items[i]["split"])):
        if not any(items[j]["melid"] == items[i]["melid"] and
                   max(items[j]["left"], items[i]["left"]) < min(items[j]["right"], items[i]["right"])
                   for j in representatives):
            representatives.append(int(i))
    report = dict(protocol="retrospective_grouped_soft_pattern_v1", source_sha256=source_hash,
                  script_sha256=hashlib.sha256(Path(__file__).read_bytes()).hexdigest(),
                  numpy_version=np.__version__, labelled_rows=len(items),
                  manual_reference_rows_excluded=len(items)-len(auto),
                  settings=dict(seeds=SEEDS, folds=FOLDS, inner_folds=3, review_fraction=REVIEW_FRACTION,
                                soft_weight=SOFT_WEIGHT, neighbors=NEIGHBORS, prior_strength=PATTERN_PRIOR_STRENGTH,
                                min_pattern_rows=MIN_PATTERN_ROWS, min_pattern_solos=MIN_PATTERN_SOLOS,
                                threshold_target=.8, threshold_min_rows=10, threshold_min_groups=3),
                  experiments={})
    for name, indices, group, seeds, nested in (
        ("all_automatic_solo", auto, "melid", SEEDS, True),
        ("mlu_only_solo", mlu, "melid", SEEDS, True),
        ("mlu_unseen_performer", mlu, "performer", SEEDS, False),
        ("one_annotation_per_overlap", np.array(sorted(representatives)), "melid", (SEEDS[0],), False),
    ):
        print(name, flush=True)
        report["experiments"][name] = evaluate(items, indices, distances, group, seeds, nested)
    # Chronological proxy: original MLU batch -> later source-tagged batches.
    later = [i for i in mlu if items[i]["source"] != "wjd_mlu_back_reference_v1"]
    later_solos = {items[i]["melid"] for i in later}
    earlier = np.array([i for i in mlu if items[i]["source"] == "wjd_mlu_back_reference_v1"
                        and items[i]["melid"] not in later_solos])
    scores = predict(items, earlier, np.array(later), distances)
    report["later_batch_check"] = dict(
        train_rows=len(earlier), test_rows=len(later), test_DA=sum(items[i]["y"] for i in later),
        note="Source-batch chronology proxy; annotation timestamps are unavailable; test solos excluded from training.",
        metrics={name: dict(auc=auc(np.array([items[i]["y"] for i in later]), value),
                            top20pct=counts(np.array([items[i]["y"] for i in later]), select_top(value)))
                 for name, value in scores.items()})
    # Audit label isolation by altering every test label and checking all scores.
    labels = np.array([item["y"] for item in items])
    altered = labels.copy()
    altered[later] = 1-altered[later]
    again = predict(items, earlier, np.array(later), distances, labels=altered)
    assert all(np.array_equal(scores[name], again[name]) for name in METHODS)
    # Reproduce actual production helpers, not just their formulas in isolation.
    rejected = [(items[i]["call"], items[i]["response"]) for i in earlier if not items[i]["y"]]
    actual_penalty_scores = np.array([
        -items[i]["base"] - _negative_example_penalty(items[i]["call"], items[i]["response"], rejected)
        for i in later])
    assert np.allclose(actual_penalty_scores, scores["existing_ne_penalty"], rtol=0, atol=1e-12)
    historical_rows = [dict(candidate_source=items[i]["source"], validnost="DA" if items[i]["y"] else "NE",
                            call_pitches=json.dumps(items[i]["call"]), response_pitches=json.dumps(items[i]["response"]),
                            pitch_dtw=items[i]["x"][0], shape_dtw=items[i]["x"][1]) for i in earlier]
    old_model = _fit_review_ranker(historical_rows)
    actual_rank_scores = np.array([_rank_probability(dict(call_pitches=items[i]["call"],
        response_pitches=items[i]["response"], pitch_dtw=items[i]["x"][0], shape_dtw=items[i]["x"][1]), old_model)
        for i in later])
    assert np.allclose(actual_rank_scores, scores["existing_ranker"], rtol=0, atol=1e-12)
    # Descriptive support table, never fed back into held-out evaluation.
    prior, rates, support = fit_patterns(items, auto, labels)
    report["descriptive_patterns"] = dict(
        training_positive_prior=prior, eligible_patterns=len(rates),
        negative_patterns=[dict(role=token[0], movement_bins=token[1:], rows=support[token][0],
                               DA=support[token][1], solos=len(support[token][2]),
                               smoothed_DA_rate=rates[token])
                           for token in sorted(rates, key=lambda t: (rates[t], t))
                           if support[token][0] >= 10][:12])
    report["controls"] = dict(test_label_invariance=True, exact_wjd_mapping=True,
                              disjoint_groups=True, interval_transposition_invariance=True,
                              existing_penalty_reproduced=True, existing_ranker_reproduced=True)
    if hashlib.sha256(SOURCE.read_bytes()).hexdigest() != source_hash:
        raise RuntimeError("Source labels changed while running; no results written.")
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(report, indent=2, ensure_ascii=False, allow_nan=False)+"\n", encoding="utf-8")
    print(f"Saved {args.output}", flush=True)


if __name__ == "__main__":
    main()
