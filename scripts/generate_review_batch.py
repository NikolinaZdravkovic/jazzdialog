"""Napravi malu, raznoliku grupu kandidata za ljudsku proveru u WJD frazama.

Ovo NIJE detektor koji automatski upisuje ``DA``.  Trazi susedne, ogranicene
call/response pod-segmente unutar *jedne* zvanicne WJD fraze i upisuje praznu
kolonu ``validnost`` u poseban CSV.  Posle slusanja korisnica unosi DA ili NE.

Primer:
    .\\venv\\Scripts\\python.exe scripts\\generate_review_batch.py --first 50 --limit 40
"""

import argparse
import csv
from pathlib import Path

try:
    from .extract_wjd_phrases import connect_db, get_melody_events, get_phrase_sections
    from .find_internal_split import _dtw_norm
    from .search_wjd_phrase_splits import _is_repetitive_loop_candidate, _write_excerpt_midi
except ImportError:
    from extract_wjd_phrases import connect_db, get_melody_events, get_phrase_sections
    from find_internal_split import _dtw_norm
    from search_wjd_phrase_splits import _is_repetitive_loop_candidate, _write_excerpt_midi


PROJECT_ROOT = Path(__file__).resolve().parents[1]
DB_PATH = PROJECT_ROOT / "data_midi" / "wjazzd.db"
OUTPUT_CSV = PROJECT_ROOT / "output" / "review_batch.csv"
EXCERPT_DIR = PROJECT_ROOT / "output" / "review_batch_midis"

# Svesno mali skup duzina: izbegava eksploziju kombinacija i mikrosemente.
# Donja granica 5 cuva ranije potvrden primer sa call-om od pet nota.
LENGTHS = (5, 8, 12)
MIN_RATIO = 0.5
MAX_RATIO = 2.0
# Kandidat sa prakticno nultim DTW-om najcesce je klizajuci isecek jednog
# ostinata. Za novu grupu za pregled ga ne stavljamo na vrh liste. Postojece,
# rucno potvrdene anotacije se ovim nikad ne menjaju.
MIN_REVIEW_DTW = 0.35


def _shape(values):
    return [value - values[0] for value in values]


def _score(call, response):
    """Vrati pitch i transponovani DTW odvojeno, bez mesanja novih kriterijuma."""
    pitch_dtw = _dtw_norm(call, response)
    shape_dtw = _dtw_norm(_shape(call), _shape(response))
    # Primarni redosled ostaje stari, korisnicki poznati pitch DTW. Shape je
    # transparentna dopunska kolona za kasniju analizu, ne automatska odluka.
    return pitch_dtw, shape_dtw


def _suffix_prefix_overlap(call, response):
    """Najduzi tacan kraj call-a koji se ponavlja na pocetku response-a."""
    for length in range(min(len(call), len(response)), 0, -1):
        if call[-length:] == response[:length]:
            return length
    return 0


def _is_sliding_repetition(call, response):
    """Odbaci isti motiv samo pomeren preko granice predlozenog segmenta."""
    if call == response:
        return True
    overlap = _suffix_prefix_overlap(call, response)
    # Jedna zajednicka nota moze biti vezani ton na granici. Cetiri ili vise
    # tacno istih uzastopnih nota preko granice jeste tipicna lazna rotacija.
    return overlap >= 4


def _longest_common_run(first, second):
    """Duzina najduzeg tacno zajednickog uzastopnog pitch motiva."""
    previous = [0] * (len(second) + 1)
    best = 0
    for value in first:
        current = [0]
        for index, other in enumerate(second, start=1):
            length = previous[index - 1] + 1 if value == other else 0
            current.append(length)
            best = max(best, length)
        previous = current
    return best


def _has_dominant_shared_motif(call, response):
    """Blokiraj kandidate gde je gotovo ceo response ista kopija call motiva."""
    return _longest_common_run(call, response) / min(len(call), len(response)) >= 0.8


def _has_short_interval_loop(values):
    """Prepoznaj ostinato i kada su pitch vrednosti transponovano pomerene."""
    intervals = [second - first for first, second in zip(values, values[1:])]
    if len(intervals) < 6:
        return False
    for period in range(1, min(4, len(intervals) // 3) + 1):
        matches = sum(
            intervals[index] == intervals[index - period]
            for index in range(period, len(intervals))
        )
        if matches / (len(intervals) - period) >= 0.8:
            return True
    return False


def _candidate_rows(conn, melids):
    """Generisi susedne podsegmente unutar WJD fraza, bez pisanja fajlova."""
    for melid, title, performer in conn.execute(
        "SELECT melid, title, performer FROM solo_info WHERE melid IN ({})".format(
            ",".join("?" for _ in melids)
        ),
        melids,
    ):
        events = get_melody_events(conn, melid)
        pitches = [int(round(event[2])) for event in events]
        for phrase_number, (start, end, phrase_value) in enumerate(
            get_phrase_sections(conn, melid), start=1
        ):
            phrase = pitches[start : end + 1]
            n = len(phrase)
            for call_start in range(n):
                for call_len in LENGTHS:
                    split = call_start + call_len
                    if split >= n:
                        continue
                    call = phrase[call_start:split]
                    for response_len in LENGTHS:
                        response_end = split + response_len
                        if response_end > n:
                            continue
                        ratio = response_len / call_len
                        if not MIN_RATIO <= ratio <= MAX_RATIO:
                            continue
                        response = phrase[split:response_end]
                        if (_is_repetitive_loop_candidate(call, response)
                                or _is_sliding_repetition(call, response)
                                or _has_dominant_shared_motif(call, response)
                                or _has_short_interval_loop(call)
                                or _has_short_interval_loop(response)):
                            continue
                        # Pet nota ostaje dozvoljeno samo kada je druga strana
                        # duza; 5 prema 5 je u dosadasnjem pregledu pretezno
                        # davao premalo muzicke informacije.
                        if min(call_len, response_len) == 5 and max(call_len, response_len) < 8:
                            continue
                        pitch_dtw, shape_dtw = _score(call, response)
                        if pitch_dtw < MIN_REVIEW_DTW:
                            continue
                        yield {
                            "melid": melid,
                            "title": title,
                            "performer": performer,
                            "phrase_number": phrase_number,
                            "phrase_value": phrase_value,
                            "phrase_start_index": start,
                            "phrase_end_index_inclusive": end,
                            "call_start_solo": start + call_start,
                            "split_point_solo": start + split,
                            "response_end_solo_inclusive": start + response_end - 1,
                            "call_start_local": call_start,
                            "split_point_local": split,
                            "response_end_local_exclusive": response_end,
                            "call_notes": call_len,
                            "response_notes": response_len,
                            "length_ratio": round(ratio, 3),
                            "pitch_dtw": round(pitch_dtw, 6),
                            "shape_dtw": round(shape_dtw, 6),
                            "call_pitches": call,
                            "response_pitches": response,
                            "validnost": "",
                            "napomena": "",
                            "candidate_source": "within_phrase_subsegment_dtw_v1",
                        }


def _select_diverse(rows, limit):
    """Najnizi skor, najvise jedan kandidat po frazi i najvise dva po solu."""
    selected, phrase_keys, per_solo = [], set(), {}
    # Srednje niske, ali ne trivijalno niske distance prve idu na slusanje.
    # Ovo nije prag za DA/NE, samo redosled ljudskog pregleda.
    for row in sorted(rows, key=lambda item: (item["pitch_dtw"], item["shape_dtw"])):
        phrase_key = (row["melid"], row["phrase_value"])
        if phrase_key in phrase_keys or per_solo.get(row["melid"], 0) >= 2:
            continue
        selected.append(row)
        phrase_keys.add(phrase_key)
        per_solo[row["melid"]] = per_solo.get(row["melid"], 0) + 1
        if len(selected) == limit:
            break
    return selected


def _write_midis(conn, rows):
    events_cache = {}
    for rank, row in enumerate(rows, start=1):
        events = events_cache.setdefault(row["melid"], get_melody_events(conn, row["melid"]))
        result = dict(row)
        result["phrase_value"] = f"batch_{rank:03d}_{row['phrase_value']}"
        path = _write_excerpt_midi(events, result, EXCERPT_DIR)
        row["review_rank"] = rank
        row["excerpt_midi"] = str(path)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    group = parser.add_mutually_exclusive_group()
    group.add_argument("--first", type=int, help="prvih N melid-a po redu")
    group.add_argument("--melids", nargs="+", type=int, help="konkretni melid brojevi")
    parser.add_argument("--limit", type=int, default=40, help="broj kandidata za pregled")
    parser.add_argument("--no-midi", action="store_true", help="samo CSV, bez MIDI iseckaka")
    args = parser.parse_args()

    conn = connect_db(str(DB_PATH))
    try:
        if args.melids:
            melids = args.melids
        else:
            count = args.first or 50
            melids = [row[0] for row in conn.execute(
                "SELECT melid FROM solo_info ORDER BY melid LIMIT ?", (count,)
            )]
        rows = list(_candidate_rows(conn, melids))
        selected = _select_diverse(rows, args.limit)
        if not args.no_midi:
            _write_midis(conn, selected)
    finally:
        conn.close()

    OUTPUT_CSV.parent.mkdir(parents=True, exist_ok=True)
    fields = list(selected[0]) if selected else ["validnost", "napomena"]
    with OUTPUT_CSV.open("w", encoding="utf-8-sig", newline="") as stream:
        writer = csv.DictWriter(stream, fieldnames=fields)
        writer.writeheader()
        writer.writerows(selected)
    print(f"Pregledano sola: {len(melids)}; generisano kandidata: {len(rows)}; za pregled: {len(selected)}")
    print(f"CSV: {OUTPUT_CSV}")
    if not args.no_midi:
        print(f"MIDI: {EXCERPT_DIR}")


if __name__ == "__main__":
    main()
