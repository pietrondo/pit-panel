with open("src/pit_panel/web/routes/security.py", "r") as f:
    text = f.read()

text = text.replace(
    "return HTMLResponse('<span class=\"text-red-600 text-sm\">Invalid action</span>', status_code=400)",
    "return HTMLResponse(\n            '<span class=\"text-red-600 text-sm\">Invalid action</span>',\n            status_code=400,\n        )"
)
text = text.replace(
    "return HTMLResponse('<span class=\"text-red-600 text-sm\">Invalid protocol</span>', status_code=400)",
    "return HTMLResponse(\n            '<span class=\"text-red-600 text-sm\">Invalid protocol</span>',\n            status_code=400,\n        )"
)
text = text.replace(
    "return HTMLResponse('<span class=\"text-red-600 text-sm\">Invalid port</span>', status_code=400)",
    "return HTMLResponse(\n            '<span class=\"text-red-600 text-sm\">Invalid port</span>',\n            status_code=400,\n        )"
)
text = text.replace(
    "return HTMLResponse('<span class=\"text-red-600 text-sm\">Invalid source IP or network</span>', status_code=400)",
    "return HTMLResponse(\n                '<span class=\"text-red-600 text-sm\">Invalid source IP or network</span>',\n                status_code=400,\n            )"
)
text = text.replace(
    "except ValueError as e:",
    "except ValueError:"
)
text = text.replace(
    "return HTMLResponse('<span class=\"text-red-600 text-sm\">Invalid jail name</span>', status_code=400)",
    "return HTMLResponse(\n            '<span class=\"text-red-600 text-sm\">Invalid jail name</span>',\n            status_code=400,\n        )"
)

with open("src/pit_panel/web/routes/security.py", "w") as f:
    f.write(text)
