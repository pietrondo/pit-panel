import re

html_path = 'src/pit_panel/web/templates/apps.html'
with open(html_path, 'r') as f:
    content = f.read()

content = content.replace('hx-post="/apps/deploy"', 'hx-post="/apps/deploy-from-repo"')
content = content.replace('action="/apps/deploy"', 'action="/apps/deploy-from-repo"')

with open(html_path, 'w') as f:
    f.write(content)
print("Updated apps.html")
