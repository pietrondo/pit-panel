import re
from pathlib import Path

html_files = Path('src/pit_panel/web/templates').rglob('*.html')

for file in html_files:
    content = file.read_text()

    # Find all <button> tags
    button_matches = re.finditer(r'<button([^>]*)>(.*?)</button>', content, re.IGNORECASE | re.DOTALL)

    for match in button_matches:
        attrs = match.group(1)
        inner_html = match.group(2)

        # Check if button has aria-label
        if 'aria-label' not in attrs.lower():
            # Check if inner content has visible text
            # Remove SVG tags and other HTML tags to see if any text remains
            text_only = re.sub(r'<[^>]+>', '', inner_html).strip()

            if not text_only and '<svg' in inner_html.lower():
                print(f"File: {file}\nAttrs: {attrs}\nInner HTML: {inner_html}\n---")
