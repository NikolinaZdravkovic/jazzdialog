"""Prebaci rucne DA/NE odluke iz MLU review CSV-a u glavni projektni CSV.

Nijedna oznaka se ne pogadja: samo eksplicitne DA i NE iz review fajla ulaze u
istoriju. ``DA`` zatim moze da se proveri i izveze pomocu
``export_reviewed_dataset.py --package``.
"""

import argparse
import csv
import os
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
SOURCE = ROOT / "output" / "mlu_review_batch.csv"
TARGET = ROOT / "output" / "wjd_phrase_call_response.csv"


def _absolute_key(row):
    start = int(row["phrase_start_index"])
    split = start + int(row["split_point_local"])
    end = start + int(row["response_end_local_exclusive"])
    return str(row["melid"]), start, split, end


def _convert(row):
    """Mapiraj MLU red u siru semu glavnog review CSV-a."""
    converted = dict(row)
    converted.update({
        "validnost": row["validnost"].strip().upper(),
        "phrase_index": "",
        "phrase_value": f"MLU:{row['call_idea_label']}->{row['response_idea_label']}",
        "osnovni_skor": row["pitch_dtw"],
        "score": row["pitch_dtw"],
        # Zadrzavamo tacan nacin na koji je kandidat dosao do pregleda. Tako
        # kasnije mozemo posteno uporediti siroki MLU generator i strogi
        # melody-link cohort, umesto da ih stopimo u jednu navodnu metodu.
        "candidate_source": row.get("candidate_source", "wjd_mlu_back_reference_v1"),
        "decision_reason": row.get(
            "decision_reason", "Rucna provera WJD IDEA back-reference kandidata"
        ),
        "automatski_status": "MLU_REVIEWED",
    })
    return converted


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--apply", action="store_true", help="upisi ocenjene redove u glavni CSV")
    parser.add_argument(
        "--input", type=Path, default=SOURCE,
        help="CSV sa rucno oznacenim MLU kandidatima (podrazumevano: mlu_review_batch.csv)",
    )
    args = parser.parse_args()
    if not args.apply:
        parser.error("Ovo menja glavni CSV; pokreni sa --apply.")

    with args.input.open(encoding="utf-8-sig", newline="") as stream:
        reviewed = [row for row in csv.DictReader(stream)
                    if row.get("validnost", "").strip().upper() in {"DA", "NE"}]
    if not reviewed:
        raise ValueError("Nema DA/NE oznaka u MLU review CSV-u.")
    with TARGET.open(encoding="utf-8-sig", newline="") as stream:
        existing = list(csv.DictReader(stream))

    by_key = {_absolute_key(row): row for row in existing}
    added, skipped = [], 0
    for source_row in reviewed:
        row = _convert(source_row)
        key = _absolute_key(row)
        previous = by_key.get(key)
        if previous is not None:
            if previous.get("validnost", "").strip().upper() != row["validnost"]:
                raise ValueError(f"Sukobljene oznake za {key}")
            skipped += 1
            continue
        by_key[key] = row
        added.append(row)

    rows = existing + added
    fields = list(dict.fromkeys(
        key for row in rows for key in row.keys()
    ))
    temporary = TARGET.with_suffix(".csv.tmp")
    with temporary.open("w", encoding="utf-8-sig", newline="") as stream:
        writer = csv.DictWriter(stream, fieldnames=fields, extrasaction="ignore")
        writer.writeheader()
        writer.writerows(rows)
    os.replace(temporary, TARGET)
    print(f"Dodato: {len(added)}; vec postojalo: {skipped}; glavni CSV: {TARGET}")


if __name__ == "__main__":
    main()
