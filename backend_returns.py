import os
import re

routes_dir = 'src/pit_panel/web/routes/'
router_pattern = re.compile(r'@router\.(get|post|put|patch|delete)\("([^"]+)"')

backend_returns = []

for root, _, files in os.walk(routes_dir):
    for f in files:
        if f.endswith('.py'):
            path = os.path.join(root, f)
            with open(path, 'r', encoding='utf-8') as file:
                lines = file.readlines()
                current_route = None

                for i, line in enumerate(lines):
                    match = router_pattern.search(line)
                    if match:
                        method, url = match.groups()
                        current_route = f"{method.upper()} {url} ({f})"

                    if current_route and 'return' in line:
                        backend_returns.append(f"{current_route}: {line.strip()}")
                        # don't reset current_route here because there might be multiple returns

print("\n".join(backend_returns))
