import re
import os

returns = []
with open('returns_analysis.txt', 'r') as f:
    for line in f:
        returns.append(line.strip())

htmx_endpoints = set()
html_routes = []
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
            break

        if mode == "html":
            parts = line.split(" in ")
            if len(parts) == 2:
                method_url = parts[0].strip()
                method, url = method_url.split(" ", 1)
                file_path = parts[1].strip()

                orig_url = url
                url = re.sub(r'\{\{\s*sd\.id\s*\}\}', '{sd_id}', url)
                url = re.sub(r'\{\{\s*rule\.index\s*\}\}', '{index}', url)
                url = url.split("?")[0]
                htmx_endpoints.add(f"{method} {url}")
                html_routes.append((method, url, file_path, orig_url))

                if url == "/apps/deploy":
                    htmx_endpoints.add(f"POST /apps/deploy-from-repo")
                    html_routes.append(("POST", "/apps/deploy-from-repo", file_path, orig_url))

# 1. Missing routes in backend
backend_routes = set()
with open('htmx_analysis.txt', 'r') as f:
    mode = None
    for line in f:
        line = line.strip()
        if line == "=== Backend routes ===":
            mode = "backend"
            continue
        if mode == "backend" and line:
            parts = line.split(" in ")
            if len(parts) == 2:
                backend_routes.add(parts[0].strip())

missing = htmx_endpoints - backend_routes
print("=== Missing routes in backend ===")
for r in missing:
    if not any(r.startswith(x) for x in ["GET /apps/", "POST /apps/"]):
        print(r)
    elif r == "POST /apps/deploy":
        print(f"{r} (renamed to deploy-from-repo?)")

print("\n=== Endpoints returning pure dictionaries ===")
for r in returns:
    m = re.match(r'([A-Z]+ \S+) \(([^)]+)\): (.*)', r)
    if m:
        route = m.group(1)
        ret_val = m.group(3)
        if route in htmx_endpoints:
            # We want to catch return {"key": "value"} or return [ ... ] or pure values
            if (ret_val.startswith("return {") or
                ret_val.startswith("return [") or
                ret_val.startswith("return True") or
                ret_val.startswith("return False") or
                ret_val.startswith("return dict(") or
                (ret_val.startswith("return ") and "HTMLResponse" not in ret_val and "Redirect" not in ret_val and "render" not in ret_val and "Response(" not in ret_val and "None" not in ret_val and "html" not in ret_val and not ret_val.startswith("return await") and not ret_val.startswith("return (sd.subdomain, pull_ok)") and not ret_val.startswith("return (sd.subdomain, False)"))):

                # Filter out variables that might be HTMLResponses
                if ret_val in ["return response", "return redirect_resp"]:
                    continue

                print(f"{route}: {ret_val}")
