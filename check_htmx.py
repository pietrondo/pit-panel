import os
import re
import ast

html_dir = 'src/pit_panel/web/templates/'
routes_dir = 'src/pit_panel/web/routes/'

htmx_pattern = re.compile(r'hx-(get|post|put|patch|delete)="([^"]+)"')
html_routes = set()

for root, _, files in os.walk(html_dir):
    for f in files:
        if f.endswith('.html'):
            path = os.path.join(root, f)
            with open(path, 'r', encoding='utf-8') as file:
                content = file.read()
                matches = htmx_pattern.findall(content)
                for method, url in matches:
                    # Replace template variables with something generic if needed
                    # but let's just keep the raw url for now
                    html_routes.add((method.upper(), url, path))

backend_routes = set()
router_pattern = re.compile(r'@router\.(get|post|put|patch|delete)\("([^"]+)"')

for root, _, files in os.walk(routes_dir):
    for f in files:
        if f.endswith('.py'):
            path = os.path.join(root, f)
            with open(path, 'r', encoding='utf-8') as file:
                content = file.read()
                matches = router_pattern.findall(content)
                for method, url in matches:
                    backend_routes.add((method.upper(), url, path))

print("=== HTMX routes from templates ===")
for method, url, path in sorted(html_routes):
    print(f"{method} {url} in {path}")

print("\n=== Backend routes ===")
for method, url, path in sorted(backend_routes):
    print(f"{method} {url} in {path}")
