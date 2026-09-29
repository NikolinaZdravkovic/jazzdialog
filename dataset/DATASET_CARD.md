# JazzDialog: dokumentacija baze

Autorka: **Nikolina Zdravković**. Mentorka: **Maja Milović**. Stanje: 29. septembar 2026.

JazzDialog sadrži **114 potvrđenih call-and-response anotacija** iz Weimar Jazz Database (WJD): 76 sola, 73 različita naslova i 42 izvođača. Baza je namenjena proučavanju odnosa muzičkih segmenata i razvoju metoda za predlaganje parova. Nije iscrpan popis svih takvih odnosa u WJD-u niti skup automatski potvrđenih rezultata.

## Šta da otvoriš

- `jazzdialog.csv`: jednostavna glavna tabela sa 24 kolone, samo dobri primeri.
- `midi/jazzdia-1.mid` do `midi/jazzdia-114.mid`: isečci sa odvojenim CALL i RESPONSE trakama i izvornim WJD vremenima relativno pomerenim na početak isečka.
- `jazzdialog.json`: ista baza sa svakom pojedinačnom notom, trajanjem, poreklom i podacima o preklapanju. Zato je mnogo duži od CSV-a.
- `jazzdialog_midi.zip`: prenosivi paket koji sadrži CSV, JSON, README i svih 114 MIDI fajlova.

Redovi su sortirani po izvođaču, naslovu, WJD broju i mestu u solu. Brojevi 1-114 služe lakom čitanju i povezivanju sa MIDI fajlovima; posle promene sastava i ponovnog sortiranja mogu se promeniti. Za trajnu identifikaciju sačuvaj `wjd_melid` i četiri granice nota (u JSON-u postoji i identifikator zasnovan na tim granicama). Git čuva prethodne snimke izdanja.

## Kolone CSV-a

| Kolona | Značenje |
| --- | --- |
| `jazzdialog_id` | Redni broj para, 1-114. |
| `performer` | Izvođač sola. |
| `title` | Naslov kompozicije prema WJD-u. |
| `wjd_melid` | Jedinstveni broj konkretnog sola u WJD-u; isti naslov može imati više snimaka. |
| `key` | Tonalitet iz metapodataka celog sola, ne nužno lokalnog odlomka. |
| `instrument` | WJD oznaka instrumenta: npr. `tp` truba, `ts` tenor saksofon, `as` alt saksofon. |
| `style` | Stilska kategorija preuzeta iz WJD-a. |
| `avgtempo_bpm` | Prosečan tempo sola u udarcima u minutu; nije lokalna brzina nota. |
| `tempo_class` | Izvorna WJD kategorija tempa. |
| `rhythm_feel` | Izvorna WJD oznaka ritmičkog karaktera. |
| `time_signature` | Oznaka takta iz metapodataka. |
| `call_start_note` | Indeks prve note call-a, brojanje od nule unutar sola. |
| `call_end_note_exclusive` | Indeks odmah posle poslednje note call-a. |
| `response_start_note` | Indeks prve note response-a. |
| `response_end_note_exclusive` | Indeks odmah posle poslednje note response-a. |
| `call_start_seconds` | Početak prve note call-a, u sekundama prema WJD vremenskoj osi sola. |
| `call_end_seconds` | Najkasniji završetak note u call-u, na istoj osi. |
| `response_start_seconds` | Početak prve note response-a. |
| `response_end_seconds` | Najkasniji završetak note u response-u. |
| `call_note_count` | Broj nota call-a. |
| `response_note_count` | Broj nota response-a. |
| `call_pitches` | JSON lista celobrojnih MIDI visina call-a, u vremenskom redosledu. |
| `response_pitches` | Ista predstava response-a. |
| `midi_file` | Putanja u odnosu na folder baze, npr. `midi/jazzdia-1.mid`. |

Primer: početak 10, kraj 18 označava osam nota, sa indeksima 10-17. Za izdvajanje iz Python liste koristi `notes[10:18]`. Sekunde nisu indeksi nota. Ako koristiš drugi audio snimak, proveri njegov početak i eventualni vremenski pomak prema WJD transkripciji.

## Sastav i potvrđivanje

Baza sadrži 1.136 call nota i 1.278 response nota. Medijane dužina su 9 i 10 nota. Stilske oznake su POSTBOP 31, COOL 29, HARDBOP 17, SWING 14, BEBOP 8, FUSION 7, TRADITIONAL 6 i FREE 2.

Kandidati su tokom razvoja nastajali podelom zvaničnih fraza i korišćenjem WJD midlevel/IDEA anotacija. Autorka ih je preslušavala i ocenjivala sa DA/NE. Dodatni ručno zapisani pozitivni primeri locirani su u izvornoj transkripciji. Glavna tabela čuva samo prihvaćene odnose, a istorija odbijenih kandidata ostaje u razvojnom CSV-u. Potvrda jednog ocenjivača nije isto što i konsenzus nezavisnih muzičara.

Od 114 anotacija, 26 je u celosti unutar jedne WJD fraze, a 88 prelazi granicu fraze. Ukupno 17 zapisa pripada osam grupa sa preklapanjem. Neke predstavljaju različite odobrene granice, a neke susedne odnose koji dele segment. Zato 114 redova ne treba predstavljati kao 114 nezavisnih muzičkih događaja. Detalji su sačuvani u JSON-u, bez opterećivanja glavnog CSV-a.

## Prvobitna ručna Excel tabela

Od 21 zapisa u `jazzdialog3(4).xlsx`, 13 je povezano sa konačnom bazom. Osam je već bilo prisutno, a pet je dodato. Sedam se odnosi na snimke kojih nema u lokalnoj WJD bazi (tri *It Could Happen to You* i četiri *Well You Needn't*), a poslednji je nepotpun. Njihovi podaci nisu izmišljeni niti označeni lažnim WJD brojem.

| Broj iz Excela | JazzDialog broj | Naslov | Provera |
| --- | --- | --- | --- |
| 1 | - | It Could Happen to You | Snimak nije u lokalnoj WJD; nije uključen. |
| 2 | - | It Could Happen to You | Snimak nije u lokalnoj WJD; nije uključen. |
| 3 | - | It Could Happen to You | Snimak nije u lokalnoj WJD; nije uključen. |
| 4 | 69 | Bessie's Blues | Povezano; proverene visine posle transpozicije i vezivanja nota. |
| 5 | - | Well You Needn't | Snimak nije u lokalnoj WJD; nije uključen. |
| 6 | - | Well You Needn't | Snimak nije u lokalnoj WJD; nije uključen. |
| 7 | - | Well You Needn't | Snimak nije u lokalnoj WJD; nije uključen. |
| 8 | - | Well You Needn't | Snimak nije u lokalnoj WJD; nije uključen. |
| 9 | 26 | I Fall in Love Too Easily | Povezano; proverene visine posle transpozicije i vezivanja nota. |
| 10 | 28 | I Fall in Love Too Easily | Povezano; proverene visine posle transpozicije i vezivanja nota. |
| 11 | 103 | My Funny Valentine  | Povezano; proverene visine posle transpozicije i vezivanja nota. |
| 12 | 104 | My Funny Valentine  | Povezano uz dokumentovane razlike nota: 1. |
| 13 | 105 | My Funny Valentine  | Povezano uz dokumentovane razlike nota: 2. |
| 14 | 29 | Just Friends | Povezano; proverene visine posle transpozicije i vezivanja nota. |
| 15 | 30 | Just Friends | Povezano uz dokumentovane razlike nota: 1. |
| 16 | 31 | Let's Get Lost | Ranije potvrđeno slušanjem; response u Excelu odstupa. |
| 17 | 34 | Long Ago and Far Away | Povezano; proverene visine posle transpozicije i vezivanja nota. |
| 18 | 23 | Donna Lee | Povezano uz dokumentovane razlike nota: 1. |
| 19 | 84 | Dickie's Dream | Povezano uz dokumentovane razlike nota: 2. |
| 20 | 35 | There Will Never Be Another You | Povezano; proverene visine posle transpozicije i vezivanja nota. |
| 21 | - | Two's Blues | Nepotpun zapis; nedostaje ceo par. |

Povezivanje uzima u obzir instrumentnu transpoziciju, oktave i vezane note. Kod četiri novododata mapiranja pronađene su male razlike u zapisu koje su proverene u izvornim WJD notnim transkripcijama. One nisu predstavljene kao doslovna poklapanja. Detaljan, neizmenjeni originalni zapis, granice, transpozicije i svaka razlika čuvaju se u `output/manual_reference_mapping.json` u repozitorijumu. Izvorni Excel nije prepisan. Trajanja u konačnoj bazi uvek su iz WJD-a; nejasne oznake T5/T6 nisu proizvoljno pretvarane u ritmičke vrednosti.

## Upotreba i ograničenja

Za trening i test koristi razdvajanje po `wjd_melid`, a za strožu proveru i po izvođaču. Primeri istog sola i preklapajući segmenti ne smeju biti raspoređeni nasumično kao nezavisni uzorci. Glavna baza sadrži samo pozitivne primere i sama po sebi ne omogućava merenje preciznosti klasifikatora; za to su potrebni negativni i nezavisno ocenjeni test podaci. Neoznačeni odlomci nisu automatski negativni.

Izbor kandidata i jedan ocenjivač uvode pristrasnost. Nije izmereno slaganje više ocenjivača niti odziv nad svim CR pojavama WJD-a. Sačuvani MIDI sadrži simboličke visine i trajanja, ne pun zvuk izvođenja. Baza ne tvrdi da iscrpno opisuje harmoniju, artikulaciju ili jazz fraziranje.

## Ponovljivost

```powershell
.\venv\Scripts\python.exe scripts\export_reviewed_dataset.py --release
.\venv\Scripts\python.exe scripts\export_reviewed_dataset.py --verify-package dataset\jazzdialog_midi.zip
```

Izvoz proverava izvorne note i obe MIDI trake, nazive fajlova i podudarnost CSV/JSON zapisa. Druga komanda proverava prenosivi ZIP i bez lokalne WJD baze. Referentni izvor je WJazzD 2.1; puni SHA-256 radnog CSV-a nalazi se u JSON manifestu.

## Izvorna prava i citiranje

WJD je objavljen pod [ODbL 1.0](https://opendatacommons.org/licenses/odbl/1-0/), a pojedinačni sadržaji pod [DbCL 1.0](https://opendatacommons.org/licenses/dbcl/1-0/), prema [zvaničnoj stranici WJD-a](https://jazzomat.hfm-weimar.de/dbformat/dboverview.html). Izvedeni zapisi ne ukidaju te uslove. Audio snimci nisu deo paketa.

Predlog citata: Zdravković, N. (2026). *JazzDialog: ručno provereni call-and-response parovi u jazz solažima*. https://github.com/NikolinaZdravkovic/jazzdialog. Uz citat navesti korišćeni Git commit, a obavezno citirati i izvorni WJD: Pfleiderer, M., Frieler, K., Abeßer, J., Zaddach, W.-G. i Burkhart, B. (ur.), *Inside the Jazzomat: New Perspectives for Jazz Research*, Schott Campus, 2017.

Organizacija dokumentacije oslanja se na Gebru et al. (2021), *Datasheets for Datasets*, DOI: 10.1145/3458723, i Wilkinson et al. (2016), *The FAIR Guiding Principles*, DOI: 10.1038/sdata.2016.18. To je smernica za dokumentovanje i ponovnu upotrebu, ne tvrdnja o formalnoj FAIR sertifikaciji.
