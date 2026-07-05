with open("src/pit_panel/web/routes/security.py", "r") as f:
    content = f.read()

import re

# Need to replace the try...except...pass block with contextlib.suppress
content = re.sub(
    r'    try:\n        await db\.rollback\(\)\n    except Exception:\n        pass',
    r'    import contextlib\n    with contextlib.suppress(Exception):\n        await db.rollback()',
    content
)

with open("src/pit_panel/web/routes/security.py", "w") as f:
    f.write(content)
