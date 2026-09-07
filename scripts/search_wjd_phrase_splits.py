"""Pronadji call-response parove unutar zvanicnih WJD fraza vise sola."""

import csv
import json
import math
import re
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
        incipit_similarity,
    )
except ImportError:  # Kada se pokrene direktno iz komandne linije
    from extract_wjd_phrases import (
        connect_db,
        find_melid_by_title,
        get_melody_events,
        get_phrase_sections,
    )
    from find_internal_split import _dtw_norm, incipit_similarity


# ---------------------------------------------------------------------------
# PODESAVANJA: menjaj samo ovaj mali blok.
# Stavke mogu biti nazivi pesama ili melid brojevi.
# ---------------------------------------------------------------------------
SEARCH_ITEMS = [
    16,17,18,19,20
]

INCIPIT_K = 5
THRESHOLD = 0.20
REVIEW_THRESHOLD = 0.30
MIN_SEGMENT_LEN = 5

# Novi kandidat mora imati dva dovoljno uravnotezena pitch niza.
MIN_RESPONSE_CALL_RATIO = 0.75
MAX_RESPONSE_CALL_RATIO = 2.00
# Rucno odbijen kandidat dobija najvise ovoliku dodatnu kaznu.
# Skor je distanca, zato veci skor znaci manju verovatnocu izbora.
NEGATIVE_PENALTY_WEIGHT = 0.20
NEGATIVE_SIMILARITY_LIMIT = 0.30

PROJECT_ROOT = Path(__file__).resolve().parents[1]
DB_PATH = PROJECT_ROOT / "data_midi" / "wjazzd.db"
OUTPUT_CSV = PROJECT_ROOT / "output" / "wjd_phrase_call_response.csv"
EXCERPT_DIR = PROJECT_ROOT / "output" / "wjd_phrase_excerpts"


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
    """Ucitaj postojece redove i zapamti DA/NE pitch parove."""
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
            # I nepregledani redovi moraju ostati u CSV-u kada se sledeci put
            # pokrene druga grupa pesama.
            reviewed_rows[key] = row
            if label not in {"DA", "NE"}:
                continue
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


def _excerpt_filename(result):
    """Napravi stabilno ime koje direktno pokazuje tri granice kandidata."""
    phrase_value = re.sub(r"[^A-Za-z0-9_-]+", "_", str(result["phrase_value"]))
    call_start = int(result["call_start_local"])
    split = int(result["split_point_local"])
    response_end = int(result["response_end_local_exclusive"])
    phrase_len = (
        int(result["phrase_end_index_inclusive"])
        - int(result["phrase_start_index"])
        + 1
    )
    if call_start == 0 and response_end == phrase_len:
        return (
            f"melid_{result['melid']}_phrase_{phrase_value}_split_{split}.mid"
        )
    return (
        f"melid_{result['melid']}_phrase_{phrase_value}_"
        f"start_{call_start}_split_{split}_end_{response_end}.mid"
    )


def _write_excerpt_midi(events, result, excerpt_dir):
    """Sacuvaj jedan kandidat kao MIDI, uz originalni tajming iz WJD baze."""
    import pretty_midi

    call_start = int(result["call_start_solo"])
    split = int(result["split_point_solo"])
    response_last = int(result["response_end_solo_inclusive"])
    if not (0 <= call_start < split <= response_last < len(events)):
        raise ValueError(
            f"neispravne solo granice {call_start}:{split}:{response_last + 1}"
        )

    excerpt_dir.mkdir(parents=True, exist_ok=True)
    output_path = excerpt_dir / _excerpt_filename(result)
    excerpt_start = float(events[call_start][1])

    midi = pretty_midi.PrettyMIDI(initial_tempo=120.0)
    call_track = pretty_midi.Instrument(program=0, name="CALL")
    response_track = pretty_midi.Instrument(program=0, name="RESPONSE")

    for event_index in range(call_start, response_last + 1):
        _eventid, onset, pitch, duration = events[event_index]
        note = pretty_midi.Note(
            velocity=100,
            pitch=int(round(pitch)),
            start=max(0.0, float(onset) - excerpt_start),
            end=max(0.001, float(onset) - excerpt_start + float(duration)),
        )
        if event_index < split:
            call_track.notes.append(note)
        else:
            response_track.notes.append(note)

    midi.instruments.extend([call_track, response_track])
    response_time = max(0.0, float(events[split][1]) - excerpt_start)
    midi.lyrics.append(pretty_midi.Lyric(text="CALL", time=0.0))
    midi.lyrics.append(pretty_midi.Lyric(text="RESPONSE", time=response_time))
    midi.write(str(output_path))
    return output_path.resolve()


def _export_result_midis(db_path, results, excerpt_dir=EXCERPT_DIR):
    """Generisi ili osvezi MIDI za svaki red koji ce biti upisan u CSV."""
    events_by_melid = {}
    written = 0
    conn = connect_db(str(db_path))
    try:
        for result in results:
            try:
                melid = int(result["melid"])
                if melid not in events_by_melid:
                    events_by_melid[melid] = get_melody_events(conn, melid)
                path = _write_excerpt_midi(
                    events_by_melid[melid], result, Path(excerpt_dir)
                )
                result["excerpt_midi"] = str(path)
                written += 1
            except Exception as error:
                existing_path = Path(excerpt_dir) / _excerpt_filename(result)
                if existing_path.exists():
                    result["excerpt_midi"] = str(existing_path.resolve())
                print(
                    f"[UPOZORENJE] MIDI nije sacuvan za melid="
                    f"{result.get('melid')}, frazu {result.get('phrase_value')}: "
                    f"{error}"
                )
    finally:
        conn.close()
    return written


def _incipit_score_with_tempo(
    phrase_pitches,
    phrase_durations,
    split,
    avgtempo,
    incipit_k,
):
    """Incipt dijagnostika; ne utice na izbor podele niti na prag."""
    call = phrase_pitches[:split]
    response = phrase_pitches[split:]
    return incipit_similarity(call, response, k=incipit_k)


def _find_best_scored_split(
    phrase_pitches,
    phrase_durations,
    avgtempo,
    min_segment_len,
    incipit_k,
    rejected_pairs,
    preferred_split=None,
):
    """Izaberi podelu sa najmanjim globalnim DTW-om celih pitch nizova."""
    candidates = []
    n = len(phrase_pitches)
    for split in range(min_segment_len, n - min_segment_len + 1):
        call = phrase_pitches[:split]
        response = phrase_pitches[split:]
        length_ratio = len(response) / len(call)
        if split != preferred_split and (
            length_ratio < MIN_RESPONSE_CALL_RATIO
            or length_ratio > MAX_RESPONSE_CALL_RATIO
        ):
            continue
        global_dtw = _dtw_norm(call, response)
        incipit_evidence = _incipit_score_with_tempo(
            phrase_pitches,
            phrase_durations,
            split,
            avgtempo,
            incipit_k,
        )
        candidates.append((global_dtw, split, call, response, incipit_evidence))

    scores_by_split = {}
    for global_dtw, split, call, response, incipit_evidence in candidates:
        penalty = _negative_example_penalty(call, response, rejected_pairs)
        reward = 0.0
        nearest_positive = float("inf")
        adjusted_score = global_dtw + penalty
        split_scores = (
            global_dtw,
            penalty,
            reward,
            incipit_evidence,
            nearest_positive,
            adjusted_score,
        )
        scores_by_split[split] = split_scores

    if not candidates:
        return None, scores_by_split, float("inf"), float("inf")

    # Sama tacka podele dolazi iz globalnog DTW-a. NE kazna menja samo
    # poverenje u rezultat, ne pomera muzicku granicu na drugu tacku.
    ranked = sorted(candidates, key=lambda item: (item[0], item[1]))
    chosen = ranked[0]
    if preferred_split is not None:
        chosen = next(
            (candidate for candidate in candidates if candidate[1] == preferred_split),
            chosen,
        )
    global_dtw, split, _call, _response, _incipit = chosen
    best = (split, *scores_by_split[split])

    second_dtw = next(
        (candidate[0] for candidate in ranked if candidate[1] != split),
        float("inf"),
    )
    dtw_gap = second_dtw - global_dtw
    relative_dtw_gap = (
        dtw_gap / global_dtw
        if global_dtw > 0 and math.isfinite(second_dtw)
        else float("inf")
    )

    return best, scores_by_split, dtw_gap, relative_dtw_gap


def search_wjd_phrases(
    search_items,
    db_path=DB_PATH,
    output_csv=OUTPUT_CSV,
    incipit_k=INCIPIT_K,
    threshold=THRESHOLD,
    review_threshold=REVIEW_THRESHOLD,
    min_segment_len=MIN_SEGMENT_LEN,
):
    """Obradi trazene soloe i vrati ``(found_pairs, summaries)``.

    Za svaku WJD frazu bira jednu podelu po globalnom DTW-u celih pitch
    nizova. Incipit se cuva samo kao dijagnostika. Rucne DA/NE oznake ostaju
    sacuvane, a NE primeri dodaju kaznu slicnim novim kandidatima.
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
                phrase_negative_count = sum(
                    1
                    for candidate_key, label in manual_labels.items()
                    if candidate_key[0] == str(melid)
                    and candidate_key[1] == str(phrase_value)
                    and label == "NE"
                )
                phrase_positive_count = sum(
                    1
                    for candidate_key, label in manual_labels.items()
                    if candidate_key[0] == str(melid)
                    and candidate_key[1] == str(phrase_value)
                    and label == "DA"
                )

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
                        (
                            best,
                            scores_by_split,
                            dtw_gap,
                            relative_dtw_gap,
                        ) = _find_best_scored_split(
                            phrase_pitches,
                            phrase_durations,
                            avgtempo,
                            min_segment_len=min_segment_len,
                            incipit_k=incipit_k,
                            rejected_pairs=rejected_pairs,
                            preferred_split=preferred_split,
                        )
                    except Exception as error:
                        print(f"  [GRESKA] Fraza {phrase_value}: {error}; preskacem.")
                        failed_phrases += 1
                        best = None
                        scores_by_split = {}
                        dtw_gap = float("inf")
                        relative_dtw_gap = float("inf")

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
                            "drugi_dtw_skor": "",
                            "dtw_gap": "",
                            "relativni_dtw_gap": "",
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
                        phrase_rejected = (
                            not manual_label
                            and phrase_negative_count > 0
                            and phrase_positive_count == 0
                        )
                        if (
                            score < review_threshold or manual_label == "DA"
                        ) and not phrase_rejected:
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
                                    else "globalni_DTW_ispod_praga"
                                    if automatic_status == "CR"
                                    else "globalni_DTW_za_pregled"
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
                                "drugi_dtw_skor": (
                                    base_score + dtw_gap
                                    if math.isfinite(dtw_gap)
                                    else ""
                                ),
                                "dtw_gap": dtw_gap if math.isfinite(dtw_gap) else "",
                                "relativni_dtw_gap": (
                                    relative_dtw_gap
                                    if math.isfinite(relative_dtw_gap)
                                    else ""
                                ),
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

    midi_count = _export_result_midis(db_path, results_to_write)

    columns = [
        "validnost", "automatski_status",
        "candidate_source", "decision_reason", "manual_reference_id",
        "title", "performer", "melid", "phrase_index", "phrase_value",
        "phrase_start_index", "phrase_end_index_inclusive",
        "call_start_local", "split_point_local", "response_end_local_exclusive",
        "call_start_solo", "split_point_solo", "response_end_solo_inclusive",
        "osnovni_skor", "drugi_dtw_skor", "dtw_gap", "relativni_dtw_gap",
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
    print(f"MIDI isecci sacuvani/osvezeni: {midi_count}")
    print(f"MIDI folder: {EXCERPT_DIR}")
    print(f"CSV sacuvan u: {output_csv}")

    return found_pairs, summaries


if __name__ == "__main__":
    search_wjd_phrases(SEARCH_ITEMS)
