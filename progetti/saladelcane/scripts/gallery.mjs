// Genera js/photos.js scansionando la cartella galleria/.
// Uso: node scripts/gallery.mjs  (oppure: npm run galleria)
import { readdirSync, writeFileSync, statSync, readFileSync, mkdirSync, existsSync } from 'node:fs';
import { join, dirname, extname, basename } from 'node:path';
import { fileURLToPath } from 'node:url';
import { execFileSync } from 'node:child_process';

const root = join(dirname(fileURLToPath(import.meta.url)), '..');
const dir = join(root, 'galleria');
const opt = join(dir, 'opt');
const out = join(root, 'js', 'photos.js');
const ext = ['.jpg', '.jpeg', '.png', '.webp', '.gif', '.avif'];

// ImageMagick, se presente: genera una versione webp piu' leggera.
const haMagick = (() => {
  try {
    execFileSync('magick', ['-version'], { stdio: 'ignore' });
    return true;
  } catch { return false; }
})();

if (haMagick) mkdirSync(opt, { recursive: true });

// Dimensioni reali lette dall'header del file: la masonry puo' posizionare subito.
function size(file) {
  const b = readFileSync(file);
  if (b.length > 24 && b.readUInt32BE(0) === 0x89504e47) {
    return { w: b.readUInt32BE(16), h: b.readUInt32BE(20) };
  }
  if (b[0] === 0xff && b[1] === 0xd8) {
    let i = 2;
    while (i < b.length - 9) {
      if (b[i] !== 0xff) { i++; continue; }
      const m = b[i + 1];
      if (m >= 0xc0 && m <= 0xcf && m !== 0xc4 && m !== 0xc8 && m !== 0xcc) {
        return { w: b.readUInt16BE(i + 7), h: b.readUInt16BE(i + 5) };
      }
      i += 2 + b.readUInt16BE(i + 2);
    }
  }
  return { w: 1200, h: 900 };
}

const didascalie = {
  acquari: 'Acquari del negozio'
};

const didascalia = (f) =>
  basename(f, extname(f)).replace(/[-_]+/g, ' ').replace(/\s+/g, ' ').trim()
    .replace(/^\p{L}/u, (c) => c.toUpperCase());

const voci = readdirSync(dir)
  .filter((f) => ext.includes(extname(f).toLowerCase()) && !f.startsWith('.'))
  .sort((a, b) => statSync(join(dir, a)).mtimeMs - statSync(join(dir, b)).mtimeMs)
  .map((f) => {
    const s = size(join(dir, f));
    const chiave = basename(f, extname(f)).toLowerCase();
    const v = { src: `galleria/${f}`, w: s.w, h: s.h, alt: didascalie[chiave] || didascalia(f) };

    // versione leggera: webp a max 1400px (stesso rapporto dell'originale)
    if (haMagick) {
      const nome = basename(f, extname(f)).replace(/[^\w.-]/g, '-');
      const webp = `opt/${nome}.webp`;
      try {
        execFileSync('magick', [
          join(dir, f), '-auto-orient', '-resize', '1400x1400>', '-quality', '80', join(opt, `${nome}.webp`)
        ], { stdio: 'ignore' });
        v.webp = `galleria/${webp}`;
      } catch { /* senza webp si usa l'originale */ }
    }
    return v;
  });

writeFileSync(out, '// Generato da scripts/gallery.mjs: non editare a mano.\n' +
  `window.FOTO_GALLERIA = ${JSON.stringify(voci, null, 2)};\n`);

console.log(`galleria: ${voci.length} foto -> js/photos.js` + (haMagick ? ' (+ webp ottimizzati)' : ''));
