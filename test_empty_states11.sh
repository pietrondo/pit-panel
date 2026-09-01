#!/bin/bash
# Review security.html buttons and forms

grep -A 2 -B 2 "<button" src/pit_panel/web/templates/security.html
