#!/bin/bash
# Find loading spinners in HTMX attributes or general lack of loading states

grep -A 2 -B 2 "hx-post" src/pit_panel/web/templates/app_detail.html
