# JazzDialog: izdvajanje i dokumentovanje call-and-response parova iz jazz solaža

Nikolina Zdravković
Mentorka: Maja Milović

## Sažetak

Call-and-response je muzički odnos u kome jedna kratka muzička celina otvara pitanje, obrazac ili ideju, a naredna celina na nju odgovara ponavljanjem, varijacijom, kontrastom ili nastavkom. Iako je takav odnos čest u jazz improvizaciji, teško ga je svesti na jednu numeričku meru: dve fraze mogu biti slične po visini tonova, a da ipak zvuče kao mehaničko ponavljanje bez muzičke funkcije; sa druge strane, dobar odgovor može da promeni melodiju, dužinu ili završetak. U radu je prikazan postupak izgradnje baze JazzDialog, skupa ručno potvrđenih call-and-response parova izdvojenih iz transkribovanih jazz solaža. Istraživanje je počelo segmentacijom po pauzama, a zatim je prešlo na zvanično anotirane granice fraza i na pretragu susednih delova fraze. Ispitane su melodijska udaljenost dinamičkim vremenskim poravnanjem, sličnost početaka, intervali, konture, relativni ritam, ograničenja dužine i modeli za rangiranje kandidata. Rezultati pokazuju da mala melodijska udaljenost sama po sebi nije dovoljna za pouzdano prepoznavanje call-and-response odnosa. Zato se konačna baza zasniva na računarski izdvojenim kandidatima i obaveznom slušanju i potvrdi. JazzDialog sadrži 114 potvrđenih zapisa iz 76 solaža, uz povezane MIDI isečke i precizne granice call i response delova.

**Ključne reči:** jazz improvizacija, call-and-response, analiza melodije, dinamičko vremensko poravnanje, baza podataka, MIDI

## 1. Uvod

Call-and-response je oblik muzičke komunikacije u kome se dva dela doživljavaju kao povezane, ali ne nužno iste celine. U jazzu se može javiti između izvođača, između soliste i pratnje, ali i unutar jedne solaže: izvođač iznese kratku ideju, pa je ponovi, promeni, dopuni ili joj odgovori novom idejom. Zbog improvizacione prirode jazza granica između ponavljanja, varijacije i odgovora nije uvek oštra. Upravo zato je zanimljivo pitanje da li se takvi odnosi mogu dovoljno dobro opisati računarom da bi se pronašli u većem broju solaža.

Početna ideja projekta odnosila se na generisanje jazz melodija koje bi mogle da vode dijalog. Tokom rada pokazalo se da pre generisanja treba bolje razumeti od čega se stvarni muzički dijalog sastoji i kako se može opisati u podacima. Konačni fokus je zato promenjen: umesto generisanja, cilj je postao izdvajanje i dokumentovanje stvarnih call-and-response parova iz postojećih solo improvizacija.

Istraživački problem rada glasi: **kako iz transkribovanog jazz sola izdvojiti muzički smislen call-and-response par, a da izbor ne zavisi samo od prividne sličnosti nekoliko tonova?** Kao praktičan rezultat nastala je baza JazzDialog. Svaki njen zapis povezuje izvođača i naslov sa preciznim indeksima nota, vremenima, visinama tonova i MIDI isečkom za ručnu proveru.

Rad ne polazi od pretpostavke da je call-and-response moguće potpuno automatski i bez greške odrediti. Umesto toga, kroz niz eksperimenata ispituje koje numeričke osobine pomažu pri pronalaženju kandidata, gde prave lažne pozitivne rezultate i kako računar može da ubrza, ali ne i da zameni, muzičko slušanje.

## 2. Priprema za obradu

### 2.1. Izvor podataka i reprezentacija solaža

Za analizu su korišćene monofone MIDI transkripcije jazz solaža i njihove prateće anotacije iz sistema Jazzomat / Weimar Jazz Database. Taj izvor je pogodan jer pored događaja nota čuva identifikatore solaža, izvođače, naslove i anotirane muzičke celine. U ovom radu baza je izvor transkripcija i granica fraza, a predmet istraživanja je sopstveni postupak analize i nastala JazzDialog kolekcija. Opis formata podataka i termina koji se odnose na sekcije solaža dat je u dokumentaciji izvora (Pfleiderer i dr., 2017; Jazzomat, 2026).

Svaka nota je predstavljena četvorkom

`(eventid, onset, pitch, duration)`,

gde je `eventid` redni broj note u solu, `onset` vreme početka, `pitch` MIDI visina tona, a `duration` trajanje. Za najveći deo melodijske analize korišćen je niz MIDI visina tonova. Na primer, niz `[67, 69, 71]` predstavlja tri uzastopne note. Kada je bilo potrebno da se proveri da li je deo prekratak ili prebrz, korišćeni su i onset i trajanje.

Kao početnu osnovnu jedinicu prihvaćena je zvanično anotirana fraza. U tabeli sekcija čuvaju se granice tipa `PHRASE`; završni indeks je inkluzivan, pa se pri izdvajanju niza u Pythonu uvećava za jedan. Takva odluka nije tvrdnja da je svaka anotirana fraza sama po sebi call-and-response. Ona samo obezbeđuje stabilniji okvir od proizvoljne podele celog sola.

### 2.2. Od fraze do kandidata

Kandidat se sastoji od dva uzastopna segmenta: call je prvi niz nota, a response počinje na tački podele. U najjednostavnijem slučaju cela fraza se deli na dva dela. Ako fraza ima niz p₁, p₂, ..., pₙ, za svaku dozvoljenu tačku s proveravaju se nizovi

`call = [p₁, ..., pₛ]` i `response = [p₍ₛ₊₁₎, ..., pₙ]`.

Na taj način se ne pretražuju sve proizvoljne četvorke granica, već samo moguće podele jedne fraze. Za frazu dužine n postoji najviše n − 1 tačaka podele; uz ograničenje minimalne dužine broj kandidata je manji. Svaka DTW provera dve sekvence u najgorem slučaju ima kvadratnu složenost po njihovoj dužini, pa je ovakav pristup praktičan za fraze u korišćenim solažama i pregledan za ručnu proveru.

Od početka su isključeni očigledno neinformativni kandidati: segmenti sa premalo nota, prekratkim ukupnim trajanjem ili izrazito neujednačenim brojem nota. U kasnijim verzijama response je mogao da ima između polovine i dvostruke dužine call-a, a svaki deo je morao da traje najmanje jednu sekundu. Ove granice nisu definicija call-and-response odnosa; one samo uklanjaju slučajeve kao što su call od tri note i response od trideset nota, koje je algoritam povremeno pogrešno favorizovao.

### 2.3. Ručna potvrda i status podataka

Računarski skor nije korišćen kao konačna oznaka. Kandidati su izvoženi u preglednu CSV tabelu i u zasebne MIDI isečke. Nakon slušanja svaki kandidat je ručno označen kao `DA` ili `NE`. Ručna oznaka znači da je par prihvaćen za bazu, a ne da predstavlja jedinu moguću analizu konkretnog sola. Pregled je obavila autorka rada; zbog toga baza nema nezavisnu međuanotatorsku saglasnost i to ograničenje je važno pri tumačenju rezultata.

## 3. Obrada

### 3.1. Prvi koraci: pauze, klizni prozori i granice fraza

Prvi postupak je delio solo na delove kada je pauza između dve note bila veća od zadatog praga. Takva segmentacija je jednostavna i korisna za brzi pregled, ali se pokazala previše krutom. Muzička ideja može da se nastavi preko kratke pauze, a call i response mogu postojati i unutar jedne celine bez jasne tišine. Zbog toga se od nje odustalo kao od glavnog izvora granica.

Ispitani su i klizni prozori kroz ceo solo, kao i pokušaji spajanja kraja jedne i početka naredne fraze. Oni su proširili broj kandidata, ali su otežali kontrolu: pretraga je često birala lokalno slične delove koji nisu činili jednu jasnu muzičku misao. Nakon ručnog pregleda vraćeno je pravilo da se osnovna pretraga obavlja u okviru jedne anotirane fraze. Parovi preko granice fraze ostali su važni za konačnu zbirku ako su ručno potvrđeni, ali nisu korišćeni kao nekontrolisana automatska pretraga.

### 3.2. Melodijska sličnost i dinamičko vremensko poravnanje

Za poređenje call-a i response-a najpre je korišćeno dinamičko vremensko poravnanje (Dynamic Time Warping, DTW). DTW pronalazi put kroz matricu parova nota tako da dozvoli da jedna nota iz jedne sekvence bude povezana sa više nota druge sekvence. Zato je koristan kada dve fraze imaju sličan oblik, ali nisu iste dužine ili nisu potpuno ravnomerno raspoređene (Müller, 2015).

U korišćenoj implementaciji prvo se računa optimalan put P kroz DTW matricu, a zatim se rastojanje deli stvarnom dužinom tog puta:

D(x,y) = sqrt( sum((x_i - y_j)^2) za (i,j) iz P ) / |P|

gde su x i y nizovi MIDI visina, P optimalni ratni put, a |P| broj njegovih koraka. Manja vrednost znači bliže melodijsko poravnanje. Deljenje dužinom optimalnog puta bilo je važno jer prosta podela maksimalnom dužinom ne opisuje stvarno poravnanje dve sekvence.

Pored apsolutne visine ispitana je i transponovana predstava. Od svake note oduzima se prva nota svog segmenta, pa niz opisuje odstupanje od početka. Tako dve fraze koje počinju na različitim visinama, ali imaju sličan oblik, mogu dobiti manju udaljenost. Za početke fraza računata je i incipit mera: porede se prve tri note apsolutno i transponovano, a uzima se manja udaljenost. U ranim pretragama kombinovani skor bio je

S(x,y) = alpha D(x,y) + (1 - alpha) I(x,y),

gde je I incipit udaljenost, a alpha težina globalnog DTW dela. Osnovna funkcija je koristila alpha = 0,5; u kasnijoj pretrazi težina globalnog dela povećana je na 0,8, uz incipit od tri note. Pri veoma brzom tempu broj uvodnih nota je po potrebi proširivan dok ne obuhvati približno 0,75 s, jer tri vrlo kratke note nisu dovoljan muzički signal.

### 3.3. Zašto jedna mera nije dovoljna

U više iteracija kombinovane su dodatne mere: kraj fraze, Parsons-kontura, intervalski nizovi i različite varijante normalizacije. Pokazalo se da mehaničko uzimanje minimuma preko više sličnosti stvara problem: što je više nezavisnih prilika da se pronađe kratko podudaranje, veća je šansa za lažni pozitivni rezultat. Takav postupak je spuštao skor i dobrim i lošim kandidatima i zato nije zadržan kao pravilo odlučivanja.

Napravljene su i kontrolne provere normalizacije. Kod dve sekvence iste stvarne greške po poravnatim notama, stara formula dala je skor 0,447 za put od pet koraka i 0,224 za put od dvadeset koraka. RMS normalizacija, koja deli zbir kvadrata dužinom puta pre korenovanja, dala je 1 u oba slučaja. Ovaj rezultat pokazuje da se skala stare DTW mere menja sa dužinom puta i da se njene vrednosti ne mogu nekritički porediti između fraza različite dužine.

Ispitane su četiri melodijske varijante na ranom skupu od 65 ručno označenih kandidata iz 22 solaže: početna DTW mera, pitch RMS, transponovani shape RMS i shape RMS sa ograničenom dijagonalnom trakom. Površine ispod ROC krive (AUC) bile su redom 0,475, 0,567, 0,557 i 0,603. Najbolja od ove četiri varijante bila je ograničena shape RMS mera, ali ni ona nije bila dovoljna za autonomno izdvajanje, što je vidljivo iz malog broja prihvaćenih primera u proveri po neviđenom solu.

### 3.4. Ritam, kontura i zaglađivanje

Ritam je razmatran poređenjem međunotnih razmaka. Svaki niz razmaka normalizovan je sopstvenom medianom, primenjen je logaritamski odnos, a zatim je računata DTW RMS udaljenost. Ovaj postupak ne meri apsolutni tempo, već odnos trajanja unutar jedne fraze. Na istom ranom skupu ritmička mera imala je AUC 0,501, praktično bez razdvajanja oznaka `DA` i `NE`. To ne znači da ritam nema muzički značaj; znači samo da ovako jednostavno poređenje razmaka nije izdvojilo pouzdan signal u raspoloživim anotacijama.

Ispitana je i sažeta kontura zasnovana na relativnim visinama tonova: prosečno odstupanje, raspon i ukupno kretanje. Ideja je bila podstaknuta radovima o statističkoj karakterizaciji melodijske konture, ali se njihov pristup ne može direktno preneti: oni rešavaju izdvajanje vodeće melodije iz audio zapisa, dok su ovde već dostupne monofone MIDI note (Salamon, Peeters i Röbel, 2012). Na označenim kandidatima sažeta kontura, kao i kombinacija konture i ritma, nisu povećale uspeh. Median filter širine tri je donekle promenio raspodelu shape RMS skora, ali nije dao stabilan napredak pri proveri po solima.

### 3.5. Rangiranje za ručni pregled

Kasniji korak nije pokušavao da automatski proglasi kandidat dobrim, već da bolje poređa listu za slušanje. Pored DTW i incipit vrednosti razmatrani su odnos dužina, zastupljenost najčešće visine, udeo različitih tonova i približno ponavljanje intervalskog obrasca. Negativno označeni primeri nisu samo brisani: iz njih su izvedene blage kazne za obrasce koji su se često javljali među odbijenim kandidatima. Kazne su bile ograničene da ne bi potpuno zabranile muzički obrazac koji u drugom kontekstu može biti ispravan call-and-response.

Za proveru su korišćene petostruke podele po solima, tako da se kandidat i njegovi srodni delovi ne pojavljuju istovremeno u učenju i testiranju. Ovo je strožije od nasumične podele redova, ali nije nezavisna završna evaluacija: ručne oznake su već služile tokom razvoja kriterijuma. Cilj je zato bio poređenje redosleda za pregled, a ne tvrdnja o opštoj tačnosti klasifikatora.

## 4. Rezultati i diskusija

### 4.1. Dva konkretna kandidata

Sledeće dve slike su iz stvarno pregledanih kandidata. U gornjem panelu svake slike horizontalna osa je redni broj note unutar call-a, odnosno response-a, a vertikalna osa je MIDI visina. U srednjem panelu horizontalna osa predstavlja indeks note response-a, vertikalna osa indeks note call-a, boja predstavlja akumulirani DTW trošak, a bela linija optimalni put poravnanja. Donji panel prikazuje koje su note uparene na svakom koraku tog puta.

![Dobar kandidat: I Fall in Love Too Easily, melid 70, fraza 5](output/dtw_graphs/da_melid_70_phrase_5.png)

Slika 1. Potvrđen kandidat iz sola „I Fall in Love Too Easily“ (melid 70, fraza 5). Call ima 11, a response 9 nota; na slici je prikazan stvarni DTW skor 0,464 i put od 12 koraka. Izbor nije zasnovan samo na skoru: pri slušanju se čuje odgovor na prethodnu ideju, dok poravnanje pokazuje da se srodne promene visine ne moraju pojaviti u potpuno istim pozicijama.

![Loš kandidat: Blues for Blanche, melid 2, fraza 39](output/dtw_graphs/ne_melid_2_phrase_39.png)

Slika 2. Odbijen kandidat iz sola „Blues for Blanche“ (melid 2, fraza 39). Iako je njegov DTW skor 0,125, manji od skora na slici 1, kandidat je pri slušanju označen kao `NE`. U oba segmenta ima kratkih, veoma sličnih i ponovljenih tonova, pa algoritam pronalazi jeftin put poravnanja. Međutim, taj lokalni obrazac ne stvara dovoljno jasnu vezu pitanja i odgovora. Ovaj primer direktno pokazuje da niži DTW skor ne znači automatski bolji call-and-response odnos.

Razlika između slika 1 i 2 ne može se potpuno svesti na geometriju dve melodijske linije. Na slici 1 response zvuči kao zaokružena reakcija na call, dok se na slici 2 ista sličnost može objasniti kratkim mehaničkim ponavljanjem. To je razlog zbog kojeg baza zadržava ljudsku potvrdu i uz svaku stavku čuva MIDI isečak koji omogućava ponovno slušanje.

### 4.2. Preklapanje DTW skorova

Na zamrznutom razvojnom skupu bilo je 299 automatski izvučenih kandidata: 101 prihvaćen i 198 odbijen. Slika 3 prikazuje raspodele normalizovanog globalnog DTW skora za te dve grupe. Horizontalna osa razlikuje ručno prihvaćene i odbijene kandidate, dok vertikalna osa prikazuje globalni pitch-DTW skor podeljen dužinom puta. Plavi violinski dijagram i tačke pripadaju grupi `DA`, a crveni grupi `NE`.

![Raspodela DTW skorova za razvojne oznake](rad/figure/figure_2_dtw_overlap.png)

Slika 3. Raspodele globalnog normalizovanog DTW skora za 101 `DA` i 198 `NE` automatskih kandidata. Širina obojenog oblika pokazuje veću zastupljenost skora, pojedinačne tačke su kandidati, a crna crta označava centralni položaj raspodele. Grupe se snažno preklapaju. Zbog toga fiksni prag može smanjiti broj kandidata za slušanje, ali ne može pouzdano razdvojiti dobre i loše parove.

Preklapanje potvrđuje nalaz iz pojedinačnih primera. Mala udaljenost može nastati zbog stvarnog odgovora, ali i zbog ponavljanja jednog tona, kratke figure ili povoljnog warping puta. Nasuprot tome, smislen odgovor može biti duži, transponovan ili melodijski promenjen i zato imati viši skor. DTW je ostao koristan kao mera sličnosti i alat za vizuelizaciju, ali nije tretiran kao samostalna definicija odnosa.

### 4.3. Rezultati rangiranja kandidata

Naknadna evaluacija je obavljena nad zamrznutim skupom od 307 označenih redova (109 `DA`, 198 `NE`). Osam ručno unetih referenci izvan automatske pretrage izdvojeno je iz poređenja, pa su glavne dve grupe bile: 299 automatskih kandidata i uži skup od 238 kandidata povezanih sa MLU anotacijama. U tabeli 1 dat je prosečan udeo prihvaćenih kandidata među prvih 20% reda za pregled, dobijen kroz tri nasumična semena i petostruku podelu po solima.

| Metod rangiranja | Automatski kandidati (299) | MLU podskup (238) |
|---|---:|---:|
| DTW i incipit | 42,78% | 44,67% |
| Postojeća kazna za `NE` obrasce | 43,33% | 46,00% |
| Raniji višekarakteristični rang | 56,11% | 54,67% |
| Ponovo prilagođen rang | 54,44% | 56,00% |
| Učestalost intervalskog obrasca | 35,00% | 31,33% |
| Blaga kazna intervalskog obrasca | 53,89% | 56,00% |

Tabela 1. Prosečan procenat ručno prihvaćenih primera među prvih 20% kandidata za pregled. Vrednosti mere kvalitet reda za slušanje, a ne ukupnu tačnost automatskog detektora.

![Poređenje kvaliteta reda za pregled](rad/figure/figure_3_ranking.png)

Slika 4. Isto poređenje prikazano stubičasto. Horizontalna osa je procenat `DA` oznaka u prvih 20% kandidata, a vertikalna osa prikazuje metode. Za svaki metod prikazani su rezultat nad svim automatskim kandidatima i nad MLU podskupom. Višekarakteristični rang i blaga kazna obrasca mogu poboljšati prioritet liste, ali nijedan rezultat nije dovoljno visok da ukloni potrebu za slušanjem.

Ovi rezultati podržavaju umeren zaključak. Više karakteristika može pomoći da se ručni pregled bolje usmeri, ali rezultati nisu dokaz da je problem rešen automatskom klasifikacijom. Posebno je važno da intervalska učestalost kao samostalan signal daje slab rezultat, dok blaga kazna može pomoći samo kada se kombinuje sa drugim informacijama. Drugim rečima, pravilo „često ponavljanje znači loš kandidat“ bilo bi previše strogo; ponavljanje je ponekad upravo deo validnog odgovora.

### 4.4. Konačna baza JazzDialog

Konačni skup JazzDialog sadrži 114 ručno potvrđenih zapisa iz 76 solaža, 73 naslova i 42 izvođača. Zapisi potiču iz više stilskih oznaka iz pratećih podataka: 31 post-bop, 29 cool, 17 hard-bop, 14 swing, 8 bebop, 7 fusion, 6 traditional i 2 free primera. Zbir nije interpretacija muzičke zastupljenosti žanrova u celom izvoru, već opis potvrđene kolekcije.

Call delovi imaju ukupno 1136, a response delovi 1278 nota. Broj nota u call-u kreće se od 5 do 25, sa medianom 9; u response-u od 6 do 38, sa medianom 10. Zbog toga baza ne zahteva jednake dužine, ali izbegava mikrosegmente. U kolekciji je 26 anotacija u potpunosti unutar jedne zvanične fraze, dok 88 prelazi njenu granicu. To opisuje način na koji su ručno potvrđeni parovi na kraju locirani, a ne procenat call-and-response odnosa u svim jazz solažama.

![Obuhvat anotacija u odnosu na granice fraza](rad/figure/figure_1_annotation_scope.png)

Slika 5. Raspodela 114 konačnih zapisa prema odnosu sa zvanično anotiranim granicama fraza. Oznake na stubičastom grafikonu daju broj zapisa, dok horizontalna osa razlikuje parove unutar jedne fraze od parova koji prelaze granicu. Slika pokazuje zašto granica fraze jeste koristan okvir za kontrolisanu pretragu, ali nije potpuna definicija muzičke ideje.

Sedamnaest zapisa pripada osam grupa preklapajućih anotacija. Takvi zapisi nisu nezavisni muzički događaji i moraju se pažljivo koristiti u svakoj kasnijoj statističkoj analizi ili podeli na trening i test skup. Svaki red finalnog CSV fajla `jazzdialog.csv` sadrži samo potrebne podatke za ponovno lociranje i korišćenje para: identifikator od 1 do 114, izvođača, naslov, `wjd_melid`, tonalitet, podatke o stilu i tempu, granice i vremena call/response delova, broj nota, nizove MIDI visina i putanju do MIDI isečka. Prateći JSON čuva bogatiju strukturu i proveru integriteta paketa.

### 4.5. Odnos prema srodnim radovima i doprinos

Postoje radovi koji call-and-response koriste kao zadatak za generisanje muzike. Na primer, Hu i saradnici (2024) opisuju skup CRD19 i model za generisanje odgovora na zadati call. JazzDialog se razlikuje po tome što polazi od stvarnih solo improvizacija i dokumentuje postupak pronalaženja i ručne potvrde parova u transkribovanom materijalu. Zato se ne poredi direktno kvalitet generisanog odgovora, već se istražuje koliko je teško pronaći odnos koji je već nastao u improvizaciji.

Drugi doprinos rada je dokumentovanje negativnih nalaza. Umesto da se neuspešne metrike prikriju, one objašnjavaju zašto je konačni proces hibridan. Melodijska udaljenost, kontura, ritam i obrasci ponavljanja mere delove muzičkog odnosa, ali nijedna korišćena mera nije obuhvatila njegovu celinu. JazzDialog zato nije „automatski dokazani“ skup, već pregledan, proverljiv skup čiji se svaki zapis može vratiti na izvorni solo i preslušati.

## 5. Ograničenja i budući rad

Najvažnije ograničenje je subjektivnost pojma call-and-response. Jedan slušalac može uočiti odgovor tamo gde drugi čuje samo ponavljanje ili nastavak fraze. U ovoj verziji bazu je proverila jedna anotatorka, pa nema mere saglasnosti više nezavisnih slušalaca. Dodatna anotacija istih kandidata od više muzičara bila bi najvažniji sledeći korak.

Drugo ograničenje je oslanjanje na transkribovane monofone note. Time su dostupne visina, vreme i trajanje, ali ne i artikulacija, dinamika, boja tona, harmonijska pratnja i interakcija sa ansamblom. Ritam je testiran samo preko odnosa međunotnih razmaka; negativan rezultat te konkretne mere ne dokazuje da ritam nema ulogu u slušanju.

Treće, razvojni skup oznaka služio je i za oblikovanje pretrage i za retrospektivno poređenje rangiranja. Zato tabela 1 ne predstavlja nezavisnu procenu generalizacije. Za buduću evaluaciju treba unapred zamrznuti deo solaža koji se neće koristiti pri podešavanju pravila, a zatim ih anotirati bez poznavanja skora algoritma.

Praktičan naredni korak je proširenje JazzDialog baze novim parovima uz isti format i jasnu evidenciju verzija. Na većoj bazi bilo bi moguće odvojeno ispitati melodijske, ritmičke i harmonske osobine, kao i trenirati model koji uči iz više potvrđenih i odbijenih primera. Takav model mogao bi da služi kao prioritet za pregled, ali ne bi trebalo da se smatra zamenom za muzičku procenu. Baza takođe može biti polazište za kasnije radove o generisanju jazz call-and-response dijaloga, što je bila početna motivacija projekta, ali nije realizovana tema ovog rada.

## 6. Zaključak

U radu je ispitan postupak računarske analize jazz solaža sa ciljem izdvajanja call-and-response parova i izgrađena je baza JazzDialog. Analiza je pokazala da se kandidati mogu uspešno pronaći pomoću granica fraza, poređenja melodijskih nizova i dodatnih ograničenja, ali da mala DTW udaljenost nije dovoljna da potvrdi muzički odnos. Kratka ponavljanja i povoljno poravnanje mogu dati veoma nizak skor i kada pri slušanju nema jasnog odgovora.

Najvažniji rezultat nije jedna univerzalna metrika, već dokumentovan hibridni proces: računar generiše i poređa proverljive kandidate, a ljudsko slušanje potvrđuje muzičku celinu. Kao rezultat tog procesa nastala je JazzDialog baza sa 114 potvrđenih parova i MIDI isečcima, spremna za dalje anotiranje, analizu i upotrebu u budućim istraživanjima jazz improvizacije.

## Literatura

Gebru, T., Morgenstern, J., Vecchione, B., Vaughan, J. W., Wallach, H., Daumé III, H. i Crawford, K. (2021). Datasheets for Datasets. *Communications of the ACM*, 64(12), 86–92. doi: 10.1145/3458723.

Hu, Y., Wang, Z., Liu, R., Liang, Y. i Zhang, Y. (2024). Responding to the Call: Exploring Automatic Music Composition Using a Knowledge-Enhanced Model. *Proceedings of the AAAI Conference on Artificial Intelligence*, 38(1), 521–529. doi: 10.1609/aaai.v38i1.27807.

Jazzomat Research Project (2026). Database format and documentation. Hochschule für Musik Franz Liszt Weimar. Dostupno na: https://jazzomat.hfm-weimar.de/dbformat/dboverview.html [pristupljeno 29. 9. 2026].

Müller, M. (2015). *Fundamentals of Music Processing: Audio, Analysis, Algorithms, Applications*. Cham: Springer. doi: 10.1007/978-3-319-21945-5.

Pfleiderer, M., Frieler, K., Abeßer, J., Zaddach, W. G. i Burkhart, B., ur. (2017). *Inside the Jazzomat: New Perspectives for Jazz Research*. Mainz: Schott Campus.

Salamon, J., Peeters, G. i Röbel, A. (2012). Statistical Characterisation of Melodic Pitch Contours and Its Application for Melody Extraction. U: *Proceedings of the 13th International Society for Music Information Retrieval Conference*, 187–192.

Wilkinson, M. D. i dr. (2016). The FAIR Guiding Principles for scientific data management and stewardship. *Scientific Data*, 3, 160018. doi: 10.1038/sdata.2016.18.
