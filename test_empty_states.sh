#!/bin/bash
# Check if there are any obvious loading spinners missing in buttons

grep -r -i -E "submit|saving|loading" src/pit_panel/web/templates/*.html
