# JazzDialog

JazzDialog je naučno-istraživački Python projekat čiji je cilj izgradnja dataseta **call-and-response parova u jazzu**.

Aktuelna detekcija poredi call i response unutar jedne zvanične WJD fraze pomoću globalnog DTW-a i incipita. Za nove kandidate traži najmanje 5 nota po segmentu, ograničava odnos dužina call-a i response-a i pamti ručno označene `NE` podele. Spajanje susednih WJD fraza je isključeno za nove kandidate, dok raniji ručno označeni redovi preko granice ostaju sačuvani u CSV-u kao istorijski primeri.

Rezultati se čuvaju u `output/wjd_phrase_call_response.csv`. Svaki kandidat se zatim ručno preslušava i označava:

- `DA` — validan call-and-response par;
- `NE` — kandidat nije call-and-response;
- prazno — kandidat još nije pregledan.

Pri svakom pokretanju za svaki red iz CSV-a automatski se generiše MIDI isečak u `output/wjd_phrase_excerpts`. Isečak sadrži samo pronađeni call i response sa originalnim ritmom, a kolona `excerpt_midi` čuva njegovu tačnu putanju.

Svi raniji CSV redovi i ručne oznake ostaju sačuvani. Ako se CSV promeni tokom pretrage, skripta ga neće prepisati.

## Pokretanje

U `SEARCH_ITEMS` unutar `scripts/search_wjd_phrase_splits.py` upiši željene WJD `melid` brojeve, a zatim pokreni:

```powershell
.\venv\Scripts\python.exe scripts\search_wjd_phrase_splits.py
```

Potrebni paketi su `dtaidistance` i `pretty_midi`. Datoteka `wjazzd.db` čuva se lokalno u folderu `data_midi` i nije uključena u repozitorijum.

## Evaluacija ručnih oznaka

Nakon što se kandidati označe sa `DA` ili `NE`, pokreni:

```powershell
.\venv\Scripts\python.exe scripts\evaluate_labelled_pairs.py
```

Skripta samo čita CSV i poredi odvojeno DTW, intervalski motiv, oblik DTW puta i gustinu nota. Ne menja rezultate, MIDI fajlove ni ručne oznake.

Za nove neproverene kandidate pretraga u CSV dodaje kolone `note_density`, `motif_run_fraction`, `dtw_diagonal_fraction` i `review_priority`. Kandidati sa manjim `review_priority` stoje prvi za ručni pregled; to je redosled pregleda, ne automatska oznaka `DA`.

## Izvor podataka

Weimar Jazz Database je deo [Jazzomat Research Project](https://jazzomat.hfm-weimar.de/) i dostupna je pod Open Data Commons Open Database License (ODbL).
