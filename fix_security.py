with open("src/pit_panel/web/routes/security.py", "r") as f:
    content = f.read()

import re

# Add top level import
content = re.sub(r"import ipaddress", "import contextlib\nimport ipaddress", content, count=1)

# Fix suppress
content = re.sub(
    r'    try:\n        await db\.rollback\(\)\n    except Exception:\n        pass',
    r'    with contextlib.suppress(Exception):\n        await db.rollback()',
    content
)

with open("src/pit_panel/web/routes/security.py", "w") as f:
    f.write(content)
