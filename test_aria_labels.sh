#!/bin/bash
# Find buttons without aria-label inside src/pit_panel/web/templates

echo "Buttons without aria-label (or missing text):"
grep -n "<button" src/pit_panel/web/templates/*.html src/pit_panel/web/templates/**/*.html | grep -v "aria-label" | grep -v ">[A-Za-z0-9]"
