import re
import os

returns = []
with open('returns_analysis.txt', 'r') as f:
    for line in f:
        returns.append(line.strip())

# We want to identify endpoints that are called by HTMX
htmx_endpoints = set()
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
                url = re.sub(r'\{\{\s*sd\.id\s*\}\}', '{sd_id}', url)
                url = re.sub(r'\{\{\s*rule\.index\s*\}\}', '{index}', url)
                url = url.split("?")[0]
                htmx_endpoints.add(f"{method} {url}")

                # specific case
                if url == "/apps/deploy":
                    htmx_endpoints.add(f"POST /apps/deploy-from-repo")

# Now let's see what those endpoints return
for r in returns:
    # format: METHOD /url (file.py): return ...
    m = re.match(r'([A-Z]+ \S+) \(([^)]+)\): (.*)', r)
    if m:
        route = m.group(1)
        ret_val = m.group(3)
        if route in htmx_endpoints:
            # Check if returning JSON, pure python dict/tuple/bool/int, or rendering full page
            if "{" in ret_val and "f\"" not in ret_val and "f'" not in ret_val and "HTMLResponse" not in ret_val:
               pass

            # Check if it renders a full page template
            if "render(" in ret_val:
                # Extract the template name
                tpl_match = re.search(r'render\(\s*["\']([^"\']+)["\']', ret_val)
                if tpl_match:
                    tpl = tpl_match.group(1)
                    # Let's see if the template extends base.html
                    tpl_path = os.path.join('src/pit_panel/web/templates', tpl)
                    if os.path.exists(tpl_path):
                        with open(tpl_path, 'r') as tf:
                            if '{% extends' in tf.read():
                                print(f"WARNING: HTMX endpoint {route} renders full page template '{tpl}':\n  {ret_val}")
                    else:
                        print(f"Unknown template: {tpl} in {route}")

            # Check for non-HTMLResponse / render returns
            if not any(x in ret_val for x in ["HTMLResponse", "render(", "RedirectResponse", "Response", "None", "name", "redirect_resp"]):
                if "return (" in ret_val or "return {" in ret_val or "return [" in ret_val:
                    pass
                    # print(f"CHECK: {route} returns non-HTML: {ret_val}")
