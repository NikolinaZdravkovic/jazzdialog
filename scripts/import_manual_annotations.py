"""Preserve manual XLSX annotations and locate exact pitch sequences in WJD.

This produces mapping proposals, never DA/NE decisions or guessed octaves.
No dependencies beyond the Python standard library.
"""
import argparse
import csv
import hashlib
import json
import re
import sqlite3
import xml.etree.ElementTree as ET
import zipfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
NS = {'s':'http://schemas.openxmlformats.org/spreadsheetml/2006/main'}
NOTE = re.compile(r'([A-GR])([#b]?)(-?\d+)?\(([^()]*)\)')
PC = {'C':0,'D':2,'E':4,'F':5,'G':7,'A':9,'B':11}


def read_sheet(path):
    with zipfile.ZipFile(path) as archive:
        strings = []
        if 'xl/sharedStrings.xml' in archive.namelist():
            shared = ET.fromstring(archive.read('xl/sharedStrings.xml'))
            strings = [''.join(n.itertext()) for n in shared.findall('s:si', NS)]
        sheet = ET.fromstring(archive.read('xl/worksheets/sheet1.xml'))
        rows = []
        for row in sheet.findall('s:sheetData/s:row', NS):
            values = {}
            for cell in row.findall('s:c', NS):
                column = re.sub(r'\d','',cell.attrib['r'])
                kind = cell.get('t')
                if kind=='inlineStr':
                    value = ''.join(n.text or '' for n in cell.findall('.//s:t',NS))
                else:
                    value = cell.findtext('s:v','',NS)
                    if kind=='s' and value:
                        value = strings[int(value)]
                values[column] = value
            rows.append((int(row.attrib['r']),values))
    header = rows[0][1]
    return [(number,{header[col]:value for col,value in values.items() if col in header})
            for number,values in rows[1:]]


def pitches(text):
    """Remove chord labels, keep rests/slide out of pitch matching, merge ties.

    Durations remain in raw text: unusual tuplets are not reinterpreted here.
    Missing octaves block an exact match instead of being silently assigned.
    """
    cleaned = re.sub(r'\[[^\]]*\]','',text or '')
    notes, issues = [], []
    end = 0
    previous_was_rest = False
    for match in NOTE.finditer(cleaned):
        between = cleaned[end:match.start()]
        if re.sub(r'[\s_~]','',between):
            issues.append('unparsed_notation')
        name, accidental, octave, duration = match.groups()
        end = match.end()
        if name=='R':
            previous_was_rest = True
            continue
        if octave is None:
            issues.append('missing_octave')
            pitch = None
        else:
            pitch = (int(octave)+1)*12+PC[name]+(1 if accidental=='#' else -1 if accidental=='b' else 0)
            if not 0<=pitch<=127:
                issues.append('invalid_pitch')
        if not duration:
            issues.append('missing_duration')
        if '_' in between and notes and not previous_was_rest:
            if pitch is not None and pitch==notes[-1]:
                continue
            issues.append('invalid_tie')
        notes.append(pitch)
        previous_was_rest = False
    if re.sub(r'[\s_~]','',cleaned[end:]):
        issues.append('unparsed_notation')
    return notes, sorted(set(issues))


def occurrences(sequence, query):
    if not query:
        return []
    return [i for i in range(len(sequence)-len(query)+1) if sequence[i:i+len(query)]==query]


def export_preview(result, identifier):
    """Export one unconfirmed mapping for listening, using original WJD timing."""
    import pretty_midi

    record = next((r for r in result['records'] if r['id']==identifier), None)
    if record is None or len(record['candidates'])!=1:
        raise ValueError('Preview requires exactly one mapping proposal for the requested ID.')
    candidate = record['candidates'][0]
    confirmed = [link for link in candidate.get('existing_annotations', []) if link.get('label')=='DA']
    if confirmed:
        path = ROOT / confirmed[0]['midi']
        if path.exists():
            return path
    with sqlite3.connect((ROOT/'data_midi/wjazzd.db').resolve().as_uri()+'?mode=ro',uri=True) as conn:
        events = conn.execute('SELECT onset,pitch,duration FROM melody WHERE melid=? ORDER BY eventid',
                              (record['melid'],)).fetchall()
    midi = pretty_midi.PrettyMIDI()
    origin = events[candidate['call_start']][0]
    for name, start, end in (
            ('CALL',candidate['call_start'],candidate['call_end_exclusive']),
            ('RESPONSE',candidate['response_start'],candidate['response_end_exclusive'])):
        track = pretty_midi.Instrument(program=0,name=name)
        for onset,pitch,duration in events[start:end]:
            track.notes.append(pretty_midi.Note(velocity=95,pitch=round(pitch),
                                                start=onset-origin,end=onset+duration-origin))
        midi.instruments.append(track)
    target = ROOT/'output/wjd_phrase_excerpts'/f"manual_{record['id'].split(':')[1]}_melid_{record['melid']}_UNCONFIRMED.mid"
    target.parent.mkdir(parents=True,exist_ok=True)
    temporary = target.with_suffix('.tmp.mid')
    try:
        midi.write(str(temporary))
        loaded = pretty_midi.PrettyMIDI(str(temporary))
        assert len(loaded.instruments)==2, 'Preview lost a track'
        for expected, actual in zip(midi.instruments,loaded.instruments):
            assert len(expected.notes)==len(actual.notes), 'Preview lost notes'
            for a,b in zip(expected.notes,actual.notes):
                assert a.pitch==b.pitch and abs(a.start-b.start)<0.005 and abs(a.end-b.end)<0.005, 'Preview timing/pitch mismatch'
        temporary.replace(target)
    finally:
        temporary.unlink(missing_ok=True)
    return target


def import_annotations(workbook):
    records = []
    with (ROOT/'output/wjd_phrase_call_response.csv').open(encoding='utf-8-sig',newline='') as stream:
        existing=list(csv.DictReader(stream))
    conn = sqlite3.connect((ROOT/'data_midi/wjazzd.db').resolve().as_uri()+'?mode=ro',uri=True)
    cache = {}
    try:
        for row_number, raw in read_sheet(workbook):
            if not any(raw.values()):
                continue
            pair_id = str(int(float(raw['pair_id'])))
            record = dict(id='manual:'+pair_id, excel_row=row_number, original=raw, candidates=[])
            records.append(record)
            if not raw.get('call_notes') and not raw.get('response_notes'):
                record['status']='empty_template_row'
                continue
            call, ci = pitches(raw.get('call_notes'))
            response, ri = pitches(raw.get('response_notes'))
            record.update(call_pitches=call,response_pitches=response,notation_issues=sorted(set(ci+ri)))
            if not call or not response:
                record['status']='incomplete_pair'
                continue
            match = re.search(r'/solo(\d+)\.html',raw.get('source',''))
            if not match:
                record['status']='external_source_requires_recording_identity'
                continue
            melid = int(match[1])
            record['melid']=melid
            if melid not in cache:
                events=conn.execute('SELECT onset,pitch,duration FROM melody WHERE melid=? ORDER BY eventid',(melid,)).fetchall()
                sections=conn.execute("SELECT start,end,value FROM sections WHERE melid=? AND type='PHRASE' ORDER BY start",(melid,)).fetchall()
                cache[melid]=(events,sections)
            events,sections=cache[melid]
            if not events:
                record['status']='missing_wjd_solo'
                continue
            if ci or ri:
                record['status']='notation_requires_review'
                continue
            if raw.get('call_notes','').rstrip().endswith('_') or raw.get('response_notes','').lstrip().startswith('_'):
                record['status']='boundary_inside_tied_note_requires_review'
                continue
            seq=[round(e[1]) for e in events]
            calls,responses=occurrences(seq,call),occurrences(seq,response)
            for left in calls:
                for split in responses:
                    if split < left+len(call):
                        continue
                    right=split+len(response)
                    spans=[str(v) for a,b,v in sections if a<right and b>=left]
                    record['candidates'].append(dict(call_start=left,call_end_exclusive=left+len(call),
                        response_start=split,response_end_exclusive=right,
                        call_start_seconds=events[left][0],response_start_seconds=events[split][0],
                        end_seconds=max(e[0]+e[2] for e in events[split:right]),
                        gap_notes=split-left-len(call),wjd_phrases=spans,
                        fits_one_wjd_phrase=any(a<=left and b>=right-1 for a,b,v in sections)))
            n=len(record['candidates'])
            record['status']='unique_exact_pitch_proposal' if n==1 else 'ambiguous_exact_pitch_proposals' if n else 'no_exact_pitch_match'
            if n==0:
                # Octave alternatives are explicit proposals, never corrections.
                for shift in (-24,-12,12,24):
                    for left in occurrences(seq,[p+shift for p in call]):
                        for split in occurrences(seq,[p+shift for p in response]):
                            if split<left+len(call):
                                continue
                            right=split+len(response)
                            record['candidates'].append(dict(call_start=left,call_end_exclusive=left+len(call),
                                response_start=split,response_end_exclusive=right,
                                octave_shift_semitones=shift,call_start_seconds=events[left][0],
                                response_start_seconds=events[split][0],end_seconds=max(e[0]+e[2] for e in events[split:right]),
                                gap_notes=split-left-len(call),wjd_phrases=[str(v) for a,b,v in sections if a<right and b>=left],
                                fits_one_wjd_phrase=any(a<=left and b>=right-1 for a,b,v in sections)))
                if record['candidates']:
                    record['status']='octave_shift_requires_review'
            if not record['candidates']:
                # Konzervativna pomoc za rucne transkripcije: call mora biti
                # tacan, response mora poceti odmah iza njega i sme imati
                # samo jednu razlicitu pitch vrednost u istom indeksu.
                # Ne koristi DTW, pa ne pretvara proizvoljnu slicnost u mapu.
                for shift in (-24, -12, 0, 12, 24):
                    shifted_call = [p + shift for p in call]
                    shifted_response = [p + shift for p in response]
                    for left in occurrences(seq, shifted_call):
                        split = left + len(call)
                        right = split + len(response)
                        observed_response = seq[split:right]
                        if len(observed_response) != len(response):
                            continue
                        differing = [index for index, (expected, observed) in enumerate(
                            zip(shifted_response, observed_response)
                        ) if expected != observed]
                        if len(differing) != 1:
                            continue
                        record['candidates'].append(dict(
                            call_start=left, call_end_exclusive=split,
                            response_start=split, response_end_exclusive=right,
                            one_pitch_mismatch_at=differing[0],
                            written_response_pitch=shifted_response[differing[0]],
                            wjd_response_pitch=observed_response[differing[0]],
                            call_start_seconds=events[left][0],
                            response_start_seconds=events[split][0],
                            end_seconds=max(e[0]+e[2] for e in events[split:right]),
                            gap_notes=0,
                            wjd_phrases=[str(v) for a,b,v in sections if a<right and b>=left],
                            fits_one_wjd_phrase=any(a<=left and b>=right-1 for a,b,v in sections),
                        ))
                if len(record['candidates']) == 1:
                    record['status']='near_exact_pitch_proposal_requires_review'
                elif record['candidates']:
                    record['status']='ambiguous_near_exact_pitch_proposals_requires_review'
            for candidate in record['candidates']:
                links=[]
                for old in existing:
                    if old['melid']!=str(melid):
                        continue
                    old_start=int(old['phrase_start_index'])
                    left=old_start+int(old.get('call_start_local') or 0)
                    split=old_start+int(old['split_point_local'])
                    right=old_start+int(old.get('response_end_local_exclusive') or int(old['phrase_end_index_inclusive'])-old_start+1)
                    if (left,split,right)==(candidate['call_start'],candidate['response_start'],candidate['response_end_exclusive']) and candidate['gap_notes']==0:
                        midi_path = Path(old['excerpt_midi'])
                        try:
                            midi_path = midi_path.resolve().relative_to(ROOT)
                        except ValueError:
                            pass
                        links.append(dict(id=f'wjd:{melid}:{left}:{split}:{right}',label=old['validnost'],midi=midi_path.as_posix()))
                candidate['existing_annotations']=links
    finally:
        conn.close()
    counts={status:sum(r['status']==status for r in records) for status in sorted({r['status'] for r in records})}
    return dict(source_file=workbook.name,source_sha256=hashlib.sha256(workbook.read_bytes()).hexdigest(),
                status='manual_reference_mapping_proposals',
                policy='Original spreadsheet preserved. Unique pitch matches require boundary/rhythm review before merging into confirmed dataset. Octave shifts are explicit proposals only; missing octaves and tuplet durations are not guessed.',
                notation_context={'underscore':'tied notes; merged within a segment only',
                                  'tilde':'slide; both written pitches retained',
                                  'manual_17_duration':'User previously corrected D5(1/14) to D5(1/4); raw text retained, durations not used for matching',
                                  'tuplets':'Original T5/T6 notation preserved; no timing reconstructed'},
                counts=counts,records=records)


if __name__=='__main__':
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('workbook',type=Path)
    parser.add_argument('--export',action='store_true')
    parser.add_argument('--preview',help='Manual ID, e.g. manual:11; writes one UNCONFIRMED MIDI, never changes CSV')
    args=parser.parse_args()
    result=import_annotations(args.workbook)
    print(json.dumps(result['counts'],ensure_ascii=False))
    for r in result['records']:
        if r['status']!='empty_template_row':
            print(r['id'],r['original'].get('tune_title'),r['status'],r['candidates'])
    if args.export:
        target=ROOT/'output/manual_reference_mapping.json'
        temporary=target.with_suffix('.json.tmp')
        temporary.write_text(json.dumps(result,ensure_ascii=False,indent=2)+'\n',encoding='utf-8')
        temporary.replace(target)
        print(target)
    if args.preview:
        print(export_preview(result,args.preview))
