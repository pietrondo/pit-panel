#!/bin/bash
# Review apps.html for "Deploying..." loading states in form submit

cat src/pit_panel/web/templates/apps.html | grep -C 10 "isSubmitting"
