import re

routes = []
with open('returns_analysis.txt', 'r') as f:
    for line in f:
        routes.append(line.strip())

# Check for routes that return full templates when they shouldn't, or return dictionaries
# Usually HTMX endpoints return HTMLResponse, render(fragment), or redirect
issues = []

for route in routes:
    if "return {" in route or "return dict(" in route:
        issues.append(f"JSON/Dict return: {route}")
    if "base.html" in route:
        issues.append(f"Full page render: {route}")

    # We should look closely at how render is used. If it renders a page that extends base.html, it might be wrong.
    # It's hard to tell without looking at the templates.

print("Potential issues found:")
for issue in issues:
    print(issue)

if not issues:
    print("No obvious JSON or base.html returns found in the extracted return statements.")
