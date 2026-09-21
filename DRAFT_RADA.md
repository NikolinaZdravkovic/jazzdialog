# Izgradnja ručno proverene zbirke call-response parova u jazz solažima

**Radna verzija za komentar mentorke — 22. septembar 2026.**

## Sažetak

Call-response je važan oblik muzičkog dijaloga u jazz improvizaciji, ali njegove granice nisu deo standardnih anotacija jazz solaža. U ovom radu gradimo ručno proverenu zbirku takvih parova nad MIDI transkripcijama Weimar Jazz Database (WJD). Svaka anotacija sadrži identitet sola, granice oba dela u indeksima nota i sekundama, pitch nizove, MIDI isečak i ljudsku odluku.

DTW koristimo za predlaganje kandidata, ne za automatsko proglašavanje call-response odnosa. Finalni radni skup ima 151 ručno ocenjen kandidat: 56 `DA` i 95 `NE`. Rezultati pokazuju veliko preklapanje DTW vrednosti dobrih i loših primera. Poseban problem su pomerena ponavljanja kratkog motiva: dobijaju nizak skor, ali pri slušanju ne funkcionišu kao muzički dijalog. Glavni rezultat rada je reproduktivan format anotacija, MIDI dokazi i dokumentovan postupak human-in-the-loop izgradnje baze.

## 1. Uvod i istraživačko pitanje

Jazz call-response ne mora da bude doslovno ponavljanje. Response može promeniti visine, dužinu i nastavak ideje, pa sama sličnost pitch-nizova nije dovoljna. Ipak, može da smanji prostor koji čovek mora da presluša.

Istraživačko pitanje je: **koliko jednostavna DTW sličnost može da pomogne pri izgradnji ručno proverene zbirke call-response parova u WJD solažima i koje su njene glavne greške?**

Ne tvrdimo da je ovo prvi call-response dataset: postoji Call-Response Dataset za zadatak generisanja odgovora [Hu i sar., 2024]. Naš fokus je na proverljivim granicama parova u konkretnim jazz MIDI transkripcijama.

## 2. Podaci i anotacije

Za svaki kandidat čuvamo `melid`, naslov, izvođača, indekse i vremena call-a i response-a, pitch nizove, MIDI sa odvojenim CALL/RESPONSE kanalima, ručnu oznaku `DA` ili `NE` i poreklo predloga.

Finalni paket sadrži 56 potvrđenih anotacija. Sedam anotacija pripada trima grupama alternativnih, preklapajućih granica; kada se takve verzije ne broje dvaput, ostaju 52 nepreklapajuća muzička događaja. Negativni skup ima 95 ručno odbijenih kandidata. Ovo nije slučajan uzorak cele WJD baze, već rezultat dokumentovanog pregleda algoritamskih predloga.

![Obuhvat WJD fraze](output/figures/figure_1_annotation_scope.png)

**Slika 1.** Dvadeset dve potvrđene anotacije nalaze se u jednoj WJD frazi, a 34 prelaze najmanje jednu WJD granicu. To je opis anotiranog skupa, ne procena učestalosti u celoj bazi. WJD fraza je koristan početni okvir, ali nije nužno granica svakog muzičkog dijaloga.

## 3. Predlaganje kandidata

Za dva pitch niza računamo DTW udaljenost podeljenu stvarnom dužinom najbolje warping putanje. Prvi pristup birao je podelu cele WJD fraze. Zbog delova tipa 3 note naspram 33 note uvedeni su minimumi dužine i odnos response/call između 0,5 i 2. Filtrirani su i klizajući isečci kod kojih se kraj call-a praktično ponavlja na početku response-a.

Korisniji izvor kandidata postale su WJD `IDEA` anotacije, odnosno ručno označene mid-level muzičke ideje. U WJD kodu `#` označava da se trenutna ideja odnosi na prethodnu. Za pregled su birani susedni povezani parovi od 7 do 20 nota po strani, bez doslovnog ponavljanja i bez `rhythm`, `expressive`, `void` i `fragment` tipova. Ni takav kandidat nije automatski `DA`: odluku daje slušanje MIDI isečka.

## 4. Rezultati

![Preklapanje DTW skora](output/figures/figure_2_dtw_overlap.png)

**Slika 2.** Manja vrednost znači veću pitch-sličnost. `DA` i `NE` vrednosti se preklapaju, pa fiksan DTW prag ne daje pouzdanu automatsku odluku. Može prihvatiti muzički prazan ostinato, a propustiti dobar response koji razvija ideju.

Od 82 ručno ocenjena WJD-MLU kandidata, 34 su potvrđena kao `DA`, a 48 odbijena kao `NE`. To je 41,5% `DA` među pregledanim MLU kandidatima, ne ukupna tačnost na svim mogućim parovima u WJD. U najstrožem početnom opsegu odnos je bio bolji; kada je DTW opseg proširen, stopa `DA` je pala na 5/20. Zato je pretraga zaustavljena umesto da se broj primera veštački poveća lošijim kandidatima.

Odvojeno su proverene RMS normalizacija, transponovani oblik, ograničena DTW putanja, relativni ritam, opis konture i median-3 zaglađivanje. Nijedna mera nije pokazala dovoljno pouzdano poboljšanje u evaluaciji po izdvojenom solu, pa nije uključena u produkcijski tok.

## 5. Diskusija i zaključak

DTW je koristan za rangiranje, ali ne prepoznaje sam muzičku funkciju odgovora. WJD `IDEA` back-reference anotacije daju muzički smislenije granice i zato su praktično poboljšale kandidatski tok, ali i dalje zahtevaju ljudsku proveru.

Rezultat projekta je baza od 56 potvrđenih anotacija (52 nepreklapajuća događaja), 95 negativnih kandidata, proverene granice i prenosivi MIDI paket. Doprinos nije tvrdnja o savršenom automatskom detektoru, već kontrolisan i reproduktivan način na koji se mala, muzički proverena jazz CR zbirka može izgraditi iz WJD-a.

## Literatura

1. Hu, J. i sar. *Responding to the Call: A Call-Response Dataset and Model for Music Generation.* AAAI, 2024. https://ojs.aaai.org/index.php/AAAI/article/view/27807
2. Frieler, K. i sar. *Midlevel Analysis: Supplement S2 MLA Codebook.* 2016. WJD `IDEA` segmenti, konektori i kategorije muzičkih ideja.
3. Jazzomat Research Project. *melpat: melodic pattern extraction and search.* https://jazzomat.hfm-weimar.de/commandline_tools/melpat/melpat.html
4. Müller, M. *Fundamentals of Music Processing*, poglavlja o DTW varijantama. https://www.audiolabs-erlangen.de/resources/MIR/FMP/C3/C3S2_DTWvariants.html
