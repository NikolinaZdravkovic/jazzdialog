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

# Nova podela cele fraze mora imati veoma jasan pocetak call-a i response-a.
# Pozitivne reference koriste se odvojeno, u kontrolisanoj pretrazi prozora.
STRONG_INCIPIT_LIMIT = 0.25

# Dodatna, kontrolisana pretraga unutrasnjih susednih delova. Duzine prozora
# moraju vec postojati u rucnoj Excel anotaciji; zato se ne isprobavaju sve
# cetiri granice i pretraga ne eksplodira kombinatorno.
INTERNAL_REFERENCE_LIMIT = 0.30
INTERNAL_APPROX_MIN_NOTES = 6
INTERNAL_MIN_RESPONSE_CALL_RATIO = 0.65
INTERNAL_MAX_RESPONSE_CALL_RATIO = 2.50
INTERNAL_NMS_IOU = 0.50

# U veoma brzom tempu tri kratke note nisu dovoljan incipit dokaz.
FAST_TEMPO_BPM = 215.0
MIN_THREE_NOTE_DURATION_SECONDS = 0.75

PROJECT_ROOT = Path(__file__).resolve().parents[1]
DB_PATH = PROJECT_ROOT / "data_midi" / "wjazzd.db"
OUTPUT_CSV = PROJECT_ROOT / "output" / "wjd_phrase_call_response.csv"


# Pitch nizovi iz pocetne rucne Excel tabele jazzdialog3(4).xlsx.
# Redovi bez oktava i nedovrseni red nisu ukljuceni. Ove reference su samo
# pozitivan dokaz; osnovni skor i dalje racunaju globalni DTW + incipit.
MANUAL_REFERENCE_PAIRS = [
    ([78, 76, 81, 76], [81, 76, 78, 81, 76, 75, 76, 74, 73]),
    ([74, 76], [73, 76, 77, 78, 73, 76, 74]),
    ([84, 82, 84, 77, 81, 82, 84], [77, 80, 77, 82, 80, 84, 77]),
    ([76, 74, 71, 72, 75], [73, 74, 71, 72, 68]),
    ([62, 63, 59, 62, 60, 63, 59, 62], [60, 63, 65, 62, 64, 65, 64, 63, 62]),
    ([65, 67, 68, 70, 67, 63, 60], [69, 70, 66, 66, 63, 58]),
    ([77, 79, 80, 77, 79, 72, 77], [77, 79, 79, 80, 77, 79, 77, 73]),
    ([84, 72, 80, 77, 80, 80, 80, 80, 76, 72, 80, 76],
     [80, 77, 80, 80, 79, 77, 76, 77, 79, 80, 77]),
    ([72, 71, 68, 65, 68, 70, 64, 67, 69, 70, 72, 76, 72, 69],
     [71, 72, 71, 68, 64, 67, 65]),
    ([64, 67, 69, 71, 64, 67, 69, 70],
     [64, 67, 69, 69, 70, 69, 67, 65, 67, 65, 63, 58, 60, 62, 64, 66]),
    ([76, 74, 71, 69, 67, 69, 66, 67, 67, 69, 66, 67, 69, 71, 67, 69],
     [74, 71, 74, 71, 69, 67, 59, 63, 57, 59, 59]),
    ([64, 67, 65, 69, 64], [79, 77, 81, 81, 79, 76, 73, 77, 74, 74]),
    ([70, 73, 74, 70, 67, 63, 67, 70, 71, 72, 69, 65, 62, 65, 69, 69, 70],
     [70, 67, 63, 60, 62, 64, 65, 66, 69, 66, 64, 57]),
    ([71, 72, 75, 79, 80, 79, 80, 80, 79, 80, 79, 80, 70, 72, 75, 79,
      80, 75, 79, 80, 80, 79, 80, 79, 80],
     [71, 72, 79, 80, 79, 80, 79, 80, 79, 79, 80, 79, 77, 76, 75, 73,
      72, 70, 69, 78, 76, 77, 74, 70, 68, 72]),
    ([79, 75, 67, 69, 74, 67, 68, 72],
     [66, 69, 75, 67, 69, 74, 72, 67, 63, 67, 60, 63, 64, 66, 68, 69,
      70, 72, 67, 65, 68, 65]),
    ([67, 65, 67, 65, 67, 65, 67, 65, 67, 65, 68, 65, 68, 65],
     [67, 65, 67, 65, 67, 65, 76, 74, 76, 74]),
]

# Brojevi redova iz pocetne Excel tabele, istim redosledom kao parovi iznad.
MANUAL_REFERENCE_IDS = [1, 3, 4, 5, 9, 10, 11, 12, 13, 14, 15, 16, 17, 18, 19, 20]


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


def _candidate_key(melid, phrase_value, split, call_start=0, response_end=""):
    """Jedinstveni kljuc ukljucuje sve tri granice kandidata."""
    return (
        str(melid),
        str(phrase_value),
        str(call_start),
        str(split),
        str(response_end),
    )


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
            label = row.get("validnost", "").strip().upper()
            if label not in {"DA", "NE"}:
                continue
            row["call_pitches"] = json.loads(row["call_pitches"])
            row["response_pitches"] = json.loads(row["response_pitches"])
            call_start = int(row.get("call_start_local") or 0)
            split = int(row.get("split_point_local") or len(row["call_pitches"]))
            response_end = int(
                row.get("response_end_local_exclusive")
                or split + len(row["response_pitches"])
            )
            key = _candidate_key(
                row.get("melid", ""),
                row.get("phrase_value", ""),
                split,
                call_start,
                response_end,
            )
            labels[key] = label
            row["validnost"] = label
            row["automatski_status"] = "CR" if label == "DA" else "ODBIJEN"
            if row.get("candidate_source") in {None, "", "cela_fraza"}:
                row["candidate_source"] = "cela_WJD_fraza"
            row["decision_reason"] = row.get("decision_reason") or (
                "rucna_oznaka_DA" if label == "DA" else "rucna_oznaka_NE"
            )
            # Stariji CSV redovi mogu sadrzati napustenu pozitivnu nagradu.
            # U aktuelnom sistemu score je osnovni skor + eventualna NE kazna.
            try:
                row["nagrada_da_primer"] = 0.0
                row["score"] = float(row.get("osnovni_skor") or 0.0) + float(
                    row.get("kazna_ne_primer") or 0.0
                )
            except (TypeError, ValueError):
                pass
            row["manual_reference_id"] = row.get("manual_reference_id", "")
            row["call_start_local"] = call_start
            row["response_end_local_exclusive"] = response_end
            row["call_start_solo"] = row.get("call_start_solo") or (
                int(row.get("phrase_start_index") or 0) + call_start
            )
            row["response_end_solo_inclusive"] = row.get(
                "response_end_solo_inclusive"
            ) or (
                int(row.get("phrase_start_index") or 0) + response_end - 1
            )
            row["reference_distance"] = row.get("reference_distance", "")
            row["response_end_seconds"] = row.get("response_end_seconds") or row.get(
                "phrase_end_seconds", ""
            )
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


def _unique_pairs(pairs):
    """Ukloni duple rucne reference bez menjanja redosleda."""
    unique = []
    seen = set()
    for call, response in pairs:
        key = tuple(call), tuple(response)
        if key in seen:
            continue
        seen.add(key)
        unique.append((call, response))
    return unique


def _nearest_pair_distance(call, response, reference_pairs):
    """Udaljenost kandidata od najslicnijeg rucno potvrđenog para."""
    if not reference_pairs:
        return float("inf")
    nearest = float("inf")
    for reference_call, reference_response in reference_pairs:
        distance = (
            _transposition_aware_distance(call, reference_call)
            + _transposition_aware_distance(response, reference_response)
        ) / 2
        nearest = min(nearest, distance)
        if nearest == 0.0:
            break
    return nearest


def _manual_reference_variants():
    """Vrati dozvoljene sablone, ukljucujuci poznatu vezanu granicnu notu."""
    for reference_id, (call, response) in zip(
        MANUAL_REFERENCE_IDS, MANUAL_REFERENCE_PAIRS
    ):
        yield reference_id, call, response, "normalna_granica"
        # U rucnom paru 17 ista vezana nota je zapisana na obe strane granice.
        # MIDI nota moze pripadati samo jednom segmentu, pa je dodeljujemo response-u.
        if reference_id == 17:
            yield reference_id, call[:-1], response, "vezana_granica"


def _window_iou(first, second):
    """Presek kroz uniju dva [start, end) prozora."""
    intersection = max(0, min(first[1], second[1]) - max(first[0], second[0]))
    union = max(first[1], second[1]) - min(first[0], second[0])
    return intersection / union if union else 0.0


def _find_internal_reference_candidates(phrase_pitches):
    """Nadji unutrasnje susedne prozore nalik rucnim Excel parovima.

    Broj prozora je O(R*n); DTW svakog prozora dodaje faktor L^2, gde je L
    duzina sablona. Ovde su R i L mali i fiksirani rucnom tabelom.
    Prvo se prihvataju tacne apsolutne kopije rucnih parova. Priblizni
    kandidati moraju biti dovoljno dugi i uravnotezeni i ostaju za pregled.
    """
    raw = []
    n = len(phrase_pitches)
    for reference_id, ref_call, ref_response, boundary_kind in (
        _manual_reference_variants()
    ):
        call_len = len(ref_call)
        response_len = len(ref_response)
        window_len = call_len + response_len
        if call_len < MIN_SEGMENT_LEN or response_len < MIN_SEGMENT_LEN:
            continue
        if window_len > n:
            continue

        ratio = response_len / call_len
        approximate_length_allowed = (
            call_len >= INTERNAL_APPROX_MIN_NOTES
            and response_len >= INTERNAL_APPROX_MIN_NOTES
            and INTERNAL_MIN_RESPONSE_CALL_RATIO
            <= ratio
            <= INTERNAL_MAX_RESPONSE_CALL_RATIO
        )
        for call_start in range(0, n - window_len + 1):
            split = call_start + call_len
            response_end = split + response_len
            call = phrase_pitches[call_start:split]
            response = phrase_pitches[split:response_end]
            exact = call == ref_call and response == ref_response
            if exact:
                reference_distance = 0.0
            elif approximate_length_allowed:
                reference_distance = (
                    _transposition_aware_distance(call, ref_call)
                    + _transposition_aware_distance(response, ref_response)
                ) / 2
                if reference_distance >= INTERNAL_REFERENCE_LIMIT:
                    continue
            else:
                continue

            raw.append({
                "call_start": call_start,
                "split": split,
                "response_end": response_end,
                "call": call,
                "response": response,
                "reference_id": reference_id,
                "reference_distance": reference_distance,
                "exact": exact,
                "boundary_kind": boundary_kind,
            })

    # Non-max suppression uklanja skoro iste rezultate pomerene za 1-2 note.
    kept = []
    for candidate in sorted(
        raw,
        key=lambda item: (
            not item["exact"],
            item["reference_distance"],
            item["call_start"],
        ),
    ):
        window = (candidate["call_start"], candidate["response_end"])
        if any(
            _window_iou(window, (old["call_start"], old["response_end"]))
            >= INTERNAL_NMS_IOU
            for old in kept
        ):
            continue
        kept.append(candidate)
    return kept


def _incipit_score_with_tempo(
    phrase_pitches,
    phrase_durations,
    split,
    avgtempo,
    incipit_k,
):
    """Incipt skor, sa vise nota kada su tempo i note veoma brzi."""
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

    return incipit_score


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
    incipit_score = _incipit_score_with_tempo(
        phrase_pitches,
        phrase_durations,
        split,
        avgtempo,
        incipit_k,
    )
    return alpha * global_score + (1 - alpha) * incipit_score


def _find_best_scored_split(
    phrase_pitches,
    phrase_durations,
    avgtempo,
    min_segment_len,
    incipit_k,
    alpha,
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
        incipit_evidence = _incipit_score_with_tempo(
            phrase_pitches,
            phrase_durations,
            split,
            avgtempo,
            incipit_k,
        )
        if (
            split != preferred_split
            and incipit_evidence > STRONG_INCIPIT_LIMIT
        ):
            continue
        base_score = _score_split_with_tempo(
            phrase_pitches,
            phrase_durations,
            split,
            avgtempo,
            incipit_k,
            alpha,
        )
        base_scores.append(
            (
                base_score,
                split,
                call,
                response,
                incipit_evidence,
            )
        )

    best = None
    scores_by_split = {}
    for (
        base_score,
        split,
        call,
        response,
        incipit_evidence,
    ) in sorted(base_scores):
        penalty = _negative_example_penalty(call, response, rejected_pairs)
        reward = 0.0
        nearest_positive = float("inf")
        adjusted_score = base_score + penalty
        split_scores = (
            base_score,
            penalty,
            reward,
            incipit_evidence,
            nearest_positive,
            adjusted_score,
        )
        scores_by_split[split] = split_scores
        if best is None or adjusted_score < best[6]:
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

    Osnovna pretraga bira jednu podelu cele WJD fraze. Dodatna pretraga
    proverava samo unutrasnje susedne prozore cije duzine vec postoje u
    rucnoj Excel anotaciji. Tacni Excel parovi su potvrđeni, a slicni parovi
    se nikada ne prihvataju automatski vec ostaju za rucni pregled.
    """
    db_path = Path(db_path)
    output_csv = Path(output_csv)
    manual_labels, accepted_pairs, rejected_pairs, reviewed_rows = (
        _read_manual_feedback(output_csv)
    )
    found_pairs = []
    found_by_key = {}
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

                # 1) Stabilna osnovna pretraga: call + response = cela fraza.
                if len(phrase_pitches) >= 2 * min_segment_len:
                    try:
                        preferred_split = next(
                            (
                                split
                                for split in range(
                                    min_segment_len,
                                    len(phrase_pitches) - min_segment_len + 1,
                                )
                                if manual_labels.get(
                                    _candidate_key(
                                        melid,
                                        phrase_value,
                                        split,
                                        0,
                                        len(phrase_pitches),
                                    )
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
                            rejected_pairs=rejected_pairs,
                            preferred_split=preferred_split,
                        )
                    except Exception as error:
                        print(f"  [GRESKA] Fraza {phrase_value}: {error}; preskacem.")
                        failed_phrases += 1
                        best = None
                        scores_by_split = {}

                    for split, split_scores in scores_by_split.items():
                        (
                            base_score,
                            penalty,
                            reward,
                            incipit_evidence,
                            nearest_positive,
                            adjusted_score,
                        ) = split_scores
                        key = _candidate_key(
                            melid, phrase_value, split, 0, len(phrase_pitches)
                        )
                        candidate_scores[key] = {
                            "osnovni_skor": base_score,
                            "kazna_ne_primer": penalty,
                            "nagrada_da_primer": reward,
                            "incipit_dokaz": incipit_evidence,
                            "najblizi_da_primer": nearest_positive,
                            "score": adjusted_score,
                        }

                    if best is None:
                        print(
                            f"  [PRESKOCENA] Fraza {phrase_value}: "
                            "nema dozvoljene podele cele fraze."
                        )
                    else:
                        (
                            split,
                            base_score,
                            penalty,
                            reward,
                            incipit_evidence,
                            nearest_positive,
                            score,
                        ) = best
                        key = _candidate_key(
                            melid, phrase_value, split, 0, len(phrase_pitches)
                        )
                        manual_label = manual_labels.get(key, "")
                        if score < review_threshold or manual_label == "DA":
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
                                "candidate_source": "cela_WJD_fraza",
                                "decision_reason": (
                                    "rucna_oznaka_DA"
                                    if manual_label == "DA"
                                    else "rucna_oznaka_NE"
                                    if manual_label == "NE"
                                    else "osnovni_skor_ispod_praga"
                                    if automatic_status == "CR"
                                    else "osnovni_skor_za_pregled"
                                ),
                                "manual_reference_id": "",
                                "title": title,
                                "performer": performer,
                                "melid": melid,
                                "phrase_index": phrase_index,
                                "phrase_value": phrase_value,
                                "phrase_start_index": start,
                                "phrase_end_index_inclusive": end,
                                "call_start_local": 0,
                                "split_point_local": split,
                                "response_end_local_exclusive": len(phrase_pitches),
                                "call_start_solo": start,
                                "split_point_solo": start + split,
                                "response_end_solo_inclusive": end,
                                "osnovni_skor": base_score,
                                "kazna_ne_primer": penalty,
                                "nagrada_da_primer": reward,
                                "incipit_dokaz": incipit_evidence,
                                "najblizi_da_primer": nearest_positive,
                                "reference_distance": "",
                                "score": score,
                                "phrase_start_seconds": events[start][1],
                                "call_start_seconds": events[start][1],
                                "response_start_seconds": events[start + split][1],
                                "response_end_seconds": events[end][1] + events[end][3],
                                "phrase_end_seconds": events[end][1] + events[end][3],
                                "call_pitches": phrase_pitches[:split],
                                "response_pitches": phrase_pitches[split:],
                                "excerpt_midi": "",
                            }
                            found_pairs.append(result)
                            found_by_key[key] = result
                else:
                    print(
                        f"  [PRESKOCENA] Fraza {phrase_value}: {len(phrase_pitches)} nota; "
                        f"cela fraza trazi najmanje {2 * min_segment_len}."
                    )
                    skipped_short += 1

                # 2) Kontrolisana unutrasnja pretraga prema rucnim sablonima.
                phrase_negative_count = sum(
                    1
                    for key, label in manual_labels.items()
                    if key[0] == str(melid)
                    and key[1] == str(phrase_value)
                    and label == "NE"
                )
                try:
                    internal_candidates = _find_internal_reference_candidates(
                        phrase_pitches
                    )
                except Exception as error:
                    print(
                        f"  [GRESKA] Unutrasnja pretraga fraze {phrase_value}: "
                        f"{error}; preskacem."
                    )
                    failed_phrases += 1
                    internal_candidates = []

                for candidate in internal_candidates:
                    if not candidate["exact"] and phrase_negative_count >= 2:
                        continue
                    call_start = candidate["call_start"]
                    split = candidate["split"]
                    response_end = candidate["response_end"]
                    key = _candidate_key(
                        melid, phrase_value, split, call_start, response_end
                    )
                    window_pitches = phrase_pitches[call_start:response_end]
                    window_durations = phrase_durations[call_start:response_end]
                    split_in_window = split - call_start
                    call = candidate["call"]
                    response = candidate["response"]
                    base_score = _score_split_with_tempo(
                        window_pitches,
                        window_durations,
                        split_in_window,
                        avgtempo,
                        incipit_k,
                        alpha,
                    )
                    incipit_evidence = _incipit_score_with_tempo(
                        window_pitches,
                        window_durations,
                        split_in_window,
                        avgtempo,
                        incipit_k,
                    )
                    penalty = _negative_example_penalty(call, response, rejected_pairs)
                    positive_references = _unique_pairs(
                        list(accepted_pairs) + MANUAL_REFERENCE_PAIRS
                    )
                    nearest_positive = _nearest_pair_distance(
                        call, response, positive_references
                    )
                    # Referentna udaljenost odlucuje da li se prozor prikazuje,
                    # ali ne obara osnovni CR skor. Tako skor ostaje citljiv.
                    reward = 0.0
                    score = base_score + penalty
                    candidate_scores[key] = {
                        "osnovni_skor": base_score,
                        "kazna_ne_primer": penalty,
                        "nagrada_da_primer": reward,
                        "incipit_dokaz": incipit_evidence,
                        "najblizi_da_primer": nearest_positive,
                        "reference_distance": candidate["reference_distance"],
                        "score": score,
                    }

                    manual_label = manual_labels.get(key, "")
                    if manual_label == "DA":
                        automatic_status = "CR"
                        decision_reason = "rucna_oznaka_DA"
                    elif manual_label == "NE":
                        automatic_status = "ODBIJEN"
                        decision_reason = "rucna_oznaka_NE"
                    elif candidate["exact"]:
                        # Ovo nije automatska pretpostavka: par je vec oznacen
                        # kao validan u korisnikovoj pocetnoj Excel anotaciji.
                        manual_label = "DA"
                        automatic_status = "CR"
                        decision_reason = "tacan_par_iz_pocetne_Excel_tabele"
                    else:
                        automatic_status = "ZA_PREGLED"
                        decision_reason = "slican_rucnom_paru_obavezan_pregled"

                    source = (
                        "rucna_referenca_tacna"
                        if candidate["exact"]
                        else "slicna_rucnoj_referenci"
                    )
                    if key in found_by_key:
                        existing = found_by_key[key]
                        existing["candidate_source"] += "+" + source
                        existing["manual_reference_id"] = candidate["reference_id"]
                        existing["reference_distance"] = candidate[
                            "reference_distance"
                        ]
                        if manual_label:
                            existing["validnost"] = manual_label
                            existing["automatski_status"] = automatic_status
                            existing["decision_reason"] = decision_reason
                        continue

                    response_last = start + response_end - 1
                    result = {
                        "validnost": manual_label,
                        "automatski_status": automatic_status,
                        "candidate_source": source,
                        "decision_reason": decision_reason,
                        "manual_reference_id": candidate["reference_id"],
                        "title": title,
                        "performer": performer,
                        "melid": melid,
                        "phrase_index": phrase_index,
                        "phrase_value": phrase_value,
                        "phrase_start_index": start,
                        "phrase_end_index_inclusive": end,
                        "call_start_local": call_start,
                        "split_point_local": split,
                        "response_end_local_exclusive": response_end,
                        "call_start_solo": start + call_start,
                        "split_point_solo": start + split,
                        "response_end_solo_inclusive": response_last,
                        "osnovni_skor": base_score,
                        "kazna_ne_primer": penalty,
                        "nagrada_da_primer": reward,
                        "incipit_dokaz": incipit_evidence,
                        "najblizi_da_primer": nearest_positive,
                        "reference_distance": candidate["reference_distance"],
                        "score": score,
                        "phrase_start_seconds": events[start][1],
                        "call_start_seconds": events[start + call_start][1],
                        "response_start_seconds": events[start + split][1],
                        "response_end_seconds": (
                            events[response_last][1] + events[response_last][3]
                        ),
                        "phrase_end_seconds": events[end][1] + events[end][3],
                        "call_pitches": call,
                        "response_pitches": response,
                        "excerpt_midi": "",
                    }
                    found_pairs.append(result)
                    found_by_key[key] = result

            song_results = [
                result for result in found_pairs if result["melid"] == melid
            ]
            found_for_song = sum(
                result["automatski_status"] == "CR" for result in song_results
            )
            review_for_song = sum(
                result["automatski_status"] == "ZA_PREGLED"
                for result in song_results
            )
            for result in song_results:
                status = result["automatski_status"]
                if status == "CR":
                    print_label = (
                        "POTVRDJEN CR" if result["validnost"] == "DA" else "CR"
                    )
                elif status == "ZA_PREGLED":
                    print_label = "ZA PREGLED"
                else:
                    print_label = "ODBIJEN"
                print(
                    f"  [{print_label}] Fraza {result['phrase_value']}: "
                    f"granice={result['call_start_local']}:"
                    f"{result['split_point_local']}:"
                    f"{result['response_end_local_exclusive']}, "
                    f"score={float(result['score']):.4f}"
                )

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
        _candidate_key(
            result["melid"],
            result["phrase_value"],
            result["split_point_local"],
            result["call_start_local"],
            result["response_end_local_exclusive"],
        )
        for result in found_pairs
    }
    for key, row in reviewed_rows.items():
        if key not in current_keys:
            if key in candidate_scores:
                row.update(candidate_scores[key])
            results_to_write.append(row)

    columns = [
        "validnost", "automatski_status",
        "candidate_source", "decision_reason", "manual_reference_id",
        "title", "performer", "melid", "phrase_index", "phrase_value",
        "phrase_start_index", "phrase_end_index_inclusive",
        "call_start_local", "split_point_local", "response_end_local_exclusive",
        "call_start_solo", "split_point_solo", "response_end_solo_inclusive",
        "osnovni_skor",
        "kazna_ne_primer", "nagrada_da_primer",
        "incipit_dokaz", "najblizi_da_primer",
        "reference_distance", "score",
        "phrase_start_seconds", "call_start_seconds", "response_start_seconds",
        "response_end_seconds", "phrase_end_seconds", "excerpt_midi",
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
                f"granice={result['call_start_local']}:"
                f"{result['split_point_local']}:"
                f"{result['response_end_local_exclusive']}, "
                f"score={result['score']:.4f}"
            )
    print(f"CSV sacuvan u: {output_csv}")

    return found_pairs, summaries


if __name__ == "__main__":
    search_wjd_phrases(SEARCH_ITEMS)
