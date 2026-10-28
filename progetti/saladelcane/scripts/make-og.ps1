# Crea l'immagine Open Graph 1200x630.
$ErrorActionPreference = 'Stop'
$root = Split-Path -Parent $PSScriptRoot
Set-Location $root

# 1. logo a sinistra su fondo giallo
magick assets\logo.jpg -resize 480x -background "#FEF200" -gravity west -extent 1200x630 assets\og-tmp.png

# 2. testo a destra
$font = "C:/Windows/Fonts/arialbd.ttf"

magick assets\og-tmp.png `
  -font $font -pointsize 74 -fill "#1D1B1E" -annotate +625+150 "Sala del cane" `
  -pointsize 36 -fill "#1D1B1E" -annotate +627+220 "Toelettatura e acquari" `
  -pointsize 27 -fill "#3a3630" -annotate +627+285 "Gravellona Toce, dal 1979" `
  -pointsize 27 -fill "#3a3630" -annotate +627+330 "Corso Roma 139" `
  -pointsize 27 -fill "#3a3630" -annotate +627+375 "Tel. 0323 846239" `
  assets\og.jpg

# 3. versione webp piu' leggera
magick assets\og.jpg -quality 85 assets\og.webp

Remove-Item assets\og-tmp.png -ErrorAction SilentlyContinue
magick identify assets\og.jpg assets\og.webp
