# JazzDialog

JazzDialog je naučno-istraživački Python projekat čiji je cilj izgradnja dataseta **call-and-response parova u jazzu**.

Aktuelna detekcija poredi call i response unutar jedne zvanične WJD fraze pomoću globalnog DTW-a i incipita. Za nove kandidate traži najmanje 5 nota po segmentu, ograničava odnos dužina call-a i response-a i pamti ručno označene `NE` podele. Spajanje susednih WJD fraza je isključeno za nove kandidate, dok raniji ručno označeni redovi preko granice ostaju sačuvani u CSV-u kao istorijski primeri.

Rezultati se čuvaju u `output/wjd_phrase_call_response.csv`. Svaki kandidat se zatim ručno preslušava i označava:

- `DA` — validan call-and-response par;
- `NE` — kandidat nije call-and-response;
- prazno — kandidat još nije pregledan.

Pri svakom pokretanju za svaki red iz CSV-a automatski se generiše MIDI isečak u `output/wjd_phrase_excerpts`. Isečak sadrži samo pronađeni call i response sa originalnim ritmom, a kolona `excerpt_midi` čuva njegovu tačnu putanju.

Raniji ocenjeni CSV redovi i ručne oznake ostaju sačuvani. Nepregledani kandidati zamenjuju se rezultatima novog pokretanja. Ako se CSV promeni tokom pretrage, skripta ga neće prepisati.

Posle izbora kandidata proverava se pauza jednu notu levo/desno od granice. Susedna pauza mora trajati najmanje 0.15 s i biti bar 0.05 s duža od trenutne. Podela se pomera samo ako nova podela zadovoljava postojeće uslove dužine, trajanja i skora. Ovo su eksperimentalni parametri, ne validirana muzička pravila.

Kolone `boundary_original_split` i `boundary_original_score` čuvaju prvobitni rezultat. `boundary_suggested_split` i `boundary_suggested_gap_seconds` prikazuju predlog, a `boundary_status` objašnjava odluku: `shifted_to_breath` znači da je granica pomerena; `review_length_or_duration` ili `review_score` znače da je samo predložena za ručni pregled. U tom slučaju MIDI i pitch nizovi ostaju na stvarnoj granici `split_point_local`. Ručno potvrđene granice se ne pomeraju. Ispravka sa `manual_original_split` blokira staru podelu, ali je ne koristi kao negativan muzički primer.

Za probu bez upisa ili brisanja fajlova, funkcija `search_wjd_phrases` prihvata `write_outputs=False`.

## Pokretanje

U `SEARCH_ITEMS` unutar `scripts/search_wjd_phrase_splits.py` upiši željene WJD `melid` brojeve, a zatim pokreni:

```powershell
.\venv\Scripts\python.exe scripts\search_wjd_phrase_splits.py
```

Potrebni paketi su `dtaidistance` i `pretty_midi`. Datoteka `wjazzd.db` čuva se lokalno u folderu `data_midi` i nije uključena u repozitorijum.

Pre detekcije možeš proveriti koliko fraza u grupi ima dovoljno nota i trajanja:

```powershell
.\venv\Scripts\python.exe scripts\search_wjd_phrase_splits.py --audit
```

Opcija `--melids 26 27 28` bira pesme bez menjanja `SEARCH_ITEMS`. Opcija `--dry-run` pokreće detekciju bez upisa ili brisanja CSV/MIDI fajlova. Svako pokretanje prikazuje razloge odbacivanja i najmanji prilagođeni skor po pesmi. „Podobna” znači samo da fraza zadovoljava ograničenja dužine, a ne da je muzički validan CR. Nula rezultata zato nije dokaz da u solu nema CR parova, posebno onih koji prelaze granice WJD fraza.

## Evaluacija ručnih oznaka

Nakon što se kandidati označe sa `DA` ili `NE`, pokreni:

```powershell
.\venv\Scripts\python.exe scripts\evaluate_labelled_pairs.py
```

Skripta samo čita CSV i poredi odvojeno DTW, intervalski motiv, oblik DTW puta i gustinu nota. Ne menja rezultate, MIDI fajlove ni ručne oznake.

Za nove neproverene kandidate pretraga u CSV dodaje kolone `note_density`, `motif_run_fraction`, `dtw_diagonal_fraction` i `review_priority`. Kandidati sa manjim `review_priority` stoje prvi za ručni pregled; to je redosled pregleda, ne automatska oznaka `DA`.

## Izvoz potvrđenog dataseta

Za izvoz svih ručno označenih `DA` primera pokreni:

```powershell
.\venv\Scripts\python.exe scripts\export_reviewed_dataset.py --export
```

Rezultat je `output/reviewed_dataset.json`: početni dataset sa pitch vrednostima, originalnim vremenima i trajanjima nota, granicama call-a i response-a i putanjama do postojećih MIDI fajlova. Bez `--export` komanda samo proverava podatke. Provera poredi note i oba MIDI kanala sa bazom; greška sprečava novi izvoz.

`overlapping_ids` označava preklapajuće verzije koje treba zajedno pregledati pre konačnog izdanja. One ostaju sačuvane, ali broj anotacija nije nužno broj nezavisnih parova. `evaluation_group` grupiše isti solo za odvajanje treninga i testa. Putanje MIDI fajlova su relativne prema korenu projekta. Originalni CSV ostaje mesto za tvoje DA/NE oznake; JSON je izvedeni snimak i treba ponovo izvesti nakon novih ocena.

Za prenosiv paket sa JSON-om, postojećim MIDI isečcima i kratkim uputstvom pokreni:

```powershell
.\venv\Scripts\python.exe scripts\export_reviewed_dataset.py --package
```

Komanda proverava podatke i pravi `output/reviewed_dataset.zip`, a osvežava i JSON. Raspakuj ZIP i otvori MIDI iz putanje navedene u manifestu; WJD baza nije potrebna za preslušavanje. Paket zadržava preklapajuće verzije kao pilot anotacije. Provera tačnih MIDI bajtova, nota, tajminga i putanja završava se pre zamene prethodnog izvoza; greška validacije ostavlja prethodni paket sačuvan. Izvorni CSV i WJD baza nisu u paketu.

JSON i kanonski ZIP sa MIDI-jima su u Git-u i lokalno u `output`; pojedinačni MIDI fajlovi ostaju na svojim mestima.

## Izvor podataka

Weimar Jazz Database je deo [Jazzomat Research Project](https://jazzomat.hfm-weimar.de/) i dostupna je pod Open Data Commons Open Database License (ODbL).
