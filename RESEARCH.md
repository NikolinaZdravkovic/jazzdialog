# Kako završiti jazz call-response dataset

## Zaključak za nastavak rada

Najbrži opravdan put je mali, jasno dokumentovan dataset koji je čovek preslušao i potvrdio, uz automatizaciju predlaganja i izvoza. Trenutni rezultati ne podržavaju tvrdnju da je pronađen pouzdan automatski klasifikator. To ne poništava dataset: algoritamski kandidati i muzički potvrđeni parovi imaju različite uloge.

Zamrznuti evaluacioni skup obuhvata 65 ranije ocenjenih automatskih kandidata iz 22 sola: 18 DA i 47 NE. Kasnije su dodata četiri ručno mapirana i potvrđena primera, pa pilot izvoz sada ima 22 DA anotacije. Ta četiri primera nisu naknadno ubačena u ranije DTW/ritam rezultate. Različite granice i skraćene verzije iste fraze treba pregledati zajedno i odabrati konačan primer, uz očuvanje istorije.

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

## Pilot izvoz i ubrzanje pretrage

Implementiran je `scripts/export_reviewed_dataset.py --export`. Izvoz trenutno sadrži 18 DA anotacija. Granice, note i vremena oba MIDI kanala provereni su prema WJD bazi. Šest anotacija čini tri preklapajuća para verzija: solo 14 (Avalon), solo 73 (Long Ago and Far Away), solo 74 (There Will Never Be Another You). Verzije su zadržane sa oznakom preklapanja; konačne granice bira čovek. Manifest `output/reviewed_dataset.json` sadrži relativne putanje, originalni tajming, stabilne identifikatore i grupu po solu za evaluaciju. Nazivi za 73 i 74 ispravljeni su prema manifestu; raniji tekst ih je pogrešno imenovao.

Pretraga DA/NE referenci ubrzana je tačnom donjom granicom. Ako distanca call-a sama ne može dati prosek manji od trenutno najboljeg čak ni uz savršen response, poređenje response-a nije potrebno. Ovo ne menja formulu, prag niti muzičke kriterijume.

Na šest stvarnih kandidata broj poređenja segmenata pao je sa 780 na 218 uz iste rezultate. U kontrolnom izvršavanju cele pretrage sola 31 kandidati, skorovi, dijagnostika i sažetak bili su identični pre i posle izmene; vreme je bilo 44,797 s naspram 31,387 s. To je merenje jednog pokretanja na ovom računaru, a ne obećanje istog ubrzanja na svakom solu. Obe pretrage bile su bez upisa CSV/MIDI fajlova.

## Predlog mentorke: statistički opis kontura

Salamon, Peeters i Röbel (ISMIR 2012) proučavaju izbor melodije iz polifonog audio-signala. Njihov indeks „melodiness” razlikuje konture koje pripadaju melodiji od ostalih kandidata. Model koristi statističke raspodele osobina kontura. Među osobinama su srednja visina, varijacija visine, dužina, salience i vibrato. To nije prepoznavanje call-response odnosa niti automatska ocena muzičke smislenosti fraze. Original je dostupan kao [PDF na sajtu autora](https://www.justinsalamon.com/uploads/4/3/9/4/4394963/salamonmelodiccontourismir12.pdf).

Korisna ideja za ovaj projekat jeste učenje raspodela osobina iz anotacija. WJD MIDI već daje izdvojenu melodiju i ne sadrži kontinualne informacije o salience i vibratu iz tog postupka. Zato sledeći mali model predstavlja našu prilagođenu hipotezu, a ne reprodukciju njihovog algoritma. Rad sam po sebi nije postupak uklanjanja sitnih ukrasa iz već transkribovane melodije.

Urađena je odvojena provera tri osobine para: apsolutna razlika srednjih visina nakon oduzimanja prve note, razlika standardnih devijacija pitch vrednosti i razlika ukupnog kretanja od prve do poslednje note. Jedan mali Gaussov klasifikator uči srednje vrednosti dve klase, zajedničku dijagonalnu kovarijansu i učestalost DA/NE isključivo na ostalim solima. Fiksni prag odluke je negativan log-odnos verovatnoća manji od nule. Nema traženja najpovoljnijeg praga ili parametara na test solima.

Druga varijanta dodaje samo ranije definisani ritmički RMS kao četvrtu osobinu. Ovo neposredno proverava pitanje da li isti ritmički signal pomaže uz opis konture, iako sam nije razdvajao klase.

| Model | AUC iz predikcija za izdvojene sole | Izabrani DA | Izabrani NE |
|---|---:|---:|---:|
| Tri osobine konture, Gaussov model | 0,332 | 0 | 0 |
| Isti model + relativni ritam RMS | 0,223 | 0 | 0 |

Korišćeno je istih 65 ocenjenih kandidata iz 22 sola (18 DA / 47 NE), bez odbacivanja pri mapiranju i sa istim SHA-256 CSV-a kao ranije. Rezultat nije poboljšanje: model na fiksnom pragu sve ocenjuje kao negativno, a rangiranje je loše. AUC nije naknadno obrnut da bi delovao povoljnije. Samo predviđanje NE za svaki primer bi imalo 47/65 = 72,3% tačnosti u ovom selektovanom skupu, ali nijedan pronađen DA — jasan primer zašto ukupna tačnost nije dovoljan cilj.

Ovaj eksperiment ne isključuje korisnost statističkog učenja ili ritma uopšte. Testirane su vrlo ograničene osobine i jedan jednostavan model; nemamo veliku, nezavisnu i reprezentativnu zbirku. Posebno, srednja vrednost i rasipanje gube redosled većine nota. Moguće je da imaju slične vrednosti za muzički veoma različite fraze. Ne postoji opravdanje da sada dodamo ovaj model produkcijskom skoru.

```powershell
.\venv\Scripts\python.exe scripts\evaluate_labelled_pairs.py --contours
```

Komanda samo čita podatke i prikazuje odvojene rezultate konture i konture sa ritmom. Nisu menjani detektor, prag, granice, CSV ili MIDI. Kontrolni primeri proverili su transpozicionu nezavisnost osobina, smer Gaussove odluke, slučaj nulte varijanse i nedovoljno trening primera.

Poruka za mentorku može glasiti: „Pogledala sam rad, sad mi je jasnije da melodiness tu znači da kontura pripada glavnoj melodiji, a ne da je fraza muzički smislena. Ideja da učimo karakteristike iz DA/NE mi ima smisla. Probala sam mali model opisa konture i posebno istu verziju sa ritmom, ali zasad ni to nije popravilo rezultat na izdvojenim solima. Za ritam nisam mislila da ga skroz odbacimo — samo ova konkretna mera nije pomogla ni sama ni u toj jednostavnoj kombinaciji.”

## Završen median-3 eksperiment

Provera blagog pojednostavljivanja konture završena je 14. septembra 2026. po lokalnom vremenu. U jednom prolazu svaka unutrašnja pitch vrednost zamenjena je medijanom tri originalne susedne vrednosti. Prva i poslednja nota ostaju iste, kao i broj nota. Zatim je oduzeta prva nota svakog segmenta i izračunat DTW RMS. Širina filtera nije podešavana prema ocenama. To je naša ograničena hipoteza, ne implementacija Salamonovog rada niti potvrđen postupak uklanjanja muzičkih ukrasa.

Na istih 65 označenih kandidata (18 DA / 47 NE, 22 sola, isti prethodno navedeni SHA-256 CSV-a), rezultati su:

| Mera | Deskriptivni AUC, niže je bolje | DA medijan | NE medijan | Izdvojeni DA / NE predlozi |
|---|---:|---:|---:|---:|
| Originalni shape RMS | 0,557 | 2,089 | 1,880 | 0 / 0 |
| Median-3 shape RMS | 0,537 | 1,504 | 1,840 | 0 / 0 |

Za oba signala svih 22 trening podela ostalo je bez praga koji daje najmanje tri predloga uz najmanje 80% preciznosti. Prag je biran samo na ostalim solima. Preciznost kod nula predloga je nedefinisana, a obuhvat poznatih DA redova je nula. Bolje razdvojeni medijani u zaglađenoj verziji nisu dovoljan dokaz: ukupno rangiranje se blago pogoršalo, a korisni predlozi nisu dobijeni. AUC nije naknadno okretan.

Kontrolni testovi potvrdili su potiskivanje izolovanog skoka u pitch-u, nepromenjen ulaz, krajeve i broj nota, konstantne nizove i transpozicionu invarijantnost. Originalni CSV, MIDI, granice, pilot paket i produkcijski kriterijumi nisu menjani. Ovaj filter može ukloniti i muzički važan ton i ne uzima trajanje nota u obzir; rezultat ne isključuje sve druge postupke pojednostavljivanja melodije.

```powershell
.\venv\Scripts\python.exe scripts\evaluate_labelled_pairs.py --median3
```

Odluka: nema dokaza za uključivanje median-3 signala u detektor. Ovim se završava dogovoreni dodatni eksperiment, bez daljeg automatskog dodavanja kriterijuma. Sledeći korak ostaje ljudska provera tri grupe granica u već pripremljenom pilot datasetu i dogovor o malom nezavisnom uzorku za procenu propuštenih CR parova.

## Dataset kao glavni rezultat — stanje 15. septembra 2026.

Cilj rada je dokumentovana zbirka call-response anotacija jazz sola iz WJD-a, uz proveru koliko jednostavne mere sličnosti pomažu pri njenoj izgradnji. Potpuno automatsko prepoznavanje nije uslov za ovaj doprinos. Tvrdnju o poboljšanju detektora moramo vezati za rezultate na nezavisnim podacima; dosadašnji eksperimenti je ne podržavaju.

### Šta već postoji u literaturi

Hu i saradnici (AAAI 2024), [Responding to the Call](https://ojs.aaai.org/index.php/AAAI/article/view/27807), objavili su Call-Response Dataset sa 19.155 anotiranih parova i model za generisanje odgovora. Zato ne možemo tvrditi da je naša zbirka prvi CR dataset. [Dig That Lick](https://dig-that-lick.eecs.qmul.ac.uk/) već omogućava pretragu melodijskih obrazaca u jazz bazama, uključujući WJD, po intervalima, konturi i visinama. Ni pretraga sličnih jazz motiva sama po sebi nije nova.

Naš konkretan doprinos može biti nova zbirka CR anotacija vezanih za WJD note, sa granicama oba segmenta, ljudskim odlukama i dokumentovanim alternativama granica, uz reproduktivan eksperiment o ograničenjima DTW mera. Prioritet tvrdnje „prva ovakva jazz zbirka” nije utvrđen ovom proverom i ne treba ga navoditi. Naučni doprinos nije isto što i dokaz da niko nije radio ništa slično.

### Šta imamo, bez dvostrukog brojanja

- Pilot izvoz ima 22 DA anotacije, uključujući tri grupe preklapajućih verzija. Korisnički izbor poželjnih granica ostaje zabeležen; 22 nije broj nezavisnih muzičkih događaja.
- Evaluacioni skup ima 65 ocenjenih kandidata: 18 DA i 47 NE, iz 22 sola. To je selektovan razvojni uzorak, a ne iscrpna anotacija svih CR pojava u tim solima.
- Početni Excel sadrži 20 popunjenih parova, jedan nepotpun i osam praznih redova sa ID-em. Uvoz je sačuvao izvorni tekst i SHA-256 fajla bez menjanja radne sveske.
- Četiri para imaju jedinstveno, potpuno pitch poklapanje u naznačenom WJD solu: ručni ID 9, 10, 14 i 20. Sva četiri već postoje među DA ocenama; uvoz povezuje poreklo, ne povećava dataset za četiri.
- Ručni ID 11 je potvrđen slušanjem: My Funny Valentine, melid 402, note [0:7] i [7:15], uz transpoziciju od -12 polutonova između zapisa i WJD visina. Obuhvata WJD fraze 1–2. U pilot izvoz je dodat kao `DA`, sa MIDI-jem iz originalnih WJD događaja.
- Ručni ID 15 je potvrđen slušanjem: Just Friends, melid 71, note [139:155] i [155:166]. Obuhvata WJD fraze 8–11. Poslednja zapisana response nota je 59, dok WJD ima 60; razlika je sačuvana u izvornoj tabeli i u opisu anotacije.
- Ručni ID 16 je potvrđen slušanjem: Let's Get Lost, melid 72, note [19:24] i [24:34]. Call se potpuno poklapa; neposredni response je predložen DTW oblikom i potom ljudski potvrđen. Obuhvata WJD fraze 1–2.
- Ručni ID 17 je potvrđen slušanjem: Long Ago and Far Away, melid 73, note [39:56] i [56:67]. Vezana pitch vrednost 70 je zapisana jednom, na kraju call-a. Ovaj par je unutar WJD fraze 4.
- Ostalih 15 popunjenih parova: osam sa spoljnim izvorima, pet bez potpunog pitch poklapanja, jedan sa nedostajućom oktavom i jedan sa granicom kroz vezanu notu. To nisu negativni CR primeri: samo nisu potpuno povezani sa WJD događajima.

Važno ograničenje metode: detektor ograničen na jednu WJD frazu po konstrukciji ne može vratiti par koji prelazi njenu granicu. Među 22 trenutne potvrđene anotacije osam prelazi najmanje jednu WJD granicu fraze. To je opis pilot anotacija, ne procena učestalosti u celoj bazi.

### Proširena eksplorativna provera nakon ručnog mapiranja

Na svih 69 trenutno označenih redova (22 DA / 47 NE) proverene su četiri DTW mere sa odvojenim solom pri izboru praga. Ova provera je odvojena od zamrznutog skupa iznad: četiri nova DA reda potiču iz početne ručne zbirke, dok NE redovi i dalje potiču iz ranije generisanih kandidata. Zato rezultat ne predstavlja tačnost na slučajnom uzorku cele WJD baze.

Najbolja opisna mera bila je ograničeni shape-DTW RMS sa AUC 0,571, ali je u leave-one-solo-out proveri vratila samo 1 DA i 2 NE (preciznost 0,333; obuhvat označenih DA 0,045). Ostale tri mere nisu vratile nijedan DA pri tom postupku. Ovo je koristan negativan nalaz: ni promena normalizacije niti ograničavanje warping puta ne rešavaju razliku između muzičkog dijaloga i ponavljajućeg motiva na ovom malom skupu.

### Protokol završavanja zbirke i rada

1. Prvo povezati postojeće ručne anotacije; ne tražiti da se već obrađeni solo ponovo anotira od početka. Za nejasne zapise tražiti samo nedostajuću informaciju ili preslušavanje konkretnog isečka.
2. U glavnu zbirku uključivati samo potvrđene parove sa proverenim izvorom i granicama. Alternativne verzije i NE primere sačuvati kao razvojnu dokumentaciju. Isti događaj ne brojati više puta zbog različitih granica.
3. Za proširenje koristiti male grupe novih kandidata uz MIDI i ručnu potvrdu. Granice ručnog referentnog dataseta mogu prelaziti WJD fraze; ograničenje trenutnog detektora mora biti jasno navedeno. Ne uvoditi automatsko spajanje kao pretpostavljeno rešenje.
4. Ako vreme dozvoli, mentorka nezavisno proverava mali unapred izabran podskup DA, NE i spornih granica. Sačuvati početne nezavisne odluke pre dogovora. Bez druge procene ne tvrdimo da smo izmerili slaganje anotatora.
5. Za rad koristiti postojeće rezultate kao pilot analizu. Na novim solima zamrznuti kriterijume pre ocenjivanja. Preciznost je udeo DA među pregledanim predlozima; recall celog sola zahteva iscrpnu referencu. Ranijih „80% accuracy” ne predstavljati kao ukupnu tačnost prepoznavanja svih fraza.

Predlog naslova: **Izgradnja ručno proverene zbirke call-response parova u jazz solažima i analiza ograničenja melodijske sličnosti**.

Osnova zaključka: na našem razvojnom uzorku testirane mere sličnosti nisu omogućile pouzdanu samostalnu identifikaciju CR odnosa. Ručna provera i izbor granica ostaju potrebni. Doprinos su proverljive anotacije i analiza konkretnih ograničenja; ne zaključujemo da je DTW beskoristan niti da ritam ne može pomoći u drugim postupcima.

## Literatura

1. scikit-learn, [Cross-validation: evaluating estimator performance](https://scikit-learn.org/stable/modules/cross_validation.html), odeljci o grupama i zavisnim uzorcima. Dokumentacija pristupljena tokom ove provere.
2. Wannes Meert i saradnici, DTAIDistance, [innerdistance.py](https://github.com/wannesm/dtaidistance/blob/master/src/dtaidistance/innerdistance.py). Podrazumevana kvadratna lokalna greška i završni kvadratni koren; dodatno provereno kontrolnim primerom u lokalnom okruženju.
3. Meinard Müller i saradnici, [FMP: DTW Variants](https://www.audiolabs-erlangen.de/resources/MIR/FMP/C3/C3S2_DTWvariants.html), zasnovano na *Fundamentals of Music Processing* (2015), deo 3.2.2. Ograničenja koraka, lokalne težine i globalna ograničenja putanje.
4. Meinard Müller i saradnici, [FMP: Subsequence DTW](https://www.audiolabs-erlangen.de/resources/MIR/FMP/C7/C7S2_SubsequenceDTW.html), zasnovano na delu 7.2.3 iste knjige. Razlika između globalnog i lokalnog poravnanja.
5. Jazzomat Research Project, [melpat](https://jazzomat.hfm-weimar.de/commandline_tools/melpat/melpat.html). Pretraga i izdvajanje melodijskih obrazaca.

Brojčani rezultati ovog dokumenta potiču iz lokalnog CSV-a i navedenog eksperimenta, ne iz navedenih publikacija. Preporučeni plan je zaključak za ovaj projekat, a ne tvrdnja da literatura garantuje njegovu uspešnost.
