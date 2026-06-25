import re

with open("src/pit_panel/web/routes/auth_routes.py", "r") as f:
    content = f.read()

# Replace HTMLResponse | RedirectResponse with just Response
content = content.replace("HTMLResponse | RedirectResponse", "Response")

if "from fastapi.responses import HTMLResponse, RedirectResponse" in content:
    if "Response" not in content.split("from fastapi.responses import")[1].split("\n")[0]:
        content = content.replace("from fastapi.responses import HTMLResponse, RedirectResponse", "from fastapi.responses import HTMLResponse, RedirectResponse, Response")

with open("src/pit_panel/web/routes/auth_routes.py", "w") as f:
    f.write(content)
