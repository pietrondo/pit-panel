#!/bin/bash
cat src/pit_panel/web/templates/file_manager.html | grep -C 5 "No files found" || echo "No empty state for files found"
