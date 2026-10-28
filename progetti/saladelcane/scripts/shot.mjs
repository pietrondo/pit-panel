// Screenshot di controllo: desktop + mobile.
import { chromium } from 'playwright';
import { createServer } from 'node:http';
import { readFile } from 'node:fs/promises';
import { join, extname } from 'node:path';

const root = process.cwd();
const tipi = {
  '.html': 'text/html', '.css': 'text/css', '.js': 'text/javascript',
  '.jpg': 'image/jpeg', '.png': 'image/png', '.webp': 'image/webp', '.ico': 'image/x-icon'
};

const server = createServer(async (req, res) => {
  let p = decodeURIComponent(req.url.split('?')[0]);
  if (p === '/') p = '/index.html';
  try {
    const buf = await readFile(join(root, p));
    res.writeHead(200, { 'Content-Type': tipi[extname(p)] || 'application/octet-stream' });
    res.end(buf);
  } catch {
    res.writeHead(404).end('nope');
  }
});
await new Promise((r) => server.listen(4321, r));

const browser = await chromium.launch();

for (const [nome, w, h] of [['desktop', 1440, 1000], ['mobile', 390, 844]]) {
  const page = await browser.newPage({ viewport: { width: w, height: h }, deviceScaleFactor: 1 });
  const errori = [];
  page.on('console', (m) => { if (m.type() === 'error') errori.push(m.text()); });
  page.on('pageerror', (e) => errori.push(String(e)));
  await page.goto('http://127.0.0.1:4321/', { waitUntil: 'networkidle' });
  // scorri tutta la pagina: senza questo le img lazy restano vuote
  await page.evaluate(async () => {
    for (let y = 0; y < document.body.scrollHeight; y += 400) {
      window.scrollTo(0, y);
      await new Promise((r) => setTimeout(r, 120));
    }
    window.scrollTo(0, 0);
  });
  // attendi che tutte le immagini siano effettivamente decodificate
  await page.evaluate(() => Promise.all(
    Array.from(document.images)
      .filter((i) => !i.complete)
      .map((i) => new Promise((r) => { i.onload = i.onerror = r; }))
  ));
  await page.waitForTimeout(1200);
  await page.screenshot({ path: `shot-${nome}-topo.png` });
  await page.screenshot({ path: `shot-${nome}-full.png`, fullPage: true });
  const stato = await page.textContent('.orari__riga--oggi .orari__giorno');
  const foto = await page.$$eval('#galleria-griglia figure', (n) => n.length);
  const rotte = await page.$$eval('#galleria-griglia img', (n) =>
    n.map((x) => (x.complete && x.naturalWidth > 0 ? 'ok' : 'VUOTO')));
  const alt = await page.$$eval('#galleria-griglia figure', (n) => n.map((x) => x.style.left));
  console.log(nome, '| stato:', stato, '| figure:', foto, '| img:', rotte.join(','),
    '| errori:', errori.length ? errori : 'nessuno');
  console.log('  left:', alt.join(' '));
  await page.close();
}

await browser.close();
server.close();
