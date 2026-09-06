# JazzDialog

JazzDialog je naučno-istraživački Python projekat čiji je cilj izgradnja dataseta **call-and-response parova u jazzu**.

Projekat analizira MIDI transkripcije improvizovanih sola iz [Weimar Jazz Database](https://jazzomat.hfm-weimar.de/dbformat/dboverview.html). Za svaku zvanično anotiranu WJD frazu algoritam traži najbolju podelu na call i response i računa skor na osnovu DTW sličnosti melodije i sličnosti početaka segmenata. Response mora imati najmanje 75% broja nota call-a, čime se odbacuju neuravnoteženi parovi sa veoma kratkim response-om.

Rezultati se čuvaju u `output/wjd_phrase_call_response.csv`. Svaki kandidat se zatim ručno preslušava i označava:

- `DA` — validan call-and-response par;
- `NE` — kandidat nije call-and-response;
- prazno — kandidat još nije pregledan.

Ručne oznake koriste se u sledećim iteracijama kao nagrade i kazne u scoring sistemu. Početna ručna Excel anotacija služi kao biblioteka pozitivnih melodijskih referenci. Krajnji rezultat istraživanja je provereni dataset jazz call-and-response primera, uz algoritam koji pomaže u njihovom pronalaženju.

## Pokretanje

U `SEARCH_ITEMS` unutar `scripts/search_wjd_phrase_splits.py` upiši željene WJD `melid` brojeve, a zatim pokreni:

```powershell
.\venv\Scripts\python.exe scripts\search_wjd_phrase_splits.py
```

Potrebni paketi su `dtaidistance` i `pretty_midi`. Datoteka `wjazzd.db` čuva se lokalno u folderu `data_midi` i nije uključena u repozitorijum.

## Izvor podataka

Weimar Jazz Database je deo [Jazzomat Research Project](https://jazzomat.hfm-weimar.de/) i dostupna je pod Open Data Commons Open Database License (ODbL).
