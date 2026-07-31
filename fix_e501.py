import re

with open("src/pit_panel/web/routes/debug_api.py", "r") as f:
    content = f.read()

content = content.replace(
    'raise HTTPException(status_code=500, detail="Permission denied and no sudo_password configured")',
    'raise HTTPException(\n                status_code=500,\n                detail="Permission denied and no sudo_password configured",\n            ) from None'
)
content = content.replace(
    'return JSONResponse({"status": "pulled", "output": pull_out, "restart": "skipped (no sudo_password)"})',
    'return JSONResponse(\n            {\n                "status": "pulled",\n                "output": pull_out,\n                "restart": "skipped (no sudo_password)",\n            }\n        )'
)

with open("src/pit_panel/web/routes/debug_api.py", "w") as f:
    f.write(content)
