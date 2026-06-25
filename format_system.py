with open('src/pit_panel/web/routes/system.py', 'r') as f:
    content = f.read()

content = content.replace(
    'async def system_page(request: Request, db: AsyncSession = Depends(get_db)) -> HTMLResponse | RedirectResponse:',
    'async def system_page(\n    request: Request, db: AsyncSession = Depends(get_db)\n) -> HTMLResponse | RedirectResponse:'
)

content = content.replace(
    'async def system_upgrade(request: Request, db: AsyncSession = Depends(get_db)) -> HTMLResponse | RedirectResponse:',
    'async def system_upgrade(\n    request: Request, db: AsyncSession = Depends(get_db)\n) -> HTMLResponse | RedirectResponse:'
)

with open('src/pit_panel/web/routes/system.py', 'w') as f:
    f.write(content)
