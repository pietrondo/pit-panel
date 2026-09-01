#!/bin/bash
# Review security.html for missing a11y labels

grep -n "<button" src/pit_panel/web/templates/security.html | grep -v "aria-label"
