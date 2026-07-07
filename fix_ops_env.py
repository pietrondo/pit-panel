with open("src/pit_panel/web/routes/app_routes/ops.py", "r") as f:
    content = f.read()

content = content.replace("return \"<div class='text-red-500'>App not found</div>\"", "return HTMLResponse(\"<div class='text-red-500'>App not found</div>\")")

with open("src/pit_panel/web/routes/app_routes/ops.py", "w") as f:
    f.write(content)
