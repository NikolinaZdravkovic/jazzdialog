"""Export manually accepted annotations, with WJD/MIDI checks and overlap flags.

Run --export to update output/reviewed_dataset.json. Without it, only check.
No labels, source rows or MIDI files are changed.
"""

import argparse
import csv
import hashlib
import io
import json
import math
import sqlite3
import zipfile
from pathlib import Path, PurePosixPath

import pretty_midi

ROOT = Path(__file__).resolve().parents[1]
SOURCE = ROOT / "output" / "wjd_phrase_call_response.csv"
DATABASE = ROOT / "data_midi" / "wjazzd.db"
OUTPUT = ROOT / "output" / "reviewed_dataset.json"
PACKAGE = ROOT / "output" / "reviewed_dataset.zip"
# Excel-prijateljski pogled finalne baze. Sadrzi iskljucivo rucno potvrdjene
# DA anotacije; JSON/ZIP iznad ostaju potpuni, proverljivi prenosivi paket.
FINAL_CSV = ROOT / "output" / "accepted_call_response_pairs.csv"


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
                preferred_annotation_id=row.get("preferred_annotation_id", ""),
                boundary_choice_note=row.get("boundary_choice_note", ""),
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


def validate_midi(record, payload):
    """Validate MIDI bytes against manifest notes, without access to WJD."""
    midi = pretty_midi.PrettyMIDI(io.BytesIO(payload))
    origin = record['call']['notes'][0]['onset_seconds']
    if len(midi.instruments) != 2:
        raise ValueError('Expected exactly two MIDI tracks')
    for role in ('call', 'response'):
        tracks = [t for t in midi.instruments if t.name == role.upper()]
        segment = record[role]
        expected = segment['notes']
        if not expected or segment['end_note_exclusive']-segment['start_note'] != len(expected):
            raise ValueError('Manifest segment length mismatch')
        if len(tracks) != 1 or len(tracks[0].notes) != len(expected):
            raise ValueError('MIDI track/count mismatch')
        for actual, note in zip(sorted(tracks[0].notes, key=lambda n:n.start), expected):
            onset, duration = note['onset_seconds']-origin, note['duration_seconds']
            if not all(math.isfinite(x) for x in (onset, duration, note['pitch'])) or duration <= 0:
                raise ValueError('Invalid manifest note')
            if actual.pitch != note['pitch'] or abs(actual.start-onset) > .005 or abs(actual.end-onset-duration) > .005:
                raise ValueError('MIDI pitch/timing mismatch')


def verify_package(source):
    """Check an archive in place, without extracting or consulting local data."""
    with zipfile.ZipFile(source) as archive:
        names = archive.namelist()
        if len(names) != len(set(names)) or archive.testzip() is not None:
            raise ValueError('Duplicate ZIP members or bad checksum')
        for name in names:
            if PurePosixPath(name).is_absolute() or '..' in PurePosixPath(name).parts or '\\' in name or ':' in name:
                raise ValueError('Unsafe archive path')
        result = json.loads(archive.read('reviewed_dataset.json'))
        records = result['records']
        if result['schema_version'] != 1 or result['annotation_count'] != len(records):
            raise ValueError('Manifest version/count mismatch')
        if len({r['id'] for r in records}) != len(records):
            raise ValueError('Duplicate annotation IDs')
        expected_members = {'README.txt', 'reviewed_dataset.json'} | {r['midi'] for r in records}
        if set(names) != expected_members:
            raise ValueError('Missing or unexpected ZIP members')
        for record in records:
            left, split = record['call']['start_note'], record['response']['start_note']
            right = record['response']['end_note_exclusive']
            if not 0 <= left < split < right or record['call']['end_note_exclusive'] != split:
                raise ValueError('Invalid segment boundaries')
            if record['id'] != f"wjd:{record['melid']}:{left}:{split}:{right}" or record['label'] != 'DA':
                raise ValueError('Invalid annotation identity/label')
            if record['evaluation_group'] != f"wjd-solo:{record['melid']}":
                raise ValueError('Invalid evaluation group')
            overlaps = {other['id'] for other in records if other['id'] != record['id']
                        and other['melid'] == record['melid']
                        and max(left,other['call']['start_note']) < min(right,other['response']['end_note_exclusive'])}
            if set(record['overlapping_ids']) != overlaps:
                raise ValueError('Incorrect overlap metadata')
            preferred = record.get('preferred_annotation_id')
            if preferred and preferred not in overlaps | {record['id']}:
                raise ValueError('Preferred annotation must belong to the overlapping versions')
            validate_midi(record, archive.read(record['midi']))
        if result['annotations_needing_overlap_review'] != sum(bool(r['overlapping_ids']) for r in records):
            raise ValueError('Incorrect overlap count')
        return result


def print_review(result):
    """Show unresolved versions without making a musical choice."""
    records = result['records']
    print(f"DA annotations: {len(records)}; with overlapping versions: {result['annotations_needing_overlap_review']}")
    for record in records:
        if not record['overlapping_ids']:
            continue
        call, response = record['call']['notes'], record['response']['notes']
        print(f"\n{record['title']} | melid {record['melid']}, phrase {record['phrase_value']} | {record['id']}")
        print(f"CALL {len(call)} notes; RESPONSE {len(response)} notes; boundary {response[0]['onset_seconds']:.3f}s in solo")
        print('MIDI:', record['midi'])
        if record.get('manual_boundary_note'):
            print('Manual note:', record['manual_boundary_note'])
        if record.get('preferred_annotation_id'):
            print('User preferred version:', record['preferred_annotation_id'])
            print('Reason:', record.get('boundary_choice_note', ''))
    print('\nStored boundary preferences are separate from DA/NE labels. Overlap counts describe geometry, not unresolved decisions.')


def package_bytes(result):
    """Validate the exact bytes being packaged before replacing any output."""
    manifest = (json.dumps(result, ensure_ascii=False, indent=2)+'\n').encode('utf-8')
    buffer = io.BytesIO()
    members = {}
    for record in result['records']:
        name = record['midi']
        relative = PurePosixPath(name)
        if relative.is_absolute() or '..' in relative.parts or '\\' in name or ':' in name:
            raise ValueError('Unsafe archive path: '+name)
        path = (ROOT / name).resolve()
        path.relative_to(ROOT.resolve())
        payload = path.read_bytes()
        validate_midi(record, payload)
        members[name] = payload
    with zipfile.ZipFile(buffer, 'w', compression=zipfile.ZIP_DEFLATED) as archive:
        archive.writestr('reviewed_dataset.json', manifest)
        archive.writestr('README.txt',
            'JazzDialog pilot manual annotations\n\n'
            'Open reviewed_dataset.json. MIDI paths are relative to this archive root.\n'
            'Each MIDI contains CALL and RESPONSE tracks. MIDI time starts at call onset;\n'
            'JSON note times are seconds from the solo origin. MIDI rounding tolerance: 5 ms.\n'
            'DA labels are human judgments. Overlapping versions are retained and flagged;\n'
            'annotation_count is not a count of independent final examples.\n'
            'Use evaluation_group to keep the same solo out of both training and test.\n\n'
            'Source: Weimar Jazz Database, Jazzomat Research Project\n'
            'https://jazzomat.hfm-weimar.de/\n'
            'WJD source database: Open Data Commons Open Database License (ODbL).\n'
            'https://opendatacommons.org/licenses/odbl/1-0/\n'
            'Source database and review CSV are not bundled. source_csv/source_sha256\n'
            'identify provenance in the project, not another required archive member.\n'
            'Project: https://github.com/NikolinaZdravkovic/jazzdialog\n')
        for name, payload in members.items():
            archive.writestr(name, payload)
    buffer.seek(0)
    verify_package(buffer)
    buffer.seek(0)
    with zipfile.ZipFile(buffer) as archive:
        if archive.testzip() is not None:
            raise ValueError('ZIP checksum validation failed')
        if json.loads(archive.read('reviewed_dataset.json')) != result:
            raise ValueError('ZIP manifest mismatch')
        for name, payload in members.items():
            if archive.read(name) != payload:
                raise ValueError('ZIP MIDI bytes changed: '+name)
    return manifest, buffer.getvalue()


def export(result, package=False):
    if package:
        manifest, payload = package_bytes(result)
    else:
        manifest = (json.dumps(result, ensure_ascii=False, indent=2)+'\n').encode('utf-8')
    if hashlib.sha256(SOURCE.read_bytes()).hexdigest() != result['source_sha256']:
        raise ValueError('Source changed before export; rerun')
    # All validation finishes before touching either previous valid output.
    temporary = OUTPUT.with_suffix('.json.tmp')
    zip_temporary = PACKAGE.with_suffix('.zip.tmp')
    try:
        temporary.write_bytes(manifest)
        if package:
            zip_temporary.write_bytes(payload)
        temporary.replace(OUTPUT)
        if package:
            zip_temporary.replace(PACKAGE)
    finally:
        temporary.unlink(missing_ok=True)
        if package:
            zip_temporary.unlink(missing_ok=True)


def _overlap_groups(records):
    """Vrati stabilan ID povezane komponente preklapajucih anotacija."""
    parent = {record["id"]: record["id"] for record in records}

    def find(item):
        while parent[item] != item:
            parent[item] = parent[parent[item]]
            item = parent[item]
        return item

    def union(first, second):
        first, second = find(first), find(second)
        if first != second:
            parent[second] = first

    for record in records:
        for other in record["overlapping_ids"]:
            union(record["id"], other)
    components = {}
    for record in records:
        components.setdefault(find(record["id"]), []).append(record["id"])
    group_by_id = {}
    for members in components.values():
        if len(members) > 1:
            group = "overlap:" + min(members)
            group_by_id.update({member: group for member in members})
    return group_by_id


def _final_csv_rows(result):
    """Izravnaj provereni manifest za pregled u Excelu i analizu u Pythonu."""
    groups = _overlap_groups(result["records"])
    rows = []
    for record in result["records"]:
        call, response = record["call"], record["response"]
        call_notes, response_notes = call["notes"], response["notes"]
        rows.append({
            "pair_id": record["id"],
            "melid": record["melid"],
            "title": record["title"],
            "performer": record["performer"],
            "evaluation_group": record["evaluation_group"],
            "call_start_note": call["start_note"],
            "call_end_note_exclusive": call["end_note_exclusive"],
            "response_start_note": response["start_note"],
            "response_end_note_exclusive": response["end_note_exclusive"],
            "call_start_seconds": call_notes[0]["onset_seconds"],
            "response_start_seconds": response_notes[0]["onset_seconds"],
            "response_end_seconds": (
                response_notes[-1]["onset_seconds"] + response_notes[-1]["duration_seconds"]
            ),
            "call_note_count": len(call_notes),
            "response_note_count": len(response_notes),
            "call_pitches": json.dumps([note["pitch"] for note in call_notes]),
            "response_pitches": json.dumps([note["pitch"] for note in response_notes]),
            "candidate_source": record["candidate_source"],
            "midi_file": record["midi"],
            "overlap_group": groups.get(record["id"], ""),
            "overlapping_pair_ids": json.dumps(record["overlapping_ids"]),
            "preferred_annotation_id": record.get("preferred_annotation_id", ""),
        })
    return rows


def export_final_csv(result, destination=FINAL_CSV):
    """Upisi samo DA parove nakon sto su manifest i MIDI vec provereni."""
    rows = _final_csv_rows(result)
    if len(rows) != result["annotation_count"] or len({row["pair_id"] for row in rows}) != len(rows):
        raise ValueError("Final CSV identity check failed")
    fields = list(rows[0]) if rows else ["pair_id"]
    buffer = io.StringIO(newline="")
    writer = csv.DictWriter(buffer, fieldnames=fields)
    writer.writeheader()
    writer.writerows(rows)
    # Proveri ono sto ce Excel otvoriti, pre zamene prethodnog fajla.
    parsed = list(csv.DictReader(io.StringIO(buffer.getvalue())))
    if len(parsed) != len(rows) or {row["pair_id"] for row in parsed} != {row["pair_id"] for row in rows}:
        raise ValueError("Final CSV round-trip check failed")
    temporary = destination.with_suffix(".csv.tmp")
    try:
        temporary.write_text(buffer.getvalue(), encoding="utf-8-sig", newline="")
        temporary.replace(destination)
    finally:
        temporary.unlink(missing_ok=True)
    return len(rows), sum(bool(row["overlap_group"]) for row in rows)


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--export", action="store_true")
    parser.add_argument("--package", action="store_true", help="Export JSON and one validated portable ZIP with MIDI files")
    parser.add_argument("--final-csv", action="store_true", help="Export only confirmed DA pairs as an Excel-friendly CSV")
    parser.add_argument("--verify-package", type=Path, metavar="ZIP", help="Check ZIP without WJD, CSV or local MIDI")
    parser.add_argument("--review", action="store_true", help="Show overlapping versions from the verified package")
    args = parser.parse_args()
    if (args.verify_package or args.review) and (args.export or args.package or args.final_csv):
        parser.error('Review/verification cannot be combined with export')
    if args.verify_package or args.review:
        result = verify_package(args.verify_package or PACKAGE)
        if args.review:
            print_review(result)
        else:
            print(f"Package verified: {result['annotation_count']} annotations. WJD and CSV were not needed.")
        raise SystemExit(0)
    result = build()
    print(f"Verified DA annotations: {result['annotation_count']}; overlapping annotations: {result['annotations_needing_overlap_review']}")
    for record in result['records']:
        if record['overlapping_ids']:
            print(record['id'], 'overlaps', ', '.join(record['overlapping_ids']))
    if args.export or args.package:
        export(result, package=args.package)
        print(OUTPUT)
        if args.package:
            print(PACKAGE)
    if args.final_csv:
        count, overlapping = export_final_csv(result)
        print(f"{FINAL_CSV} ({count} DA annotations; {overlapping} in overlap groups)")
