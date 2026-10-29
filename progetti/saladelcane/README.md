# Sala del cane — sito

Pagina unica (desktop + mobile), statica. Nessun framework, nessuna build.

```
index.html          la pagina
css/style.css       tutto lo stile
js/site.js          menu mobile, giorno corrente, galleria masonry, lightbox
js/photos.js        elenco delle foto (GENERATO, non editare a mano)
assets/             logo, icone, immagine Open Graph
fonts/              i due font del sito in .woff2 (serviti dal sito, non da Google)
favicon.ico         icona multi-risoluzione (16 -> 256)
manifest.webmanifest dati per l'installazione su home screen
galleria/           le foto: mettile qui
scripts/gallery.mjs rigenera js/photos.js leggendo galleria/
scripts/make-og.ps1 rigenera assets/og.jpg (serve ImageMagick)
scripts/seo-check.mjs controlla meta tag, JSON-LD, sitemap, alt
scripts/shot.mjs    screenshot di controllo (desktop + mobile)
scripts/check.mjs   controlli contrasto, overflow, menu, lightbox
```

## Aggiungere foto alla galleria

1. Metti i file in `galleria/` (jpg, jpeg, png, webp, gif, avif).
2. Dai un nome che descriva la foto: diventa la didascalia sotto l'immagine
   (`betta-rosso.jpg` → "Betta rosso"). Rinomina con trattini, non spazi.
   Se il nome da solo non basta, metti la didascalia giusta nella mappa
   `didascalie` di `scripts/gallery.mjs`.
3. Lancia:

```
npm run galleria
```

Il sito mostra le foto in griglia masonry, con il nome del file come didascalia.
Le foto hanno proporzioni diverse: la masonry le dispone nelle colonne.
Le panoramiche (rapporto almeno 1,5, tipo la foto dell'interno) prendono
tutta la larghezza della griglia invece di stare in una colonna.

Se hai ImageMagick installato, lo script genera anche una versione `.webp`
leggera in `galleria/opt/`: il browser scarica quella, il jpg resta come
riserva per i browser vecchi.

## Font

I due font del sito (Paytone One per i titoli, Hanken Grotesk per il testo)
sono in `fonts/` e vengono serviti dal sito: nessuna richiesta a Google Fonts,
quindi nessun indirizzo IP del visitatore finisce a Google.

I file sono i .woff2 presi da Google Fonts, sottoinsiemi `latin` e `latin-ext`
(94 KB in tutto). Per cambiare font: scarica il .woff2, mettilo in `fonts/` e
cambia l'`@font-face` in `css/style.css` (le famiglie sono usate dalle
variabili `--display` e `--testo`).

Se aggiungi un peso nuovo di Hanken Grotesk, ricorda che il file è variabile:
basta un solo file per tutti i pesi da 400 a 800.

## Controlli

```
npm run dev            # server locale su http://localhost:4321
node scripts/check.mjs # contrasto, overflow orizzontale, menu, lightbox
node scripts/seo-check.mjs  # meta tag, JSON-LD, sitemap, alt, link
node scripts/shot.mjs  # screenshot in shot-desktop-*.png e shot-mobile-*.png
```

## SEO

Cosa c'e' gia' fatto, cosi' non va rifatto:

- title e meta description entro i limiti di Google
- canonical assoluto su `https://www.saladelcane.com/`
- Open Graph e Twitter card con `assets/og.jpg` (1200x630) e dimensioni dichiarate
- JSON-LD `PetStore` con orari, indirizzo, coordinate, telefono, prezzi
  accettati, area servita, catalogo dei servizi e valutazione 4,8/5 (196 recensioni)
- `sitemap.xml` con `lastmod` e `robots.txt` che lo punta
- `manifest.webmanifest` e icone 192/512 per l'installazione su home screen
- `preload` dell'immagine principale

Se cambi i dati del negozio, aggiorna in tre posti: la tabella orari in
`index.html`, il blocco `openingHoursSpecification` nel JSON-LD, e il
`foundingDate` se cambia l'anno di apertura. Poi rilancia `node scripts/seo-check.mjs`.

L'immagine Open Graph si rigenera con `pwsh -File scripts/make-og.ps1`
(richiede ImageMagick).

## Dati

Aggiornati il 26 ottobre 2026 da: pagina Facebook, profilo Instagram, Google
Business (196 recensioni, 4,8/5), PagineGialle, PagineBianche.

- Sala del cane di Fioravanti C. e Bonali L. s.n.c.
- Corso Roma 139, 28883 Gravellona Toce (VB) — 0323 846239 — info@saladelcane.com
- Facebook: facebook.com/saladecane · Instagram: instagram.com/sala_del_cane
- Orari: lun 15:00–19:30 · mar–sab 08:30–12:30 e 15:00–19:30 · dom chiuso

Il dominio è `saladelcane.com`: in `index.html` il canonical, i meta tag
Open Graph e il JSON-LD puntano già lì. Se il dominio cambia, aggiornali.

## Deploy

Il sito è statico: si pubblica su Netlify (o qualsiasi hosting statico).

```
node scripts/deploy.mjs                 # deploy diretto via API Netlify
```

oppure, con la CLI:

```
bash scripts/build-dist.sh              # copia in _dist/ solo i file del sito
npx netlify-cli deploy --dir _dist --prod
```

Il token di Netlify sta in `.netlify-token` (non va su git). Il sito è già
collegato: `gregarious-souffle-81b8b5` su
https://gregarious-souffle-81b8b5.netlify.app

Ogni volta che aggiungi foto, ricorda di rilanciare `npm run galleria` prima
del deploy.

Se `saladelcane.com` viene collegato al sito Netlify, aggiorna `canonical`,
gli `og:url` e il `loc` della sitemap (sono in `index.html` e `sitemap.xml`).
