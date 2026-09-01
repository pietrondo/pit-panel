#!/bin/bash
# Review apps.html logic for empty states

cat src/pit_panel/web/templates/apps.html | grep -C 5 "No apps deployed yet"
