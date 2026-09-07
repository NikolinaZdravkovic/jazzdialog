"""Primeni postojecu internu podelu na sve zvanicne WJD fraze vise sola."""

import csv
import json
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
    1,2,3,4,5,6,7,8,9,10
]

ALPHA = 0.5
INCIPIT_K = 3
THRESHOLD = 0.4
MIN_SEGMENT_LEN = 3
# Ogranicenja se primenjuju pre skora, pa DA nagrada ne moze da ih zaobidje.
MIN_SEGMENT_SOUND_SECONDS = 1.0
MIN_RESPONSE_CALL_RATIO = 0.75
MAX_RESPONSE_CALL_RATIO = 2.0
# Rucno odbijen kandidat dobija najvise ovoliku dodatnu kaznu.
# Skor je distanca, zato veci skor znaci manju verovatnocu izbora.
NEGATIVE_PENALTY_WEIGHT = 0.20
NEGATIVE_SIMILARITY_LIMIT = 0.30
POSITIVE_REWARD_WEIGHT = 0.65
POSITIVE_SIMILARITY_LIMIT = 0.30

# U veoma brzom tempu tri kratke note nisu dovoljan incipit dokaz.
FAST_TEMPO_BPM = 215.0
MIN_THREE_NOTE_DURATION_SECONDS = 0.75

PROJECT_ROOT = Path(__file__).resolve().parents[1]
DB_PATH = PROJECT_ROOT / "data_midi" / "wjazzd.db"
OUTPUT_CSV = PROJECT_ROOT / "output" / "wjd_phrase_call_response.csv"
EXCERPT_DIR = PROJECT_ROOT / "output" / "wjd_phrase_excerpts"


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
            key = _candidate_key(
                row.get("melid", ""),
                row.get("phrase_value", ""),
                row.get("split_point_local", ""),
            )
            label = row.get("validnost", "").strip().upper()
            if label not in {"DA", "NE"}:
                continue
            # Stari algoritam analizira celu frazu; oznaka skracenog para
            # ne sme se preneti na drugog kandidata sa istim split brojem.
            call_start = int(row.get("call_start_local") or 0)
            response_end = int(row.get("response_end_local_exclusive") or
                               int(row["phrase_end_index_inclusive"]) - int(row["phrase_start_index"]) + 1)
            phrase_len = int(row["phrase_end_index_inclusive"]) - int(row["phrase_start_index"]) + 1
            if call_start == 0 and response_end == phrase_len:
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
    allowed_splits=None,
):
    """Izaberi najbolju podelu jedne ili dve spojene WJD fraze."""
    _split, _score, all_splits = find_best_internal_split(
        phrase_pitches,
        use_intervals=False,
        min_segment_len=min_segment_len,
        incipit_k=incipit_k,
        alpha=alpha,
    )
    if allowed_splits is not None:
        allowed_splits = set(allowed_splits)
        all_splits = [item for item in all_splits if item[0] in allowed_splits]

    base_scores = []
    for split, _original_base_score in all_splits:
        call = phrase_pitches[:split]
        response = phrase_pitches[split:]
        ratio = len(response) / len(call)
        if not MIN_RESPONSE_CALL_RATIO <= ratio <= MAX_RESPONSE_CALL_RATIO:
            continue
        # Zbir trajanja nota ne ukljucuje pauzu do sledeceg segmenta.
        if min(sum(phrase_durations[:split]), sum(phrase_durations[split:])) < MIN_SEGMENT_SOUND_SECONDS:
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
        # Kazna je uvek pozitivna, pa visi osnovni skor vise ne moze pobediti.
        if best is not None and base_score - POSITIVE_REWARD_WEIGHT >= best[4]:
            break
        penalty = _negative_example_penalty(call, response, rejected_pairs)
        reward = _positive_example_reward(call, response, accepted_pairs)
        adjusted_score = max(0.0, base_score + penalty - reward)
        scores_by_split[split] = (base_score, penalty, reward, adjusted_score)
        if best is None or adjusted_score < best[4]:
            best = (split, base_score, penalty, reward, adjusted_score)

    return best, scores_by_split


def search_wjd_phrases(
    search_items,
    db_path=DB_PATH,
    output_csv=OUTPUT_CSV,
    alpha=ALPHA,
    incipit_k=INCIPIT_K,
    threshold=THRESHOLD,
    min_segment_len=MIN_SEGMENT_LEN,
):
    """Obradi trazene soloe i vrati ``(found_pairs, summaries)``.

    Za svaku zvanicnu frazu bira se samo najbolja podela cele fraze.
    Rezultat se prihvata samo kada je ``score < threshold``.
    """
    db_path = Path(db_path)
    output_csv = Path(output_csv)
    previous_rows = []
    if output_csv.exists():
        with output_csv.open(encoding="utf-8-sig", newline="") as stream:
            previous_rows = list(csv.DictReader(stream))
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
                    best, scores_by_split = _find_best_scored_split(
                        phrase_pitches,
                        phrase_durations,
                        avgtempo,
                        min_segment_len=min_segment_len,
                        incipit_k=incipit_k,
                        alpha=alpha,
                        accepted_pairs=accepted_pairs,
                        rejected_pairs=rejected_pairs,
                    )
                except Exception as error:
                    print(f"  [GRESKA] Fraza {phrase_value}: {error}; preskacem.")
                    failed_phrases += 1
                    continue

                for split, split_scores in scores_by_split.items():
                    base_score, penalty, reward, adjusted_score = split_scores
                    candidate_scores[_candidate_key(melid, phrase_value, split)] = (
                        base_score,
                        penalty,
                        reward,
                        adjusted_score,
                    )

                if best is None:
                    print(f"  [PRESKOCENA] Fraza {phrase_value}: nema dozvoljene podele.")
                    skipped_short += 1
                    continue
                best_split, best_base_score, best_penalty, best_reward, best_score = best
                if best_score >= threshold:
                    continue

                split = best_split
                score = best_score
                call_pitches = phrase_pitches[:split]
                response_pitches = phrase_pitches[split:]
                result = {
                    "validnost": manual_labels.get(
                        _candidate_key(melid, phrase_value, split), ""
                    ),
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
                found_for_song += 1

                print(f"  [CR] Fraza {phrase_value}: split={split}, score={score:.4f}")
                print(f"       CALL:     {call_pitches}")
                print(f"       RESPONSE: {response_pitches}")

            # Drugi jednostavan prolaz: spoji svake dve susedne WJD fraze.
            for pair_index in range(len(sections) - 1):
                first_start, first_end, first_value = sections[pair_index]
                second_start, second_end, second_value = sections[pair_index + 1]
                if (
                    first_start < 0
                    or first_end < first_start
                    or second_start <= first_end
                    or second_end < second_start
                    or second_end >= len(pitches)
                ):
                    continue

                start = first_start
                end = second_end
                phrase_value = f"{first_value}+{second_value}"
                phrase_pitches = pitches[start:end + 1]
                phrase_durations = durations[start:end + 1]
                if len(phrase_pitches) < 2 * min_segment_len:
                    continue

                try:
                    boundary_split = second_start - start
                    best, scores_by_split = _find_best_scored_split(
                        phrase_pitches,
                        phrase_durations,
                        avgtempo,
                        min_segment_len=min_segment_len,
                        incipit_k=incipit_k,
                        alpha=alpha,
                        accepted_pairs=accepted_pairs,
                        rejected_pairs=rejected_pairs,
                        allowed_splits=range(boundary_split - 2, boundary_split + 3),
                    )
                except Exception as error:
                    print(
                        f"  [GRESKA] Spojene fraze {phrase_value}: {error}; preskacem."
                    )
                    continue

                for split, split_scores in scores_by_split.items():
                    base_score, penalty, reward, adjusted_score = split_scores
                    candidate_scores[_candidate_key(melid, phrase_value, split)] = (
                        base_score,
                        penalty,
                        reward,
                        adjusted_score,
                    )

                if best is None:
                    continue
                split, base_score, penalty, reward, score = best
                if score >= threshold:
                    continue

                call_pitches = phrase_pitches[:split]
                response_pitches = phrase_pitches[split:]
                result = {
                    "validnost": manual_labels.get(
                        _candidate_key(melid, phrase_value, split), ""
                    ),
                    "title": title,
                    "performer": performer,
                    "melid": melid,
                    "phrase_index": f"{pair_index + 1}+{pair_index + 2}",
                    "phrase_value": phrase_value,
                    "phrase_start_index": start,
                    "phrase_end_index_inclusive": end,
                    "split_point_local": split,
                    "split_point_solo": start + split,
                    "osnovni_skor": base_score,
                    "kazna_ne_primer": penalty,
                    "nagrada_da_primer": reward,
                    "score": score,
                    "phrase_start_seconds": events[start][1],
                    "call_start_seconds": events[start][1],
                    "response_start_seconds": events[start + split][1],
                    "phrase_end_seconds": events[end][1] + events[end][3],
                    "excerpt_midi": "",
                    "call_pitches": call_pitches,
                    "response_pitches": response_pitches,
                }
                found_pairs.append(result)
                found_for_song += 1

                print(
                    f"  [CR PREKO GRANICE] Fraze {phrase_value}: "
                    f"split={split}, score={score:.4f}"
                )

            summaries.append({
                "title": title,
                "performer": performer,
                "melid": melid,
                "phrase_count": len(sections),
                "found_count": found_for_song,
                "skipped_short": skipped_short,
                "failed_phrases": failed_phrases,
            })
    finally:
        conn.close()

    # Sacuvaj sve stare redove i oznake, ukljucujuci nepregledane kandidate.
    def identity(row):
        def pitches(value):
            return tuple(json.loads(value) if isinstance(value, str) else value)
        return (str(row["melid"]), str(row["phrase_value"]),
                str(row["split_point_local"]), pitches(row["call_pitches"]),
                pitches(row["response_pitches"]))

    merged = {identity(row): dict(row) for row in previous_rows}
    for result in found_pairs:
        key = identity(result)
        if key in merged:
            continue  # Rucne oznake i istorijski skor ostaju kakvi su bili.
        result["call_start_local"] = 0
        result["response_end_local_exclusive"] = len(result["call_pitches"]) + len(result["response_pitches"])
        result["call_start_solo"] = result["phrase_start_index"]
        result["response_end_solo_inclusive"] = result["phrase_end_index_inclusive"]
        result["response_end_seconds"] = result["phrase_end_seconds"]
        result["candidate_source"] = "verzija_7bd878a"
        result["decision_reason"] = "istorijski_DTW_incipit_i_feedback"
        result["automatski_status"] = "ODBIJEN" if result.get("validnost") == "NE" else "CR"
        merged[key] = result
    results_to_write = list(merged.values())
    _export_result_midis(db_path, results_to_write)
    columns = list(dict.fromkeys(key for row in results_to_write for key in row))
    if not columns:
        columns = ["validnost", "melid", "phrase_value", "score", "call_pitches", "response_pitches"]
    output_csv.parent.mkdir(parents=True, exist_ok=True)
    with output_csv.open("w", encoding="utf-8-sig", newline="") as stream:
        writer = csv.DictWriter(stream, fieldnames=columns)
        writer.writeheader()
        for result in results_to_write:
            row = dict(result)
            for name in ("call_pitches", "response_pitches"):
                if isinstance(row[name], list):
                    row[name] = json.dumps(row[name])
            writer.writerow(row)

    print("\n================ SUMARNI IZVESTAJ ================")
    if not summaries:
        print("Nijedan solo nije obradjen.")
    for summary in summaries:
        print(
            f"{summary['title']} (melid={summary['melid']}): "
            f"{summary['found_count']} CR / {summary['phrase_count']} fraza"
        )
    print(f"Ukupno pronadjenih parova: {len(found_pairs)}")
    if found_pairs:
        print("Pronadjeni parovi:")
        for result in found_pairs:
            print(
                f"  - {result['title']}, fraza {result['phrase_value']}, "
                f"split={result['split_point_local']}, score={result['score']:.4f}"
            )
    print(f"CSV sacuvan u: {output_csv}")

    return found_pairs, summaries


if __name__ == "__main__":
    search_wjd_phrases(SEARCH_ITEMS)
