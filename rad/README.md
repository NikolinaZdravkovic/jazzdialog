# Rad za pregled

Najlakše je da otvoriš **jazzdialog_rad.docx** i upisuješ komentare ili menjaš tekst. **jazzdialog_rad.pdf** je provereni prikaz iste verzije na deset strana. To je rukopis za tvoju i Majinu proveru, ne rad koji je već recenziran ili prihvaćen na konferenciji.

Rad obuhvata cilj, pripremu podataka, postupak anotiranja, DTW i druga ispitivanja, rangiranje, rezultate, ograničenja i dalju upotrebu. Ima pet grafikona, jednu tabelu poređenja i sedam bibliografskih stavki; nema engleski sažetak.

## Šta je još potrebno pre slanja

- Dopuniti školu, razred, mesto i godinu rođenja autorke, kao i titulu i ustanovu mentorke, ako se rad predaje Petničkim sveskama. Ti podaci nisu nagađani.
- Proveriti konkretan poziv i šablon konferencije u Nišu. Dostavljene Petničke smernice nisu dokaz da je tekst već usklađen sa zahtevima neke IEEE konferencije. Za sada je pripremljen pregledan rukopis na srpskom, po njihovoj sadržinskoj strukturi.
- Razrešiti sedam ručnih referenci čiji snimci nisu u lokalnom WJD-u i jedan nepotpun Excel zapis. Nisu uračunati u 114 parova.
- Pregledati zapisane razlike pri mapiranju ručnih referenci i konačne granice; tabela povezivanja je u `../dataset/DATASET_CARD.md`.

Smernice korišćene za organizaciju: https://konferencija.petnica.rs/korisne-smernice-za-pripremu-radova/ . Strukturni uzori pregledani su u https://esveske.github.io/prog-rac.html , naročito Milanovićev rad *Ekstrakcija melodije iz polifonih zvučnih izvora* (2018). To su uzori za izlaganje, ne eksperimenti koje smo mi sproveli. Njihov tekst, podaci i rezultati nisu preuzeti kao naši.

## Datoteke i ponovljivost

- `../DRAFT_RADA.md` je izvorni tekst iz kog je napravljen Word. Ako menjaš Word ručno, ne pokreći ponovnu izgradnju preko svojih izmena pre nego što se one prenesu i u izvorni tekst.
- `figure/` sadrži tri sažeta grafikona kao PNG od 320 dpi i SVG vektore, kao i dve slike formula. Uz njih su u radu iskorišćena dva postojeća DTW prikaza konkretnih kandidata iz `../output/dtw_graphs/`. Natpisi i opisi u radu su na srpskom latinicom.
- `statistika.json` čuva brojeve za grafikone, rezultate po podelama i kontrolne sažetke izvora.
- `evaluacija.json.gz` je komprimovan kompletan izveštaj ranijeg eksperimenta. Čita se funkcijom `gzip.open` i ne služi ručnom pregledu baze.

Konačna baza ima 114 DA. Evaluacija koristi raniji snimak od 307 oznaka, sa 299 algoritamskih kandidata posle izostavljanja osam tadašnjih ručnih referenci. Pet naknadno unetih ručnih pozitivnih referenci nije uključeno u eksperimentalne rezultate. Izvorni eksperimentalni CSV dostupan je u Git commitu `d6c4003`; njegov SHA-256 je `6d3c073282ccb9cc41b279bf24a21c8d02b54d60a3dede8c8ae2ca217d320fde`.

Grafikoni se obnavljaju komandom `python scripts/make_paper_figures.py` iz korena projekta (NumPy, Matplotlib, DTAIDistance). Grafik rangiranja uvek čita zamrznuti izveštaj uz rad. Pre promene oznaka potrebno je namerno ažurirati i opis uzorka u radu.

Word se obnavlja komandom `python scripts/build_paper.py` (python-docx). Za ovu izradu korišćen je raspoloživi Codex Python runtime. PDF je izvezen iz Worda i svih deset strana provereno je posle rasterizacije. Za izmene koje radiš u Wordu izaberi Save As / PDF da bi PDF ponovo odgovarao izmenjenom dokumentu.
