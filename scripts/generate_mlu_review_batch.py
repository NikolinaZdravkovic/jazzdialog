"""Izvezi kandidate iz WJD rucno anotiranih povezanih muzickih ideja.

WJD ``IDEA`` segmenti su mid-level units (MLU). Oznaka ``#`` znaci da se
trenutna ideja odnosi na neposredno prethodnu; ``#+``/``#-`` su transpozicije,
a ``#=`` je tacno ponavljanje. To je izvor kandidata za proveru, ne gotova
call-response oznaka.

Primer:
    .\\venv\\Scripts\\python.exe scripts\\generate_mlu_review_batch.py --limit 20
"""

import argparse
import csv
import re
from pathlib import Path

try:
    from .extract_wjd_phrases import connect_db, get_melody_events
    from .find_internal_split import _dtw_norm
    from .search_wjd_phrase_splits import _write_excerpt_midi
except ImportError:
    from extract_wjd_phrases import connect_db, get_melody_events
    from find_internal_split import _dtw_norm
    from search_wjd_phrase_splits import _write_excerpt_midi


ROOT = Path(__file__).resolve().parents[1]
DB_PATH = ROOT / "data_midi" / "wjazzd.db"
OUTPUT_CSV = ROOT / "output" / "mlu_review_batch.csv"
EXCERPT_DIR = ROOT / "output" / "mlu_review_midis"
REVIEW_HISTORY = ROOT / "output" / "wjd_phrase_call_response.csv"
MIN_NOTES = 7
MAX_NOTES = 20
MIN_RATIO = 0.5
MAX_RATIO = 2.0
MIN_REVIEW_DTW = 0.30


def _relation(label):
    """Vrati vrstu neposredne MLU veze ili None za nepovezanu ideju."""
    # Samo jedan # znaci neposredno prethodna ideja. ## i #2 namerno ostaju za
    # kasniji korak jer preskacu posrednu ideju i nisu neposredan odgovor.
    if not label.startswith("#") or label.startswith("##") or re.match(r"#\d", label):
        return None
    after = label[1:]
    if after.startswith("="):
        return "exact_repeat"
    if after.startswith("+"):
        return "transposed_up"
    if after.startswith("-"):
        return "transposed_down"
    return "variation"


def _shape(values):
    return [value - values[0] for value in values]


def _is_excluded_category(label):
    """Prvi batch je odbacio MLU ritma i ekspresivnog gesta kao CR parove."""
    lowered = str(label).lower()
    return any(category in lowered for category in ("rhythm", "expressive", "void", "fragment"))


def _all_rows(conn, excluded_keys, max_dtw=None):
    solos = conn.execute(
        "SELECT melid, title, performer FROM solo_info ORDER BY melid"
    ).fetchall()
    for melid, title, performer in solos:
        ideas = conn.execute(
            "SELECT start, end, value FROM sections "
            "WHERE melid=? AND type='IDEA' ORDER BY start, end", (melid,)
        ).fetchall()
        events = get_melody_events(conn, melid)
        pitches = [int(round(event[2])) for event in events]
        for index, (response_start, response_end, label) in enumerate(ideas):
            kind = _relation(str(label))
            if kind is None or index == 0:
                continue
            call_start, call_end, call_label = ideas[index - 1]
            call = pitches[call_start : call_end + 1]
            response = pitches[response_start : response_end + 1]
            key = (str(melid), call_start, response_start, response_end + 1)
            if key in excluded_keys:
                continue
            if min(len(call), len(response)) < MIN_NOTES or max(len(call), len(response)) > MAX_NOTES:
                continue
            ratio = len(response) / len(call)
            if not MIN_RATIO <= ratio <= MAX_RATIO:
                continue
            # Tacno ponavljanje je dokumentovano, ali nije dobar prvi izbor za
            # CR pregled: korisnica ga je vise puta odbacila kao ostinato.
            if kind == "exact_repeat":
                continue
            # Neki podrazumevani #* unosi ipak imaju isti zapis tona. WJD time
            # belezi vezu ideja, ali za nas prvi CR batch to je upravo klasa
            # doslovnih repeticija koju korisnica ne zeli da pregleda.
            if call == response:
                continue
            if _is_excluded_category(call_label) or _is_excluded_category(label):
                continue
            pitch_dtw = _dtw_norm(call, response)
            shape_dtw = _dtw_norm(_shape(call), _shape(response))
            if pitch_dtw < MIN_REVIEW_DTW or (max_dtw is not None and pitch_dtw > max_dtw):
                continue
            yield {
                "melid": melid,
                "title": title,
                "performer": performer,
                "call_start_solo": call_start,
                "split_point_solo": response_start,
                "response_end_solo_inclusive": response_end,
                "call_notes": len(call),
                "response_notes": len(response),
                "length_ratio": round(ratio, 3),
                "call_idea_label": call_label,
                "response_idea_label": label,
                "mlu_relation": kind,
                "pitch_dtw": round(pitch_dtw, 6),
                "shape_dtw": round(shape_dtw, 6),
                "call_pitches": call,
                "response_pitches": response,
                "validnost": "",
                "napomena": "",
                "candidate_source": "wjd_mlu_back_reference_v1",
            }, events


def _priority(row):
    # Varijacija je za CR zanimljivija od ciste transpozicione sekvence;
    # potom favorizujemo uravnotezene ideje. DTW ostaje izvestajna kolona,
    # nikad automatska DA odluka.
    relation_rank = {"variation": 0, "transposed_up": 1, "transposed_down": 1}[row["mlu_relation"]]
    return (relation_rank, abs(1 - row["length_ratio"]), row["pitch_dtw"])


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--limit", type=int, default=20, help="broj MIDI kandidata za pregled")
    parser.add_argument("--no-midi", action="store_true")
    parser.add_argument(
        "--max-dtw", type=float,
        help="gornja granica pitch-DTW-a samo za redosled sledeceg review batcha",
    )
    parser.add_argument(
        "--normalize-existing", action="store_true",
        help="popravi CSV ako je Excel dodao DA/NE kao novu prvu kolonu",
    )
    args = parser.parse_args()

    if args.normalize_existing:
        with OUTPUT_CSV.open(encoding="utf-8-sig", newline="") as stream:
            raw_rows = list(csv.reader(stream))
        if not raw_rows:
            raise ValueError(f"Prazan CSV: {OUTPUT_CSV}")
        old_fields, data = raw_rows[0], raw_rows[1:]
        # Excel je dozvolio unos u prvu novu kolonu, ali nije azurirao header.
        # Zato svaki red ima tacno jednu celiju vise od zaglavlja.
        shifted = all(len(row) == len(old_fields) + 1 for row in data)
        if not shifted:
            print("CSV nije pomeren; nema sta da se popravlja.")
            return
        fields = ["validnost"] + [field for field in old_fields if field != "validnost"]
        repaired = []
        for row in data:
            label, original = row[0].strip().upper(), row[1:]
            record = dict(zip(old_fields, original))
            record["validnost"] = label
            repaired.append(record)
        with OUTPUT_CSV.open("w", encoding="utf-8-sig", newline="") as stream:
            writer = csv.DictWriter(stream, fieldnames=fields)
            writer.writeheader()
            writer.writerows(repaired)
        print(f"Popravljeno redova: {len(repaired)}; CSV: {OUTPUT_CSV}")
        return

    with REVIEW_HISTORY.open(encoding="utf-8-sig", newline="") as stream:
        history = list(csv.DictReader(stream))
    excluded_keys = {
        (str(row["melid"]), int(row["call_start_solo"]), int(row["split_point_solo"]),
         int(row["response_end_solo_inclusive"]) + 1)
        for row in history
        if row.get("candidate_source") == "wjd_mlu_back_reference_v1"
    }
    conn = connect_db(str(DB_PATH))
    try:
        candidates = list(_all_rows(conn, excluded_keys, args.max_dtw))
        chosen, used_solos = [], set()
        for row, events in sorted(candidates, key=lambda item: _priority(item[0])):
            if row["melid"] in used_solos:
                continue
            row["review_rank"] = len(chosen) + 1
            # _write_excerpt_midi koristi ova polja samo za stabilno ime fajla.
            row.update({
                "phrase_value": f"mlu_{row['review_rank']:03d}",
                "call_start_local": 0,
                "split_point_local": row["call_notes"],
                "response_end_local_exclusive": row["call_notes"] + row["response_notes"],
                "phrase_start_index": row["call_start_solo"],
                "phrase_end_index_inclusive": row["response_end_solo_inclusive"],
            })
            if not args.no_midi:
                row["excerpt_midi"] = str(_write_excerpt_midi(events, row, EXCERPT_DIR))
            chosen.append(row)
            used_solos.add(row["melid"])
            if len(chosen) >= args.limit:
                break
    finally:
        conn.close()

    OUTPUT_CSV.parent.mkdir(parents=True, exist_ok=True)
    fields = (["validnost"] + [field for field in chosen[0] if field != "validnost"]
              if chosen else ["validnost", "napomena"])
    with OUTPUT_CSV.open("w", encoding="utf-8-sig", newline="") as stream:
        writer = csv.DictWriter(stream, fieldnames=fields)
        writer.writeheader()
        writer.writerows(chosen)
    print(f"MLU kandidata posle ogranicenja: {len(candidates)}; za pregled: {len(chosen)}")
    print(f"CSV: {OUTPUT_CSV}")
    if not args.no_midi:
        print(f"MIDI: {EXCERPT_DIR}")


if __name__ == "__main__":
    main()
