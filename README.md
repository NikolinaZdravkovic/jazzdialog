# JazzDialog

JazzDialog je naučno-istraživački Python projekat čiji je cilj izgradnja dataseta **call-and-response parova u jazzu**.

Projekat analizira MIDI transkripcije improvizovanih sola iz [Weimar Jazz Database](https://jazzomat.hfm-weimar.de/dbformat/dboverview.html). Za svaku zvanično anotiranu WJD frazu algoritam isprobava moguće podele na call i response. Podelu bira samo prema najmanjoj normalizovanoj DTW udaljenosti dva cela MIDI pitch niza. Oba dela imaju najmanje pet nota i ne mogu biti izrazito nejednake dužine. Incipit se čuva u CSV-u samo kao dijagnostički podatak, dok ritam, trajanje i harmonija za sada ne odlučuju o rezultatu.

Rezultati se čuvaju u `output/wjd_phrase_call_response.csv`. Svaki kandidat se zatim ručno preslušava i označava:

- `DA` — validan call-and-response par;
- `NE` — kandidat nije call-and-response;
- prazno — kandidat još nije pregledan.

Pri svakom pokretanju za svaki red iz CSV-a automatski se generiše MIDI isečak u `output/wjd_phrase_excerpts`. Isečak sadrži samo pronađeni call i response sa originalnim ritmom, a kolona `excerpt_midi` čuva njegovu tačnu putanju.

Ručne `NE` oznake dodaju kaznu sličnim kandidatima u sledećim iteracijama, a sve postojeće `DA` i `NE` oznake ostaju sačuvane. DTW ispod `0.20` daje automatski CR, a rezultat od `0.20` do `0.30` ide na ručni pregled. Kolone `dtw_gap` i `relativni_dtw_gap` pokazuju koliko se izabrana podela odvaja od sledeće najbolje. Krajnji rezultat istraživanja je provereni dataset jazz call-and-response primera, uz algoritam koji pomaže u njihovom pronalaženju.

## Pokretanje

U `SEARCH_ITEMS` unutar `scripts/search_wjd_phrase_splits.py` upiši željene WJD `melid` brojeve, a zatim pokreni:

```powershell
.\venv\Scripts\python.exe scripts\search_wjd_phrase_splits.py
```

Potrebni paketi su `dtaidistance` i `pretty_midi`. Datoteka `wjazzd.db` čuva se lokalno u folderu `data_midi` i nije uključena u repozitorijum.

## Izvor podataka

Weimar Jazz Database je deo [Jazzomat Research Project](https://jazzomat.hfm-weimar.de/) i dostupna je pod Open Data Commons Open Database License (ODbL).
