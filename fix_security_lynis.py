import re

path = 'src/pit_panel/web/routes/security.py'
with open(path, 'r') as f:
    content = f.read()

# find lynis report
# wait, hx-get="/security/lynis/report" is fetched using fetch() in frontend:
# fetch('/security/lynis/report').then(r => r.json())
# It is NOT an hx-get call! It expects JSON.
# grep -r 'lynis/report' src/pit_panel/web/templates/
#  security.html: <button @click="loading = true; fetch('/security/lynis/report').then(r => r.json()).then(data => { report = data; loading = false; })" class="btn-ghost text-xs">
# So returning a dict here is completely correct because it's fetched via JS.
