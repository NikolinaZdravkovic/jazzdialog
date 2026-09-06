# JazzDialog

JazzDialog je Python istraživački prototip za automatsko pronalaženje **call-and-response** odnosa u MIDI transkripcijama jazz sola iz Weimar Jazz Database (WJD).

Program koristi zvanične WJD granice fraza, traži najbolju podelu na call i response i rezultat ocenjuje kombinacijom globalne DTW udaljenosti i sličnosti početaka segmenata. Ručne oznake `DA` i `NE` iz CSV tabele vraćaju se u scoring kao nagrade i kazne, tako da se pretraga iterativno prilagođava muzičkoj proceni.

## Trenutna logika

- Call i response zajedno čine jednu zvaničnu WJD frazu.
- Svaki kandidat ostaje unutar jedne zvanične WJD fraze.
- Call i response moraju imati najmanje po 5 nota.
- Niži skor znači bolji kandidat; trenutni prag je `0.3`.
- Osnovni skor je `alpha * globalni_DTW + (1 - alpha) * incipit`.
- Kandidati slični ručno odbijenim primerima (`NE`) dobijaju kaznu.
- Kandidati slični ručno potvrđenim primerima (`DA`) dobijaju nagradu.
- Za veoma brz tempo (najmanje 215 BPM), incipit mora da obuhvati najmanje 0.75 sekundi muzike kako nekoliko kratkih nota ne bi slučajno dalo nizak skor.

Ovo je eksperimentalni sistem za pronalaženje kandidata i ručnu muzičku proveru. Za objektivnu evaluaciju treba odvojiti primere korišćene za podešavanje od zasebnog test skupa.

## Struktura projekta

```text
jazzdialog/
├── scripts/
│   ├── extract_wjd_phrases.py
│   ├── find_internal_split.py
│   ├── search_wjd_phrase_splits.py
│   ├── segment_phrases.py
│   ├── solo_wide_search.py
│   └── read_midi.py
├── data_midi/
│   └── wjazzd.db                 # lokalno; nije u Git repozitorijumu
└── output/
    └── wjd_phrase_call_response.csv
```

`search_wjd_phrase_splits.py` je glavna skripta. `output/wjd_phrase_call_response.csv` sadrži pronađene kandidate i ručne oznake.

## Instalacija na Windowsu

Potreban je Python i paketi `dtaidistance` i `pretty_midi`.

```powershell
python -m venv venv
.\venv\Scripts\Activate.ps1
python -m pip install dtaidistance pretty_midi
```

Preuzmi `wjazzd.db` sa [zvanične Jazzomat stranice](https://jazzomat.hfm-weimar.de/download/download.html) i smesti ga u `data_midi/wjazzd.db`. Baza i MIDI fajlovi namerno nisu deo ovog repozitorijuma.

## Pokretanje

U `SEARCH_ITEMS` na vrhu `scripts/search_wjd_phrase_splits.py` upiši željene `melid` brojeve ili nazive pesama:

```python
SEARCH_ITEMS = [70, 71, 72]
```

Zatim iz glavnog foldera projekta pokreni:

```powershell
.\venv\Scripts\python.exe scripts\search_wjd_phrase_splits.py
```

Skripta ažurira postojeći `output/wjd_phrase_call_response.csv`. Pre pokretanja zatvori CSV u Excelu da Excel ne zadrži staru verziju fajla.

## Ručna validacija

U prvoj koloni `validnost` upiši:

- `DA` ako kandidat muzički funkcioniše kao call-and-response;
- `NE` ako kandidat nije call-and-response;
- ostavi prazno ako kandidat još nije pregledan.

Pri sledećem pokretanju skripta čita te oznake. Kolone `osnovni_skor`, `kazna_ne_primer`, `nagrada_da_primer` i `score` pokazuju kako je dobijen konačni rezultat.

## Osnovni Git rad

Proveri koje si fajlove promenila:

```powershell
git status
```

Sačuvaj novu verziju projekta:

```powershell
git add scripts output/wjd_phrase_call_response.csv README.md
git commit -m "Kratak opis promene"
git push
```

Preuzmi promene sa GitHub-a:

```powershell
git pull --rebase
```

Git pamti istoriju koda i anotacija. Lokalni `venv`, WJD baza, izvorni MIDI fajlovi i generisani MIDI isečci ignorisani su preko `.gitignore`.

## Podaci i citiranje

Weimar Jazz Database razvijena je u okviru [Jazzomat Research Project](https://jazzomat.hfm-weimar.de/dbformat/dboverview.html) i objavljena je pod Open Data Commons Open Database License (ODbL). Pri akademskoj upotrebi treba navesti citat koji preporučuju autori baze:

> Pfleiderer, M., Frieler, K., Abeßer, J., Zaddach, W.-G., & Burkhart, B. (Eds.). (2017). *Inside the Jazzomat: New Perspectives for Jazz Research*. Schott Campus.
