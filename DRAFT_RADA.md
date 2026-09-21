# Izgradnja ručno proverene zbirke call-response parova u jazz solažima

**Radna verzija za komentar mentorke — 21. septembar 2026.**

## Sažetak

Call-response je važan oblik muzičkog dijaloga u jazz improvizaciji, ali granice
poziva i odgovora nisu deo standardnih anotacija dostupnih za jazz solaže. U
ovom radu gradimo ručno proverenu zbirku takvih parova nad MIDI
transkripcijama Weimar Jazz Database (WJD). Svaka anotacija sadrži identitet
sola, indekse nota i vremena početka i kraja call-a i response-a, njihove pitch
nizove, MIDI isečak i ljudsku odluku. Jednostavan DTW postupak koristimo za
predlaganje kandidata, a ne za automatsko proglašavanje call-response odnosa.
Na trenutnom pilot-skupu od 69 ručno ocenjenih kandidata (22 `DA`, 47 `NE`)
pokazujemo da se vrednosti globalnog pitch-DTW-a jako preklapaju za dobre i
loše primere. Posebno su problem pomerena ponavljanja kratkog motiva, koja
imaju izuzetno nizak DTW skor, a pri slušanju ne funkcionišu kao muzički
dijalog. Rezultat rada je reproduktivan format anotacija i dokumentovana
analiza ograničenja pitch-sličnosti pri njegovoj izgradnji.

## 1. Uvod i istraživačko pitanje

Jazz call-response ne mora da bude doslovno ponavljanje: odgovor može promeniti
visine, dužinu ili nastavak ideje. Zbog toga sama sličnost pitch-nizova nije
dovoljna. Ipak, ona može biti koristan početni signal za brzo nalaženje delova
koje potom proverava čovek.

Pitanje rada je: **koliko jednostavna DTW sličnost pitch-nizova može da pomogne
pri izgradnji ručno proverene zbirke call-response parova u WJD solažima i koje
su njene glavne greške?**

Ne tvrdimo da je ovo prvi call-response dataset: postoji Call-Response Dataset
za zadatak generisanja odgovora [Hu i sar., 2024]. Naš fokus je na proverljivim
granicama parova u konkretnim jazz MIDI transkripcijama i na procesu njihove
ručne validacije.

## 2. Podaci i format anotacije

Izvor nota i zvaničnih granica fraza je WJD. Za svaki kandidat čuvamo:

- `melid`, naslov i izvođača;
- indekse i vremena početka/završetka call-a i response-a;
- pitch nizove oba dela;
- putanju do MIDI isečka sa odvojenim CALL i RESPONSE kanalima;
- ručnu oznaku `DA` ili `NE`, napomenu i poreklo kandidata.

Trenutni pilot sadrži 22 potvrđene anotacije i 47 odbijenih kandidata, iz 22
sola. Broj 22 je broj anotacija, ne broj nezavisnih muzičkih događaja: neke
anotacije predstavljaju alternativne granice istog događaja i ostaju sačuvane
zbog transparentnosti.

![Obuhvat WJD fraze u pilot anotacijama](output/figures/figure_1_annotation_scope.png)

**Slika 1.** Četrnaest od 22 potvrđene anotacije je unutar jedne zvanične WJD
fraze, a osam prelazi najmanje jednu WJD granicu. Ovo je opis pilot-skupa, ne
procena učestalosti u celoj bazi. Pokazuje da WJD fraza jeste koristan početni
okvir, ali nije nužno granica svakog muzičkog dijaloga.

## 3. Predlaganje kandidata

Za dva pitch niza računamo DTW udaljenost, podeljenu stvarnom dužinom najbolje
warping putanje. U ranijoj verziji kandidat je bio jedna podela cele WJD fraze.
Zbog ekstremno neujednačenih delova uvedeni su minimalno pet nota po delu i
odnos dužina response/call između 0,5 i 2. Za novi pregledni batch pretražuju
se samo susedni podsegmenti dužina 5, 8 ili 12 nota unutar iste WJD fraze.

Ovaj batch nije automatski dataset. Njegova kolona `validnost` je namerno
prazna dok se MIDI isečak ne presluša i ne označi `DA` ili `NE`. Time se
odvajaju algoritamski predlozi od ljudskih anotacija.

Otkriven je tipičan lažni minimum: kraj call-a i početak response-a dele četiri
ili više identičnih uzastopnih nota. To najčešće znači da je kratki motiv samo
pomeren kroz granicu prozora. Takve kandidate novi batch filtrira. Ta odluka
ne menja nijednu postojeću ručnu oznaku.

## 4. Rezultati

Na 69 ručno ocenjenih kandidata ponovo smo izračunali isti globalni pitch-DTW,
bez mešanja istorijskih score kolona iz različitih verzija skripte.

![Preklapanje DTW skora](output/figures/figure_2_dtw_overlap.png)

**Slika 2.** Manji rezultat znači veću pitch-sličnost. Vrednosti `DA` i `NE`
se preklapaju. Zato fiksan DTW prag ne daje pouzdanu automatsku odluku: može
prihvatiti muzički prazan ostinato, ali propustiti dobar odgovor koji menja
nastavak melodijske ideje.

Testirane su i odvojene varijante: RMS normalizacija, transponovani oblik,
ograničena warping putanja, relativni ritam, opis konture i median-3
zaglađivanje. Nijedna nije dala pouzdano poboljšanje u evaluaciji po izdvojenom
solu. To je važan rezultat: ne uvodimo kriterijum u produkcijski tok samo zato
što na nekoliko primera izgleda obećavajuće.

## 5. Diskusija

DTW je koristan za rangiranje kandidata, ali ne prepoznaje sam muzičku funkciju
odgovora. Posebno zavodi kada poravna istu kratku figuru pomerenu za jednu ili
više nota. Ritam i pitch-kontura mogu ostati buduće hipoteze, ali na ovom
skupu nisu pokazali dovoljnu samostalnu diskriminativnost.

Zato je doprinos rada human-in-the-loop postupak: algoritam smanjuje prostor
pretrage, a slušanje potvrđuje muzičku celinu i granice. Za sledeću verziju
zbirke potrebno je dopuniti broj nezavisnih, ručno potvrđenih događaja i da
drugi anotator nezavisno proveri unapred definisan mali uzorak.

## 6. Zaključak

Napravljen je format za precizne i proverljive WJD call-response anotacije,
MIDI isečke za proveru i skup ručnih `DA/NE` odluka. Rezultati pokazuju da
pitch-DTW nije dovoljan kao automatski klasifikator, ali je koristan kao alat
za generisanje kandidata kada se eksplicitno filtriraju klizajuće repeticije.
Sledeći merljiv korak je proširivanje ručno proverene zbirke kroz male,
raznovrsne batcheve, uz čuvanje svih odluka.

## Literatura

1. Hu, J. i sar. *Responding to the Call: A Call-Response Dataset and Model for
   Music Generation.* AAAI, 2024. https://ojs.aaai.org/index.php/AAAI/article/view/27807
2. Jazzomat Research Project. *melpat: melodic pattern extraction and search.*
   https://jazzomat.hfm-weimar.de/commandline_tools/melpat/melpat.html
3. Müller, M. *Fundamentals of Music Processing*, poglavlja o DTW varijantama.
   https://www.audiolabs-erlangen.de/resources/MIR/FMP/C3/C3S2_DTWvariants.html
