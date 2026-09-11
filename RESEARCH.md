# Kako završiti jazz call-response dataset

## Zaključak za nastavak rada

Najbrži opravdan put je mali, jasno dokumentovan dataset koji je čovek preslušao i potvrdio, uz automatizaciju predlaganja i izvoza. Trenutni rezultati ne podržavaju tvrdnju da je pronađen pouzdan automatski klasifikator. To ne poništava dataset: algoritamski kandidati i muzički potvrđeni parovi imaju različite uloge.

U trenutnom CSV-u postoje 65 ocenjenih kandidata iz 22 sola: 18 DA i 47 NE. Svih 18 DA redova ima postojeći MIDI fajl. DA redovi obuhvataju 15 različitih kombinacija `melid/phrase_value`, pa 18 redova ne treba predstavljati kao 18 nezavisnih muzičkih događaja. Različite granice i skraćene verzije iste fraze treba pregledati zajedno i odabrati konačan primer, uz očuvanje istorije.

Ovo istraživanje dodaje read-only eksperiment u postojeću evaluacionu skriptu. Produkcijski prag i kriterijumi detekcije nisu promenjeni. Nijedan nov kandidat nije označen kao DA bez preslušavanja.

## Šta smo stvarno testirali

Izvor je `output/wjd_phrase_call_response.csv`, SHA-256 `77ee4abe33837616d50bdab302d846bbc885ea8321231406cd163b222af16a48`. U ovom snimku ima 65 jedinstvenih ključeva koji uključuju solo, frazu, podelu i oba pitch niza. Nije pronađena konfliktna DA/NE oznaka za potpuno isti ključ. To ne isključuje preklapanje različitih kandidata.

Četiri unapred definisana signala poređena su odvojeno. Nismo uzimali minimum preko njih, niti ih zajedno dodali produkcijskom skoru:

1. Postojeća globalna DTW distanca: `distance / path_length`.
2. RMS greška na istoj optimalnoj putanji: `distance / sqrt(path_length)`.
3. RMS posle oduzimanja prve note svakog segmenta, da se ukloni transpozicija.
4. Isti oblik, ali uz putanju ograničenu na razliku normalizovanih pozicija nota najviše 0,2.

Za svaku meru manja vrednost unapred znači veću sličnost. Deskriptivni AUC ne okrećemo naknadno da bi izgledao bolji. AUC 0,5 znači slučajno rangiranje pozitivnog naspram negativnog kandidata; to nije procenat tačnih odluka.

| Mera | Deskriptivni AUC | DA medijan | NE medijan | DA izabrani na izdvojenim solima | NE izabrani na izdvojenim solima |
|---|---:|---:|---:|---:|---:|
| Postojeći globalni DTW | 0,475 | 0,482 | 0,440 | 0 | 1 |
| Pitch RMS | 0,567 | 1,785 | 1,900 | 0 | 0 |
| Transponovani oblik RMS | 0,557 | 2,089 | 1,880 | 0 | 0 |
| Oblik RMS uz ograničenu putanju | 0,603 | 2,545 | 2,358 | 1 | 2 |

Prag smo birali odvojeno za svaki izdvojeni solo, koristeći samo ostale sole. Na trening delu tražena je preciznost najmanje 80% i najmanje tri izabrana primera. Među dozvoljenim pragovima biran je onaj koji zadržava najviše DA, a pri izjednačenju manje NE. Ako nijedan ne zadovolji uslove, metoda ne predlaže ništa. Za četiri mere, redom, to se desilo u 21, 22, 22 i 1 od ukupno 22 podele.

Poslednja varijanta zato ima 1/3 = 33,3% preciznosti među samo tri izabrana kandidata i pronalazi 1 od 18 već poznatih DA redova. To nije uspešno poboljšanje. Za varijante bez predloga preciznost nije definisana, a ne 100%.

Grupisanje po solu sprečava da se kandidati istog sola pojave i pri biranju praga i pri testiranju. Takva evaluacija odgovara problemu zavisnih opažanja opisanom u scikit-learn dokumentaciji.[1] Ipak, ovo ostaje istraživački rezultat: iste oznake su već više puta korišćene tokom razvoja i sadašnji kandidati su selektovani ranijim detektorima. Novi, netaknuti soli ostaju potrebni za konačnu potvrdu.

Eksperiment poredi pojedinačne signale na već označenim granicama. Ne poredi ceo produkcijski sistem sa incipitom, prilagođavanjem brzom tempu i DA/NE nagradama/kaznama. Ne meri koliko svih pravih parova u solu pronalazimo, jer nemamo potpunu referentnu anotaciju svih pregledanih sola. Te granice zaključka su važne.

## Zašto mali DTW skor može da zavara

DTAIDistance za podrazumevanu kvadratnu lokalnu grešku vraća kvadratni koren akumulirane greške.[2] Ako putanja ima L poravnanja i zbir kvadrata grešaka S, trenutni rezultat je `sqrt(S)/L`. RMS na toj putanji je `sqrt(S/L)`. Zato važi:

`trenutni_skor = RMS / sqrt(L)`

Pri istoj RMS grešci, duža putanja spušta trenutni skor. Kontrolni test sa konstantnim nizovima 60 i 61 daje 0,447 za pet nota i 0,224 za dvadeset nota, iako je greška svuda jedan polustepen. RMS je 1 u oba slučaja. To potvrđuje problem skale, ali ne znači da je RMS dovoljan muzički kriterijum — naš test pokazuje da nije.

RMS koji ovde računamo jeste greška na putanji koja minimizuje zbir kvadrata, a ne putanja posebno optimizovana za najmanju prosečnu grešku. Takođe ne uklanja svaku zavisnost od dužine: izbor putanje i muzički sadržaj i dalje utiču na rezultat. Prag 0,2 ne sme se jednostavno preneti sa stare formule na novu.

Drugi problem je preterano rastezanje. Standardni DTW može povezati jednu notu sa više nota drugog segmenta. Literatura opisuje upravo ovakve degeneracije i mogućnost ograničavanja putanje.[3] Testirana traka ograničava odstupanje relativnih pozicija, ali nije stroga zabrana ponavljanja jedne note u više poravnanja. Zato ona ne rešava automatski problem trilera ili ponavljanih tonova.

Treći problem je šta poredimo. Sličnost note-po-notu ne dokazuje da dva dela čine muzički smislen poziv i odgovor. Nizovi mogu imati ponavljanje, lestvicu ili ukras koji daje dobar matematički rezultat. Obrnuto, dobar odgovor može promeniti dovoljno nota da globalna distanca bude visoka. Zaključak iz oznaka je da je preklapanje DA i NE rezultata veliko; iz toga ne možemo zaključiti da je svaki oblik DTW-a beskoristan.

## Granice WJD fraza

Za poslednju grupu 26–30 provereno je 59 zvaničnih fraza. Njih 28 ima manje od deset nota, četiri nemaju dozvoljenu podelu u kojoj oba dela imaju najmanje sekundu zbirnog trajanja nota, a 27 stiže do scoringa. Svih tih 27 ostaje iznad praga 0,2. Nije nađen znak pogrešnog indeksiranja pri izvlačenju ove grupe.

To objašnjava nulu u toj grupi, ali ne dokazuje da tih pet sola nema call-response. Par preko granice dve zvanične fraze nije dostupan sadašnjoj pretrazi. Zvanična fraza je jedinica ulaza, a ne potvrda da svaka tražena muzička veza mora stati u nju.

Za tekući eksperiment ostaje pretraga unutar jedne fraze, prema dogovoru sa mentorkom. Ručno pronađeni parovi preko granica mogu biti deo šireg, ručno anotiranog dataseta, uz eksplicitnu oznaku obuhvata. Ne treba ih koristiti kao dokaz uspeha detektora koji ih ne može predložiti.

Subsequence DTW je relevantan za buduću pretragu kraćeg motiva unutar dužeg niza.[4] On zahteva i definisanje poziva/upita i dozvoljenog prostora odgovora. Veći prostor pretrage donosi više prilika za slučajno poklapanje, pa njegovo uključivanje pred rok bez zasebne evaluacije nije potvrđeno rešenje.

## Ritam, kumulativna kontura i pretraga motiva

Ritam vredi proveriti kao jednu odvojenu hipotezu. Praktična reprezentacija su razmaci između početaka uzastopnih nota, podeljeni tipičnim razmakom segmenta, zatim poređeni u logaritamskoj skali. Tako se ispituje relativni ritmički obrazac, a ne samo apsolutni tempo. Međutim, ponavljane osmine i jednostavni ritmovi mogu biti česti u celom solu. Dobar ritmički skor sam po sebi ne bi bio potvrda CR. U ovom izveštaju još nema rezultata takvog testa.

Izraz „kumulativna pitch kontura” mora se vezati za konkretnu definiciju ili rad. Ako znači kumulativni zbir uzastopnih pitch intervala, onda zbir od početka do i-te note daje tačno `pitch[i] - pitch[0]`. To je već naš transponovani oblik, a ne nova informacija. Ako znači zbir apsolutnih intervala, gubi se smer kretanja i dobija se druga mera. Ne treba uvoditi novu funkciju samo zbog drugačijeg naziva.

Jazzomat već ima melpat za pretragu obrazaca u monofonim melodijama, sa predstavama poput pitch vrednosti, intervala i kategorija trajanja.[5] To je relevantan osnov za buduću pretragu sličnih motiva prema pouzdanim ručnim primerima. Ipak, ponovljen motiv i call-response nisu isti zadatak. Preporuka je ograničena pretraga prema dobro definisanom primeru, uz proveru celog predloženog para, a ne automatsko proglašavanje pronađenog motiva za CR.

## Plan za dataset koji možemo završiti

Prvi korak je pregled postojećih DA po grupama fraza. Potrebno je odabrati konačne granice tamo gde imamo više verzija. Odluka treba da zabeleži šta tačno pripada call-u i response-u, posebno primer gde je prva nota odgovora zapravo završetak poziva. Originalna oznaka i ranija granica ostaju istorija, a ne nestaju brisanjem.

Drugi korak je definisanje minimalnog zapisa: stabilan identifikator, WJD melid, granice oba segmenta u indeksima nota, vremena početka/kraja, pitch nizovi, putanja do MIDI-ja, ručna ocena, napomena i poreklo predloga. Većina toga već postoji. Za konačni skup treba razlikovati ručno pronađene parove od algoritamski predloženih i naknadno potvrđenih. Primer izvan jedne WJD fraze ima istu vrednost kao anotacija, ali drugi obuhvat u evaluaciji.

Treći korak je kratak dogovor o anotaciji sa mentorkom: da li identičan eho važi; kada je triler samo ukras; koliko nastavka odgovora zadržavamo; da li postoji „nesigurno”; da li ocenjujemo muzičku vezu, granicu ili oboje. Različiti odgovori menjaju cilj detekcije. Samo dodavanje novih kazni ne može zameniti ovaj dogovor.

Četvrti korak je mali nezavisan pregled. Za rast dataseta birati male grupe kandidata i meriti koliko potvrđenih parova dobijamo po uloženom vremenu. Za procenu detektora potrebno je preslušati i mali unapred izabran skup fraza koje detektor nije predložio. Neoznačeni kandidati i nepredložene fraze nisu automatski NE. Tek kompletno anotiran definisan uzorak omogućava procenu propuštenih parova.

Peti korak je zaustavljanje podešavanja kada novi kriterijum ne donese napredak na izdvojenim solima. Jedna unapred izabrana promena, jedna jasna provera i zapis rezultata daju više naučne vrednosti od mnogih promena koje gledaju iste oznake. Sadašnje četiri varijante nisu opravdale uključivanje u produkciju.

Za brzo izdanje moguće je objaviti skroman pilot dataset sa potvrđenim granicama, negativnim kandidatima kao pomoćnim anotacijama i jasnim ograničenjima. Broj potvrđenih nezavisnih parova i saglasnost drugog ocenjivača vredniji su od većeg broja automatski generisanih redova. Veličinu konačnog uzorka treba dogovoriti prema zahtevu rada; iz trenutnih podataka ne postoji opravdan unapred obećan broj novih validnih parova.

## Ponovljivost i naredni eksperiment

Pokretanje iz korena projekta:

```powershell
.\venv\Scripts\python.exe scripts\evaluate_labelled_pairs.py --research
```

Skripta čita oznake, računa nove vrednosti od pitch nizova i prikazuje rezultate. Ne koristi istorijski `score` kao zajedničku meru različitih verzija. Ne menja CSV, MIDI niti produkcijske parametre. Kontrolni test potvrdio je očekivanu razliku između normalizacija i odustajanje kada trening primeri ne podržavaju prag.

Naredni ograničen eksperiment je ritam na istom skupu, samo za redove čije note i granice možemo tačno povezati sa bazom. Njegove rezultate treba porediti sa istim grupisanim postupkom i navesti koliko redova je ostalo dostupno. Tek ako donese koristan signal, razmatra se jedna jednostavna kombinacija sa melodijskim skorom. Novi DA i automatska promena produkcije nisu deo tog eksperimenta.

## Završen ritmički eksperiment

Ritmički eksperiment je završen 12. septembra 2026. po lokalnom vremenu. Sledeći rezultati zamenjuju raniju napomenu da ritam još nije testiran. Korišćen je isti SHA-256 CSV-a naveden na početku, sa 65 ocenjenih redova, 18 DA i 47 NE iz 22 sola.

Svih 65 kandidata uspešno je povezano sa WJD notama: proverene su granice, dužine, pitch nizovi, a gde postoje i apsolutni indeksi i vremena početaka. Nije bilo odbačenih redova. Nedostajuće lokalne granice tumače se kao cela deklarisana fraza samo kada se oba pitch niza tačno poklapaju. Kod ne traži sličnu pojavu motiva na drugom mestu. Baza je otvorena u read-only režimu.

Za svaki segment računati su pozitivni razmaci između početaka susednih nota (IOI). Svaki niz podeljen je sopstvenim medijanom, pa transformisan funkcijom log2. Standardni DTW zatim poravnava te nizove, a rezultat je RMS na odabranoj putanji. Tako dva ritma koja se razlikuju samo po ravnomernom ubrzanju imaju isti prikaz. Test ne uključuje trajanje završne note, artikulaciju niti položaj u taktu. Pauza između call-a i response-a nije deo unutrašnjih IOI nizova.

| Mera na istih 65 kandidata | AUC, niže je bolje | DA medijan | NE medijan | Izdvojeni DA/NE predlozi |
|---|---:|---:|---:|---:|
| Relativni ritam RMS | 0,501 | 0,560 | 0,566 | 0 / 0 |
| Pitch RMS | 0,567 | 1,785 | 1,900 | 0 / 0 |
| Oblik RMS sa trakom | 0,603 | 2,545 | 2,358 | 1 / 2 |

Sve četiri melodijske mere ponovo su izračunate na istom dostupnom skupu i dale su iste rezultate kao u prvoj tabeli. Za ritam nijedna od 22 trening podele nije dala prag sa najmanje tri predloga i najmanje 80% preciznosti. Metoda je zato svuda odustala; preciznost predloga nije definisana. AUC od 0,501 pokazuje da ova konkretna mera u ovom uzorku praktično ne razdvaja DA od NE. To nije dokaz da ritam uopšte nije važan, niti test svih ritmičkih reprezentacija.

Kontrolnim primerima provereni su isti relativni ritam pri dvostruko sporijem izvođenju, odbacivanje nepodudarnih indeksa, pitch nizova i početnih vremena, kao i odbacivanje nultog IOI-ja. CSV, MIDI fajlovi, produkcijski scoring i prag nisu menjani.

Ponovljivo pokretanje:

```powershell
.\venv\Scripts\python.exe scripts\evaluate_labelled_pairs.py --rhythm
```

Odluka: nema dovoljno dokaza da se ova ritmička mera doda produkcijskom skoru. Najkorisniji sledeći korak ostaje završavanje konačnih granica postojećih 18 DA redova, grupisanih u 15 oznaka fraza, i nezavisna provera malog definisanog uzorka sa mentorkom. Novi kriterijumi sada nemaju potvrđenu prednost nad tim radom. Automatski nastavak istraživanja završava se ovim jednim eksperimentom.

## Izvori

1. scikit-learn, [Cross-validation: evaluating estimator performance](https://scikit-learn.org/stable/modules/cross_validation.html), odeljci o grupama i zavisnim uzorcima. Dokumentacija pristupljena tokom ove provere.
2. Wannes Meert i saradnici, DTAIDistance, [innerdistance.py](https://github.com/wannesm/dtaidistance/blob/master/src/dtaidistance/innerdistance.py). Podrazumevana kvadratna lokalna greška i završni kvadratni koren; dodatno provereno kontrolnim primerom u lokalnom okruženju.
3. Meinard Müller i saradnici, [FMP: DTW Variants](https://www.audiolabs-erlangen.de/resources/MIR/FMP/C3/C3S2_DTWvariants.html), zasnovano na *Fundamentals of Music Processing* (2015), deo 3.2.2. Ograničenja koraka, lokalne težine i globalna ograničenja putanje.
4. Meinard Müller i saradnici, [FMP: Subsequence DTW](https://www.audiolabs-erlangen.de/resources/MIR/FMP/C7/C7S2_SubsequenceDTW.html), zasnovano na delu 7.2.3 iste knjige. Razlika između globalnog i lokalnog poravnanja.
5. Jazzomat Research Project, [melpat](https://jazzomat.hfm-weimar.de/commandline_tools/melpat/melpat.html). Pretraga i izdvajanje melodijskih obrazaca.

Brojčani rezultati ovog dokumenta potiču iz lokalnog CSV-a i navedenog eksperimenta, ne iz navedenih publikacija. Preporučeni plan je zaključak za ovaj projekat, a ne tvrdnja da literatura garantuje njegovu uspešnost.
