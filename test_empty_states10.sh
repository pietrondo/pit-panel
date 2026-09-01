#!/bin/bash

# Find icon-only buttons missing aria-labels.
# Usually this means a button contains an svg but no textual content and no aria-label.

grep -n "<button" src/pit_panel/web/templates/*.html src/pit_panel/web/templates/**/*.html | grep -v "aria-label" > buttons.txt

echo "Checking for icon-only buttons (no text inside)..."

for file in $(find src/pit_panel/web/templates -name "*.html"); do
  # Simplistic check using perl or awk might be easier, but let's just inspect some common patterns.
  awk '/<button/ && !/aria-label/ {
    match($0, /<button[^>]*>(.*)<\/button>/, arr);
    if (arr[1] != "" && arr[1] !~ /[a-zA-Z0-9]/) {
        print FILENAME ":" FNR, $0
    }
  }' $file
done
