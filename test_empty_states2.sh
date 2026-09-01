#!/bin/bash
# Check apps.html and other files for potential UX issues

grep -A 5 -B 5 "btn" src/pit_panel/web/templates/apps.html
