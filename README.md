# JazzDialog

JazzDialog je naučno-istraživački Python projekat čiji je cilj izgradnja dataseta **call-and-response parova u jazzu**.

Projekat analizira MIDI transkripcije improvizovanih sola iz [Weimar Jazz Database](https://jazzomat.hfm-weimar.de/dbformat/dboverview.html). Za svaku zvanično anotiranu WJD frazu algoritam traži najbolju podelu na call i response i računa skor na osnovu DTW sličnosti melodije i sličnosti početaka segmenata. Pored podele cele fraze, proverava kontrolisane unutrašnje prozore čije su dužine naučene iz ručne Excel anotacije. Response cele fraze mora imati najmanje 75% broja nota call-a, čime se odbacuju neuravnoteženi parovi sa veoma kratkim response-om.

Rezultati se čuvaju u `output/wjd_phrase_call_response.csv`. Svaki kandidat se zatim ručno preslušava i označava:

- `DA` — validan call-and-response par;
- `NE` — kandidat nije call-and-response;
- prazno — kandidat još nije pregledan.

Pri svakom pokretanju za svaki red iz CSV-a automatski se generiše MIDI isečak u `output/wjd_phrase_excerpts`. Isečak sadrži samo pronađeni call i response sa originalnim ritmom, a kolona `excerpt_midi` čuva njegovu tačnu putanju.

Ručne `NE` oznake dodaju kaznu sličnim kandidatima u sledećim iteracijama. Početna ručna Excel anotacija služi kao biblioteka pozitivnih melodijskih referenci za unutrašnje prozore. Kolone `candidate_source` i `decision_reason` pokazuju zašto je svaki red dodat, dok `call_start_local`, `split_point_local` i `response_end_local_exclusive` čuvaju njegove tačne granice unutar WJD fraze. Krajnji rezultat istraživanja je provereni dataset jazz call-and-response primera, uz algoritam koji pomaže u njihovom pronalaženju.

## Pokretanje

U `SEARCH_ITEMS` unutar `scripts/search_wjd_phrase_splits.py` upiši željene WJD `melid` brojeve, a zatim pokreni:

```powershell
.\venv\Scripts\python.exe scripts\search_wjd_phrase_splits.py
```

Potrebni paketi su `dtaidistance` i `pretty_midi`. Datoteka `wjazzd.db` čuva se lokalno u folderu `data_midi` i nije uključena u repozitorijum.

## Izvor podataka

Weimar Jazz Database je deo [Jazzomat Research Project](https://jazzomat.hfm-weimar.de/) i dostupna je pod Open Data Commons Open Database License (ODbL).
