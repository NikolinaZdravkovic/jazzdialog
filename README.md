# JazzDialog

JazzDialog je naučno-istraživački Python projekat čiji je cilj izgradnja dataseta **call-and-response parova u jazzu**.

Aktuelna detekcija vracena je na algoritam iz commita `7bd878a` (5. septembar 2026). Koristi DTW + incipit, alpha 0.5, najmanje 3 note po segmentu i prag 0.4. Ova istorijska verzija ukljucuje i spajanje dve susedne WJD fraze, prilagodjavanje incipita brzom tempu i nagrade/kazne prema rucnim oznakama. Nije potvrdjeno da je upravo ovaj commit dao raniji rezultat 6 dobrih od 8.

Rezultati se čuvaju u `output/wjd_phrase_call_response.csv`. Svaki kandidat se zatim ručno preslušava i označava:

- `DA` — validan call-and-response par;
- `NE` — kandidat nije call-and-response;
- prazno — kandidat još nije pregledan.

Pri svakom pokretanju za svaki red iz CSV-a automatski se generiše MIDI isečak u `output/wjd_phrase_excerpts`. Isečak sadrži samo pronađeni call i response sa originalnim ritmom, a kolona `excerpt_midi` čuva njegovu tačnu putanju.

Svi raniji CSV redovi, rucne oznake i istorijski skorovi ostaju sacuvani. Novi redovi imaju `candidate_source=verzija_7bd878a`; njihove skorove ne treba direktno porediti sa skorovima prethodnog DTW eksperimenta. MIDI izvoz i cuvanje savremenih CSV kolona zadrzani su radi kompatibilnosti.

## Pokretanje

U `SEARCH_ITEMS` unutar `scripts/search_wjd_phrase_splits.py` upiši željene WJD `melid` brojeve, a zatim pokreni:

```powershell
.\venv\Scripts\python.exe scripts\search_wjd_phrase_splits.py
```

Potrebni paketi su `dtaidistance` i `pretty_midi`. Datoteka `wjazzd.db` čuva se lokalno u folderu `data_midi` i nije uključena u repozitorijum.

## Izvor podataka

Weimar Jazz Database je deo [Jazzomat Research Project](https://jazzomat.hfm-weimar.de/) i dostupna je pod Open Data Commons Open Database License (ODbL).
