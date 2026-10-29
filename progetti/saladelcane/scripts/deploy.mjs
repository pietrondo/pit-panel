// Deploy su Netlify via API REST: digest sha1 + upload dei file richiesti.
// Uso: node scripts/deploy.mjs
import { readFile, readdir, stat } from 'node:fs/promises';
import { join, dirname, relative, extname } from 'node:path';
import { fileURLToPath } from 'node:url';
import { createHash } from 'node:crypto';

const root = join(dirname(fileURLToPath(import.meta.url)), '..');
const token = (await readFile(join(root, '.netlify-token'), 'utf8')).trim();
const API = 'https://api.netlify.com/api/v1';

const TIPI = {
  '.html': 'text/html', '.css': 'text/css', '.js': 'text/javascript',
  '.json': 'application/json', '.webmanifest': 'application/manifest+json',
  '.jpg': 'image/jpeg', '.jpeg': 'image/jpeg', '.png': 'image/png',
  '.webp': 'image/webp', '.gif': 'image/gif', '.ico': 'image/x-icon',
  '.svg': 'image/svg+xml', '.txt': 'text/plain', '.xml': 'application/xml'
};
const ESCLUDI = new Set(['.git', 'node_modules', '.netlify-token', '.engram',
  'scripts', 'package.json', 'package-lock.json', '.gitignore', 'shot-*.png',
  'live-*.png', '_dist', 'README.md', '.netlifyignore', 'LAVORO-FATTO.txt']);

async function api(method, path, body, headers = {}) {
  const res = await fetch(API + path, {
    method,
    headers: { Authorization: `Bearer ${token}`, 'Content-Type': 'application/json', ...headers },
    body: body ? JSON.stringify(body) : undefined
  });
  const txt = await res.text();
  let json = null;
  try { json = JSON.parse(txt); } catch {}
  if (!res.ok) throw new Error(`${method} ${path} -> ${res.status} ${txt.slice(0, 500)}`);
  return json;
}

// 1. il sito
const siti = await api('GET', '/sites?per_page=100');
const mio = siti.find((s) => s.name === 'gregarious-souffle-81b8b5');
if (!mio) {
  console.log('Sito non trovato.');
  siti.forEach((s) => console.log('  ', s.id, s.name, s.url));
  process.exit(1);
}
console.log('sito:', mio.id, mio.name, '->', mio.url);

// 2. i file
async function raccogli(dir, fuori = []) {
  for (const v of await readdir(dir, { withFileTypes: true })) {
    if (ESCLUDI.has(v.name) || v.name.startsWith('shot-') || v.name.endsWith('.zip')) continue;
    const p = join(dir, v.name);
    if (v.isDirectory()) await raccogli(p, fuori);
    else fuori.push(p);
  }
  return fuori;
}
const file = [];
for (const p of await raccogli(root)) {
  const rel = relative(root, p).split('\\').join('/');
  const buf = await readFile(p);
  file.push({
    path: rel,
    contentType: TIPI[extname(p).toLowerCase()] || 'application/octet-stream',
    sha1: createHash('sha1').update(buf).digest('hex'),
    size: (await stat(p)).size,
    _buf: buf
  });
}
console.log('file:', file.length);

// 3. crea il deploy
// Netlify vuole i file come mappa "path -> sha1", non come elenco:
// con un elenco la diff dei file fallisce e il deploy resta in 'preparing'.
const corpo = {
  files: Object.fromEntries(file.map((f) => [f.path, f.sha1])),
  async: false,
  draft: false,
  title: 'Sala del cane'
};
const deploy = await api('POST', `/sites/${mio.id}/deploys`, corpo);
console.log('deploy:', deploy.id, deploy.state);

// 4. la lista dei file da caricare la dà il deploy aggiornato
// (gli elementi di 'required' sono gli sha1 dei file, non i path)
const aggiornato = (await api('PUT', `/sites/${mio.id}/deploys/${deploy.id}`, corpo)) || deploy;
const daCaricare = new Set((aggiornato.required || [])
  .map((r) => (typeof r === 'string' ? r : r.sha1 || r.digest)));
console.log('da caricare:', daCaricare.size);

// 5. carica i file richiesti
for (const f of file) {
  if (!daCaricare.has(f.sha1)) continue;
  const res = await fetch(`${API}/deploys/${deploy.id}/files/${encodeURI(f.path)}`, {
    method: 'PUT',
    headers: { Authorization: `Bearer ${token}`, 'Content-Type': f.contentType },
    body: f._buf
  });
  if (!res.ok) console.log('  ERRORE', f.path, res.status, (await res.text()).slice(0, 200));
}
console.log('file caricati');

// 6. aspetta la fine
let stato = deploy;
for (let i = 0; i < 90; i++) {
  await new Promise((r) => setTimeout(r, 2500));
  stato = await api('GET', `/deploys/${deploy.id}`);
  if (!['enqueued', 'building', 'uploading', 'preparing', 'new'].includes(stato.state)) break;
}
console.log('stato:', stato.state);
if (stato.state === 'error') {
  console.log('errore:', JSON.stringify(stato.error_message || stato.summary));
  process.exit(1);
}
console.log('pubblico:', stato.deploy_ssl_url || stato.deploy_url);
console.log('principale:', stato.ssl_url || stato.url);
