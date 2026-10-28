// Audit SEO: meta tag, JSON-LD, href, immagini, accessibilita' dei link.
import { readFile } from 'node:fs/promises';
import { join, dirname } from 'node:path';
import { fileURLToPath } from 'node:url';

const root = join(dirname(fileURLToPath(import.meta.url)), '..');
const html = await readFile(join(root, 'index.html'), 'utf8');

const ok = [];
const ko = [];
const meta = (nome) => {
  const m = html.match(new RegExp(`<meta[^>]+(?:name|property)="${nome}"[^>]*content="([^"]*)"`, 'i'))
    || html.match(new RegExp(`<meta[^>]+content="([^"]*)"[^>]*(?:name|property)="${nome}"`, 'i'));
  return m ? m[1] : null;
};
const check = (cond, testo, dettaglio = '') => (cond ? ok : ko).push(testo + (dettaglio ? ' -> ' + dettaglio : ''));

// --- meta base ---
const titolo = (html.match(/<title>([^<]*)<\/title>/i) || [])[1];
check(titolo && titolo.length >= 30 && titolo.length <= 60, 'title 30-60 caratteri', `${(titolo || '').length}: ${titolo}`);
const desc = meta('description');
check(desc && desc.length >= 70 && desc.length <= 160, 'meta description 70-160', `${(desc || '').length} caratteri`);
check(!!meta('robots'), 'meta robots presente');
check(!!meta('author'), 'meta author presente');
check(!!meta('theme-color'), 'meta theme-color presente');
check(/^https:\/\/www\.saladelcane\.com\/$/.test((html.match(/rel="canonical" href="([^"]+)"/) || [])[1] || ''), 'canonical assoluto e coerente');

// --- open graph ---
for (const p of ['og:type', 'og:locale', 'og:site_name', 'og:url', 'og:title', 'og:description', 'og:image', 'og:image:width', 'og:image:height', 'og:image:alt']) {
  check(!!meta(p), `og:${p} presente`);
}
check(meta('og:image')?.startsWith('https://'), 'og:image URL assoluta', meta('og:image'));
check(meta('og:locale') === 'it_IT', 'og:locale it_IT', meta('og:locale'));

// --- twitter ---
for (const p of ['twitter:card', 'twitter:title', 'twitter:description', 'twitter:image']) {
  check(!!meta(p), `${p} presente`);
}
check(meta('twitter:card') === 'summary_large_image', 'twitter:card summary_large_image', meta('twitter:card'));

// --- icone ---
check(/rel="icon"[^>]*favicon\.ico|rel="icon"[^>]*icon-192/.test(html), 'favicon dichiarato');
check(/rel="apple-touch-icon"/.test(html), 'apple-touch-icon presente');
check(/rel="manifest"/.test(html), 'manifest dichiarato');
const icone = await readFile(join(root, 'manifest.webmanifest'), 'utf8');
check(/192x192/.test(icone) && /512x512/.test(icone), 'manifest con icone 192 e 512');

// --- JSON-LD ---
const ld = html.match(/<script type="application\/ld\+json">([\s\S]*?)<\/script>/);
let json = null;
try { json = JSON.parse(ld[1]); } catch (e) { ko.push('JSON-LD non valido: ' + e.message); }
if (json) {
  check(json['@type'] === 'PetStore', 'JSON-LD @type PetStore', json['@type']);
  for (const c of ['name', 'telephone', 'address', 'geo', 'openingHoursSpecification', 'sameAs', 'aggregateRating', 'url', 'image', 'priceRange', 'paymentAccepted', 'areaServed', 'hasOfferCatalog', 'foundingDate']) {
    check(json[c] !== undefined, `JSON-LD ${c} presente`);
  }
  check(json.openingHoursSpecification?.length === 11, 'JSON-LD 11 fasce orarie (lun pomeriggio + mar-sab)', String(json.openingHoursSpecification?.length));
  const agg = json.aggregateRating;
  check(agg && agg.ratingValue <= agg.bestRating, 'aggregateRating coerente', `${agg?.ratingValue}/${agg?.bestRating}`);
  check(json.geo.latitude > 45 && json.geo.latitude < 46, 'geo latitudine plausibile (Gravellona Toce)', String(json.geo.latitude));
}

// --- struttura ---
const h1 = (html.match(/<h1[^>]*>([\s\S]*?)<\/h1>/gi) || []).length;
check(h1 === 1, 'un solo h1', String(h1));
const h2 = (html.match(/<h2[^>]*>/gi) || []).length;
check(h2 >= 4, 'h2 presenti per le sezioni', String(h2));
check(/<html lang="it">/.test(html), 'lang="it"');
check(/<meta name="viewport"[^>]*width=device-width/.test(html), 'viewport responsive');
check(!/<img(?![^>]*alt=)[^>]*>/.test(html), 'tutte le immagini hanno alt');
check(!/<a (?![^>]*href=)[^>]*>/.test(html), 'tutti i link hanno href');
check(/rel="noopener"/.test(html), 'link esterni con rel=noopener');

// --- sitemap / robots ---
const sm = await readFile(join(root, 'sitemap.xml'), 'utf8');
check(/<loc>https:\/\/www\.saladelcane\.com\/<\/loc>/.test(sm), 'sitemap con URL canonico');
check(/<lastmod>/.test(sm), 'sitemap con lastmod');
const rb = await readFile(join(root, 'robots.txt'), 'utf8');
check(/Sitemap: https:\/\/www\.saladelcane\.com\/sitemap\.xml/.test(rb), 'robots.txt con sitemap');
check(/User-agent: \*/.test(rb), 'robots.txt con User-agent');

console.log('=== OK (' + ok.length + ') ===');
ok.forEach(x => console.log('  ok  ' + x));
if (ko.length) {
  console.log('\n=== DA SISTEMARE (' + ko.length + ') ===');
  ko.forEach(x => console.log('  !!  ' + x));
} else {
  console.log('\nNessun problema.');
}
process.exit(ko.length ? 1 : 0);
