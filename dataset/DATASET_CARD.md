# JazzDialog v1.0

## Dataset summary

JazzDialog v1.0 is a human-verified dataset of **109 jazz call-and-response
annotations** from monophonic Weimar Jazz Database (WJD) solo transcriptions.
Every released row has been listened to and explicitly marked `DA` by the
project reviewer. It is a curated positive dataset, not an automatically
labeled benchmark or an exhaustive list of every call-response event in WJD.

| Release fact | Value |
| --- | --- |
| Version | 1.0.0 |
| Release date | 2026-09-26 |
| Confirmed annotations | 109 |
| WJD solos | 74 |
| Tune titles | 71 |
| Performers | 42 |
| Call / response notes | 1,070 / 1,205 |
| Median call / response length | 9 / 10 notes |
| Annotations in overlap groups | 15 across 7 groups |

Records are alphabetically ordered by `performer`, `title`, then position in
the solo. `JD0001`–`JD0109` are frozen, readable IDs for this release.
`source_pair_id` is the stable WJD boundary identity:
`wjd:<melid>:<call_start>:<response_start>:<response_end>`.

## Files

| File | Contents |
| --- | --- |
| `jazzdialog_v1.0.csv` | One Excel-friendly row per confirmed pair. |
| `jazzdialog_v1.0.json` | Full machine-readable manifest, including every note's pitch, onset and duration. |
| `jazzdialog_v1.0_midi.zip` | Portable JSON manifest plus one original-timing MIDI excerpt per pair. Each excerpt has `CALL` and `RESPONSE` tracks. |
| `DATASET_CARD.md` | Documentation, provenance, limitations and usage guidance. |

The ZIP is verified before release against the JSON manifest and does not need
the local WJD SQLite database to be checked or played.

## CSV schema

| Field group | Meaning |
| --- | --- |
| `jazzdialog_id`, `dataset_version`, `source_pair_id` | Release ID, version and stable WJD boundary reference. |
| `wjd_melid`, `performer`, `title` | WJD source identity. |
| `instrument`, `style`, `avgtempo_bpm`, `tempo_class`, `rhythm_feel`, `key`, `time_signature` | WJD solo-level metadata. |
| `call_*`, `response_*` | Zero-based, end-exclusive note boundaries and solo-relative seconds. |
| `call_pitches`, `response_pitches` | JSON arrays of MIDI pitch values. |
| `midi_member` | Relative path to the excerpt inside the MIDI ZIP. |
| `candidate_family`, `candidate_source` | Readable candidate family and precise generation provenance; neither is a label or confidence score. |
| `evaluation_group` | `wjd-solo:<melid>`; use it to keep one solo in only one evaluation split. |
| `overlap_group`, `overlapping_pair_ids`, `preferred_annotation_id` | Explicit metadata for overlapping valid boundary versions. |

The JSON is authoritative for all note-level onset and duration information.
Pitch values are WJD MIDI-note numbers. Indices are zero-based within a solo;
all end indices are exclusive, like Python slicing.

## Source and composition

WJD supplies the transcriptions, note timing, pitch, phrase and midlevel-unit
annotations, beat grid and solo metadata. The local source used here is WJazzD
release 2.1. The release spans eight styles: Postbop (30), Cool (27), Hardbop
(17), Swing (13), Bebop (7), Fusion (7), Traditional (6) and Free (2).

Instruments: tenor saxophone (46), trumpet (27), alto saxophone (21), bass
saxophone (4), clarinet (4), trombone (3), cornet (2), soprano saxophone (1)
and vibraphone (1).

## Collection and validation

1. Candidates came from official WJD phrase boundaries and adjacent WJD
   midlevel-unit relationships.
2. DTW, transposition-normalized pitch shape, segment balance and
   tempo-aware readability formed review queues only. Exploratory contour and
   rhythm comparisons were tested as well.
3. The reviewer listened to each original-timing MIDI excerpt and entered
   `DA` or `NE`. Only explicit `DA` decisions are in this release.
4. The exporter validates note pitches, onset/duration, call/response
   boundaries and both MIDI tracks against WJD before creating the release.

The internal project history retains `NE` decisions for methodological analysis,
but no `NE` row is distributed here. The tested DTW, contour and rhythm signals
did not generalize reliably enough to be a high-precision automatic acceptor on
unseen solos. Accordingly, every record has `annotation_status=human_confirmed`.

## Recommended use and limitations

- Use CSV for browsing and descriptive analysis; use JSON or MIDI when timing
  is required.
- Split train/validation/test data by `evaluation_group`, never independently
  by row.
- Overlap groups contain distinct approved boundaries but are not independent
  observations.
- v1.0 has one musical reviewer; no inter-annotator agreement is available.
- The release models symbolic pitch and timing. It does not encode a complete
  theory of harmony, articulation, timbre or jazz call-and-response.
- Candidate provenance can introduce sampling bias; `candidate_source` remains
  in the data so it can be studied rather than hidden.

## Reproducibility

The canonical review history is `output/wjd_phrase_call_response.csv`. Rebuild
the versioned release from the repository root:

```powershell
.\venv\Scripts\python.exe scripts\export_reviewed_dataset.py --release
```

Check a copied archive without WJD:

```powershell
python scripts\export_reviewed_dataset.py --verify-package dataset\jazzdialog_v1.0_midi.zip
```

## License, citation and references

JazzDialog is derived from WJD. The source database is distributed under the
[Open Database License (ODbL) 1.0](https://opendatacommons.org/licenses/odbl/1-0/)
and its individual contents under the [Database Contents License
(DbCL) 1.0](https://opendatacommons.org/licenses/dbcl/1-0/). Users must follow
those terms and cite WJD.

```bibtex
@dataset{zdravkovic_2026_jazzdialog,
  author  = {Zdravkovic, Nikolina},
  title   = {JazzDialog: Human-Verified Jazz Call-and-Response Pairs},
  version = {1.0.0},
  year    = {2026},
  url     = {https://github.com/NikolinaZdravkovic/jazzdialog}
}
```

1. Pfleiderer, M., Frieler, K., Abeßer, J., Zaddach, W.-G. and Burkhart, B.
   (eds.). *Inside the Jazzomat: New Perspectives for Jazz Research*. Schott
   Campus, 2017. This is the citation requested by the [WJD project
   page](https://jazzomat.hfm-weimar.de/dbformat/dboverview.html).
2. [Jazzomat WJD database format](https://jazzomat.hfm-weimar.de/dbformat/dbformat.html):
   source for `melid`, `melody`, `sections`, `solo_info` and beat metadata.
3. Salamon, J., Peeters, G. and Röbel, A. “Statistical Characterisation of
   Melodic Pitch Contours and Its Application for Melody Extraction.” ISMIR,
   2012. [Paper](https://www.justinsalamon.com/uploads/4/3/9/4/4394963/salamonmelodiccontourismir12.pdf).
   It motivated the exploratory contour analysis only; its task differs from
   JazzDialog's symbolic-pair task.
4. Gebru, T. *et al.* “Datasheets for Datasets.” *Communications of the ACM*,
   64(12), 2021. [DOI](https://doi.org/10.1145/3458723). Its documentation
   approach informed this dataset card.
5. Wilkinson, M. D. *et al.* “The FAIR Guiding Principles for Scientific Data
   Management and Stewardship.” *Scientific Data*, 3, 160018, 2016.
   [DOI](https://doi.org/10.1038/sdata.2016.18). Persistent IDs, metadata,
   provenance and license information follow these principles.
