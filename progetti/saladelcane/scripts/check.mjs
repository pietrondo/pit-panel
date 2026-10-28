// Verifica contrasto, mobile e lightbox.
import { chromium } from 'playwright';
import { createServer } from 'node:http';
import { readFile } from 'node:fs/promises';
import { join, extname } from 'node:path';

const root = process.cwd();
const tipi = { '.html': 'text/html', '.css': 'text/css', '.js': 'text/javascript', '.jpg': 'image/jpeg', '.png': 'image/png', '.webp': 'image/webp', '.ico': 'image/x-icon' };
const server = createServer(async (req, res) => {
  let p = decodeURIComponent(req.url.split('?')[0]);
  if (p === '/') p = '/index.html';
  try {
    const buf = await readFile(join(root, p));
    res.writeHead(200, { 'Content-Type': tipi[extname(p)] || 'application/octet-stream' });
    res.end(buf);
  } catch { res.writeHead(404).end(''); }
});
await new Promise((r) => server.listen(4321, r));

function lum(hex) {
  const v = [1, 3, 5].map((i) => parseInt(hex.substr(i, 2), 16) / 255)
    .map((c) => (c <= 0.03928 ? c / 12.92 : Math.pow((c + 0.055) / 1.055, 2.4)));
  return 0.2126 * v[0] + 0.7152 * v[1] + 0.0722 * v[2];
}
function ratio(a, b) {
  const l1 = lum(a), l2 = lum(b);
  return ((Math.max(l1, l2) + 0.05) / (Math.min(l1, l2) + 0.05)).toFixed(2);
}

console.log('--- contrasto (dal CSS reale) ---');
const css = await readFile(join(root, 'css/style.css'), 'utf8');
const varCss = (nome) => {
  const m = css.match(new RegExp('--' + nome + ':\\s*(#[0-9a-fA-F]{6})'));
  return m ? m[1] : null;
};
const V = {};
for (const n of ['china', 'giallo', 'verde', 'rosso', 'blu', 'grigio', 'avorio']) {
  V[n] = varCss(n);
  if (!V[n]) console.log('  (variabile --' + n + ' non trovata)');
}
for (const [nome, fg, bg, min] of [
  ['testo su bianco', V.china, '#ffffff', 4.5],
  ['grigio su bianco', V.grigio, '#ffffff', 4.5],
  ['grigio su avorio', V.grigio, V.avorio, 4.5],
  ['china su giallo', V.china, V.giallo, 4.5],
  ['blu link su bianco', V.blu, '#ffffff', 4.5],
  ['verde su bianco', V.verde, '#ffffff', 3],
  ['rosso su bianco', V.rosso, '#ffffff', 3]
]) {
  const r = ratio(fg, bg);
  console.log(`${r >= min ? 'OK  ' : 'BASSO'} ${nome}: ${r} (min ${min})`);
}

const browser = await chromium.launch();

/* mobile: menu + orizzontale */
const m = await browser.newPage({ viewport: { width: 360, height: 740 } });
const errori = [];
m.on('pageerror', (e) => errori.push(String(e)));
await m.goto('http://127.0.0.1:4321/', { waitUntil: 'networkidle' });

const overflow = await m.evaluate(() =>
  document.documentElement.scrollWidth - document.documentElement.clientWidth);
console.log('\n--- mobile 360px ---');
console.log('overflow orizzontale:', overflow, 'px', overflow > 0 ? '<< PROBLEMA' : 'OK');
console.log('menu chiuso:', !(await m.isVisible('#menu a')));
await m.click('.menu-btn');
await m.waitForTimeout(300);
console.log('menu aperto:', await m.isVisible('#menu a'));
await m.screenshot({ path: 'shot-mobile-menu.png' });
await m.click('.menu-btn');
await m.waitForTimeout(200);

/* lightbox */
await m.evaluate(() => document.querySelector('#galleria-griglia').scrollIntoView());
await m.waitForTimeout(400);
await m.click('#galleria-griglia figure:first-child button');
await m.waitForTimeout(400);
const lbAperto = await m.evaluate(() => !!document.querySelector('dialog.lightbox[open]'));
const lbSrc = await m.evaluate(() => document.querySelector('dialog.lightbox img')?.src);
console.log('lightbox aperto:', lbAperto, '| img:', lbSrc?.split('/').pop());
await m.screenshot({ path: 'shot-mobile-lightbox.png' });
await m.keyboard.press('Escape');
await m.waitForTimeout(200);
console.log('lightbox chiuso:', await m.evaluate(() => !document.querySelector('dialog.lightbox[open]')));

/* tap target */
const piccoli = await m.$$eval('a, button', (els) =>
  els.map((e) => {
    const r = e.getBoundingClientRect();
    return { t: (e.textContent || '').trim().slice(0, 28), h: Math.round(r.height), w: Math.round(r.width) };
  }).filter((x) => x.h > 0 && x.h < 44));
console.log('tap target < 44px:', piccoli.length ? JSON.stringify(piccoli) : 'nessuno');
console.log('errori:', errori.length ? errori : 'nessuno');

await browser.close();
server.close();
