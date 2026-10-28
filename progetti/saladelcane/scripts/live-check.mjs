// Verifica del sito pubblicato su Netlify.
import { chromium } from 'playwright';

const URL = process.argv[2] || 'https://gregarious-souffle-81b8b5.netlify.app';
const browser = await chromium.launch();
const errori = [];

for (const [nome, w, h] of [['desktop', 1440, 1000], ['mobile', 390, 844]]) {
  const page = await browser.newPage({ viewport: { width: w, height: h } });
  page.on('console', (m) => { if (m.type() === 'error') errori.push(m.text()); });
  page.on('pageerror', (e) => errori.push(String(e)));
  page.on('response', (r) => {
    if (r.status() >= 400) errori.push(`${r.status()} ${r.url()}`);
  });

  await page.goto(URL, { waitUntil: 'networkidle', timeout: 45000 });
  await page.evaluate(async () => {
    for (let y = 0; y < document.body.scrollHeight; y += 400) {
      window.scrollTo(0, y);
      await new Promise((r) => setTimeout(r, 100));
    }
    window.scrollTo(0, 0);
  });
  await page.waitForTimeout(1500);
  await page.screenshot({ path: `live-${nome}.png`, fullPage: true });

  const dati = await page.evaluate(() => ({
    titolo: document.title,
    desc: document.querySelector('meta[name="description"]')?.content?.length,
    h1: document.querySelectorAll('h1').length,
    ld: !!document.querySelector('script[type="application/ld+json"]'),
    figure: document.querySelectorAll('#galleria-griglia figure').length,
    imgCariche: Array.from(document.querySelectorAll('#galleria-griglia img'))
      .filter((i) => i.complete && i.naturalWidth > 0).length,
    barraTel: getComputedStyle(document.querySelector('.barra-tel')).display,
    overflow: document.documentElement.scrollWidth - document.documentElement.clientWidth,
    oggi: document.querySelector('.orari__riga--oggi .orari__giorno')?.textContent
  }));
  console.log(nome, JSON.stringify(dati));
  await page.close();
}

console.log(errori.length ? '\nPROBLEMI:\n' + [...new Set(errori)].join('\n') : '\nNessun errore.');
await browser.close();
