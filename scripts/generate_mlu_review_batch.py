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
import json
import re
from pathlib import Path

import numpy as np

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
AUTO_OUTPUT_CSV = ROOT / "output" / "automatic_high_confidence_candidates.csv"
EXCERPT_DIR = ROOT / "output" / "mlu_review_midis"
AUTO_EXCERPT_DIR = ROOT / "output" / "automatic_high_confidence_midis"
# Poseban mali batch za najprecizniji dosadasnji signal. Ne prepisuje siroki
# MLU batch koji korisnica eventualno jos proverava.
MELODY_OUTPUT_CSV = ROOT / "output" / "melody_link_review_batch.csv"
MELODY_EXCERPT_DIR = ROOT / "output" / "melody_link_review_midis"
REVIEW_HISTORY = ROOT / "output" / "wjd_phrase_call_response.csv"
MIN_NOTES = 7
MAX_NOTES = 20
MIN_RATIO = 0.5
MAX_RATIO = 2.0
MIN_REVIEW_DTW = 0.30

# Pocetni pilot na istorijskim primerima je izgledao obecavajuce, ali se nije
# ponovio na sledecoj nezavisnoj turi. Zato ovi pragovi sluze iskljucivo za
# cuvanje tog eksperimenta; nijedan kandidat nikad ne postaje DA automatski.
MIN_DURATION_RATIO = 0.90
MAX_NOTE_DENSITY = 5.0
# Potpuno prepisivanje vecine kraceg segmenta nije dijalog nego motiv koji se
# ponavlja. Ovaj prag sledi korisnicke odbacene primere; ne povecava prijavljenu
# validacionu preciznost, vec uklanja ocigledne skoro-iste kopije.
MAX_SHARED_EXACT_MOTIF_FRACTION = 0.65

# Za veliku turu za slusanje izbacujemo samo ekstremno kratke/brze ideje.
# To su ogranicenja citljivosti za ljudski pregled, ne klasifikator DA/NE.
MIN_REVIEW_SECONDS = 1.0
MAX_REVIEW_NOTE_DENSITY = 8.0


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


def _longest_common_fraction(first, second):
    """Udeo kraceg segmenta u najduzem zajednickom uzastopnom motivu."""
    previous = [0] * (len(second) + 1)
    best = 0
    for value in first:
        current = [0]
        for index, other in enumerate(second, start=1):
            length = previous[index - 1] + 1 if value == other else 0
            current.append(length)
            best = max(best, length)
        previous = current
    return best / min(len(first), len(second))


def _max_pitch_repeat(values):
    return max(values.count(value) for value in set(values)) / len(values)


def _review_features(call, response, pitch_dtw, shape_dtw):
    """Mali, objasnjivi skup osobina za redosled ljudskog pregleda."""
    return np.asarray([
        pitch_dtw,
        shape_dtw,
        len(call),
        len(response),
        abs(len(call) - len(response)) / (len(call) + len(response)),
        _longest_common_fraction(call, response),
        _max_pitch_repeat(call),
        _max_pitch_repeat(response),
        len(set(call)) / len(call),
        len(set(response)) / len(response),
    ], dtype=float)


def _fit_review_ranker(history):
    """Nauci samo redosled iz rucno ocenjenih WJD-MLU kandidata.

    Model je regularizovana logisticka regresija implementirana ovde da tok ne
    zavisi od scikit-learn-a. Ne odlucuje DA/NE i ne menja postojece oznake.
    """
    examples = [row for row in history
                if row.get("candidate_source") == "wjd_mlu_back_reference_v1"
                and row.get("validnost", "").strip().upper() in {"DA", "NE"}]
    if len(examples) < 20:
        raise ValueError("Nema dovoljno rucno ocenjenih MLU primera za ranker.")
    features, labels = [], []
    for row in examples:
        call = [float(value) for value in json.loads(row["call_pitches"])]
        response = [float(value) for value in json.loads(row["response_pitches"])]
        features.append(_review_features(
            call, response, float(row["pitch_dtw"]), float(row["shape_dtw"])
        ))
        labels.append(row["validnost"].strip().upper() == "DA")
    matrix = np.asarray(features)
    target = np.asarray(labels, dtype=float)
    mean, std = matrix.mean(axis=0), matrix.std(axis=0)
    std[std < 1e-9] = 1.0
    matrix = np.column_stack([np.ones(len(matrix)), (matrix - mean) / std])
    weights = np.zeros(matrix.shape[1])
    for _ in range(2500):
        probability = 1 / (1 + np.exp(-np.clip(matrix @ weights, -25, 25)))
        gradient = matrix.T @ (probability - target) / len(matrix)
        gradient[1:] += 0.02 * weights[1:]
        weights -= 0.08 * gradient
    return weights, mean, std


def _rank_probability(row, model):
    weights, mean, std = model
    call, response = row["call_pitches"], row["response_pitches"]
    vector = _review_features(call, response, row["pitch_dtw"], row["shape_dtw"])
    value = np.r_[1.0, (vector - mean) / std] @ weights
    return float(1 / (1 + np.exp(-np.clip(value, -25, 25))))


def _is_excluded_category(label):
    """Prvi batch je odbacio MLU ritma i ekspresivnog gesta kao CR parove."""
    lowered = str(label).lower()
    return any(category in lowered for category in ("rhythm", "expressive", "void", "fragment"))


def _is_melody_link(row):
    """Vrati da samo za WJD oznaku direktne melodijske veze.

    Ovo nije automatska CR odluka. U dve nezavisne rucno ocenjene ture
    ``melody -> #melody`` je imao mnogo bolju preciznost od DTW skora, pa ga
    izdvajamo kao mali prioritetni skup za sledece slusanje. Namerno je tacno
    poredenje oznaka: sire kategorije poput ``#-melody`` nisu jos proverene.
    """
    return (
        str(row["call_idea_label"]).strip().lower() == "melody"
        and str(row["response_idea_label"]).strip().lower() == "#melody"
    )


def _temporal_features(events, row):
    """Vrati trajanja segmenata i njihovu najveću gustinu nota.

    ``get_melody_events`` vraca ``(eventid, onset, pitch, duration)``.
    Trajanje obuhvata poslednju notu, zato nije isto sto i razlika dva
    pocetka. Time kratke, brze MLU ideje ne prolaze kao dug call-response.
    """
    call = events[row["call_start_solo"] : row["split_point_solo"]]
    response = events[row["split_point_solo"] : row["response_end_solo_inclusive"] + 1]
    if not call or not response:
        raise ValueError("Prazan call ili response")

    def span(notes):
        return notes[-1][1] + notes[-1][3] - notes[0][1]

    call_seconds, response_seconds = span(call), span(response)
    if call_seconds <= 0 or response_seconds <= 0:
        raise ValueError("Nedefinisano trajanje segmenta")
    return {
        "call_seconds": call_seconds,
        "response_seconds": response_seconds,
        "duration_ratio": min(call_seconds, response_seconds) / max(call_seconds, response_seconds),
        "max_note_density": max(len(call) / call_seconds, len(response) / response_seconds),
    }


def _passes_strict_time_gate(events, row):
    """Istorijski strogi vremenski eksperiment; nije automatska odluka."""
    features = _temporal_features(events, row)
    features["shared_exact_motif_fraction"] = _longest_common_fraction(
        row["call_pitches"], row["response_pitches"]
    )
    return (
        features["duration_ratio"] >= MIN_DURATION_RATIO
        and features["max_note_density"] <= MAX_NOTE_DENSITY
        and features["shared_exact_motif_fraction"] <= MAX_SHARED_EXACT_MOTIF_FRACTION
    ), features


def _passes_review_readability_gate(events, row):
    """Skloni samo kandidate koje je tesko smisleno preslusati."""
    features = _temporal_features(events, row)
    return (
        min(features["call_seconds"], features["response_seconds"]) >= MIN_REVIEW_SECONDS
        and features["max_note_density"] <= MAX_REVIEW_NOTE_DENSITY
    ), features


def _all_rows(conn, excluded_keys, max_dtw=None, variation_only=False):
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
            if variation_only and kind != "variation":
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
            # Ni skoro cela doslovna kopija kraceg segmenta nije koristan CR
            # kandidat za ovu bazu. Ona je korisnicom dosledno odbacivana kao
            # ostinato/puko ponavljanje, cak i kada WJD vezu belezi sa #.
            if _longest_common_fraction(call, response) > MAX_SHARED_EXACT_MOTIF_FRACTION:
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
        "--variation-only", action="store_true",
        help="uzmi samo # varijacije, isti tip na kome imamo rucne oznake",
    )
    parser.add_argument(
        "--rank-model", action="store_true",
        help="rangiraj pomocu malog modela naucenog samo iz rucnih MLU oznaka",
    )
    parser.add_argument(
        "--auto-high-confidence", action="store_true",
        help=(
            "istorijski strogi vremenski eksperiment; ne upisuje DA "
            "i ne predstavlja se kao pouzdana automatska klasifikacija"
        ),
    )
    parser.add_argument(
        "--melody-links", action="store_true",
        help=(
            "izvezi samo WJD IDEA melodija -> #melodija veze u poseban mali "
            "batch; ovo je prednost za rucni pregled, ne automatska DA oznaka"
        ),
    )
    parser.add_argument(
        "--normalize-existing", action="store_true",
        help="popravi CSV ako je Excel dodao DA/NE kao novu prvu kolonu",
    )
    args = parser.parse_args()

    if args.melody_links and (args.auto_high_confidence or args.rank_model):
        parser.error("--melody-links se ne kombinuje sa --auto-high-confidence ni --rank-model")

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
    # Isti apsolutni isečak može ranije da je ušao kroz drugi generator
    # (npr. kroz pretragu WJD fraza, a ne kao MLU kandidat). Za sledeći
    # pregled ga ne nudimo ponovo: korisnica je taj tačan call/response
    # već čula i ocenila. Ne ograničavamo ovo po ``candidate_source``.
    excluded_keys = {
        (str(row["melid"]), int(row["call_start_solo"]), int(row["split_point_solo"]),
         int(row["response_end_solo_inclusive"]) + 1)
        for row in history
        if row.get("validnost", "").strip().upper() in {"DA", "NE"}
        and row.get("melid")
        and row.get("call_start_solo")
        and row.get("split_point_solo")
        and row.get("response_end_solo_inclusive")
    }
    conn = connect_db(str(DB_PATH))
    try:
        candidates = list(_all_rows(
            conn, excluded_keys, args.max_dtw, args.variation_only
        ))
        if args.auto_high_confidence:
            filtered = []
            for row, events in candidates:
                passes, features = _passes_strict_time_gate(events, row)
                if not passes:
                    continue
                row.update({key: round(value, 6) for key, value in features.items()})
                row["automatski_status"] = "STROGI_VREMENSKI_EKSPERIMENT"
                filtered.append((row, events))
            candidates = filtered
        else:
            readable = []
            for row, events in candidates:
                passes, features = _passes_review_readability_gate(events, row)
                if not passes:
                    continue
                row.update({key: round(value, 6) for key, value in features.items()})
                readable.append((row, events))
            candidates = readable

        if args.melody_links:
            candidates = [
                (row, events) for row, events in candidates if _is_melody_link(row)
            ]
            for row, _ in candidates:
                row["candidate_source"] = "wjd_mlu_melody_link_v1"
                row["decision_reason"] = (
                    "WJD IDEA oznaka melody -> #melody; prioritet za rucnu proveru"
                )
                row["automatski_status"] = "ZA_RUCNI_PREGLED_MELODY_LINK"

        chosen, used_solos = [], set()
        model = _fit_review_ranker(history) if args.rank_model and not args.auto_high_confidence else None
        for row, events in sorted(
            candidates,
            key=lambda item: (-_rank_probability(item[0], model), _priority(item[0]))
            if model is not None else _priority(item[0]),
        ):
            # U sirokom batchu jedna pesma daje najvise jedan kandidat da
            # pregled ne bi preplavila. Melody-link batch je namerno veoma
            # mali, pa cuvamo sve razlicite anotirane veze, i iz iste pesme.
            if not args.melody_links and row["melid"] in used_solos:
                continue
            row["review_rank"] = len(chosen) + 1
            # _write_excerpt_midi koristi ova polja samo za stabilno ime fajla.
            row.update({
                # Rank sam nije dovoljan: isti melid moze imati vise review
                # kandidata sa istim brojem nota i istim split-om. Apsolutne
                # granice u imenu sprecavaju da korisnica slusa pogresan MIDI
                # ili da nov batch prepise vec potvrden fajl.
                "phrase_value": (
                    f"mlu_{row['review_rank']:03d}_"
                    f"n{row['call_start_solo']}_s{row['split_point_solo']}_"
                    f"e{row['response_end_solo_inclusive'] + 1}"
                ),
                "call_start_local": 0,
                "split_point_local": row["call_notes"],
                "response_end_local_exclusive": row["call_notes"] + row["response_notes"],
                "phrase_start_index": row["call_start_solo"],
                "phrase_end_index_inclusive": row["response_end_solo_inclusive"],
            })
            if not args.no_midi:
                excerpt_dir = (
                    MELODY_EXCERPT_DIR if args.melody_links
                    else AUTO_EXCERPT_DIR if args.auto_high_confidence
                    else EXCERPT_DIR
                )
                row["excerpt_midi"] = str(_write_excerpt_midi(events, row, excerpt_dir))
            chosen.append(row)
            if not args.melody_links:
                used_solos.add(row["melid"])
            if len(chosen) >= args.limit:
                break
    finally:
        conn.close()

    output_csv = (
        MELODY_OUTPUT_CSV if args.melody_links
        else AUTO_OUTPUT_CSV if args.auto_high_confidence
        else OUTPUT_CSV
    )
    output_csv.parent.mkdir(parents=True, exist_ok=True)
    fields = (["validnost"] + [field for field in chosen[0] if field != "validnost"]
              if chosen else ["validnost", "napomena"])
    with output_csv.open("w", encoding="utf-8-sig", newline="") as stream:
        writer = csv.DictWriter(stream, fieldnames=fields)
        writer.writeheader()
        writer.writerows(chosen)
    kind = (
        "melody-link kandidata za pregled" if args.melody_links
        else "automatskih predloga" if args.auto_high_confidence
        else "za pregled"
    )
    print(f"MLU kandidata posle ogranicenja: {len(candidates)}; {kind}: {len(chosen)}")
    print(f"CSV: {output_csv}")
    if not args.no_midi:
        midi_dir = (
            MELODY_EXCERPT_DIR if args.melody_links
            else AUTO_EXCERPT_DIR if args.auto_high_confidence
            else EXCERPT_DIR
        )
        print(f"MIDI: {midi_dir}")


if __name__ == "__main__":
    main()
