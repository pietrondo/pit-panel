#!/bin/bash
cat src/pit_panel/web/templates/file_manager.html | grep -C 5 "item.is_dir"
