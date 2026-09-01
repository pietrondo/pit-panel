#!/bin/bash
# Checking for missing placeholder, a11y on settings/tabs

grep -B 2 -A 2 "input " src/pit_panel/web/templates/setup_2fa.html
