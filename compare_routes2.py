import re

html_routes = set()
backend_routes = set()

with open('htmx_analysis.txt', 'r') as f:
    mode = None
    for line in f:
        line = line.strip()
        if not line:
            continue
        if line == "=== HTMX routes from templates ===":
            mode = "html"
            continue
        elif line == "=== Backend routes ===":
            mode = "backend"
            continue

        if mode == "html":
            # format: METHOD URL in FILE
            parts = line.split(" in ")
            if len(parts) == 2:
                method_url = parts[0].strip()
                method, url = method_url.split(" ", 1)
                # print(f"Raw HTML: {method} {url}")
                url = re.sub(r'\{\{\s*sd\.id\s*\}\}', '{sd_id}', url)
                url = re.sub(r'\{\{\s*rule\.index\s*\}\}', '{index}', url)
                url = url.split("?")[0]
                html_routes.add(f"{method} {url}")
        elif mode == "backend":
            parts = line.split(" in ")
            if len(parts) == 2:
                method_url = parts[0].strip()
                backend_routes.add(method_url)

print("Routes in HTML but missing or different in Backend:")
missing_in_backend = html_routes - backend_routes
for r in sorted(missing_in_backend):
    print(r)
