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
from fractions import Fraction
from pathlib import Path

try:
    from .find_internal_split import _dtw_norm
except ImportError:
    from find_internal_split import _dtw_norm

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


def notation_events(text):
    """Parse explicit pitches and notated onsets; keep unknown octaves unknown.

    T5/T6 are preserved without guessing their metric interpretation. Ordinary
    T denotes a triplet. Rests advance the notated clock, not the note index.
    """
    clean = re.sub(r'\[[^\]]*\]', '', text or '')
    result, cursor, end, rest = [], 0., 0, False
    for match in NOTE.finditer(clean):
        name, accidental, octave, raw_duration = match.groups()
        between = clean[end:match.start()]
        if re.sub(r'[\s_~]', '', between):
            raise ValueError('unparsed notation: ' + between)
        end = match.end()
        duration = raw_duration.replace('1/14', '1/4')
        try:
            if re.search(r'T\d', duration):
                raise ValueError('unspecified tuplet ratio')
            triplet = duration.endswith('T')
            duration = duration.removesuffix('T')
            dotted = duration.startswith('dotted-')
            duration = duration.removeprefix('dotted-')
            beats = float(sum(Fraction(term) for term in duration.split('+'))) * 4
            beats *= (2/3 if triplet else 1) * (1.5 if dotted else 1)
        except (ValueError, ZeroDivisionError):
            beats = None
        if name == 'R':
            rest = True
        else:
            pc = (PC[name] + (1 if accidental == '#' else -1 if accidental == 'b' else 0)) % 12
            pitch = (int(octave)+1)*12 + PC[name] + (1 if accidental == '#' else -1 if accidental == 'b' else 0) if octave else None
            tied = ('_' in between and result and not rest
                    and result[-1]['pitch'] == pitch and result[-1]['pitch_class'] == pc)
            if not tied:
                result.append(dict(pitch=pitch, pitch_class=pc, onset_beats=cursor,
                                   spelling=name+accidental+(octave or '')))
            rest = False
        cursor = cursor + beats if cursor is not None and beats is not None else None
    if re.sub(r'[\s_~]', '', clean[end:]):
        raise ValueError('unparsed trailing notation')
    return result


def reconcile(workbook, merge=False):
    """Locate all manual references and optionally merge verified WJD mappings.

    New near-exact mappings require a unique adjacent full-pair location with
    >=90% pitch agreement and <=2 spelling differences, plus explicitly
    checked source-score corrections below. This is import of user-confirmed
    references, never automatic acceptance of detector candidates.
    """
    import numpy as np
    from search_wjd_phrase_splits import _write_excerpt_midi
    from extract_wjd_phrases import get_melody_events

    # WJD source scores visually checked on 2026-09-28. Indices are local to
    # the combined manual pair, after merging written ties. No global fuzzy
    # matcher is allowed to promote a different discrepancy automatically.
    checked_corrections = {
        12: {10: (68, 56)},       # written Ab one octave too high; missing E octave mapped by context
        13: {8: (57, 56), 13: (57, 56)},  # Ab key signature at both notes
        18: {12: (58, 59)},       # B natural rather than Bb
        19: {0: (67, 55), 6: (56, 57)},  # G octave; A natural rather than Ab
    }
    source = ROOT/'output/wjd_phrase_call_response.csv'
    snapshot = source.read_bytes()
    with source.open(encoding='utf-8-sig', newline='') as stream:
        reader = csv.DictReader(stream)
        fields, history = reader.fieldnames, list(reader)
    def key(row):
        a = int(row['phrase_start_index'])
        return (int(row['melid']), a+int(row.get('call_start_local') or 0),
                a+int(row['split_point_local']),
                a+int(row.get('response_end_local_exclusive') or int(row['phrase_end_index_inclusive'])-a+1))
    existing = {key(row): row for row in history}
    report, additions = [], []
    with sqlite3.connect((ROOT/'data_midi/wjazzd.db').resolve().as_uri()+'?mode=ro', uri=True) as conn:
        for row_number, raw in read_sheet(workbook):
            if not raw.get('call_notes') and not raw.get('response_notes'):
                continue
            pid = int(float(raw['pair_id']))
            record = dict(manual_id=pid, excel_row=row_number, original=raw)
            report.append(record)
            if not raw.get('response_notes'):
                record['status'] = 'incomplete_pair'
                continue
            call, response = notation_events(raw['call_notes']), notation_events(raw['response_notes'])
            url_match = re.search(r'/solo(\d+)\.html', raw.get('source',''))
            solos = [int(url_match[1])] if url_match else [r[0] for r in conn.execute(
                'SELECT melid FROM solo_info WHERE lower(trim(title))=lower(?)', (raw['tune_title'].strip(),))]
            if not solos:
                record['status'] = 'recording_not_in_wjd'
                continue
            # Previously listened-to mappings remain authoritative, including
            # explicitly accepted correction of the response in reference 16.
            prior = [r for r in history if str(r.get('manual_reference_id','')).split(':')[-1] == str(pid)
                     and r['validnost'].strip().upper() == 'DA']
            candidates = []
            for melid in solos:
                events = get_melody_events(conn, melid)
                sequence = [round(e[2]) for e in events]
                tied = raw['call_notes'].rstrip().endswith('_') and call[-1]['pitch'] == response[0]['pitch']
                query = call + (response[1:] if tied else response)
                shifts = (-24,-12,0,12,24) if url_match else (-14,-2,10)
                for shift in shifts:
                    for left in range(len(sequence)-len(query)+1):
                        differences, inferred = [], []
                        for j, note in enumerate(query):
                            actual = sequence[left+j]
                            if note['pitch'] is None:
                                if actual % 12 != (note['pitch_class']+shift) % 12:
                                    differences.append(dict(index=j, expected=None, actual=actual))
                                else:
                                    inferred.append(dict(index=j, spelling=note['spelling'], concert_pitch=actual))
                            elif actual != note['pitch']+shift:
                                differences.append(dict(index=j, expected=note['pitch']+shift, actual=actual))
                        if len(differences) > 2 or len(differences)/len(query) > .1:
                            continue
                        candidates.append(dict(melid=melid, left=left, split=left+len(call), right=left+len(query),
                                               transpose=shift, differences=differences, inferred_octaves=inferred,
                                               tied_boundary=tied))
            record['candidates'] = candidates
            if prior:
                matching_prior = [r for r in prior if any(
                    key(r) == (x['melid'],x['left'],x['split'],x['right']) for x in candidates)]
                k = key((matching_prior or prior)[0])
                selected = next((x for x in candidates if (x['melid'],x['left'],x['split'],x['right']) == k), None)
                record.update(status='already_confirmed', source_pair_id='wjd:' + ':'.join(map(str,k)),
                              mapping=selected or dict(melid=k[0],left=k[1],split=k[2],right=k[3],
                                                     note='Previously verified by listening; original response differs.'))
                continue
            if len(candidates) != 1:
                record['status'] = 'ambiguous_or_unmatched'
                continue
            selected = candidates[0]
            observed = {d['index']:(d['expected'],d['actual']) for d in selected['differences']}
            if observed and observed != checked_corrections.get(pid):
                record['status'] = 'notation_discrepancy_requires_review'
                continue
            melid,left,split,right = (selected[k] for k in ('melid','left','split','right'))
            events = get_melody_events(conn, melid)
            # Timing is an independent check, not a source of invented MIDI
            # durations. Report within-side onset errors in beat-grid units.
            beats = [r[0] for r in conn.execute('SELECT onset FROM beats WHERE melid=? ORDER BY onset',(melid,))]
            rhythm = []
            for manual, a, b in ((call,left,split),(response[1:] if selected['tied_boundary'] else response,split,right)):
                observed_beats = np.interp([e[1] for e in events[a:b]], beats, np.arange(len(beats)))
                expected = [n['onset_beats'] for n in manual]
                known = [j for j in range(len(expected)) if expected[j] is not None]
                if len(known) >= 2:
                    origin = known[0]
                    rhythm.extend(abs((observed_beats[j]-observed_beats[origin])-(expected[j]-expected[origin])) for j in known)
            selected['median_onset_error_beats'] = float(np.median(rhythm)) if rhythm else None
            selected['timing_note'] = 'Descriptive onset check; WJD timings exported unchanged. T5/T6 timing not guessed.'
            k = (melid,left,split,right)
            record.update(status='mapped_source_score_checked' if observed else 'mapped_exact_after_transposition',
                          mapping=selected, source_pair_id='wjd:' + ':'.join(map(str,k)))
            if k in existing:
                if existing[k]['validnost'].strip().upper() != 'DA':
                    record['status']='conflicting_existing_label'
                    continue
                if merge:
                    existing[k]['manual_reference_id']=str(pid)
                continue
            title,performer=conn.execute('SELECT title,performer FROM solo_info WHERE melid=?',(melid,)).fetchone()
            result = {field:'' for field in fields}
            result.update(validnost='DA',title=title,performer=performer,melid=melid,
                          phrase_index=f'manual:{pid}',phrase_value=f'manual:{pid}',
                          phrase_start_index=left,phrase_end_index_inclusive=right-1,
                          split_point_local=split-left,split_point_solo=split,
                          call_start_local=0,response_end_local_exclusive=right-left,
                          call_start_solo=left,response_end_solo_inclusive=right-1,
                          call_start_seconds=events[left][1],phrase_start_seconds=events[left][1],
                          response_start_seconds=events[split][1],
                          response_end_seconds=max(e[1]+e[3] for e in events[split:right]),
                          phrase_end_seconds=max(e[1]+e[3] for e in events[left:right]),
                          call_pitches=json.dumps([round(e[2]) for e in events[left:split]]),
                          response_pitches=json.dumps([round(e[2]) for e in events[split:right]]),
                          candidate_source='manual_reference_import',manual_reference_id=str(pid),
                          decision_reason='User-confirmed Excel reference, mapped to WJD; see manual_reference_mapping.json.',
                          manual_boundary_note=json.dumps(selected,ensure_ascii=False))
            if merge:
                result['excerpt_midi']=str(_write_excerpt_midi(events,result,ROOT/'output/wjd_phrase_excerpts'))
            additions.append(result)
        if merge:
            if source.read_bytes()!=snapshot:
                raise ValueError('Review CSV changed; merge cancelled')
            temp=source.with_suffix('.csv.tmp')
            with temp.open('w',encoding='utf-8-sig',newline='') as stream:
                writer=csv.DictWriter(stream,fieldnames=fields);writer.writeheader();writer.writerows(history+additions)
            temp.replace(source)
    result=dict(source_file=workbook.name,source_sha256=hashlib.sha256(workbook.read_bytes()).hexdigest(),
                purpose='Audit of user-requested manual-reference import on 2026-09-28',
                counts={status:sum(r['status']==status for r in report) for status in sorted({r['status'] for r in report})},
                added=len(additions) if merge else 0,records=report)
    if merge:
        (ROOT/'output/manual_reference_mapping.json').write_text(json.dumps(result,ensure_ascii=False,indent=2)+'\n',encoding='utf-8')
    return result


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
            boundary_tie = (raw.get('call_notes','').rstrip().endswith('_')
                            or raw.get('response_notes','').lstrip().startswith('_'))
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
            if n==0 and boundary_tie and call[-1] == response[0]:
                # Jedna vezana nota pripada kraju call-a i ne duplira se kao
                # nova MIDI nota na pocetku response-a.
                for shift in (-24, -12, 0, 12, 24):
                    combined = [p + shift for p in call + response[1:]]
                    for left in occurrences(seq, combined):
                        split = left + len(call)
                        right = left + len(combined)
                        record['candidates'].append(dict(
                            call_start=left, call_end_exclusive=split,
                            response_start=split, response_end_exclusive=right,
                            shared_tied_pitch=call[-1] + shift,
                            call_start_seconds=events[left][0],
                            response_start_seconds=events[split][0],
                            end_seconds=max(e[0]+e[2] for e in events[split:right]),
                            gap_notes=0,
                            wjd_phrases=[str(v) for a,b,v in sections if a<right and b>=left],
                            fits_one_wjd_phrase=any(a<=left and b>=right-1 for a,b,v in sections),
                        ))
                if len(record['candidates']) == 1:
                    record['status']='tied_boundary_pitch_proposal_requires_review'
                elif record['candidates']:
                    record['status']='ambiguous_tied_boundary_pitch_proposals_requires_review'
                n = len(record['candidates'])
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
            if not record['candidates']:
                # Poslednji, i dalje strogo vezan predlog: tacan call i
                # neposredan response iste duzine, sa DTW oblikom <= 0.20.
                # Ovo samo priprema MIDI za ljudsko slusanje.
                for shift in (-24, -12, 0, 12, 24):
                    shifted_call = [p + shift for p in call]
                    shifted_response = [p + shift for p in response]
                    response_shape = [p - shifted_response[0] for p in shifted_response]
                    for left in occurrences(seq, shifted_call):
                        split = left + len(call)
                        right = split + len(response)
                        observed_response = seq[split:right]
                        if len(observed_response) != len(response):
                            continue
                        score = _dtw_norm(
                            response_shape,
                            [p - observed_response[0] for p in observed_response],
                        )
                        if score > 0.20:
                            continue
                        record['candidates'].append(dict(
                            call_start=left, call_end_exclusive=split,
                            response_start=split, response_end_exclusive=right,
                            response_shape_dtw=score,
                            call_start_seconds=events[left][0],
                            response_start_seconds=events[split][0],
                            end_seconds=max(e[0]+e[2] for e in events[split:right]),
                            gap_notes=0,
                            wjd_phrases=[str(v) for a,b,v in sections if a<right and b>=left],
                            fits_one_wjd_phrase=any(a<=left and b>=right-1 for a,b,v in sections),
                        ))
                if len(record['candidates']) == 1:
                    record['status']='anchored_shape_proposal_requires_review'
                elif record['candidates']:
                    record['status']='ambiguous_anchored_shape_proposals_requires_review'
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
    parser.add_argument('--reconcile',action='store_true',help='Recheck all references against exact WJD positions and audited score corrections')
    parser.add_argument('--merge-verified',action='store_true',help='Import located user-confirmed references and save the mapping audit')
    parser.add_argument('--preview',help='Manual ID, e.g. manual:11; writes one UNCONFIRMED MIDI, never changes CSV')
    args=parser.parse_args()
    if args.reconcile or args.merge_verified:
        result=reconcile(args.workbook,merge=args.merge_verified)
        print(json.dumps(result,ensure_ascii=False,indent=2))
        raise SystemExit(0)
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
