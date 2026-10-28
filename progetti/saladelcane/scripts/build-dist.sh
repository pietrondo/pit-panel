#!/bin/sh
# Prepara la cartella da pubblicare: copia solo il sito in _dist/
# ed elimina tutto quello che non deve finire online.
set -e

ROOT="$(cd "$(dirname "$0")/.." && pwd)"
DIST="$ROOT/_dist"

rm -rf "$DIST"
mkdir -p "$DIST"

# il sito: tutto tranne development
cd "$ROOT"
for f in index.html favicon.ico robots.txt sitemap.xml manifest.webmanifest .netlifyignore; do
  [ -f "$f" ] && cp "$f" "$DIST/"
done
for d in assets css js galleria fonts; do
  [ -d "$d" ] && cp -r "$d" "$DIST/"
done

echo "pubblicati:"
find "$DIST" -type f | wc -l
