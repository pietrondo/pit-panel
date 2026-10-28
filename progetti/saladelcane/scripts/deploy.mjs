// Deploy su Netlify via API REST: digest + upload dei file richiesti.
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
  '.netlifyignore', 'LAVORO-FATTO.txt']);

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
    nome: rel,
    path: rel,
    contentType: TIPI[extname(p).toLowerCase()] || 'application/octet-stream',
    digest: createHash('sha256').update(buf).digest('hex'),
    size: (await stat(p)).size,
    _buf: buf
  });
}
console.log('file:', file.length);

// 3. crea il deploy
const deploy = await api('POST', `/sites/${mio.id}/deploys`, {
  files: file.map(({ _buf, ...f }) => f),
  async: true,
  branch: mio.deploy_settings?.branch || 'main',
  draft: false,
  title: 'Sala del cane'
});
console.log('deploy:', deploy.id, deploy.state);
console.log('da caricare:', (deploy.required || []).length);

// 4. carica i file richiesti
const richiesti = deploy.required || [];
for (const req of richiesti) {
  if (req.type && req.type !== 'file') continue;
  const mioFile = file.find((f) => f.nome === req.path || f.path === req.path);
  if (!mioFile) { console.log('  (nessun file per', req.path, ')'); continue; }
  const url = `${API}/deploys/${deploy.id}/files/${encodeURI(req.path)}`;
  const res = await fetch(url, {
    method: 'PUT',
    headers: {
      Authorization: `Bearer ${token}`,
      'Content-Type': req.contentType || mioFile.contentType
    },
    body: mioFile._buf
  });
  const txt = await res.text();
  if (!res.ok) {
    console.log('  ERRORE', req.path, res.status, txt.slice(0, 200));
    // la firma del file richiede il digest nell'header
    const res2 = await fetch(url + '?d=' + encodeURI(req.digest || ''), {
      method: 'PUT',
      headers: { Authorization: `Bearer ${token}`, 'Content-Type': req.contentType || mioFile.contentType },
      body: mioFile._buf
    });
    console.log('   retry ->', res2.status);
  }
}
console.log('file caricati');

// 5. aspetta la fine
let stato = deploy;
for (let i = 0; i < 90; i++) {
  await new Promise((r) => setTimeout(r, 2500));
  stato = await api('GET', `/deploys/${deploy.id}`);
  if (!['enqueued', 'building', 'uploading', 'preparing'].includes(stato.state)) break;
}
console.log('stato:', stato.state);
if (stato.state === 'error') {
  console.log('errore:', JSON.stringify(stato.error_message || stato.summary));
  process.exit(1);
}
console.log('pubblico:', stato.deploy_ssl_url || stato.deploy_url);
console.log('principale:', stato.ssl_url || stato.url);
