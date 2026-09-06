"""Pronadji call-response parove unutar zvanicnih WJD fraza vise sola."""

import csv
import json
import math
from pathlib import Path


try:  # Kada se uvozi kao scripts.search_wjd_phrase_splits
    from .extract_wjd_phrases import (
        connect_db,
        find_melid_by_title,
        get_melody_events,
        get_phrase_sections,
    )
    from .find_internal_split import (
        _dtw_norm,
        find_best_internal_split,
        incipit_similarity,
    )
except ImportError:  # Kada se pokrene direktno iz komandne linije
    from extract_wjd_phrases import (
        connect_db,
        find_melid_by_title,
        get_melody_events,
        get_phrase_sections,
    )
    from find_internal_split import _dtw_norm, find_best_internal_split, incipit_similarity


# ---------------------------------------------------------------------------
# PODESAVANJA: menjaj samo ovaj mali blok.
# Stavke mogu biti nazivi pesama ili melid brojevi.
# ---------------------------------------------------------------------------
SEARCH_ITEMS = [
    70,  # I Fall in Love Too Easily - Chet Baker
    71,  # Just Friends - Chet Baker
    72,  # Let's Get Lost - Chet Baker
    73, 74, 76, 402, 55, 282
]

ALPHA = 0.5
INCIPIT_K = 3
THRESHOLD = 0.3
REVIEW_THRESHOLD = 0.45
MIN_SEGMENT_LEN = 5

# Response ne sme da bude samo kratak fragment dugog call-a.
MIN_RESPONSE_CALL_RATIO = 0.75
# Rucno odbijen kandidat dobija najvise ovoliku dodatnu kaznu.
# Skor je distanca, zato veci skor znaci manju verovatnocu izbora.
NEGATIVE_PENALTY_WEIGHT = 0.20
NEGATIVE_SIMILARITY_LIMIT = 0.30
POSITIVE_REWARD_WEIGHT = 0.70
POSITIVE_SIMILARITY_LIMIT = 0.30

# Mala dodatna korekcija uci profil veze iz oznacenih DA/NE primera.
# Profil koristi samo oblik cele linije i prvih pet nota; ne menja osnovni
# DTW + incipit skor i sam ne moze da napravi veliki skok u rezultatu.
PROFILE_INCIPIT_K = 5
PROFILE_ADJUSTMENT_WEIGHT = 0.10

# U veoma brzom tempu tri kratke note nisu dovoljan incipit dokaz.
FAST_TEMPO_BPM = 215.0
MIN_THREE_NOTE_DURATION_SECONDS = 0.75

PROJECT_ROOT = Path(__file__).resolve().parents[1]
DB_PATH = PROJECT_ROOT / "data_midi" / "wjazzd.db"
OUTPUT_CSV = PROJECT_ROOT / "output" / "wjd_phrase_call_response.csv"


def _resolve_solo(conn, item):
    """Vrati (melid, title, performer, avgtempo) ili prijavi problem."""
    if isinstance(item, int):
        row = conn.execute(
            "SELECT melid, title, performer, avgtempo FROM solo_info WHERE melid = ?",
            (item,),
        ).fetchone()
        if row is None:
            print(f"[UPOZORENJE] melid={item} nije pronadjen; preskacem.")
        return row

    if not isinstance(item, str) or not item.strip():
        print(f"[UPOZORENJE] Neispravna ulazna stavka {item!r}; preskacem.")
        return None

    matches = find_melid_by_title(conn, item.strip())
    exact = [row for row in matches if row[1].strip().casefold() == item.strip().casefold()]
    usable = exact if exact else matches

    if not usable:
        print(f"[UPOZORENJE] Pesma {item!r} nije pronadjena; preskacem.")
        return None
    if len(usable) > 1:
        choices = ", ".join(f"melid={row[0]} ({row[2]})" for row in usable)
        print(f"[UPOZORENJE] Naziv {item!r} nije jednoznacan: {choices}.")
        print("              Unesi zeljeni melid u SEARCH_ITEMS; ovu stavku preskacem.")
        return None

    melid, title, performer, _instrument = usable[0]
    tempo_row = conn.execute(
        "SELECT avgtempo FROM solo_info WHERE melid = ?", (melid,)
    ).fetchone()
    avgtempo = tempo_row[0] if tempo_row else None
    return melid, title, performer, avgtempo


def _candidate_key(melid, phrase_value, split):
    return str(melid), str(phrase_value), str(split)


def _read_manual_feedback(output_csv):
    """Ucitaj rucne oznake i zapamti DA/NE pitch parove."""
    if not output_csv.exists():
        return {}, [], [], {}

    labels = {}
    accepted_pairs = []
    rejected_pairs = []
    reviewed_rows = {}
    with output_csv.open(encoding="utf-8-sig", newline="") as stream:
        for row in csv.DictReader(stream):
            # Spojene fraze pripadaju napustenom eksperimentu i ne uticu na model.
            if "+" in row.get("phrase_value", ""):
                continue
            key = _candidate_key(
                row.get("melid", ""),
                row.get("phrase_value", ""),
                row.get("split_point_local", ""),
            )
            label = row.get("validnost", "").strip().upper()
            if label not in {"DA", "NE"}:
                continue
            labels[key] = label
            row["validnost"] = label
            row["call_pitches"] = json.loads(row["call_pitches"])
            row["response_pitches"] = json.loads(row["response_pitches"])
            reviewed_rows[key] = row
            if label == "DA":
                accepted_pairs.append((row["call_pitches"], row["response_pitches"]))
            else:
                rejected_pairs.append((row["call_pitches"], row["response_pitches"]))
    return labels, accepted_pairs, rejected_pairs, reviewed_rows


def _transposition_aware_distance(first, second):
    """DTW udaljenost celih segmenata, apsolutno ili bez transpozicije."""
    absolute = _dtw_norm(first, second)
    first_shape = [pitch - first[0] for pitch in first]
    second_shape = [pitch - second[0] for pitch in second]
    return min(absolute, _dtw_norm(first_shape, second_shape))


def _negative_example_penalty(call, response, rejected_pairs):
    """Kazni samo kandidata koji licI na vec rucno odbijen par."""
    if not rejected_pairs:
        return 0.0

    nearest_distance = min(
        (
            _transposition_aware_distance(call, rejected_call)
            + _transposition_aware_distance(response, rejected_response)
        ) / 2
        for rejected_call, rejected_response in rejected_pairs
    )
    if nearest_distance >= NEGATIVE_SIMILARITY_LIMIT:
        return 0.0
    return NEGATIVE_PENALTY_WEIGHT * (
        1 - nearest_distance / NEGATIVE_SIMILARITY_LIMIT
    )


def _positive_example_reward(call, response, accepted_pairs):
    """Nagradi samo kandidata koji lici na vec rucno potvrđen par."""
    if not accepted_pairs:
        return 0.0

    nearest_distance = min(
        (
            _transposition_aware_distance(call, accepted_call)
            + _transposition_aware_distance(response, accepted_response)
        ) / 2
        for accepted_call, accepted_response in accepted_pairs
    )
    if nearest_distance >= POSITIVE_SIMILARITY_LIMIT:
        return 0.0
    return POSITIVE_REWARD_WEIGHT * (
        1 - nearest_distance / POSITIVE_SIMILARITY_LIMIT
    )


def _relationship_profile(call, response):
    """Dve razumljive osobine veze: ceo oblik i duzi incipit."""
    shape_score = _transposition_aware_distance(call, response)
    profile_k = min(PROFILE_INCIPIT_K, len(call), len(response))
    longer_incipit_score = incipit_similarity(call, response, k=profile_k)
    return shape_score, longer_incipit_score


def _profile_correction(call, response, accepted_pairs, rejected_pairs):
    """Vrati malu korekciju prema najblizem DA i NE profilu.

    Negativna vrednost popravlja skor, a pozitivna ga kaznjava. Obe osobine
    se skaliraju rasipanjem rucno oznacenih primera da nijedna ne dominira
    samo zato sto prirodno ima vece brojeve.
    """
    if not accepted_pairs or not rejected_pairs:
        return 0.0, None, None

    accepted_profiles = [
        _relationship_profile(accepted_call, accepted_response)
        for accepted_call, accepted_response in accepted_pairs
    ]
    rejected_profiles = [
        _relationship_profile(rejected_call, rejected_response)
        for rejected_call, rejected_response in rejected_pairs
    ]
    all_profiles = accepted_profiles + rejected_profiles

    scales = []
    for feature_index in range(2):
        values = [profile[feature_index] for profile in all_profiles]
        mean = sum(values) / len(values)
        variance = sum((value - mean) ** 2 for value in values) / len(values)
        scales.append(max(math.sqrt(variance), 0.1))

    candidate_profile = _relationship_profile(call, response)

    def distance(first, second):
        squared = sum(
            ((first[index] - second[index]) / scales[index]) ** 2
            for index in range(2)
        )
        return math.sqrt(squared / 2)

    nearest_da = min(
        distance(candidate_profile, profile) for profile in accepted_profiles
    )
    nearest_ne = min(
        distance(candidate_profile, profile) for profile in rejected_profiles
    )
    correction = PROFILE_ADJUSTMENT_WEIGHT * (
        (nearest_da - nearest_ne) / (nearest_da + nearest_ne + 1e-12)
    )
    return correction, nearest_da, nearest_ne


def _score_split_with_tempo(
    phrase_pitches,
    phrase_durations,
    split,
    avgtempo,
    incipit_k,
    alpha,
):
    """Osnovni DTW+incipit skor, sa duzim incipitom samo u brzom tempu."""
    call = phrase_pitches[:split]
    response = phrase_pitches[split:]
    global_score = _dtw_norm(call, response)

    effective_k = incipit_k
    if avgtempo is not None and avgtempo >= FAST_TEMPO_BPM:
        def notes_needed(durations):
            total_duration = 0.0
            for note_count, duration in enumerate(durations, start=1):
                total_duration += duration
                if (
                    note_count >= incipit_k
                    and total_duration >= MIN_THREE_NOTE_DURATION_SECONDS
                ):
                    return note_count
            return None

        call_k = notes_needed(phrase_durations[:split])
        response_k = notes_needed(phrase_durations[split:])
        if call_k is None or response_k is None:
            effective_k = None
        else:
            effective_k = max(call_k, response_k)

    if effective_k is None or min(len(call), len(response)) < effective_k:
        # Nema dovoljno nota da kratki incipit bude samostalan dokaz slicnosti.
        incipit_score = global_score
    else:
        incipit_score = incipit_similarity(call, response, k=effective_k)

    return alpha * global_score + (1 - alpha) * incipit_score


def _find_best_scored_split(
    phrase_pitches,
    phrase_durations,
    avgtempo,
    min_segment_len,
    incipit_k,
    alpha,
    accepted_pairs,
    rejected_pairs,
    preferred_split=None,
):
    """Izaberi najbolju podelu jedne zvanicne WJD fraze."""
    _split, _score, all_splits = find_best_internal_split(
        phrase_pitches,
        use_intervals=False,
        min_segment_len=min_segment_len,
        incipit_k=incipit_k,
        alpha=alpha,
    )
    base_scores = []
    for split, _original_base_score in all_splits:
        call = phrase_pitches[:split]
        response = phrase_pitches[split:]
        if len(response) < math.ceil(MIN_RESPONSE_CALL_RATIO * len(call)):
            continue
        base_score = _score_split_with_tempo(
            phrase_pitches,
            phrase_durations,
            split,
            avgtempo,
            incipit_k,
            alpha,
        )
        base_scores.append((base_score, split, call, response))

    best = None
    scores_by_split = {}
    for base_score, split, call, response in sorted(base_scores):
        # Ovo je najbolji moguci skor koji naredni kandidat moze dostici.
        if (
            best is not None
            and base_score - POSITIVE_REWARD_WEIGHT - PROFILE_ADJUSTMENT_WEIGHT
            >= best[7]
            and (preferred_split is None or preferred_split in scores_by_split)
        ):
            break
        penalty = _negative_example_penalty(call, response, rejected_pairs)
        reward = _positive_example_reward(call, response, accepted_pairs)
        profile_correction, nearest_da, nearest_ne = _profile_correction(
            call,
            response,
            accepted_pairs,
            rejected_pairs,
        )
        adjusted_score = max(
            0.0,
            base_score + penalty - reward + profile_correction,
        )
        split_scores = (
            base_score,
            penalty,
            reward,
            profile_correction,
            nearest_da,
            nearest_ne,
            adjusted_score,
        )
        scores_by_split[split] = split_scores
        if best is None or adjusted_score < best[7]:
            best = (split, *split_scores)

    # Rucno potvrđen DA ostaje na istoj tacki podele kroz nove iteracije.
    if preferred_split is not None and preferred_split in scores_by_split:
        best = (preferred_split, *scores_by_split[preferred_split])

    return best, scores_by_split


def search_wjd_phrases(
    search_items,
    db_path=DB_PATH,
    output_csv=OUTPUT_CSV,
    alpha=ALPHA,
    incipit_k=INCIPIT_K,
    threshold=THRESHOLD,
    review_threshold=REVIEW_THRESHOLD,
    min_segment_len=MIN_SEGMENT_LEN,
):
    """Obradi trazene soloe i vrati ``(found_pairs, summaries)``.

    Za svaku zvanicnu frazu bira se samo jedna najbolja tacka podele, a
    call i response zajedno pokrivaju celu frazu.
    Rezultat se prihvata samo kada je ``score < threshold``.
    """
    db_path = Path(db_path)
    output_csv = Path(output_csv)
    manual_labels, accepted_pairs, rejected_pairs, reviewed_rows = (
        _read_manual_feedback(output_csv)
    )
    found_pairs = []
    candidate_scores = {}
    summaries = []
    processed_melids = set()

    if not db_path.exists():
        raise FileNotFoundError(f"WJD baza nije pronadjena: {db_path}")
    if not 0 <= alpha <= 1:
        raise ValueError("alpha mora biti izmedju 0 i 1")
    if review_threshold < threshold:
        raise ValueError("review_threshold mora biti veci ili jednak threshold-u")
    if min_segment_len < 2 or incipit_k < 2:
        raise ValueError("min_segment_len i incipit_k moraju biti najmanje 2")

    conn = connect_db(str(db_path))
    try:
        for item in search_items:
            try:
                solo = _resolve_solo(conn, item)
            except Exception as error:
                print(f"[GRESKA] Ne mogu da pronadjem {item!r}: {error}; preskacem.")
                continue

            if solo is None:
                continue
            melid, title, performer, avgtempo = solo
            if melid in processed_melids:
                print(f"[INFO] melid={melid} je vec obradjen; preskacem duplikat.")
                continue
            processed_melids.add(melid)

            try:
                events = get_melody_events(conn, melid)
                sections = get_phrase_sections(conn, melid)
            except Exception as error:
                print(f"[GRESKA] Ne mogu da ucitam melid={melid}: {error}; preskacem.")
                continue

            pitches = [round(event[2]) for event in events]
            durations = [event[3] for event in events]
            found_for_song = 0
            review_for_song = 0
            skipped_short = 0
            failed_phrases = 0

            print(f"\n=== {title} — {performer} (melid={melid}) ===")
            print(f"Ukupno nota: {len(pitches)}; zvanicnih fraza: {len(sections)}")

            for phrase_index, (start, end, phrase_value) in enumerate(sections, start=1):
                if start < 0 or end < start or end >= len(pitches):
                    print(f"  [GRESKA] Fraza {phrase_value}: neispravne granice {start}-{end}.")
                    failed_phrases += 1
                    continue

                phrase_pitches = pitches[start:end + 1]  # WJD end je inkluzivan.
                phrase_durations = durations[start:end + 1]
                if len(phrase_pitches) < 2 * min_segment_len:
                    print(
                        f"  [PRESKOCENA] Fraza {phrase_value}: {len(phrase_pitches)} nota; "
                        f"potrebno je najmanje {2 * min_segment_len}."
                    )
                    skipped_short += 1
                    continue

                try:
                    preferred_split = next(
                        (
                            split
                            for split in range(
                                min_segment_len,
                                len(phrase_pitches) - min_segment_len + 1,
                            )
                            if manual_labels.get(
                                _candidate_key(melid, phrase_value, split)
                            ) == "DA"
                        ),
                        None,
                    )
                    best, scores_by_split = _find_best_scored_split(
                        phrase_pitches,
                        phrase_durations,
                        avgtempo,
                        min_segment_len=min_segment_len,
                        incipit_k=incipit_k,
                        alpha=alpha,
                        accepted_pairs=accepted_pairs,
                        rejected_pairs=rejected_pairs,
                        preferred_split=preferred_split,
                    )
                except Exception as error:
                    print(f"  [GRESKA] Fraza {phrase_value}: {error}; preskacem.")
                    failed_phrases += 1
                    continue

                for split, split_scores in scores_by_split.items():
                    (
                        base_score,
                        penalty,
                        reward,
                        profile_correction,
                        nearest_da,
                        nearest_ne,
                        adjusted_score,
                    ) = split_scores
                    candidate_scores[_candidate_key(melid, phrase_value, split)] = (
                        base_score,
                        penalty,
                        reward,
                        profile_correction,
                        nearest_da,
                        nearest_ne,
                        adjusted_score,
                    )

                if best is None:
                    print(f"  [PRESKOCENA] Fraza {phrase_value}: nema dozvoljene podele.")
                    skipped_short += 1
                    continue
                (
                    best_split,
                    best_base_score,
                    best_penalty,
                    best_reward,
                    best_profile_correction,
                    best_nearest_da,
                    best_nearest_ne,
                    best_score,
                ) = best
                if best_score >= review_threshold:
                    continue

                split = best_split
                score = best_score
                call_pitches = phrase_pitches[:split]
                response_pitches = phrase_pitches[split:]
                manual_label = manual_labels.get(
                    _candidate_key(melid, phrase_value, split), ""
                )
                if manual_label == "DA":
                    automatic_status = "CR"
                elif manual_label == "NE":
                    automatic_status = "ODBIJEN"
                else:
                    automatic_status = (
                        "CR" if score < threshold else "ZA_PREGLED"
                    )
                result = {
                    "validnost": manual_label,
                    "automatski_status": automatic_status,
                    "title": title,
                    "performer": performer,
                    "melid": melid,
                    "phrase_index": phrase_index,
                    "phrase_value": phrase_value,
                    "phrase_start_index": start,
                    "phrase_end_index_inclusive": end,
                    "split_point_local": split,
                    "split_point_solo": start + split,
                    "osnovni_skor": best_base_score,
                    "kazna_ne_primer": best_penalty,
                    "nagrada_da_primer": best_reward,
                    "profil_korekcija": best_profile_correction,
                    "profil_da_udaljenost": best_nearest_da,
                    "profil_ne_udaljenost": best_nearest_ne,
                    "score": score,
                    "phrase_start_seconds": events[start][1],
                    "call_start_seconds": events[start][1],
                    "response_start_seconds": events[start + split][1],
                    "phrase_end_seconds": events[end][1] + events[end][3],
                    "call_pitches": call_pitches,
                    "response_pitches": response_pitches,
                    "excerpt_midi": "",
                }
                found_pairs.append(result)
                if automatic_status == "CR":
                    found_for_song += 1
                    print_label = "POTVRDJEN CR" if manual_label == "DA" else "CR"
                elif automatic_status == "ZA_PREGLED":
                    review_for_song += 1
                    print_label = "ZA PREGLED"
                else:
                    print_label = "ODBIJEN"

                print(
                    f"  [{print_label}] Fraza {phrase_value}: "
                    f"split={split}, score={score:.4f}"
                )
                print(f"       CALL:     {call_pitches}")
                print(f"       RESPONSE: {response_pitches}")

            summaries.append({
                "title": title,
                "performer": performer,
                "melid": melid,
                "phrase_count": len(sections),
                "found_count": found_for_song,
                "review_count": review_for_song,
                "skipped_short": skipped_short,
                "failed_phrases": failed_phrases,
            })
    finally:
        conn.close()

    output_csv.parent.mkdir(parents=True, exist_ok=True)
    results_to_write = list(found_pairs)
    current_keys = {
        _candidate_key(result["melid"], result["phrase_value"], result["split_point_local"])
        for result in found_pairs
    }
    for key, row in reviewed_rows.items():
        if key not in current_keys:
            if key in candidate_scores:
                (
                    base_score,
                    penalty,
                    reward,
                    profile_correction,
                    nearest_da,
                    nearest_ne,
                    adjusted_score,
                ) = candidate_scores[key]
                row["osnovni_skor"] = base_score
                row["kazna_ne_primer"] = penalty
                row["nagrada_da_primer"] = reward
                row["profil_korekcija"] = profile_correction
                row["profil_da_udaljenost"] = nearest_da
                row["profil_ne_udaljenost"] = nearest_ne
                row["score"] = adjusted_score
            results_to_write.append(row)

    columns = [
        "validnost", "automatski_status",
        "title", "performer", "melid", "phrase_index", "phrase_value",
        "phrase_start_index", "phrase_end_index_inclusive",
        "split_point_local", "split_point_solo", "osnovni_skor",
        "kazna_ne_primer", "nagrada_da_primer",
        "profil_korekcija", "profil_da_udaljenost", "profil_ne_udaljenost",
        "score",
        "phrase_start_seconds", "call_start_seconds", "response_start_seconds",
        "phrase_end_seconds", "excerpt_midi",
        "call_pitches", "response_pitches",
    ]
    with output_csv.open("w", encoding="utf-8-sig", newline="") as stream:
        writer = csv.DictWriter(stream, fieldnames=columns, extrasaction="ignore")
        writer.writeheader()
        for result in results_to_write:
            row = dict(result)
            if isinstance(row["call_pitches"], list):
                row["call_pitches"] = json.dumps(row["call_pitches"])
            if isinstance(row["response_pitches"], list):
                row["response_pitches"] = json.dumps(row["response_pitches"])
            writer.writerow(row)

    print("\n================ SUMARNI IZVESTAJ ================")
    if not summaries:
        print("Nijedan solo nije obradjen.")
    for summary in summaries:
        print(
            f"{summary['title']} (melid={summary['melid']}): "
            f"{summary['found_count']} CR + {summary['review_count']} za pregled "
            f"/ {summary['phrase_count']} fraza"
        )
    accepted_results = [
        result for result in found_pairs if result["automatski_status"] == "CR"
    ]
    review_results = [
        result
        for result in found_pairs
        if result["automatski_status"] == "ZA_PREGLED"
    ]
    print(f"Automatski CR: {len(accepted_results)}")
    print(f"Za rucni pregled: {len(review_results)}")
    if review_results:
        print("Novi kandidati za pregled:")
        for result in review_results:
            print(
                f"  - {result['title']}, fraza {result['phrase_value']}, "
                f"split={result['split_point_local']}, score={result['score']:.4f}"
            )
    print(f"CSV sacuvan u: {output_csv}")

    return found_pairs, summaries


if __name__ == "__main__":
    search_wjd_phrases(SEARCH_ITEMS)
