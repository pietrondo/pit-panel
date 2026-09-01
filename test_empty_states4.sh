#!/bin/bash
# Review logs.html missing empty state or loading for HTMX

grep -C 5 "Refresh" src/pit_panel/web/templates/logs.html
