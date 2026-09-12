"""Export manually accepted annotations, with WJD/MIDI checks and overlap flags.

Run --export to update output/reviewed_dataset.json. Without it, only check.
No labels, source rows or MIDI files are changed.
"""

import argparse
import csv
import hashlib
import json
import math
import sqlite3
from pathlib import Path

import pretty_midi

ROOT = Path(__file__).resolve().parents[1]
SOURCE = ROOT / "output" / "wjd_phrase_call_response.csv"
DATABASE = ROOT / "data_midi" / "wjazzd.db"
OUTPUT = ROOT / "output" / "reviewed_dataset.json"


def annotation(row, events):
    start = int(row["phrase_start_index"])
    end = int(row["phrase_end_index_inclusive"])
    left = start + int(row.get("call_start_local") or 0)
    split = start + int(row["split_point_local"])
    right = start + int(row.get("response_end_local_exclusive") or end-start+1)
    if not 0 <= start <= left < split < right <= end+1 <= len(events):
        raise ValueError("invalid note boundaries")
    for field, expected in (("call_start_solo", left), ("split_point_solo", split),
                            ("response_end_solo_inclusive", right-1)):
        if row.get(field) and int(row[field]) != expected:
            raise ValueError(f"inconsistent {field}")
    call, response = events[left:split], events[split:right]
    for name, notes in (("call", call), ("response", response)):
        if [round(n[1]) for n in notes] != json.loads(row[name+"_pitches"]):
            raise ValueError(f"{name} pitches differ from WJD")
        for onset, pitch, duration in notes:
            if not all(math.isfinite(x) for x in (onset, pitch, duration)) or duration <= 0:
                raise ValueError("invalid note timing")
    for field, expected in (("call_start_seconds", call[0][0]),
                            ("response_start_seconds", response[0][0])):
        if row.get(field) and not math.isclose(float(row[field]), expected, abs_tol=1e-5, rel_tol=0):
            raise ValueError(f"inconsistent {field}")
    midi_path = Path(row["excerpt_midi"])
    if not midi_path.is_absolute():
        midi_path = ROOT / midi_path
    relative = midi_path.resolve().relative_to(ROOT.resolve()).as_posix()
    midi = pretty_midi.PrettyMIDI(str(midi_path))
    origin = call[0][0]
    for name, notes in (("CALL", call), ("RESPONSE", response)):
        tracks = [track for track in midi.instruments if track.name == name]
        if len(tracks) != 1 or len(tracks[0].notes) != len(notes):
            raise ValueError(f"MIDI {name} track/count mismatch")
        actual = sorted(tracks[0].notes, key=lambda n: n.start)
        for note, (onset, pitch, duration) in zip(actual, notes):
            # Existing excerpts use 120 BPM / 220 ticks: allow two tick rounding.
            if note.pitch != round(pitch) or abs(note.start-(onset-origin)) > .005 or abs(note.end-(onset+duration-origin)) > .005:
                raise ValueError(f"MIDI {name} notes/timing mismatch")
    key = f"wjd:{row['melid']}:{left}:{split}:{right}"
    def segment(notes, first, last):
        return dict(start_note=first, end_note_exclusive=last,
                    notes=[dict(pitch=round(p), onset_seconds=o, duration_seconds=d) for o,p,d in notes])
    return dict(id=key, melid=int(row["melid"]), title=row["title"],
                performer=row["performer"], phrase_value=row["phrase_value"],
                evaluation_group=f"wjd-solo:{row['melid']}",
                label="DA", candidate_source=row.get("candidate_source") or "unspecified",
                manual_boundary_note=row.get("manual_boundary_note", ""),
                source_key=dict(phrase_start_index=start, phrase_end_index_inclusive=end,
                                split_point_local=int(row["split_point_local"])),
                call=segment(call,left,split), response=segment(response,split,right),
                midi=relative, overlapping_ids=[])


def build(source=SOURCE, database=DATABASE):
    snapshot = source.read_bytes()
    with source.open(encoding="utf-8-sig", newline="") as stream:
        accepted = [r for r in csv.DictReader(stream) if r.get("validnost", "").strip().upper()=="DA"]
    records, errors, cache = [], [], {}
    conn = sqlite3.connect(database.resolve().as_uri()+"?mode=ro", uri=True)
    try:
        for row in accepted:
            try:
                melid = int(row["melid"])
                if melid not in cache:
                    cache[melid] = conn.execute("SELECT onset,pitch,duration FROM melody WHERE melid=? ORDER BY eventid", (melid,)).fetchall()
                records.append(annotation(row, cache[melid]))
            except (ValueError, KeyError, OSError, EOFError) as error:
                errors.append(f"{row.get('melid')}/{row.get('phrase_value')}: {error}")
    finally:
        conn.close()
    if len({r['id'] for r in records}) != len(records):
        errors.append("Duplicate absolute annotation boundaries; resolve before export")
    if source.read_bytes() != snapshot:
        errors.append("Source CSV changed during validation; rerun")
    if errors:
        raise ValueError("\n".join(errors))
    for i, first in enumerate(records):
        for second in records[i+1:]:
            if first['melid'] == second['melid'] and max(first['call']['start_note'], second['call']['start_note']) < min(first['response']['end_note_exclusive'], second['response']['end_note_exclusive']):
                first['overlapping_ids'].append(second['id'])
                second['overlapping_ids'].append(first['id'])
    return dict(schema_version=1, status="pilot_manual_annotations",
                source_csv=source.relative_to(ROOT).as_posix(), source_sha256=hashlib.sha256(snapshot).hexdigest(),
                note_indices="zero-based within solo; end exclusive",
                time_units="seconds from solo origin",
                annotation_count=len(records),
                annotations_needing_overlap_review=sum(bool(r['overlapping_ids']) for r in records),
                validation="Pitch sequences and CALL/RESPONSE MIDI tracks checked against WJD; musical validity supplied by human DA labels",
                records=records)


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--export", action="store_true")
    args = parser.parse_args()
    result = build()
    print(f"Verified DA annotations: {result['annotation_count']}; overlapping annotations: {result['annotations_needing_overlap_review']}")
    for record in result['records']:
        if record['overlapping_ids']:
            print(record['id'], 'overlaps', ', '.join(record['overlapping_ids']))
    if args.export:
        # Derived artifact only. Atomic replacement preserves last valid export.
        temporary = OUTPUT.with_suffix('.json.tmp')
        temporary.write_text(json.dumps(result, ensure_ascii=False, indent=2)+'\n', encoding='utf-8')
        temporary.replace(OUTPUT)
        print(OUTPUT)
