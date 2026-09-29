# JazzDialog

JazzDialog je skup ručno potvrđenih call-and-response parova izdvojenih iz transkribovanih jazz improvizacija. Projekat povezuje računarsku analizu sa slušanjem: program predlaže i rangira kandidate, a muzičku smislenost svakog para potvrđuje čovek.

## Postupak

```text
transkribovani solo → kandidati → numeričke osobine → rangiranje → slušanje i ručna potvrda → JazzDialog
```

Melodijska sličnost sama po sebi, uključujući DTW, nije dovoljna da pouzdano odredi call-and-response odnos. Rangiranje zato služi da odredi redosled ručnog pregleda; nije automatski klasifikator.

## Konačna baza

Kolekcija sadrži **114 potvrđenih parova** iz **76 sola**, **73 naslova** i **42 izvođača**.

- [`dataset/jazzdialog.csv`](dataset/jazzdialog.csv) — glavna tabela sa pozitivnim, potvrđenim parovima.
- [`dataset/jazzdialog.json`](dataset/jazzdialog.json) — prošireni zapis sa notama, trajanjem i poreklom svakog para.
- [`dataset/midi/`](dataset/midi/) — 114 MIDI isečaka; `jazzdia-1.mid` odgovara prvom redu CSV-a. Svaki isečak ima odvojene CALL i RESPONSE trake.
- [`dataset/jazzdialog_midi.zip`](dataset/jazzdialog_midi.zip) — prenosivi paket CSV-a, JSON-a i MIDI isečaka.
- [`dataset/DATASET_CARD.md`](dataset/DATASET_CARD.md) — opis kolona, ograničenja, porekla i citiranja.

Za pregled otvori CSV u Excelu i MIDI fajl iz kolone `midi_file`. Granice nota su nula-indeksirane, a završni indeks je isključiv, pa `notes[start:end]` daje tačno označeni segment.

## Kod

- [`scripts/export_reviewed_dataset.py`](scripts/export_reviewed_dataset.py) — proverava i izvozi konačnu bazu.
- [`scripts/search_wjd_phrase_splits.py`](scripts/search_wjd_phrase_splits.py) — razvojna pretraga kandidata unutar anotiranih fraza.

Za proveru već napravljenog paketa, bez izvorne baze, pokreni:

```powershell
.\venv\Scripts\python.exe scripts\export_reviewed_dataset.py --verify-package dataset\jazzdialog_midi.zip
```

Za ponovni izvoz iz lokalnih radnih ručnih oznaka potrebni su WJD baza u `data_midi/wjazzd.db` i razvojni CSV u `output/`:

```powershell
.\venv\Scripts\python.exe scripts\export_reviewed_dataset.py --release
```

`data_midi/` nije deo repozitorijuma. Razvojni CSV fajlovi u `output/` čuvaju istoriju označavanja i nisu konačna baza.

## Izvor i prava

Transkripcije i anotacije potiču iz [Weimar Jazz Database / Jazzomat Research Project](https://jazzomat.hfm-weimar.de/). WJD je objavljen pod [ODbL 1.0](https://opendatacommons.org/licenses/odbl/1-0/), a sadržaji baze pod [DbCL 1.0](https://opendatacommons.org/licenses/dbcl/1-0/); detalji o poreklu i ograničenjima nalaze se u [kartici baze](dataset/DATASET_CARD.md). Audio snimci nisu uključeni.
