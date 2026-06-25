with open('src/pit_panel/web/routes/system.py', 'r') as f:
    content = f.read()

content = content.replace(
    'def _sudo(cmd: list[str], timeout: int = 60) -> subprocess.CompletedProcess:',
    'def _sudo(cmd: list[str], timeout: int = 60) -> subprocess.CompletedProcess[str]:'
)

content = content.replace(
    'async def system_page(request: Request, db: AsyncSession = Depends(get_db)):',
    'async def system_page(request: Request, db: AsyncSession = Depends(get_db)) -> HTMLResponse | RedirectResponse:'
)

content = content.replace(
    'async def system_upgrade(request: Request, db: AsyncSession = Depends(get_db)):',
    'async def system_upgrade(request: Request, db: AsyncSession = Depends(get_db)) -> HTMLResponse | RedirectResponse:'
)

with open('src/pit_panel/web/routes/system.py', 'w') as f:
    f.write(content)
